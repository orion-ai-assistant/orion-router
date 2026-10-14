"""Local-only dashboard/browser fixture. Never connects to the production database.

Run benchmark_tts_archive.py --write-audio first, then open :8879/test or /dashboard/logs.
"""
import base64
import json
from pathlib import Path
import sys
from unittest.mock import AsyncMock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, Response, FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from api.tts_archives import router
from core.dependencies import verify_admin
from database import db_manager

root=Path(__file__).resolve().parents[1]
output=root/'scratch'/'tts-archive-benchmark'
report=json.loads((output/'report.json').read_text(encoding='utf-8'))
app=FastAPI()
counts={'audio_requests':0}
archives=[dict(id=index+1,log_id=None,provider=sample['provider'],requested_model='fixture',resolved_model='fixture',
    created_at='2026-10-14T12:00:00Z',tts_text='Browser playback test',codec='opus',container='ogg',mime_type='audio/ogg; codecs=opus',
    duration_seconds=sample['opus_duration_seconds'],archive_size_bytes=sample['opus_bytes'],generation_status='completed')
    for index,sample in enumerate(report['samples']) if not sample.get('unavailable')]

async def auth(x_admin_key: str = Header(default='')):
    if x_admin_key != 'fixture-key': raise HTTPException(401)
app.dependency_overrides[verify_admin]=auth
app.include_router(router)

async def fetchrow(query,*args):
    if 'SELECT audio, mime_type' in query:
        counts['audio_requests']+=1
        row=next((row for row in archives if row['id']==args[0]),None)
        return {'audio':(output/f'{row["provider"]}-archive.ogg').read_bytes(),'mime_type':row['mime_type']} if row else None
    return {'archive_relation_bytes':253952,'database_bytes':0,'logged_archive_errors':0}

@app.post('/dashboard/api/auth/login')
async def login(request:Request):
    await auth(request.headers.get('x-admin-key','')); return Response(status_code=204)

@app.get('/dashboard/api/routers/browse')
async def browse():
    return {'current':{'id':'00000000-0000-4000-8000-000000000001','name':'Audio test fixture'},'routers':[]}

@app.get('/dashboard/api/settings/is-default-password')
async def password_status(): return {'is_default':False}

@app.get('/dashboard/api/system/version')
async def version(): return {'current_version':'test','update_available':False}

@app.get('/dashboard/api/logs')
async def logs(): return {'logs':[{'id':1,'key_name':'Test','provider':'gemini','requested_model':'fixture','tokens_used':None,
    'prompt_tokens':None,'completion_tokens':None,'thoughts_tokens':None,'cost':None,'success':True,'status':'success',
    'capability':'tts','created_at':'2026-10-14T12:00:00Z'},
    {'id':2,'key_name':'Legacy test','provider':'local','requested_model':'legacy-fixture','cost':None,
    'success':True,'status':'success','capability':'tts','created_at':'2026-10-14T12:00:00Z'}],'total':2}

@app.get('/dashboard/api/logs/{log_id}')
async def details(log_id:int):
    audio={'audio_archive_id':1} if log_id==1 else {'audio_base64':base64.b64encode((output/'local-original.wav').read_bytes()).decode(),'content_type':'audio/wav'}
    return {'request_json':{'input':'Browser playback fixture'},'response_json':audio,'capability':'tts'}

@app.get('/test-status')
async def status(): return counts

@app.post('/test-results')
async def result(request:Request):
    data=await request.json()
    if len(json.dumps(data))>8192: raise HTTPException(413)
    filename='browser-'+('brave' if 'Brave' in data.get('browser','') else 'chrome')+'.json'
    (output/filename).write_text(json.dumps(data,indent=2),encoding='utf-8')
    return {'saved':True}

@app.get('/test')
async def test_page():
    return HTMLResponse('''<!doctype html><html lang="en"><meta charset="utf-8"><title>TTS archive playback test</title>
<style>body{background:#18181b;color:white;font:18px system-ui;padding:40px}button{padding:12px;margin:8px}pre{white-space:pre-wrap}audio{display:block}</style>
<h1>Orion TTS archive playback / seek</h1><p>Local fixture, admin key: fixture-key. Audio is fetched only after a click.</p>
<button onclick="run(1)">Test Gemini fetch/blob playback and seek</button><button onclick="run(2)">Test local fetch/blob playback and seek</button>
<div id="players"></div><pre id="result">Ready. No audio fetched.</pre>
<script>
let results=[];
async function run(id){
 const a=document.createElement('audio');a.controls=true;document.querySelector('#players').append(a);
 const r={id,browser:navigator.userAgent,codec:a.canPlayType('audio/ogg; codecs=opus')};
 function event(name){return new Promise((resolve,reject)=>{let timer=setTimeout(()=>reject(new Error(name+' timeout')),10000);a.addEventListener(name,()=>{clearTimeout(timer);resolve()},{once:true});a.addEventListener('error',()=>reject(new Error('media '+a.error?.code)),{once:true})})}
 try{
  const url='/dashboard/api/audio-archives/'+id+'/audio';
  r.unauthorized=(await fetch(url)).status;
  const response=await fetch(url,{headers:{'X-Admin-Key':'fixture-key'}});r.status=response.status;
  const metadata=event('loadedmetadata');a.src=URL.createObjectURL(await response.blob());await metadata;r.duration=a.duration;
  await a.play();r.played=true;await new Promise(resolve=>setTimeout(resolve,150));
  const seeked=event('seeked');a.currentTime=a.duration/2;await seeked;r.seek=a.currentTime;r.seekPassed=Math.abs(a.currentTime-a.duration/2)<.2;
  await new Promise(resolve=>setTimeout(resolve,150));r.advancedAfterSeek=a.currentTime>r.seek;
  a.pause();r.passed=r.unauthorized===401&&r.status===200&&r.played&&r.seekPassed&&r.advancedAfterSeek;
 }catch(e){r.error=String(e);r.passed=false}
 results.push(r);document.querySelector('#result').textContent=JSON.stringify(results,null,2);
 await fetch('/test-results',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({browser:navigator.brave?'Brave':navigator.userAgent,results})});
}
</script></html>''')

@app.get('/dashboard/logs')
async def dashboard_logs(): return FileResponse(root/'dashboard'/'out'/'logs.html')
app.mount('/dashboard',StaticFiles(directory=root/'dashboard'/'out',html=True),name='dashboard')

if __name__=='__main__':
    with patch.object(db_manager,'fetchrow',fetchrow),patch.object(db_manager,'fetch',AsyncMock(return_value=archives)),patch.object(db_manager,'fetchval',AsyncMock(return_value=len(archives))):
        uvicorn.run(app,host='127.0.0.1',port=8879)
