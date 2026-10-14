import asyncio
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI
from api.media_archives import router, video_router
from core.security import hash_secret
from core.tts_archive import binary, save_archive
from core.video_archive import decode_video, archive_videos_json, save_video
from database import db_manager
import test_image_archive as image_tests


def sample_video():
    options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / 'original.mp4'
        subprocess.run([binary('ffmpeg'), '-hide_banner', '-v', 'error', '-f', 'lavfi',
            '-i', 'color=c=blue:s=64x48:r=10', '-t', '0.3', '-c:v', 'mpeg4', '-y', str(target)],
            capture_output=True, check=True, timeout=20, **options)
        return target.read_bytes()


def video_payload(data):
    encoded = base64.b64encode(data).decode()
    return {'messages': [{'role': 'user', 'content': [
        {'type': 'text', 'text': 'Ek 1 — Video: original.mp4'},
        {'type': 'input_video', 'input_video': {'data': encoded, 'format': 'mp4'}},
        {'type': 'text', 'text': 'Ek 2 — Video: renamed.mp4'},
        {'type': 'video_url', 'video_url': {'url': 'data:video/mp4;base64,' + encoded}},
        {'type': 'video_url', 'video_url': {'url': 'https://example.test/original.mp4'}},
    ]}]}


class VideoTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = sample_video()

    async def test_original_bytes_metadata_names_dedup_and_nonmutation(self):
        data, info = await asyncio.to_thread(decode_video, base64.b64encode(self.data).decode())
        self.assertEqual(data, self.data)
        self.assertEqual((info['width'], info['height'], info['mime_type']), (64,48,'video/mp4'))
        self.assertEqual(info['sha256'],hashlib.sha256(data).hexdigest())
        self.assertAlmostEqual(info['duration_seconds'],.3,delta=.1)
        payload = video_payload(data); original = copy.deepcopy(payload)
        with patch('core.video_archive.save_video',AsyncMock(return_value={'video_archive_id':7,**info})) as save:
            stored = json.loads(await archive_videos_json(json.dumps(payload),object()))
        parts = stored['messages'][0]['content']
        self.assertEqual(parts[1]['input_video']['data']['filename'],'original.mp4')
        self.assertEqual(parts[3]['video_url']['url']['filename'],'renamed.mp4')
        self.assertEqual(parts[4],payload['messages'][0]['content'][4])
        self.assertEqual(payload,original); save.assert_awaited_once()

    async def test_database_decode_and_resource_failures_preserve_inline(self):
        original = json.dumps(video_payload(self.data))
        with patch('core.video_archive.save_video',AsyncMock(side_effect=OSError('disk full'))):
            self.assertEqual(await archive_videos_json(original,object()),original)
        for setting in ('MAX_VIDEO_BYTES','MAX_VIDEO_JOBS'):
            with patch('core.video_archive.'+setting,0):
                self.assertEqual(await archive_videos_json(original,object()),original)
        broken = json.dumps({'inlineData':{'mimeType':'video/mp4','data':'not video'}})
        self.assertEqual(await archive_videos_json(broken,object()),broken)
        self.assertEqual(await archive_videos_json('invalid JSON',object()),'invalid JSON')


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_auth_filter_validation_delete_range_head_and_no_prompt(self):
        app = FastAPI(); app.include_router(router); app.include_router(video_router)
        headers = {'X-Admin-Key':'test-key'}
        with patch.object(db_manager,'get_config',AsyncMock(return_value=hash_secret('test-key'))), \
                patch.object(db_manager,'fetch',AsyncMock(return_value=[{'id':1}])) as rows, \
                patch.object(db_manager,'fetchrow',AsyncMock(return_value={'total':1,'total_bytes':10})) as row, \
                patch.object(db_manager,'fetchval',AsyncMock(return_value=1)) as delete:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
                self.assertEqual((await client.delete('/dashboard/api/media-archives/video/1')).status_code,401)
                delete.assert_not_awaited()
                self.assertEqual((await client.get('/dashboard/api/video-archives/1/video')).status_code,401)
                for kind in ('video','audio','image'):
                    response = await client.get(f'/dashboard/api/media-archives/{kind}?start=2026-01-01T00:00:00Z&end=2026-02-01T00:00:00Z',headers=headers)
                    self.assertEqual(response.status_code,200)
                    self.assertNotIn('tts_text',rows.call_args.args[0])
                    self.assertIsNotNone(rows.call_args.args[1].tzinfo)
                    self.assertEqual((await client.delete(f'/dashboard/api/media-archives/{kind}/1',headers=headers)).status_code,200)
                for query in ('limit=101','offset=-1','start=2026-01-01T00:00:00','start=2026-02-01T00:00:00Z&end=2026-01-01T00:00:00Z'):
                    self.assertEqual((await client.get('/dashboard/api/media-archives/video?'+query,headers=headers)).status_code,422)
                self.assertEqual((await client.delete('/dashboard/api/media-archives/invalid/1',headers=headers)).status_code,422)
                row.return_value={'video':b'0123456789','mime_type':'video/mp4','size_bytes':10}
                response=await client.get('/dashboard/api/video-archives/1/video',headers={**headers,'Range':'bytes=2-4'})
                self.assertEqual(response.status_code,206); self.assertEqual(response.content,b'234')
                response=await client.head('/dashboard/api/video-archives/1/video',headers=headers)
                self.assertEqual(response.content,b''); self.assertEqual(response.headers['content-length'],'10')
                self.assertNotIn('SELECT video',row.call_args.args[0])
                delete.return_value=None; row.return_value=None
                self.assertEqual((await client.delete('/dashboard/api/media-archives/video/1',headers=headers)).status_code,404)
                self.assertEqual((await client.get('/dashboard/api/video-archives/1/video',headers=headers)).status_code,404)


