// Runs the log-attachment extractor over every provider body shape: node scripts/test-log-attachments.mjs
import { execFileSync } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import test from 'node:test';
import assert from 'node:assert/strict';

const root = resolve(import.meta.dirname, '..');
const out = mkdtempSync(join(tmpdir(), 'log-att-'));
execFileSync(process.execPath, [join(root, 'node_modules/typescript/bin/tsc'), 'lib/log-attachments.ts',
  '--module', 'commonjs', '--target', 'es2020', '--skipLibCheck', '--outDir', out], { cwd: root, stdio: 'inherit' });
const { extractLogAttachments } = createRequire(import.meta.url)(join(out, 'log-attachments.js'));
test.after(() => rmSync(out, { recursive: true, force: true }));

const PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==';
const ref = (kind, id) => ({ [`${kind}_archive_id`]: id, sha256: 'x'.repeat(64) });
const summary = body => extractLogAttachments(JSON.stringify(body), null).map(a => `${a.kind}:${a.image_archive_id ?? a.audio_archive_id ?? a.video_archive_id ?? a.document_archive_id ?? a.external_url ?? 'inline'}`).sort();

test('OpenAI image_url, input_audio, file', () => {
  assert.deepEqual(summary({ messages: [{ role: 'user', content: [
    { type: 'image_url', image_url: { url: `data:image/png;base64,${PNG}` } },
    { type: 'image_url', image_url: { url: 'https://x/y.png' } },
    { type: 'input_audio', input_audio: { data: 'AAAA', format: 'wav' } },
    { type: 'file', file: { filename: 'a.pdf', file_data: 'data:application/pdf;base64,AAAA' } }] }] }),
  ['image:inline', 'document:inline', 'image:https://x/y.png', 'audio:inline'].sort());
});

test('Gemini inlineData / inline_data (raw and archived)', () => {
  assert.deepEqual(summary({ tools: [{}], systemInstruction: { parts: [{ text: 's' }] }, contents: [{ role: 'user', parts: [
    { inlineData: { mimeType: 'image/png', data: PNG } }, { inline_data: { mime_type: 'image/png', data: PNG } }] }] }).length, 1);
  assert.deepEqual(summary({ contents: [{ parts: [
    { inlineData: { mimeType: 'image/png', data: ref('image', 5) } },
    { inlineData: { mimeType: 'audio/wav', data: ref('audio', 6) } },
    { inlineData: { mimeType: 'video/mp4', data: ref('video', 7) } },
    { inlineData: { mimeType: 'application/pdf', data: ref('document', 8) } }] }] }),
  ['image:5', 'audio:6', 'video:7', 'document:8'].sort());
});

test('Gemini fileData', () => {
  assert.deepEqual(summary({ contents: [{ parts: [
    { fileData: { mimeType: 'video/mp4', fileUri: 'https://x/v.mp4' } },
    { fileData: { mimeType: 'image/png', fileUri: 'https://x/i.png' } },
    { file_data: { mime_type: 'application/pdf', file_uri: 'https://x/d.pdf' } },
    { fileData: { mimeType: 'image/png', fileUri: 'gs://bucket/i.png' } }] }] }),
  ['video:https://x/v.mp4', 'image:https://x/i.png', 'document:https://x/d.pdf'].sort());
});

test('Anthropic image/document blocks', () => {
  assert.deepEqual(summary({ messages: [{ role: 'user', content: [
    { type: 'image', source: { type: 'base64', media_type: 'image/png', data: ref('image', 3) } },
    { type: 'image', source: { type: 'url', url: 'https://x/a.png' } },
    { type: 'document', source: { type: 'url', url: 'https://x/a.pdf' } },
    { type: 'document', source: { type: 'base64', media_type: 'application/pdf', data: 'AAAA' } }] }] }),
  ['image:3', 'image:https://x/a.png', 'document:https://x/a.pdf', 'document:inline'].sort());
});

test('image injected after a tool result is listed once, even when repeated', () => {
  const injected = { role: 'user', parts: [{ text: 'Hafızadan açılan dosyalar…' }, { inlineData: { mimeType: 'image/png', data: ref('image', 9) } }] };
  assert.deepEqual(summary({ contents: [
    { role: 'user', parts: [{ inlineData: { mimeType: 'image/png', data: ref('image', 4) } }] },
    { role: 'model', parts: [{ functionCall: { name: 'open', args: {} } }] },
    { role: 'user', parts: [{ functionResponse: { name: 'open', response: { ok: true } } }] },
    injected, injected] }),
  ['image:4', 'image:9'].sort());
});

test('unarchived Gemini inlineData with URL-safe Base64 still shows', () => {
  const urlsafe = PNG.replace(/\+/g, '-').replace(/\//g, '_');
  const [a] = extractLogAttachments(JSON.stringify({ contents: [{ parts: [{ inlineData: { mimeType: 'image/png', data: urlsafe } }] }] }), null);
  assert.equal(a.kind, 'image');
  assert.ok(/^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(a.data_url));
});
