import test from 'node:test';
import assert from 'node:assert/strict';
import {startServer, loadPage} from './harness.mjs';

// Items tab of a mod with a material set: it draws (regression: the set card read a variable that did not exist), and
// "Make it 3D" asks the designer for one item after saying what designer runs have cost.
let server, page;
const row = (id) => page.$$('#features-list .feature').find((r) => r.querySelector('.fid')?.textContent === `quiet:${id}`);
const btnOf = (root, label) => [...root.querySelectorAll('button')].find((b) => b.textContent.trim() === label);
const posts = (suffix) => page.calls.filter((c) => c.method === 'POST' && c.path.endsWith(suffix));
const dlgOpen = () => !page.hidden('#dlg');
const press = (label) => page.click(btnOf(page.$('#dlg'), label));

test.before(async () => {
  server = await startServer(); page = await loadPage(server); await page.eval('openProject("quiet")');
  page.click(page.$('.tab[data-tab="features"]')); page.click(page.$('.subtab[data-sub="items"]'));
  await page.waitFor(() => row('ruby_steel_sword'), 'the Items list with the material set');
});
test.after(async () => { if (page) await page.close(); if (server) server.stop(); });
test.beforeEach(async () => { page.overrides['/api/project/quiet/dispatch'] = {started: true}; await page.idle(); await page.waitFor(() => row('ruby_steel_sword')); });

test('a material set is drawn as its own card', () => {
  assert.ok(page.$('[data-focus="set:ruby_steel"]'), 'the set card'); assert.ok(row('ruby_steel_helmet'));
});

test('items, tools and weapons offer 3D; armor pieces do not', () => {
  assert.ok(btnOf(row('ruby_steel_sword'), 'Make it 3D')); assert.ok(btnOf(row('ruby'), '3D model…'), 'already 3D: change it');
  assert.equal(btnOf(row('ruby_steel_helmet'), 'Make it 3D'), undefined);
});

test('it says what it costs before anything is asked, and Cancel asks nothing', async () => {
  page.click(btnOf(row('ruby_steel_sword'), 'Make it 3D')); await page.waitFor(dlgOpen, 'the dialog');
  const text = page.$('#dlg').textContent;
  assert.match(text, /no earlier designer runs to estimate from/); assert.match(text, /inventory keeps the icon/);
  press('Cancel'); await page.waitFor(() => !dlgOpen()); assert.equal(posts('/item3d').length, 0);
});

test('Ask the designer sends the item and the notes; "Not now" starts nothing', async () => {
  page.click(btnOf(row('ruby_steel_sword'), 'Make it 3D')); await page.waitFor(dlgOpen);
  page.$('#dlg textarea').value = 'a curved blade'; press('Ask the designer');
  await page.waitFor(() => posts('/item3d').length === 1, 'the request');
  assert.deepEqual({...posts('/item3d')[0].body}, {item: 'ruby_steel_sword', notes: 'a curved blade'});
  await page.waitFor(dlgOpen, 'start now?'); press('Not now'); await page.waitFor(() => !dlgOpen());
  assert.equal(posts('/dispatch').length, 0);
});

test('a 3D item opens in Blockbench from its row; one without a model does not offer it', async () => {
  page.overrides['/api/project/quiet/open-model'] = {opened: 'C:/x/models/items3d/ruby.bbmodel', app: 'blockbench'};
  assert.equal(btnOf(row('ruby_steel_sword'), 'Open in Blockbench'), undefined);
  assert.ok(btnOf(row('ruby'), '3D model…'));
  page.click(btnOf(row('ruby'), 'Open in Blockbench'));
  await page.waitFor(() => posts('/open-model').length === 1, 'the request');
  assert.deepEqual({...posts('/open-model')[0].body}, {item: 'ruby'});
  await page.waitFor(() => /Opening ruby\.bbmodel in Blockbench/.test(page.toasts()), 'the toast');
});

test('a block offers 3D too, and asks the block route', async () => {
  page.overrides['/api/project/quiet/block3d'] = {task: 'quiet:BLOCK3D:ruby_lamp', block: 'ruby_lamp', estimate: {runs: 0}};
  await page.waitFor(() => row('ruby_lamp'), 'the block row');
  page.click(btnOf(row('ruby_lamp'), 'Make it 3D')); await page.waitFor(dlgOpen, 'the dialog');
  assert.match(page.$('#dlg').textContent, /replaces the cube \(its item keeps the icon\)/);
  press('Ask the designer'); await page.waitFor(() => posts('/block3d').length === 1, 'the request');
  assert.equal(posts('/block3d')[0].body.block, 'ruby_lamp'); assert.equal(posts('/item3d').length, 1, 'the item route was not used');
  await page.waitFor(dlgOpen, 'start now?'); press('Not now'); await page.waitFor(() => !dlgOpen());
});

