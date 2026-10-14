import asyncio
import base64
import copy
import hashlib
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI
from api.media_archives import router
from api.files import router as upload_router
from core.dependencies import authenticate_request
from core.document_archive import decode_document, archive_documents_json, save_document, archive_uploaded_document
from core.security import hash_secret
from database import db_manager
import test_image_archive as image_tests

PDF = b'%PDF-1.4\noriginal PDF bytes\n%%EOF'
TEXT = 'kürşat\nEk 3:\n<file_content>\n</file_content>\n'


def wrapped(name='note.txt',text=TEXT):
    return {'type':'text','text':f'Ek 1 — Metin dosyası: {name}\n<file_content>\n{text}\n</file_content>'}


class DocumentTests(unittest.IsolatedAsyncioTestCase):
    def test_decode_original_pdf_utf8_empty_text_and_crlf(self):
        data,info=decode_document('data:application/pdf;base64,'+base64.b64encode(PDF).decode(),'base64',filename='report.pdf')
        self.assertEqual(data,PDF); self.assertEqual(info['sha256'],hashlib.sha256(PDF).hexdigest())
        self.assertEqual(info['mime_type'],'application/pdf')
        for name,text in [('note.txt',TEXT),('empty.md',''),('extracted.pdf','PDF text')]:
            data,info=decode_document(wrapped(name,text)['text'],'wrapped')
            self.assertEqual(data,text.encode()); self.assertEqual(info['representation'],'text')
            if name.endswith('.pdf'): self.assertEqual(info['mime_type'],'text/plain')
        data,_=decode_document('Ek 1 — Metin dosyası: crlf.txt\r\n<file_content>\r\na\r\nb\r\n</file_content>','wrapped')
        self.assertEqual(data,b'a\r\nb')

    async def test_shapes_names_and_normal_text_provider_copy_are_preserved(self):
        data=TEXT.encode(); b64=base64.b64encode(data).decode()
        payload={'messages':[{'role':'user','content':[
            wrapped(),wrapped('renamed.txt'),{'name':'third.txt','mime_type':'text/plain','isText':True,'data':TEXT},
            {'type':'input_file','filename':'original.pdf','file_data':'data:application/pdf;base64,'+base64.b64encode(PDF).decode()},
            {'type':'document','source':{'type':'base64','media_type':'application/pdf','data':base64.b64encode(PDF).decode()}},
            {'inlineData':{'mimeType':'text/plain','data':b64}},
            {'type':'text','text':'Ordinary prompt: '+TEXT},
            {'type':'input_file','file_data':'https://example.test/file.pdf'},
        ]}]}
        before=copy.deepcopy(payload)
        async def save(manager,data,metadata): return {'document_archive_id':1 if data==TEXT.encode() else 2,**metadata}
        with patch('core.document_archive.save_document',AsyncMock(side_effect=save)) as writer:
            stored=json.loads(await archive_documents_json(json.dumps(payload),object()))['messages'][0]['content']
        self.assertEqual(writer.await_count,2)
        self.assertEqual([stored[0]['text']['filename'],stored[1]['text']['filename']],['note.txt','renamed.txt'])
        self.assertEqual(stored[0]['text']['document_archive_id'],stored[2]['data']['document_archive_id'])
        self.assertEqual(stored[6:],payload['messages'][0]['content'][6:]); self.assertEqual(payload,before)

    async def test_error_and_resource_fallback_do_not_change_log(self):
        raw=json.dumps({'content':[wrapped()]})
        with patch('core.document_archive.save_document',AsyncMock(side_effect=OSError('db unavailable'))):
            self.assertEqual(await archive_documents_json(raw,object()),raw)
        for limit in ('MAX_DOCUMENT_BYTES','MAX_DOCUMENT_JOBS'):
            with patch('core.document_archive.'+limit,0):
                self.assertEqual(await archive_documents_json(raw,object()),raw)
        broken=json.dumps({'type':'input_file','filename':'bad.pdf','file_data':'not valid base64!'})
        self.assertEqual(await archive_documents_json(broken,object()),broken)
        self.assertEqual(await archive_documents_json('bad JSON',object()),'bad JSON')

    async def test_multipart_upload_keeps_provider_response_and_archives_original_bytes(self):
        app=FastAPI(); app.include_router(upload_router)
        app.dependency_overrides[authenticate_request]=lambda:{'key_id':'fixture'}
        provider_result={'file_uri':'files/upstream','mime_type':'application/pdf'}
        app.state.dynamic_router=SimpleNamespace(file_providers={'gemini':True},upload_file=AsyncMock(return_value=provider_result))
        tasks=[]
        with patch('core.tts_archive.background',side_effect=lambda coro:tasks.append(coro)), \
                patch('core.document_archive.save_document',AsyncMock(return_value={'document_archive_id':1})) as save:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
                response=await client.post('/v1/files',files={'file':('original.pdf',PDF,'application/pdf')})
                self.assertEqual(response.json(),provider_result)
            await asyncio.gather(*tasks)
        self.assertEqual(save.call_args.args[1],PDF)
        self.assertEqual(save.call_args.args[2]['filename'],'original.pdf')
        self.assertEqual(app.state.dynamic_router.upload_file.call_args.kwargs['file_bytes'],PDF)
        with patch('core.document_archive.save_document',AsyncMock(side_effect=OSError('db down'))):
            await archive_uploaded_document(PDF,'application/pdf','original.pdf',object())


