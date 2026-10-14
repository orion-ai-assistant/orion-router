"""Offline contracts and optional isolated PostgreSQL integration.

ORION_IMAGE_TEST_PORT points to a disposable localhost postgres test cluster.
"""
import asyncio
import base64
import copy
import hashlib
import io
import json
import os
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI
from PIL import Image

from api.image_archives import router
from core.image_archive import archive_images_json, _decode_image, save_image
from core.security import hash_secret
from database import db_manager
from database.manager import DatabaseManager


def image_bytes(fmt='PNG'):
    output = io.BytesIO()
    Image.new('RGB', (7, 5), (15, 80, 120)).save(output, format=fmt)
    return output.getvalue()


def encoded(data): return base64.b64encode(data).decode('ascii')
def message(data): return {'messages':[{'role':'user','content':[{'type':'text','text':'hello'},
    {'type':'image_url','image_url':{'url':'data:image/png;base64,'+encoded(data),'detail':'high'}}]}]}


class HeaderTests(unittest.TestCase):
    def test_original_bytes_and_actual_file_header_metadata(self):
        for fmt in ('PNG','JPEG','WEBP','GIF'):
            data=image_bytes(fmt)
            # Deliberately wrong declared MIME; the original file is authoritative.
            result,info=_decode_image('data:image/jpeg;base64,'+encoded(data))
            self.assertEqual(result,data); self.assertEqual(info['sha256'],hashlib.sha256(data).hexdigest())
            self.assertEqual((info['width'],info['height']),(7,5)); self.assertEqual(info['format'],fmt.lower())
            self.assertEqual(info['size_bytes'],len(data))
        self.assertEqual(_decode_image(encoded(image_bytes()).rstrip('='))[0],image_bytes())


class TransformTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_image_shapes_deduplicate_without_mutating_source_or_text(self):
        data=image_bytes(); b64=encoded(data)
        payload=message(data)
        payload['messages'][0]['content'].extend([
            {'type':'input_image','input_image':{'data':b64,'format':'png'}},
            {'type':'input_image','image_url':b64},
            {'type':'image','source':{'type':'base64','media_type':'image/png','data':b64}},
            {'inlineData':{'mimeType':'image/png','data':b64}},
            {'inline_data':{'mime_type':'image/png','data':b64}},
            {'type':'image_url','image_url':{'url':'https://example.test/image.png'}},
            {'type':'text','text':b64},
        ])
        payload['metadata']={'images':[b64], 'attachments':[{'mime_type':'image/png','data':b64},
            {'mime_type':'image/png','data':b64,'isText':True}]}
        original=copy.deepcopy(payload); serialized=json.dumps(payload)
        reference={'image_archive_id':11,'mime_type':'image/png','width':7,'height':5}
        with patch('core.image_archive.save_image',AsyncMock(return_value=reference)) as save:
            result=json.loads(await archive_images_json(serialized,object()))
        save.assert_awaited_once(); self.assertEqual(save.call_args.args[1],data)
        self.assertEqual(payload,original)
        content=result['messages'][0]['content']
        self.assertEqual(content[1]['image_url']['url'],reference)
        self.assertEqual(content[1]['image_url']['detail'],'high')
        self.assertEqual(content[2]['input_image']['data'],reference)
        self.assertEqual(content[3]['image_url'],reference)
        self.assertEqual(content[4]['source']['data'],reference)
        self.assertEqual(content[5]['inlineData']['data'],reference)
        self.assertEqual(content[6]['inline_data']['data'],reference)
        self.assertEqual(content[7]['image_url']['url'],'https://example.test/image.png')
        self.assertEqual(content[8]['text'],b64)
        self.assertEqual(result['metadata']['attachments'][1]['data'],b64)

    async def test_failure_preserves_exact_base64_and_other_images_can_succeed(self):
        data=image_bytes(); original=json.dumps(message(data))
        with patch('core.image_archive.save_image',AsyncMock(side_effect=OSError('database full'))):
            self.assertEqual(await archive_images_json(original,object()),original)
        invalid=json.dumps({'messages':[{'content':[{'type':'image_url','image_url':{'url':'data:image/png;base64,invalid!'}}]}]})
        with patch('core.image_archive.save_image',AsyncMock()) as save:
            self.assertEqual(await archive_images_json(invalid,object()),invalid); save.assert_not_awaited()
        payload=message(data); payload['messages'][0]['content'].append({'type':'image_url','image_url':{'url':'data:image/png;base64,bad!'}})
        with patch('core.image_archive.save_image',AsyncMock(return_value={'image_archive_id':1})):
            result=json.loads(await archive_images_json(json.dumps(payload),object()))
        self.assertEqual(result['messages'][0]['content'][1]['image_url']['url'],{'image_archive_id':1})
        self.assertEqual(result['messages'][0]['content'][2],payload['messages'][0]['content'][2])
        for setting in ('MAX_IMAGE_BYTES','MAX_IMAGE_JOBS'):
            with patch('core.image_archive.'+setting,0):
                self.assertEqual(await archive_images_json(original,object()),original)

    async def test_conflict_uses_existing_id_without_rewriting_bytes(self):
        data,info=_decode_image(encoded(image_bytes()))
        conn=SimpleNamespace(fetchval=AsyncMock(side_effect=[None,42]))
        class Acquire:
            async def __aenter__(self): return conn
            async def __aexit__(self,*args): pass
        manager=SimpleNamespace(get_db_pool=AsyncMock(return_value=SimpleNamespace(acquire=lambda:Acquire())))
        result=await save_image(manager,data,info)
        self.assertEqual(result['image_archive_id'],42)
        self.assertIn('ON CONFLICT (sha256) DO NOTHING',conn.fetchval.call_args_list[0].args[0])
        self.assertNotIn('UPDATE',conn.fetchval.call_args_list[0].args[0])


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_main_archive_routes_precede_dashboard_static_fallback(self):
        from main import app
        async def loopback(scope,receive,send):
            scope['orion_loopback_listener']=True
            await app(scope,receive,send)
        data=image_bytes()
        row={'image':data,'audio':b'audio','mime_type':'image/png','size_bytes':len(data)}
        with patch.object(db_manager,'get_config',AsyncMock(return_value=hash_secret('fixture-key'))), \
                patch.object(db_manager,'fetchrow',AsyncMock(return_value=row)):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=loopback),base_url='http://127.0.0.1') as client:
                for path,expected in [('/dashboard/api/image-archives/1/image',data),('/dashboard/api/audio-archives/1/audio',b'audio')]:
                    self.assertEqual((await client.get(path)).status_code,401)
                    response=await client.get(path,headers={'X-Admin-Key':'fixture-key'})
                    self.assertEqual(response.status_code,200); self.assertEqual(response.content,expected)

    async def test_admin_bytes_head_list_and_not_found(self):
        data=image_bytes(); app=FastAPI(); app.include_router(router)
        with patch.object(db_manager,'get_config',AsyncMock(return_value=hash_secret('fixture-key'))), \
            patch.object(db_manager,'fetchrow',AsyncMock(return_value={'image':data,'mime_type':'image/png','size_bytes':len(data)})) as row, \
            patch.object(db_manager,'fetch',AsyncMock(return_value=[{'id':1,'size_bytes':len(data)}])) as fetch:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
                for method in ('GET','HEAD'):
                    self.assertEqual((await client.request(method,'/dashboard/api/image-archives/1/image')).status_code,401)
                self.assertEqual((await client.get('/dashboard/api/image-archives')).status_code,401)
                row.assert_not_awaited(); fetch.assert_not_awaited()
                headers={'X-Admin-Key':'fixture-key'}
                response=await client.get('/dashboard/api/image-archives/1/image',headers=headers)
                self.assertEqual(response.content,data); self.assertEqual(response.headers['content-type'],'image/png')
                self.assertEqual(response.headers['x-content-type-options'],'nosniff')
                response=await client.head('/dashboard/api/image-archives/1/image',headers=headers)
                self.assertEqual(response.content,b''); self.assertEqual(response.headers['content-length'],str(len(data)))
                self.assertNotIn('SELECT image,',row.call_args.args[0])
                row.return_value={'total':1,'total_bytes':len(data)}
                response=await client.get('/dashboard/api/image-archives',headers=headers)
                self.assertEqual(response.json()['total'],1)
                self.assertNotIn('SELECT image,',fetch.call_args.args[0])
                self.assertEqual((await client.get('/dashboard/api/image-archives?limit=999',headers=headers)).status_code,422)
                row.return_value=None
                self.assertEqual((await client.get('/dashboard/api/image-archives/999/image',headers=headers)).status_code,404)


