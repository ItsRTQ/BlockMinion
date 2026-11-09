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
