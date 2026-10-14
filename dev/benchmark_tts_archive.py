"""Read real existing Gemini/local logs; compare archives in a disposable DB schema.

Does not change source logs or migrate audio. --write-audio exports listening pairs.
"""
import argparse
import asyncio
import base64
import json
import os
import re
from pathlib import Path
import sys
import subprocess
import time
from unittest.mock import AsyncMock, patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import asyncpg
from core.config import POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
from core.tts_archive import ArchiveSession, check_runtime, inspect_audio
from database.manager import DatabaseManager


async def connect():
    return await asyncpg.connect(host=POSTGRES_HOST, port=int(POSTGRES_PORT), database=POSTGRES_DB,
        user=POSTGRES_USER, password=POSTGRES_PASSWORD, timeout=10)


def backup_roundtrip(schema):
    root = Path(__file__).resolve().parents[1]
    suffix = '.exe' if os.name == 'nt' else ''
    environment = {**os.environ, 'PGPASSWORD': POSTGRES_PASSWORD}
    flags = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    common = ['-h', POSTGRES_HOST, '-p', str(POSTGRES_PORT), '-U', POSTGRES_USER, '-d', POSTGRES_DB]
    dump = subprocess.run([str(root / 'tools' / 'pgsql' / 'bin' / ('pg_dump'+suffix)), *common,
        '-Fc', '-t', f'{schema}.router_tts_audio_archives'], env=environment, capture_output=True, timeout=60, check=True, **flags)
    return dump.stdout, environment, flags, common


async def encode(data):
    session = ArchiveSession()
    for offset in range(0, len(data), 16000):
        while session.queued_bytes > 1024 * 1024 and not session.error:
            await asyncio.sleep(.005)
        session.feed(data[offset:offset + 16000])
        await asyncio.sleep(0)
    with patch('core.tts_archive.save_archive', AsyncMock(return_value=1)) as save:
        result = await session.finish(log_id=None, provider='benchmark', requested_model='benchmark',
            resolved_model='benchmark', text='', status='completed')
        if 'archive_error' in result: raise RuntimeError(result['archive_error'])
        return save.call_args.args