@unittest.skipUnless(os.getenv('ORION_IMAGE_TEST_PORT'),'Requires disposable PostgreSQL test cluster')
class PostgresTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import asyncpg
        self.schema='image_archive_test_'+uuid.uuid4().hex
        self.connection=await asyncpg.connect(host='127.0.0.1',port=int(os.environ['ORION_IMAGE_TEST_PORT']),user='postgres',database='postgres')
        await self.connection.execute(f'CREATE SCHEMA "{self.schema}"')
        self.manager=DatabaseManager()
        self.manager.pool=await asyncpg.create_pool(host='127.0.0.1',port=int(os.environ['ORION_IMAGE_TEST_PORT']),user='postgres',database='postgres',
            min_size=1,max_size=8,server_settings={'search_path':self.schema})
        async with self.manager.pool.acquire() as conn:
            with patch.object(self.manager,'_seed_default_models',AsyncMock()),patch.object(self.manager,'_seed_admin_secret',AsyncMock()), \
                patch.object(self.manager,'_migrate_legacy_provider_keys',AsyncMock()),patch.object(self.manager,'_migrate_plaintext_keys',AsyncMock()):
                await self.manager._ensure_tables(conn)

    async def asyncTearDown(self):
        await self.manager.pool.close()
        assert self.schema.startswith('image_archive_test_') and len(self.schema)==51
        await self.connection.execute(f'DROP SCHEMA "{self.schema}" CASCADE')
        await self.connection.close()

    async def test_concurrent_dedup_and_original_roundtrip(self):
        data,info=_decode_image(encoded(image_bytes()))
        references=await asyncio.gather(*(save_image(self.manager,data,info) for _ in range(16)))
        self.assertEqual(len({r['image_archive_id'] for r in references}),1)
        self.assertEqual(await self.manager.fetchval('SELECT count(*) FROM router_image_archives'),1)
        self.assertEqual(await self.manager.fetchval('SELECT image FROM router_image_archives'),data)

    async def test_all_log_write_paths_and_log_clear_preserve_archive(self):
        data=image_bytes(); raw=json.dumps(message(data))
        log_id=await self.manager.create_streaming_log(None,'gemini','model',raw,'{}',capability='chat')
        original_ref=json.loads(await self.manager.fetchval('SELECT request_json::text FROM router_request_logs WHERE id=$1',log_id))
        self.assertNotIn(encoded(data),json.dumps(original_ref))
        await self.manager.update_streaming_request(log_id,raw)
        await self.manager.update_streaming_log(log_id,request_json=raw,response_json='{}',capability='chat')
        await self.manager.log_request(None,'gemini','model',0,0,0,0,0,request_json=raw,capability='chat')
        self.assertEqual(await self.manager.fetchval('SELECT count(*) FROM router_image_archives'),1)
        for record in await self.manager.fetch('SELECT request_json::text FROM router_request_logs'):
            self.assertEqual(json.loads(record['request_json']),original_ref)
        from api.admin import delete_all_logs
        with patch.object(db_manager,'get_db_pool',AsyncMock(return_value=self.manager.pool)):
            await delete_all_logs()
        self.assertEqual(await self.manager.fetchval('SELECT count(*) FROM router_request_logs'),0)
        self.assertEqual(await self.manager.fetchval('SELECT image FROM router_image_archives'),data)
        app=FastAPI(); app.include_router(router)
        archive_id=await self.manager.fetchval('SELECT id FROM router_image_archives')
        with patch.object(db_manager,'get_db_pool',AsyncMock(return_value=self.manager.pool)),patch.object(db_manager,'get_config',AsyncMock(return_value=hash_secret('fixture-key'))):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
                response=await client.get(f'/dashboard/api/image-archives/{archive_id}/image',headers={'X-Admin-Key':'fixture-key'})
                self.assertEqual(response.content,data)

    async def test_missing_archive_table_falls_back_and_nonchat_is_unchanged(self):
        raw=json.dumps(message(image_bytes()))
        await self.manager.execute('DROP TABLE router_image_archives')
        for capability in ('chat','stt','embed','tts'):
            log_id=await self.manager.create_streaming_log(None,'test','model',raw,'{}',capability=capability)
            await self.manager.update_streaming_log(log_id,request_json=raw,capability=capability)
            result=await self.manager.fetchval('SELECT request_json::text FROM router_request_logs WHERE id=$1',log_id)
            self.assertEqual(json.loads(result),json.loads(raw))

    async def test_provider_receives_original_messages_while_logs_get_references(self):
        from core.router.runners.chat import ChatRunner
        from core.router.telemetry import TelemetryService
        from core.router.route_types import RoutePlan
        original=message(image_bytes())['messages']; received=[]
        async def stream_chat(**kwargs):
            received.append(copy.deepcopy(kwargs['messages']))
            yield 'data: {"choices":[{"delta":{"content":"hello"}}]}\n\n'
            yield {'internal_usage':{'prompt_tokens':12,'completion_tokens':1}}
        runner=ChatRunner(SimpleNamespace(chat_providers={'test':SimpleNamespace(stream_chat=stream_chat)}),
            SimpleNamespace(resolve=AsyncMock(return_value=RoutePlan.direct('model','test'))),
            SimpleNamespace(get_keys_for_provider=AsyncMock(return_value=[(None,None)]),mark_key_error=AsyncMock()),TelemetryService())
        tasks=[]; create_task=asyncio.create_task
        def track(coro):
            task=create_task(coro); tasks.append(task); return task
        with patch.object(db_manager,'get_db_pool',AsyncMock(return_value=self.manager.pool)), \
                patch('core.router.runners.chat.asyncio.create_task',side_effect=track):
            chunks=[chunk async for chunk in runner.run_combo('test','model',original)]
            await asyncio.sleep(0)
            await asyncio.gather(*tasks)
        self.assertTrue(chunks); self.assertEqual(received,[original])
        self.assertIsInstance(original[0]['content'][1]['image_url']['url'],str)
        stored=json.loads(await self.manager.fetchval('SELECT request_json::text FROM router_request_logs ORDER BY id DESC LIMIT 1'))
        self.assertIn('image_archive_id',stored['messages'][0]['content'][1]['image_url']['url'])
        self.assertEqual(await self.manager.fetchval('SELECT count(*) FROM router_image_archives'),1)


if __name__=='__main__': unittest.main()
