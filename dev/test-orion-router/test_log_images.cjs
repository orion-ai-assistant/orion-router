const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('../../dashboard/node_modules/typescript');
const source = fs.readFileSync(path.join(__dirname,'../../dashboard/lib/log-images.ts'),'utf8');
const exported = {};
new Function('exports', ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText)(exported);
const {extractLogImages} = exported;

test('new references are collected once across request and response',()=>{
  const ref={image_archive_id:7,mime_type:'image/png',width:10,height:5};
  assert.deepEqual(extractLogImages(JSON.stringify({messages:[{content:[{type:'image_url',image_url:{url:ref}}]}]}),{image:ref}),[ref]);
});
test('legacy inline image shapes stay viewable; text and external URLs never load',()=>{
  const result=extractLogImages({messages:[{content:[
    {type:'image_url',image_url:{url:'data:image/png;base64,dGVzdA=='}},
    {type:'image',source:{type:'base64',media_type:'image/webp',data:'d2VicA=='}},
    {inline_data:{mime_type:'image/gif',data:'Z2lm'}},
    {type:'text',text:'data:image/png;base64,bm90YW5pbWFnZQ=='},
    {type:'image_url',image_url:{url:'https://example.test/image.png'}},
    {mime_type:'image/png',isText:true,data:'dGV4dA=='},
  ]}]});
  assert.equal(result.length,3);
  assert.equal(result[0].data_url,'data:image/png;base64,dGVzdA==');
  assert.equal(result[1].data_url,'data:image/webp;base64,d2VicA==');
  assert.equal(result[2].data_url,'data:image/gif;base64,Z2lm');
  assert.deepEqual(extractLogImages(null,'invalid JSON',{type:'image_url',image_url:{url:'javascript:alert(1)'}}),[]);
});
