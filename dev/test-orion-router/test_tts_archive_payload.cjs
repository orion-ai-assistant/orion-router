const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('../../dashboard/node_modules/typescript');
const source = fs.readFileSync(path.join(__dirname, '../../dashboard/lib/format-payload.ts'), 'utf8');
const compiled = ts.transpileModule(source, {compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
const exported = {};
new Function('exports', compiled)(exported);

test('new archive reference plays without inline audio; legacy Base64 remains available', () => {
  assert.deepEqual(exported.extractTtsAudio(JSON.stringify({audio_archive_id:42,audio_archive:{codec:'opus'}})), {audio_archive_id:42});
  assert.deepEqual(exported.extractTtsAudio({audio_base64:'dGVzdA==',content_type:'audio/wav'}), {audio_base64:'dGVzdA==',content_type:'audio/wav'});
  for (const value of [null, {}, 'invalid JSON', {archive_error:'encoder failed'}]) assert.equal(exported.extractTtsAudio(value),null);
});
