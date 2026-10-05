const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('../../dashboard/node_modules/typescript');
const source = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../../dashboard/lib/clipboard.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 }
}).outputText;

function session(clipboard, result = true) {
  const calls = [];
  class HTMLElement {}
  const previous = new HTMLElement();
  previous.closest = () => ({ appendChild: () => calls.push('inside dialog') });
  previous.focus = () => calls.push('restore focus');
  const field = { style: {}, focus() {}, select() {}, setSelectionRange() {}, remove: () => calls.push('remove') };
  const context = { exports: {}, navigator: { clipboard }, HTMLElement, document: {
    activeElement: previous, createElement: () => field,
    execCommand: () => { calls.push('copy'); return result; }
  }};
  vm.runInNewContext(source, context);
  return { copy: context.exports.copyText, calls, field };
}

test('uses the modern Clipboard API when available', async () => {
  const texts = [];
  const current = session({ writeText: async text => texts.push(text) });
  assert.equal(await current.copy('sample'), true);
  assert.deepEqual(texts, ['sample']);
  assert.deepEqual(current.calls, []);
});
test('copies on local HTTP inside the modal and restores focus', async () => {
  const current = session(undefined);
  assert.equal(await current.copy('sample'), true);
  assert.equal(current.field.value, 'sample');
  assert.deepEqual(current.calls, ['inside dialog', 'copy', 'remove', 'restore focus']);
});
test('falls back after denied iframe clipboard permissions', async () => {
  const current = session({ writeText: async () => { throw new Error('denied'); } });
  assert.equal(await current.copy('sample'), true);
  assert.ok(current.calls.includes('copy'));
});
test('reports a failed copy rather than claiming success', async () => {
  const current = session(undefined, false);
  assert.equal(await current.copy('sample'), false);
  assert.deepEqual(current.calls.slice(-2), ['remove', 'restore focus']);
});
