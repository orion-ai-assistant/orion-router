const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('../../dashboard/node_modules/typescript');
function load(name) {
  const source = fs.readFileSync(path.join(__dirname, '../../dashboard/lib', name + '.ts'), 'utf8');
  const exported = {};
  new Function('exports', 'require', ts.transpileModule(source, {compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText)(exported, name => load(name.replace('./','')));
  return exported;
}
const {extractLogAttachments} = load('log-attachments');
test('nested legacy filename and MIME are kept without duplicate audio entries', () => {
  const result=extractLogAttachments({content:[
    {type:'image_url',image_url:{filename:'photo.png',url:'data:image/png;base64,aW1hZ2U='}},
    {audio:{filename:'voice.ogg',mime_type:'audio/ogg',data:'YXVkaW8='}},
  ]},null);
  assert.equal(result.length,2);
  assert.equal(result[0].filename,'photo.png');
  assert.equal(result[1].filename,'voice.ogg');
  assert.equal(result[1].mime_type,'audio/ogg');
});
test('archive video and original filenames survive; arbitrary text is never used as a filename', () => {
  const result = extractLogAttachments({messages:[{content:[
    {type:'text',text:'Ek 1 — Görsel: screenshot.jpg'},
    {type:'image_url',image_url:{url:{image_archive_id:5,mime_type:'image/jpeg'}}},
    {type:'text',text:'Ek 2 — Video: original.mp4'},
    {type:'input_video',input_video:{data:{video_archive_id:6,mime_type:'video/mp4',size_bytes:100,width:10,height:20}}},
    {type:'text',text:'This prompt is not a filename'},
    {type:'input_audio',input_audio:{data:'YXVkaW8=',format:'wav'}},
    {type:'input_audio',input_audio:{filename:'C:\\uploads\\recording.wav',data:'b3RoZXI=',format:'wav'}},
  ]}]},null);
  assert.equal(result[0].filename,'screenshot.jpg');
  assert.equal(result[1].filename,'original.mp4');
  assert.equal(result[1].video_archive_id,6);
  assert.equal(result[2].filename,undefined);
  assert.equal(result[3].filename,'recording.wav');
});
test('input and output attachments remain distinct and deduplicate within each side', () => {
  const image = {image_archive_id:8, mime_type:'image/png'};
  const input = {messages:[{content:[{image}, {image}, {type:'input_audio',input_audio:{format:'mp3',data:'YXVkaW8='}}, {type:'input_video',input_video:{format:'mp4',data:'dmlkZW8='}}]}]};
  const output = {image, audio_archive_id:9};
  const result = extractLogAttachments(JSON.stringify(input), JSON.stringify(output));
  assert.deepEqual(result.map(a=>[a.direction,a.kind]), [['input','image'],['input','audio'],['input','video'],['output','image'],['output','audio']]);
  assert.equal(result[1].data_url,'data:audio/mpeg;base64,YXVkaW8=');
  assert.equal(result[2].data_url,'data:video/mp4;base64,dmlkZW8=');
});
test('legacy, Gemini, URL video and generated media are recognized without scanning normal text', () => {
  const result = extractLogAttachments({parts:[{inlineData:{mimeType:'video/webm',data:'d2VibQ=='}},
    {type:'video_url',video_url:{url:'https://example.test/video.mp4'}},
    {type:'text',text:'data:video/mp4;base64,dGV4dA=='},
    {mime_type:'audio/wav',isText:true,data:'dGV4dA=='},
    {type:'video_url',video_url:{url:'file:///secret'}},
    {type:'input_video',input_video:{data:'javascript:alert(1)'}}]},
    {audio_base64:'YXVkaW8=',content_type:'audio/wav', data:[{b64_json:'aW1hZ2U='}]});
  assert.deepEqual(result.map(a=>a.kind), ['video','video','image','audio']);
  assert.equal(result[1].external_url, 'https://example.test/video.mp4');
  assert.deepEqual(extractLogAttachments('bad JSON',null),[]);
});