test('a 3D item has a Hold panel: declare how it is held, and tune the style for the whole project', async () => {
  page.overrides['/api/project/quiet/hold'] = {hold: {style: 'aim', front: '-z', top: '+y'}};
  page.overrides['/api/project/quiet/hold-style'] = {style: 'aim', tweaks: {}, recomputed: ['ruby']};
  const panel = row('ruby').querySelector('.hold-panel'); assert.ok(panel, 'the Hold panel'); assert.match(panel.querySelector('summary').textContent, /not set yet/);
  assert.match(panel.textContent, /1\. What kind of thing is it\?/); assert.match(panel.textContent, /2\. Which way does its front point/); assert.match(panel.textContent, /3\. How big/);
  panel.querySelector('input[name="style-ruby"][value="aim"]').checked = true; panel.querySelector('input[name="front-ruby"][value="-z"]').checked = true;
  panel.querySelector('.hold-size').value = '1.5';
  page.click(btnOf(panel, 'Apply')); await page.waitFor(() => posts('/hold').length === 1, 'the hold request');
  assert.deepEqual({...posts('/hold')[0].body}, {item: 'ruby', style: 'aim', front: '-z', top: null, size: 1.5});
  await page.waitFor(() => /Held as aim, front -z/.test(page.toasts()), 'the toast');
  await page.idle(); await page.waitFor(() => page.$('#features-list .hold-style-panel'), 'the style panel');
  const sp = page.$('#features-list .hold-style-panel'); sp.querySelector('.hs-style').value = 'aim'; sp.querySelector('.hs-context').value = 'firstperson_righthand';
  sp.querySelector('.hs-translation-y').value = '-3'; sp.querySelector('.hs-scale').value = '1.2';
  page.click(btnOf(sp, 'Apply')); await page.waitFor(() => posts('/hold-style').length === 1, 'the tweak');
  const b = posts('/hold-style')[0].body; assert.equal(b.style, 'aim'); assert.deepEqual({...b.tweaks.firstperson_righthand, translation: [...b.tweaks.firstperson_righthand.translation]}, {translation: [0, -3, 0], scale: 1.2});
});

test('Ask: your words become a planner task, started on confirmation', async () => {
  page.overrides['/api/project/quiet/ask'] = {task: 'quiet:ASK:1'};
  const box = page.$('#features-list .ask-box'); assert.ok(box, 'the Ask box');
  page.click(btnOf(box, 'Plan it')); await page.waitFor(() => /Say what you want first/.test(page.toasts()), 'the hint'); assert.equal(posts('/ask').length, 0);
  box.querySelector('.ask-text').value = 'make the ruby glow when held';
  page.click(btnOf(box, 'Plan it')); await page.waitFor(() => posts('/ask').length === 1, 'the request'); assert.equal(posts('/ask')[0].body.text, 'make the ruby glow when held');
  await page.waitFor(dlgOpen); press('Start planner'); await page.waitFor(() => posts('/dispatch').length >= 1 && posts('/dispatch').at(-1).body.task === 'quiet:ASK:1', 'the dispatch');
});

test('Items: the create buttons sit above the list; search filters; pages appear past 12 items', async () => {
  const pane = page.$('#sub-items'); const order = [...pane.querySelectorAll('.add-bar, .features-toolbar, #features-list')].map((n) => n.id || n.className);
  assert.deepEqual(order, ['add-bar', 'features-toolbar', 'features-list']);
  const search = page.$('#features-search'); search.value = 'sapph'; search.dispatchEvent(new page.w.Event('input', {bubbles: true}));
  await page.waitFor(() => row('sapphire') && !row('ruby'), 'only the sapphire matches');
  search.value = ''; search.dispatchEvent(new page.w.Event('input', {bubbles: true})); await page.waitFor(() => row('ruby'), 'all back');
  assert.equal(page.$('#features-pager').children.length, 0, 'no pager with a handful of items');
  const many = Array.from({length: 30}, (_, i) => ({identifier: `gem_${i}`, label: `Gem ${i}`, kind: 'item', icon_status: 'placeholder', recipes: [], can3d: true, model3d: false}));
  page.overrides['/api/project/quiet/features'] = many;
  await page.eval('renderFeatures({id: "quiet", status: "BUILD_PASSED_GAME_UNTESTED"})'); await page.waitFor(() => page.$('#features-pager').children.length === 3, 'the pager');
  assert.match(page.$('#features-pager').textContent, /1–12 of 30/); assert.equal(page.$$('#features-list .feature').length, 12);
  page.click(page.$$('#features-pager button')[1]); await page.waitFor(() => /13–24 of 30/.test(page.$('#features-pager').textContent), 'page 2');
  delete page.overrides['/api/project/quiet/features']; await page.eval('renderFeatures({id: "quiet", status: "BUILD_PASSED_GAME_UNTESTED"})'); await page.waitFor(() => row('ruby'));
});
