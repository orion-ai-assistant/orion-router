const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const Module = require('node:module');
const path = require('node:path');
const ts = require('../../dashboard/node_modules/typescript');
const filename = path.resolve(__dirname, '../../dashboard/lib/usage.ts');
const compiled = new Module(filename, module);
compiled._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'), {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText, filename);
const {summarizeUsage,dailyRequests} = compiled.exports;
const bucket = overrides => ({capability:'chat',requests:2,succeeded:2,failed:0,input:20,output:4,thoughts:1,total:25,cost:0,missing_usage:0,missing_cost:0,...overrides});
test('legacy unknown unit and token chat rows produce one complete card',()=>{
 const result=summarizeUsage([bucket({usage_unit:null,requests:8,total:7944}),bucket({usage_unit:'token',total:2332})]);
 assert.equal(result.length,1);
 assert.equal(result[0].requests,10);
 assert.equal(result[0].total,10276);
 assert.deepEqual(Object.keys(result[0].amounts),['token']);
});
test('different physical units stay separate and unknown sums stay null',()=>{
 const [result]=summarizeUsage([bucket({capability:'tts',usage_unit:'character',usage_amount:100,total:null,cost:null}),bucket({capability:'tts',usage_unit:'second',usage_amount:5,total:null,cost:null})]);
 assert.deepEqual(result.amounts,{character:100,second:5});
 assert.equal(result.total,null);
 assert.equal(result.cost,null);
});
test('daily series sum unit buckets once per day and operation in date order',()=>{
 assert.deepEqual(dailyRequests([bucket({day:'2026-10-08',requests:3}),bucket({day:'2026-10-07',requests:2,usage_unit:'token'}),bucket({day:'2026-10-07',requests:8,usage_unit:null}),bucket({day:'2026-10-07',capability:'tts',requests:4})]),[
 {day:'2026-10-07',counts:{chat:10,tts:4}}, {day:'2026-10-08',counts:{chat:3}}
 ]);
});
