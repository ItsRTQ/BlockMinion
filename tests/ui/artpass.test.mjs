import test from 'node:test';
import assert from 'node:assert/strict';
import {startServer, loadPage} from './harness.mjs';

// A custom feature on the Map can be given its own art: coder lists what it borrows, the designer paints, the coder wires.
let server, page;
const side = () => page.$('#map-side');
const btnOf = (root, label) => [...root.querySelectorAll('button')].find((b) => b.textContent.trim() === label);
const posts = (suffix) => page.calls.filter((c) => c.method === 'POST' && c.path.endsWith(suffix));
const dlgOpen = () => !page.hidden('#dlg');
const press = (label) => page.click(btnOf(page.$('#dlg'), label));
const open = async () => {
  await page.idle(); await page.eval('openCard(lastProject, "infection")');
  await page.waitFor(() => side() && btnOf(side(), 'Give it its own art'), 'the infection card with its art button');
};

test.before(async () => {
  server = await startServer(); page = await loadPage(server); await page.eval('openProject("infect")');
  page.click(page.$('.tab[data-tab="map"]')); await page.waitFor(() => page.eval('typeof mapState !== "undefined" && !!mapState.data'), 'the map');
});
test.after(async () => { if (page) await page.close(); if (server) server.stop(); });
test.beforeEach(async () => { page.overrides['/api/project/infect/dispatch'] = {started: true}; await open(); });

test('the button says what will happen and "Not now" does nothing', async () => {
  page.click(btnOf(side(), 'Give it its own art')); await page.waitFor(dlgOpen, 'the confirmation');
  assert.match(page.$('#dlg-body').textContent, /borrows from vanilla/); assert.match(page.$('#dlg-body').textContent, /designer paints them/);
  press('Not now'); await page.waitFor(() => !dlgOpen());
  assert.equal(posts('/art-pass').length, 0); assert.equal(posts('/dispatch').length, 0);
});

test('Start coder creates the art pass for this card and starts it', async () => {
  page.click(btnOf(side(), 'Give it its own art')); await page.waitFor(dlgOpen); press('Start coder');
  await page.waitFor(() => posts('/art-pass').length === 1 && posts('/dispatch').length === 1, 'the art pass and its dispatch');
  assert.equal(posts('/art-pass')[0].body.card, 'infection');
  assert.match(posts('/dispatch')[0].body.task, /^infect:ARTPASS:infection/);
  await page.waitFor(() => /Coder started/.test(page.toasts()), 'the toast');
});

test('vanilla and spec-derived cards do not offer it', async () => {
  await page.eval('openCard(lastProject, "runner")');
  await page.waitFor(() => side() && /Request a change/.test(side().textContent), 'the runner card');
  assert.equal(btnOf(side(), 'Give it its own art'), undefined);
});

test('a projectile with its own art can be made 3D from its feature card', async () => {
  await page.waitFor(() => side().querySelector('.card-projectiles .proj-line'), 'the projectile line');
  const line = side().querySelector('.card-projectiles .proj-line'); assert.match(line.textContent, /bile_glob: a glob of bile/);
  page.click(btnOf(line, '3D model…')); await page.waitFor(dlgOpen, 'the dialog');   // the seed already gave it a model
  assert.match(page.$('#dlg').textContent, /flies nose first/); assert.match(page.$('#dlg').textContent, /earlier designer run|no earlier designer runs/);
  press('Ask the designer'); await page.waitFor(() => posts('/proj3d').length === 1, 'the request');
  assert.equal(posts('/proj3d')[0].body.projectile, 'bile_glob');
  await page.waitFor(dlgOpen, 'start now?'); press('Not now'); await page.waitFor(() => !dlgOpen());
});

test('a 3D projectile opens in Blockbench from its feature card', async () => {
  page.overrides['/api/project/infect/open-model'] = {opened: '/x/models/projectiles3d/bile_glob.bbmodel', app: null, note: null};
  await page.waitFor(() => side().querySelector('.card-projectiles .proj-line'), 'the projectile line');
  const line = side().querySelector('.card-projectiles .proj-line');
  page.click(btnOf(line, 'Open in Blockbench'));
  await page.waitFor(() => posts('/open-model').length === 1, 'the request');
  assert.deepEqual({...posts('/open-model')[0].body}, {projectile: 'bile_glob'});
  await page.waitFor(() => /Opening bile_glob\.bbmodel in the default app/.test(page.toasts()), 'the toast');
});

test('a 3D projectile is animated with one question: how it moves in flight', async () => {
  page.overrides['/api/project/infect/animate'] = {task: 'infect:ANIMATE:projectile:bile_glob', anims: ['idle']};
  await page.waitFor(() => side().querySelector('.card-projectiles .proj-line'), 'the projectile line');
  page.click(btnOf(side().querySelector('.card-projectiles .proj-line'), 'Animate')); await page.waitFor(dlgOpen, 'the question');
  assert.match(page.$('#dlg').textContent, /How does it move while it flies/);
  page.$('#dlg textarea').value = 'it tumbles end over end'; press('Animate');
  await page.waitFor(() => posts('/animate').length === 1, 'the request');
  const b = posts('/animate')[0].body; assert.deepEqual({kind: b.kind, ident: b.ident, what: b.anims[0].what}, {kind: 'projectile', ident: 'bile_glob', what: 'it tumbles end over end'});
  await page.waitFor(dlgOpen, 'start now?'); press('Not now'); await page.waitFor(() => !dlgOpen());
});

test('a change request can also apply to other cards: one task, every card listed', async () => {
  page.overrides['/api/project/infect/change'] = {card: 'infection', cards: ['infection', 'runner'], task: 'infect:CHANGE:infection+runner:1'};
  await open();
  const also = side().querySelector('.also-cards'); assert.ok(also, 'the Also apply to panel');
  const box = [...also.querySelectorAll('.also-card')].find((c) => c.value === 'runner'); assert.ok(box, 'other cards listed'); box.checked = true; box.onchange();
  side().querySelector('textarea').value = 'all zombies reload their bile from a pouch';
  page.click(btnOf(side(), 'Send to a coder')); await page.waitFor(() => posts('/change').length === 1, 'the request');
  const b = posts('/change')[0].body; assert.equal(b.card, 'infection'); assert.deepEqual([...b.cards], ['runner']);
  await page.waitFor(dlgOpen); press('Cancel');
});