async def main(args):
    version = check_runtime()
    output = Path(args.output_dir); output.mkdir(parents=True, exist_ok=True)
    conn = await connect()
    schema = 'tts_archive_benchmark_' + uuid.uuid4().hex
    report = {'ffmpeg':version, 'samples':[], 'limitations':[
        'Existing provider recordings; no new provider API calls. Listening quality needs human review.',
        'Relation sizes include allocated heap, TOAST and indexes for a small isolated sample; not a projected fixed saving.',
        'FFmpeg -benchmark reports encoder and decode CPU; ffprobe CPU is excluded. Parent CPU includes Python archive control.',
        'Event loop probe simulates concurrent activity; it is not a provider-to-client network latency measurement.']}
    try:
        await conn.execute(f'CREATE SCHEMA "{schema}"')
        await conn.execute(f'SET search_path TO "{schema}"')
        spy = SimpleSchemaCollector()
        await DatabaseManager()._ensure_tables(spy)
        ddl = next(query for query in spy.queries if 'CREATE TABLE IF NOT EXISTS router_tts_audio_archives' in query)
        await conn.execute('CREATE TABLE router_request_logs (id BIGSERIAL PRIMARY KEY, response_json JSONB)')
        await conn.execute(ddl)
        await conn.execute('CREATE TABLE legacy_samples (id BIGSERIAL PRIMARY KEY, response_json JSONB)')
        await conn.execute('CREATE TABLE router_virtual_keys (used_amount NUMERIC DEFAULT 1)')
        await conn.execute('INSERT INTO router_virtual_keys DEFAULT VALUES')
        for provider in ('gemini', 'local'):
            print(f'Loading existing {provider} sample...', flush=True)
            row = await conn.fetchrow("""WITH candidates AS MATERIALIZED (
                SELECT id FROM public.router_request_logs WHERE capability='tts' AND provider=$1 ORDER BY id DESC LIMIT 20
                ) SELECT l.id, provider, requested_model, response_json::text AS response,
                pg_column_size(response_json) AS actual_response_storage
                FROM public.router_request_logs l JOIN candidates c ON c.id=l.id
                WHERE response_json->>'audio_base64' IS NOT NULL
                ORDER BY l.id DESC LIMIT 1""", provider)
            if not row:
                report['samples'].append({'provider':provider,'unavailable':True}); continue
            source = json.loads(row['response']); data = base64.b64decode(source['audio_base64'], validate=True)
            gaps, stop = [], asyncio.Event()
            async def heartbeat():
                previous = time.perf_counter()
                while not stop.is_set():
                    await asyncio.sleep(.005)
                    now = time.perf_counter(); gaps.append(max(0, now - previous - .005)); previous = now
            from core import tts_archive
            spawn, read = tts_archive._spawn, tts_archive._read_limited
            cpu_records = []
            async def measured_spawn(*command):
                if Path(command[0]).stem == 'ffmpeg':
                    command = [command[0], '-benchmark', '-nostats', *command[1:]]
                    command[command.index('-v')+1] = 'info'
                return await spawn(*command)
            async def measured_read(stream, limit):
                result = await read(stream,limit)
                for user,system in re.findall(rb'bench: utime=([\d.]+)s stime=([\d.]+)s', result):
                    cpu_records.append({'user_seconds':float(user),'system_seconds':float(system)})
                return result
            pulse = asyncio.create_task(heartbeat())
            begin = time.perf_counter(); cpu_begin = time.process_time()
            with patch.object(tts_archive,'_spawn',measured_spawn), patch.object(tts_archive,'_read_limited',measured_read):
                encoded, info = await encode(data)
            elapsed = time.perf_counter() - begin; parent_cpu = time.process_time() - cpu_begin
            stop.set(); await pulse
            original_info = await asyncio.to_thread(lambda: asyncio.run(inspect_audio(data)))
            # Use the exact production insert against the isolated schema.
            from core.tts_archive import save_archive
            from database import db_manager
            pool = await asyncpg.create_pool(host=POSTGRES_HOST,port=int(POSTGRES_PORT),database=POSTGRES_DB,
                user=POSTGRES_USER,password=POSTGRES_PASSWORD,min_size=1,max_size=2,
                server_settings={'search_path':schema})
            try:
                legacy_id = await conn.fetchval('INSERT INTO legacy_samples(response_json) VALUES($1::jsonb) RETURNING id',row['response'])
                log_id = await conn.fetchval('INSERT INTO router_request_logs(response_json) VALUES($1::jsonb) RETURNING id','{}')
                with patch.object(db_manager,'get_db_pool',AsyncMock(return_value=pool)):
                    archive_id = await save_archive(encoded,info,log_id=log_id,provider=provider,requested_model=row['requested_model'],
                        resolved_model=row['requested_model'],text='Benchmark retained identity',status='completed',created_at=__import__('datetime').datetime.now(__import__('datetime').timezone.utc))
                stored = await conn.fetchrow('SELECT audio,pg_column_size(audio) AS stored_size FROM router_tts_audio_archives WHERE id=$1',archive_id)
                assert bytes(stored['audio']) == encoded
                await conn.execute('DELETE FROM router_request_logs WHERE id=$1',log_id)
                preserved = await conn.fetchrow('SELECT log_id,tts_text,audio FROM router_tts_audio_archives WHERE id=$1',archive_id)
                assert preserved['log_id'] is None and bytes(preserved['audio']) == encoded and preserved['tts_text']
                with patch.object(db_manager,'get_db_pool',AsyncMock(return_value=pool)):
                    orphan_id = await save_archive(encoded,info,log_id=log_id,provider=provider,requested_model=row['requested_model'],
                        resolved_model=row['requested_model'],text='Already deleted log',status='interrupted',created_at=__import__('datetime').datetime.now(__import__('datetime').timezone.utc))
                assert await conn.fetchval('SELECT log_id IS NULL FROM router_tts_audio_archives WHERE id=$1',orphan_id)
                await conn.execute('DELETE FROM router_tts_audio_archives WHERE id=$1',orphan_id)
                from api.admin import delete_all_logs
                with patch.object(db_manager,'get_db_pool',AsyncMock(return_value=pool)):
                    await delete_all_logs()
                assert await conn.fetchval('SELECT used_amount FROM router_virtual_keys') == 0
                assert await conn.fetchval('SELECT count(*) FROM router_tts_audio_archives WHERE id=$1',archive_id) == 1
                sample = {'provider':provider,'source_log_id':row['id'],'source_sample_rate':info['source_sample_rate'],
                    'source_bytes':len(data),'base64_bytes':len(source['audio_base64']),'opus_bytes':len(encoded),
                    'source_duration_seconds':original_info['duration_seconds'],'opus_duration_seconds':info['duration_seconds'],
                    'encode_probe_decode_wall_seconds':elapsed,'parent_cpu_seconds':parent_cpu,'ffmpeg_encode_decode_cpu':cpu_records,
                    'event_loop_max_extra_delay_ms':max(gaps,default=0)*1000,
                    'original_actual_response_pg_column_size':row['actual_response_storage'],
                    'isolated_legacy_pg_column_size':await conn.fetchval('SELECT pg_column_size(response_json) FROM legacy_samples WHERE id=$1',legacy_id),
                    'isolated_archive_pg_column_size':stored['stored_size'],'archive_survives_log_delete':True,
                    'insert_after_log_delete':True}
                report['samples'].append(sample)
                if args.write_audio:
                    (output / f'{provider}-original.wav').write_bytes(data)
                    (output / f'{provider}-archive.ogg').write_bytes(encoded)
            finally: await pool.close()
        report['isolated_relations'] = dict(await conn.fetchrow("SELECT pg_total_relation_size('legacy_samples') AS legacy_total_bytes, pg_total_relation_size('router_tts_audio_archives') AS archive_total_bytes"))
        before = [dict(row) for row in await conn.fetch('SELECT * FROM router_tts_audio_archives ORDER BY id')]
        dump, environment, flags, common = await asyncio.to_thread(backup_roundtrip, schema)
        await conn.execute('DELETE FROM router_tts_audio_archives')
        root = Path(__file__).resolve().parents[1]
        restore = root / 'tools' / 'pgsql' / 'bin' / ('pg_restore.exe' if os.name == 'nt' else 'pg_restore')
        await asyncio.to_thread(subprocess.run, [str(restore),*common,'--data-only','--no-owner'],
            input=dump,env=environment,capture_output=True,timeout=60,check=True,**flags)
        after = [dict(row) for row in await conn.fetch('SELECT * FROM router_tts_audio_archives ORDER BY id')]
        assert before == after
        report['backup_restore_exact_rows'] = True
        await conn.execute('RESET search_path')
    finally:
        await conn.execute('RESET search_path')
        if schema.startswith('tts_archive_benchmark_') and len(schema) == 54:
            await conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await conn.close()
    (output / 'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))


class SimpleSchemaCollector:
    def __init__(self): self.queries = []
    async def execute(self, query, *args): self.queries.append(query)
    async def fetchval(self, *args): return 0
    async def fetch(self,*args): return []


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',default='scratch/tts-archive-benchmark')
    parser.add_argument('--write-audio',action='store_true')
    asyncio.run(main(parser.parse_args()))
