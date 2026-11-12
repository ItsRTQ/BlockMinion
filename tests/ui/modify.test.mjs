import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import path from 'node:path';
import {startServer, loadPage} from './harness.mjs';

// Modify a finished model (the seeded Spitter) and bring your own, against the real server.
let server, page;
const card = (mob) => page.$(`[data-focus="mob:${mob}"]`);
const panel = (mob, cls) => card(mob)?.querySelector('.' + cls);
const btnOf = (root, label) => [...root.querySelectorAll('button')].find((b) => b.textContent.trim() === label);
const posts = (suffix) => page.calls.filter((c) => c.method === 'POST' && c.path.endsWith(suffix));
const dlgOpen = () => !page.hidden('#dlg');
const press = (label) => page.click(btnOf(page.$('#dlg'), label));
const ready = async () => { await page.idle(); await page.waitFor(() => panel('spitter', 'modify-panel') && panel('brute', 'modify-panel'), 'the cards to be drawn again'); };
const setFiles = (input, files) => { Object.defineProperty(input, 'files', {value: files, configurable: true}); };

test.before(async () => {
  server = await startServer(); page = await loadPage(server); await page.eval('openProject("infect")');
  page.click(page.$('.tab[data-tab="features"]')); page.click(page.$('.subtab[data-sub="mobs"]'));
  await page.waitFor(() => panel('spitter', 'modify-panel'), 'the Spitter card');
});
test.after(async () => { if (page) await page.close(); if (server) server.stop(); });
test.beforeEach(async () => { page.overrides['/api/project/infect/dispatch'] = {started: true}; await ready(); });

test('a mob without a finished model cannot be modified yet, and says how to get one', () => {
  const p = panel('brute', 'modify-panel');
  assert.match(p.textContent, /no finished model yet/); assert.equal(p.querySelector('textarea'), null);
});

test('the panel lists the model\'s parts, none ticked: by default it only adds', () => {
  const p = panel('spitter', 'modify-panel');
  const boxes = [...p.querySelectorAll('.modify-parts input[type=checkbox]')];
  assert.ok(boxes.length >= 5, 'one box per bone'); assert.ok(boxes.some((b) => b.value === 'head'));
  assert.equal(boxes.filter((b) => b.checked).length, 0);
});

test('Modify with no words asks for them and sends nothing', async () => {
  const n = posts('/model-edit').length; page.click(btnOf(panel('spitter', 'modify-panel'), 'Modify'));
  await page.waitFor(() => /Write what to change on the model/.test(page.toasts()), 'the hint'); assert.equal(posts('/model-edit').length, n);
});

test('Modify sends the words and the ticked parts; "Not now" starts nothing; the card shows it pending', async () => {
  const p = panel('spitter', 'modify-panel');
  p.querySelector('textarea').value = 'add a long tail';
  const head = [...p.querySelectorAll('.modify-parts input')].find((b) => b.value === 'head'); head.checked = true;
  const dispatches = posts('/dispatch').length; page.click(btnOf(p, 'Modify'));
  await page.waitFor(dlgOpen, 'the confirmation'); press('Not now'); await page.waitFor(() => !dlgOpen());
  assert.deepEqual({...posts('/model-edit').at(-1).body, may_change: [...posts('/model-edit').at(-1).body.may_change]}, {mob: 'spitter', text: 'add a long tail', may_change: ['head']});
  assert.equal(posts('/dispatch').length, dispatches);
  await page.waitFor(() => panel('spitter', 'modify-pending'), 'the pending modification');
  assert.match(panel('spitter', 'modify-pending').textContent, /add a long tail.*may change: head/);
});

test('Run designer starts the MODEL task; Cancel modification puts the form back', async () => {
  await page.waitFor(() => panel('spitter', 'modify-pending'));
  page.click(btnOf(panel('spitter', 'modify-pending'), 'Run designer'));
  await page.waitFor(() => posts('/dispatch').length && posts('/dispatch').at(-1).body.task === 'infect:MODEL:spitter', 'the dispatch');
  await ready(); page.click(btnOf(panel('spitter', 'modify-pending'), 'Cancel modification'));
  await page.waitFor(() => posts('/model-edit-cancel').length === 1, 'the cancel');
  await page.waitFor(() => panel('spitter', 'modify-panel')?.querySelector('textarea'), 'the form again');
});

test('Use your own model: without a file it asks for one; with one it installs it', async () => {
  const own = panel('brute', 'own-model'); assert.match(own.textContent, /No agent runs/);
  const n = posts('/model-import').length; page.click(btnOf(own, 'Install this model'));
  await page.waitFor(() => /Choose the .bbmodel file first/.test(page.toasts()), 'the hint'); assert.equal(posts('/model-import').length, n);
  const bytes = readFileSync(path.join(server.home, 'own.bbmodel'));
  setFiles(own.querySelector('.own-bbmodel'), [new page.w.File([bytes], 'own.bbmodel', {type: 'application/json'})]);
  page.click(btnOf(own, 'Install this model')); await page.waitFor(dlgOpen, 'replace?');
  assert.match(page.$('#dlg-body').textContent, /Replace Brute's current model with own\.bbmodel/); press('Replace');
  await page.waitFor(() => posts('/model-import').length === n + 1, 'the import');
  await page.waitFor(() => /Installed as your model/.test(page.toasts()), 'the server\'s note');
  await ready(); assert.ok(panel('brute', 'modify-panel').querySelector('textarea'), 'the Brute now has a model that can be modified');
});

test('a model that does not pass is refused with the reason, nothing replaced', async () => {
  const own = panel('spitter', 'own-model');
  setFiles(own.querySelector('.own-bbmodel'), [new page.w.File(['{"meta":{}}'], 'broken.bbmodel', {type: 'application/json'})]);
  page.click(btnOf(own, 'Install this model')); await page.waitFor(dlgOpen, 'replace?'); press('Replace');
  await page.waitFor(() => /could not be exported|not a supported/.test(page.toasts()), 'the reason');
});

test('Install my Blockbench edits asks first and reinstalls models/<mob>.bbmodel', async () => {
  const n = posts('/model-reinstall').length; page.click(btnOf(card('spitter'), 'Install my Blockbench edits'));
  await page.waitFor(dlgOpen); press('Cancel'); await page.waitFor(() => !dlgOpen()); assert.equal(posts('/model-reinstall').length, n);
  page.click(btnOf(card('spitter'), 'Install my Blockbench edits')); await page.waitFor(dlgOpen); press('Install');
  await page.waitFor(() => posts('/model-reinstall').length === n + 1, 'the reinstall');
  await page.waitFor(() => /Installed as your model/.test(page.toasts()), 'installed');
});
