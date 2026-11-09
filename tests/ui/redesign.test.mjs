import test from 'node:test';
import assert from 'node:assert/strict';
import {startServer, loadPage} from './harness.mjs';

let server, page;
const card = () => page.$('[data-focus="mob:brute"]');
const btnOf = (root, label) => [...root.querySelectorAll('button')].find((b) => b.textContent.trim() === label);
const posts = (suffix) => page.calls.filter((c) => c.method === 'POST' && c.path.endsWith(suffix));
const dlgOpen = () => !page.hidden('#dlg');
const send = () => page.click(btnOf(card(), 'Send feedback and rerun designer'));
const options = () => card()?.querySelector('.redesign-options');
const ready = async () => { await page.idle(); await page.waitFor(() => card() && options(), 'the Brute card to be drawn again'); };
const PNG = Uint8Array.from(Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFElEQVR4nGP8z8Dwn4EIwESMolGFUAkAfQcCCL1mpgIAAAAASUVORK5CYII=', 'base64'));

test.before(async () => {
  server = await startServer(); page = await loadPage(server); await page.eval('openProject("infect")');
  page.click(page.$('.tab[data-tab="features"]')); page.click(page.$('.subtab[data-sub="mobs"]'));
  await page.waitFor(() => card(), 'the Brute card');
});
test.after(async () => { if (page) await page.close(); if (server) server.stop(); });
// the page redraws after every action; a test must never start while it is still doing so (a slow runner shows it)
test.beforeEach(async () => { page.overrides['/api/project/infect/dispatch'] = {started: true}; await ready(); });

test('the card shows the designer\'s notes (the built take highlighted) and the mood', () => {
  const notes = card().querySelector('.design-notes'); assert.ok(notes);
  assert.equal(notes.querySelectorAll('li').length, 3); assert.match(notes.querySelector('li.chosen').textContent, /oversized arm/); assert.match(notes.textContent, /lopsided arm reads at a glance/);
  assert.match(card().textContent, /mood: grotesque 0\.8 · toon 0/);
});

test('the options are folded away and every one of them is optional', () => {
  assert.ok(options() && !options().open, 'closed by default');
  assert.deepEqual([...options().querySelectorAll('select option')].map((o) => o.value), ['all', 'shape', 'skin']);
  assert.equal(options().querySelectorAll('input[type=radio]').length, 4, 'keep + three takes'); assert.equal(options().querySelector('input[type=radio]:checked').value, '');
  assert.deepEqual([...options().querySelectorAll('.mood-name')].map((n) => n.textContent), ['grotesque', 'toon']); assert.ok(options().querySelector('input[type=file]'));
});

test('sending with nothing at all asks what should change and starts nothing', async () => {
  const before = posts('/feedback').length; send();
  await page.waitFor(() => /Write what should change/.test(page.toasts()), 'the hint'); assert.equal(posts('/feedback').length, before); assert.ok(!dlgOpen());
});

test('"Not now" really does not start the designer (regression: the answer was never awaited)', async () => {
  page.$('textarea', card()); const ta = card().querySelector('textarea'); ta.value = 'a bit more hunched';
  const feedbacks = posts('/feedback').length, dispatches = posts('/dispatch').length; send();
  await page.waitFor(dlgOpen, 'the confirmation'); assert.match(page.$('#dlg-body').textContent, /about \$12 and 24 minutes/);
  assert.equal(posts('/dispatch').length, dispatches, 'nothing started while the question is open');
  page.click(btnOf(page.$('#dlg'), 'Not now')); await page.waitFor(() => !dlgOpen()); await ready();
  assert.equal(posts('/feedback').length, feedbacks + 1, 'the feedback itself was saved'); assert.equal(posts('/dispatch').length, dispatches, 'but the designer was not started');
});

test('"Start designer" starts it with the task of the mob', async () => {
  const ta = card().querySelector('textarea'); ta.value = 'wider shoulders'; const dispatches = posts('/dispatch').length; send();
  await page.waitFor(dlgOpen); page.click(btnOf(page.$('#dlg'), 'Start designer')); await page.waitFor(() => posts('/dispatch').length === dispatches + 1, 'the dispatch');
  assert.equal(posts('/dispatch').at(-1).body.task, 'infect:MODEL:brute');
});

test('only the skin: the options alone are enough, without a word', async () => {
  const sel = options().querySelector('select'); sel.value = 'skin'; sel.dispatchEvent(new page.w.Event('change'));
  const n = posts('/feedback').length; card().querySelector('textarea').value = ''; send(); await page.waitFor(dlgOpen);
  const body = posts('/feedback').at(-1).body; assert.equal(posts('/feedback').length, n + 1);
  assert.deepEqual([body.scope, body.text, 'take' in body, 'mood' in body], ['skin', '', false, false], 'only what changed is sent');
  page.click(btnOf(page.$('#dlg'), 'Not now')); await page.waitFor(() => !dlgOpen()); await ready();
});

test('another of its ideas: take 2 is sent as a number', async () => {
  const r = [...options().querySelectorAll('input[type=radio]')].find((i) => i.value === '2'); r.checked = true; r.dispatchEvent(new page.w.Event('change'));
  card().querySelector('textarea').value = ''; send(); await page.waitFor(dlgOpen);
  assert.equal(posts('/feedback').at(-1).body.take, 2); page.click(btnOf(page.$('#dlg'), 'Not now')); await page.waitFor(() => !dlgOpen()); await ready();
});

test('mood: moving a slider and adding a dial of your own are sent, and nothing is sent when nothing moved', async () => {
  const slider = options().querySelector('.mood-dial input[type=range]'); slider.value = '0.35'; slider.dispatchEvent(new page.w.Event('input'));
  const name = options().querySelector('.mood-add input'); name.value = 'Eerie'; page.click(btnOf(options(), 'Add'));
  assert.deepEqual([...options().querySelectorAll('.mood-name')].map((n) => n.textContent), ['grotesque', 'toon', 'eerie']);
  card().querySelector('textarea').value = ''; send(); await page.waitFor(dlgOpen);
  assert.deepEqual({...posts('/feedback').at(-1).body.mood}, {grotesque: 0.35, toon: 0, eerie: 0.5});
  page.click(btnOf(page.$('#dlg'), 'Not now')); await page.waitFor(() => !dlgOpen()); await ready();
});

test('a bad dial name is refused before anything is sent', async () => {
  await ready();
  const name = options().querySelector('.mood-add input'); name.value = 'x'; const before = posts('/feedback').length; page.click(btnOf(options(), 'Add'));
  assert.match(page.toasts(), /A dial is a word or two/); assert.equal(posts('/feedback').length, before);
});

test('what you sent shows up in the feedback list with its options', async () => {
  await page.eval('openProject("infect")'); page.click(page.$('.tab[data-tab="features"]')); page.click(page.$('.subtab[data-sub="mobs"]'));
  const list = await page.waitFor(() => card()?.querySelector('.feedback-list')?.textContent, 'the list');
  assert.match(list, /you: \(only the skin\)/); assert.match(list, /\(take 2\)/); assert.match(list, /mood: eerie 0\.5 · grotesque 0\.35 · toon 0/);
});

test('reference images: attach one, see it, remove it; none is ever required', async () => {
  assert.equal(card().querySelectorAll('.ref-thumb').length, 0);
  const input = options().querySelector('input[type=file]'); const file = new page.w.File([PNG], 'tank.png', {type: 'image/png'});
  Object.defineProperty(input, 'files', {value: [file], configurable: true}); input.dispatchEvent(new page.w.Event('change'));
  await page.waitFor(() => posts('/reference').length === 1, 'the upload'); assert.equal(posts('/reference').at(-1).body.mob, 'brute'); assert.ok(posts('/reference').at(-1).body.data.length > 20);
  page.click(page.$('.tab[data-tab="features"]')); page.click(page.$('.subtab[data-sub="mobs"]'));
  await page.waitFor(() => card()?.querySelectorAll('.ref-thumb').length === 1, 'the thumbnail');
  assert.match(card().querySelector('.ref-thumb img').src, /references%2Fbrute%2Fref-1\.png/);
  page.click(btnOf(card().querySelector('.ref-thumb'), '×')); await page.waitFor(() => posts('/remove-reference').length === 1); await ready(); assert.equal(posts('/remove-reference').at(-1).body.name, 'ref-1.png');
});

test('with only a reference attached, sending needs no words', async () => {
  const input = options().querySelector('input[type=file]'); Object.defineProperty(input, 'files', {value: [new page.w.File([PNG], 'a.png', {type: 'image/png'})], configurable: true}); input.dispatchEvent(new page.w.Event('change'));
  await page.waitFor(() => card()?.querySelectorAll('.ref-thumb').length === 1, 'the thumbnail');
  const n = posts('/feedback').length; card().querySelector('textarea').value = ''; send(); await page.waitFor(dlgOpen);
  assert.equal(posts('/feedback').length, n + 1); assert.match(posts('/feedback').at(-1).body.text, /reference images into account/);
  page.click(btnOf(page.$('#dlg'), 'Not now')); await page.waitFor(() => !dlgOpen()); await ready();
});

test('no native popup in any of it', () => { assert.deepEqual(page.popups, []); });