@unittest.skipUnless(os.getenv('ORION_IMAGE_TEST_PORT'),'Requires disposable PostgreSQL cluster')
class PostgresTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = image_tests.PostgresTests.asyncSetUp
    asyncTearDown = image_tests.PostgresTests.asyncTearDown

    async def test_dedup_log_paths_original_roundtrip_delete_and_date_filter(self):
        data = await asyncio.to_thread(sample_video)
        _, info = await asyncio.to_thread(decode_video,base64.b64encode(data).decode())
        references=await asyncio.gather(*(save_video(self.manager,data,info) for _ in range(16)))
        archive_id=references[0]['video_archive_id']
        self.assertEqual(len({item['video_archive_id'] for item in references}),1)
        raw=json.dumps(video_payload(data))
        log_id=await self.manager.create_streaming_log(None,'gemini','model',raw,'{}',capability='chat')
        await self.manager.update_streaming_request(log_id,raw)
        await self.manager.update_streaming_log(log_id,request_json=raw,capability='chat')
        await self.manager.log_request(None,'gemini','model',0,0,0,0,0,request_json=raw,capability='chat')
        stored=json.loads(await self.manager.fetchval('SELECT request_json::text FROM router_request_logs WHERE id=$1',log_id))
        self.assertEqual(stored['messages'][0]['content'][1]['input_video']['data']['video_archive_id'],archive_id)
        self.assertEqual(await self.manager.fetchval('SELECT count(*) FROM router_video_archives'),1)
        app=FastAPI(); app.include_router(router); app.include_router(video_router)
        with patch.object(db_manager,'get_db_pool',AsyncMock(return_value=self.manager.pool)), \
                patch.object(db_manager,'get_config',AsyncMock(return_value=hash_secret('test-key'))):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
                headers={'X-Admin-Key':'test-key'}
                self.assertEqual((await client.get(f'/dashboard/api/video-archives/{archive_id}/video',headers=headers)).content,data)
                future=await client.get('/dashboard/api/media-archives/video?start=2100-01-01T00:00:00Z',headers=headers)
                self.assertEqual(future.json()['total'],0)
                self.assertEqual((await client.delete(f'/dashboard/api/media-archives/video/{archive_id}',headers=headers)).status_code,200)
                self.assertEqual(await self.manager.fetchval('SELECT count(*) FROM router_request_logs'),2)
                self.assertEqual((await client.get(f'/dashboard/api/video-archives/{archive_id}/video',headers=headers)).status_code,404)
                renewed=await save_video(self.manager,data,info)
                self.assertNotEqual(renewed['video_archive_id'],archive_id)
                await self.manager.execute('DELETE FROM router_request_logs')
                self.assertEqual(await self.manager.fetchval('SELECT video FROM router_video_archives'),data)

    async def test_existing_schema_drops_prompt_and_tts_insert_does_not_copy_text(self):
        await self.manager.execute('ALTER TABLE router_tts_audio_archives ADD COLUMN tts_text TEXT')
        async with self.manager.pool.acquire() as conn:
            with patch.object(self.manager,'_seed_default_models',AsyncMock()),patch.object(self.manager,'_seed_admin_secret',AsyncMock()), \
                    patch.object(self.manager,'_migrate_legacy_provider_keys',AsyncMock()),patch.object(self.manager,'_migrate_plaintext_keys',AsyncMock()):
                await self.manager._ensure_tables(conn)
        self.assertIsNone(await self.manager.fetchval("SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='router_tts_audio_archives' AND column_name='tts_text'"))
        info=dict(codec='opus',container='ogg',mime_type='audio/ogg',duration_seconds=1,channels=1,sample_rate=48000,
            source_sample_rate=24000,source_channels=1,source_format='s16le',source_size_bytes=48000,archive_size_bytes=5)
        with patch.object(db_manager,'get_db_pool',AsyncMock(return_value=self.manager.pool)):
            archive_id=await save_archive(b'audio',info,log_id=None,provider='test',requested_model='test',resolved_model='test',
                text='PROMPT MUST NOT BE COPIED',status='completed',created_at=datetime.now(timezone.utc))
        row=await self.manager.fetchrow('SELECT * FROM router_tts_audio_archives WHERE id=$1',archive_id)
        self.assertNotIn('PROMPT MUST NOT BE COPIED',str(dict(row)))


if __name__ == '__main__': unittest.main()
