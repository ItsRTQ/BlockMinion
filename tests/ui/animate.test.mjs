import test from 'node:test';
import assert from 'node:assert/strict';
import {startServer, loadPage} from './harness.mjs';

// Animate: rows of name / what / when / loops, sent as one request; the designer only animates.
let server, page;
const row = (id) => page.$$('#features-list .feature').find((r) => r.querySelector('.fid')?.textContent === `quiet:${id}`);
const btnOf = (root, label) => [...root.querySelectorAll('button')].find((b) => b.textContent.trim() === label);
const posts = (suffix) => page.calls.filter((c) => c.method === 'POST' && c.path.endsWith(suffix));
const dlgOpen = () => !page.hidden('#dlg');
const press = (label) => page.click(btnOf(page.$('#dlg'), label));

test.before(async () => {
  server = await startServer(); page = await loadPage(server); await page.eval('openProject("quiet")');
  page.click(page.$('.tab[data-tab="features"]')); page.click(page.$('.subtab[data-sub="items"]'));
  await page.waitFor(() => row('ruby')?.querySelector('.animate-panel'), 'the 3D ruby with its Animate panel');
});
test.after(async () => { if (page) await page.close(); if (server) server.stop(); });
test.beforeEach(async () => {
  page.overrides['/api/project/quiet/animate'] = {task: 'quiet:ANIMATE:item:ruby', kind: 'item', ident: 'ruby', anims: ['shine']};
  page.overrides['/api/project/quiet/dispatch'] = {started: true};
  await page.idle(); await page.waitFor(() => row('ruby')?.querySelector('.animate-panel'));
});

test('only 3D items have the panel', () => {
  assert.equal(row('sapphire').querySelector('.animate-panel'), null); assert.match(row('ruby').querySelector('.animate-panel').textContent, /what it does/);
});

test('empty rows send nothing', async () => {
  page.click(btnOf(row('ruby').querySelector('.animate-panel'), 'Animate'));
  await page.waitFor(() => /Describe at least one animation/.test(page.toasts()), 'the hint'); assert.equal(posts('/animate').length, 0);
});

test('two rows, one that loops and a clip to remove, go in one request; "Not now" starts nothing', async () => {
  const panel = row('ruby').querySelector('.animate-panel');
  page.click(btnOf(panel, 'Add another'));
  const rows = [...panel.querySelectorAll('.anim-row')]; assert.equal(rows.length, 2);
  rows[0].querySelector('.anim-name').value = 'shine'; rows[0].querySelector('.anim-what').value = 'a glint runs along it'; rows[0].querySelector('.anim-when').value = 'when it is picked up';
  rows[1].querySelector('.anim-name').value = 'pulse'; rows[1].querySelector('.anim-what').value = 'it throbs'; rows[1].querySelector('.anim-when').value = 'while it is held'; rows[1].querySelector('.anim-loop').checked = true;
  panel.querySelector('.anim-remove').value = 'idle, spin';
  page.click(btnOf(panel, 'Animate'));
  await page.waitFor(() => posts('/animate').length === 1, 'the request');
  const body = posts('/animate')[0].body;
  assert.deepEqual({kind: body.kind, ident: body.ident, remove: [...body.remove]}, {kind: 'item', ident: 'ruby', remove: ['idle', 'spin']});
  assert.deepEqual(body.anims.map((a) => ({...a})), [{name: 'shine', what: 'a glint runs along it', when: 'when it is picked up', loop: false},
                                                     {name: 'pulse', what: 'it throbs', when: 'while it is held', loop: true}]);
  await page.waitFor(dlgOpen, 'start now?'); assert.match(page.$('#dlg').textContent, /shape and texture are locked/);
  press('Not now'); await page.waitFor(() => !dlgOpen()); assert.equal(posts('/dispatch').length, 0);
});

test('Reinstall says which actions went to a coder', async () => {
  page.overrides['/api/project/quiet/reinstall-3d'] = {installed: [], actions: ['fire', 'reload'], anim_task: 'quiet:ITEM3DANIM:ruby'};
  page.click(btnOf(row('ruby'), 'Reinstall'));
  await page.waitFor(() => posts('/reinstall-3d').length === 1, 'the request'); assert.deepEqual({...posts('/reinstall-3d')[0].body}, {item: 'ruby'});
  await page.waitFor(() => /fire, reload\) go to a coder: quiet:ITEM3DANIM:ruby/.test(page.toasts()), 'the toast');
});

test('a mob with a model has the panel, one without does not', async () => {
  await page.eval('openProject("infect")');
  page.click(page.$('.tab[data-tab="features"]')); page.click(page.$('.subtab[data-sub="mobs"]'));
  await page.waitFor(() => page.$('[data-focus="mob:spitter"] .animate-panel'), 'the spitter panel');
  assert.match(page.$('[data-focus="mob:spitter"] .animate-panel summary').textContent, /movement states/);
  assert.equal(page.$('[data-focus="mob:runner"] .animate-panel'), null);
});