@unittest.skipUnless(os.getenv('ORION_IMAGE_TEST_PORT'),'Requires disposable PostgreSQL cluster')
class PostgresTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=image_tests.PostgresTests.asyncSetUp
    asyncTearDown=image_tests.PostgresTests.asyncTearDown

    async def test_dedup_all_log_paths_archive_access_and_delete_preserve_logs(self):
        data,info=decode_document(TEXT,'text','text/plain','first.txt')
        references=await asyncio.gather(*(save_document(self.manager,data,{**info,'filename':f'{index}.txt'}) for index in range(16)))
        archive_id=references[0]['document_archive_id']
        self.assertEqual(len({item['document_archive_id'] for item in references}),1)
        raw=json.dumps({'messages':[{'role':'user','content':[wrapped(),{'type':'text','text':'hello'}]}]})
        log_id=await self.manager.create_streaming_log(None,'test','model',raw,'{}',capability='chat')
        await self.manager.update_streaming_request(log_id,raw)
        await self.manager.update_streaming_log(log_id,request_json=raw,capability='chat')
        await self.manager.log_request(None,'test','model',0,0,0,0,0,request_json=raw,capability='chat')
        stored=json.loads(await self.manager.fetchval('SELECT request_json::text FROM router_request_logs WHERE id=$1',log_id))
        self.assertEqual(stored['messages'][0]['content'][0]['text']['document_archive_id'],archive_id)
        self.assertEqual(stored['messages'][0]['content'][1]['text'],'hello')
        app=FastAPI(); app.include_router(router)
        with patch.object(db_manager,'get_db_pool',AsyncMock(return_value=self.manager.pool)), \
                patch.object(db_manager,'get_config',AsyncMock(return_value=hash_secret('fixture'))):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
                path=f'/dashboard/api/media-archives/document/{archive_id}/file'; headers={'X-Admin-Key':'fixture'}
                self.assertEqual((await client.get(path)).status_code,401)
                self.assertEqual((await client.delete(f'/dashboard/api/media-archives/document/{archive_id}')).status_code,401)
                response=await client.get(path,headers=headers)
                self.assertEqual(response.content,data); self.assertIn('attachment;',response.headers['content-disposition'])
                self.assertEqual(response.headers['x-content-type-options'],'nosniff')
                self.assertEqual((await client.head(path,headers=headers)).content,b'')
                response=await client.get(path,headers={**headers,'Range':'bytes=0-2'})
                self.assertEqual(response.status_code,206); self.assertEqual(response.content,data[:3])
                listing=(await client.get('/dashboard/api/media-archives/document',headers=headers)).json()
                self.assertEqual(listing['total'],1); self.assertNotIn('document',listing['items'][0])
                self.assertEqual((await client.delete(f'/dashboard/api/media-archives/document/{archive_id}',headers=headers)).status_code,200)
                self.assertEqual(await self.manager.fetchval('SELECT count(*) FROM router_request_logs'),2)
                self.assertEqual((await client.get(path,headers=headers)).status_code,404)
                await save_document(self.manager,data,info)
                await self.manager.execute('DELETE FROM router_request_logs')
                self.assertEqual(await self.manager.fetchval('SELECT document FROM router_document_archives'),data)

    async def test_original_pdf_empty_note_and_nonchat_are_unchanged(self):
        data,info=decode_document(PDF,'binary','application/pdf','original.pdf')
        await save_document(self.manager,data,info)
        self.assertEqual(await self.manager.fetchval('SELECT document FROM router_document_archives'),PDF)
        empty,metadata=decode_document('','text','text/plain','empty.txt')
        await save_document(self.manager,empty,metadata)
        self.assertEqual(await self.manager.fetchval('SELECT size_bytes FROM router_document_archives WHERE filename=$1','empty.txt'),0)
        raw=json.dumps({'content':[wrapped()]})
        for capability in ('stt','embed','tts'):
            log_id=await self.manager.create_streaming_log(None,'test','model',raw,'{}',capability=capability)
            result=await self.manager.fetchval('SELECT request_json::text FROM router_request_logs WHERE id=$1',log_id)
            self.assertEqual(json.loads(result),json.loads(raw))


if __name__ == '__main__': unittest.main()
