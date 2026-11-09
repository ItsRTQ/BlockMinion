import test from 'node:test';
import assert from 'node:assert/strict';
import {startServer, loadPage} from './harness.mjs';

// Resize a mob without redesigning it: one number, no agent, against the real server (the seeded `infect` project is generated).
let server, page;
const card = () => page.$('[data-focus="mob:runner"]');
const size = () => card()?.querySelector('.size-inline');
const btnOf = (root, label) => [...root.querySelectorAll('button')].find((b) => b.textContent.trim() === label);
const posts = (suffix) => page.calls.filter((c) => c.method === 'POST' && c.path.endsWith(suffix));
const dlgOpen = () => !page.hidden('#dlg');
const press = (label) => page.click(btnOf(page.$('#dlg'), label));
const ready = async () => { await page.idle(); await page.waitFor(() => size(), 'the Runner card to be drawn again'); };

test.before(async () => {
  server = await startServer(); page = await loadPage(server); await page.eval('openProject("infect")');
  page.click(page.$('.tab[data-tab="features"]')); page.click(page.$('.subtab[data-sub="mobs"]'));
  await page.waitFor(() => size(), 'the Runner card');
});
test.after(async () => { if (page) await page.close(); if (server) server.stop(); });
test.beforeEach(ready);

test('every mob card says its size and offers Resize', () => {
  assert.match(size().textContent, /Size:\s*as modeled/);
  assert.ok(btnOf(size(), 'Resize'));
});

test('Cancel changes nothing', async () => {
  const before = posts('/mob-scale').length; page.click(btnOf(size(), 'Resize'));
  await page.waitFor(dlgOpen, 'the size question'); assert.equal(page.$('#dlg-f-0').value, '1');
  press('Cancel'); await page.waitFor(() => !dlgOpen()); assert.equal(posts('/mob-scale').length, before);
});

test('Resize patches the generated entity and the card shows the new size without leaving the tab', async () => {
  page.w.scrollTo(0, 480);
  page.click(btnOf(size(), 'Resize')); await page.waitFor(dlgOpen, 'the size question');
  assert.match(page.$('#dlg-body').textContent, /hitbox grows with it/); assert.match(page.$('#dlg-body').textContent, /no agent runs/);
  page.$('#dlg-f-0').value = '1.5'; press('Resize');
  await page.waitFor(() => posts('/mob-scale').length === 1, 'the resize');
  assert.deepEqual({...posts('/mob-scale')[0].body}, {mob: 'runner', scale: 1.5});
  await page.waitFor(() => /Rebuild to apply/.test(page.toasts()), 'the server\'s note');
  await page.waitFor(() => size() && /1\.5× the model/.test(size().textContent), 'the card with the new size');
  assert.ok(page.$('.subtab[data-sub="mobs"].active'), 'still on the Mobs sub-tab'); assert.equal(page.w.__y, 480, 'and at the same scroll position');
});

test('a size outside the range is refused by the server and said', async () => {
  page.click(btnOf(size(), 'Resize')); await page.waitFor(dlgOpen);
  page.$('#dlg-f-0').value = '40'; press('Resize');
  await page.waitFor(() => /0\.0625-16/.test(page.toasts()), 'the range error');
  await ready(); assert.match(size().textContent, /1\.5× the model/, 'the size did not change');
});
