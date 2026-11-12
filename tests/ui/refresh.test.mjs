import test from 'node:test';
import assert from 'node:assert/strict';
import {startServer, loadPage} from './harness.mjs';

let server, page;
const realProject = async () => (await fetch(`${server.base}/api/project/infect`, {headers: {Authorization: 'Bearer ' + server.token}})).json();
// the server's answer, but with another status: what the page sees when something changed while an agent worked
const changed = (status) => async () => ({...(await realProject()), status});
const refresh = () => page.eval('refreshProject("infect")');
const projectCalls = () => page.calls.filter((c) => c.path === '/api/project/infect').length;

test.before(async () => { server = await startServer(); page = await loadPage(server); });
test.after(async () => { if (page) await page.close(); if (server) server.stop(); });
test.beforeEach(async () => { for (const k of Object.keys(page.overrides)) delete page.overrides[k]; await page.eval('openProject("infect")'); });

test('boot draws the selected project and the sidebar lists every project with a marker slot', () => {
  assert.equal(page.$('#p-name').textContent, 'Infectious Zombies');
  const rows = page.$$('#project-list .proj[data-pid]'); assert.deepEqual(rows.map((r) => r.dataset.pid).sort(), ['draft', 'infect', 'quiet']);
  assert.ok(rows.every((r) => r.querySelector('.pwork') && r.querySelector('.pwork').hidden));
});

test('a refresh never moves you: with Environment open the project stays hidden', async () => {
  page.click(page.$('#nav-env')); await page.waitFor(() => !page.hidden('#view-env'));
  page.overrides['/api/project/infect'] = changed('BUILD_FAILED');
  await refresh();
  assert.ok(!page.hidden('#view-env')); assert.ok(page.hidden('#view-project'));
});

test('a refresh for a project you are not looking at does nothing', async () => {
  const before = page.calls.length; await page.eval('refreshProject("quiet")');
  assert.equal(page.calls.slice(before).filter((c) => c.path === '/api/project/quiet').length, 0);
});

test('an unchanged payload is not redrawn', async () => {
  const marker = page.$('#spec-body'); marker.dataset.mark = 'still here'; const stage = page.$('#stepper'); stage.dataset.mark = 'still here';
  await refresh(); await refresh();
  assert.equal(page.$('#spec-body').dataset.mark, 'still here'); assert.equal(page.$('#stepper').firstElementChild.isConnected, true);
  const first = page.$('#spec-body').firstElementChild; await refresh(); assert.equal(page.$('#spec-body').firstElementChild, first, 'the same DOM node: nothing was rebuilt');
});

test('a changed payload is redrawn, and the scroll, the open sections and the project view survive', async () => {
  const perms = page.$$('#view-project details').find((d) => d.textContent.includes('Autopilot permissions')); assert.ok(perms, 'the Autopilot permissions section exists');
  perms.open = true; page.w.scrollTo(0, 480);
  const oldNode = page.$('#spec-body').firstElementChild;
  page.overrides['/api/project/infect'] = changed('BUILD_FAILED');
  await refresh();
  assert.notEqual(page.$('#spec-body').firstElementChild, oldNode, 'it was rebuilt'); assert.equal(page.$('#p-status').textContent, 'BUILD FAILED');
  const again = page.$$('#view-project details').find((d) => d.textContent.includes('Autopilot permissions'));
  assert.ok(again.open, 'the open section is still open'); assert.equal(page.w.__y, 480, 'the scroll position was restored'); assert.ok(!page.hidden('#view-project'));
  assert.equal(page.doc.body.style.minHeight, '', 'the height hold was released');
});

test('while you type in a field the refresh waits, and it lands once you stop', async () => {
  const before = page.$('#p-status').textContent, box = page.$('#theme-text'); box.focus();
  page.overrides['/api/project/infect'] = changed('BUILD_FAILED');
  await refresh(); assert.equal(page.$('#p-status').textContent, before, 'nothing moved under the typing hand');
  box.blur(); await refresh(); assert.equal(page.$('#p-status').textContent, 'BUILD FAILED');
});

test('a dialog or a modal also holds the refresh', async () => {
  const before = page.$('#p-status').textContent; page.overrides['/api/project/infect'] = changed('BUILD_FAILED');
  const asking = page.eval('confirmBox("Start the designer now?")'); await page.waitFor(() => !page.hidden('#dlg'));
  await refresh(); assert.equal(page.$('#p-status').textContent, before);
  page.click(page.$('#dlg-actions button')); await asking; await refresh(); assert.equal(page.$('#p-status').textContent, 'BUILD FAILED');
});

test('theme text you typed and have not saved is not overwritten by a refresh', async () => {
  page.$('#theme-text').value = 'my unsaved words'; page.$('#theme-text').dataset.dirty = '1';
  page.overrides['/api/project/infect'] = changed('BUILD_FAILED'); await refresh();
  assert.equal(page.$('#theme-text').value, 'my unsaved words');
  delete page.$('#theme-text').dataset.dirty; page.overrides['/api/project/infect'] = changed('GAME_VERIFIED'); await refresh();
  assert.match(page.$('#theme-text').value, /Rotting infection/, 'once saved (or untouched) the server text is shown again');
});

test('opening a project navigates, even from another view', async () => {
  page.click(page.$('#nav-env')); await page.waitFor(() => !page.hidden('#view-env'));
  await page.eval('openProject("infect")'); assert.ok(page.hidden('#view-env')); assert.ok(!page.hidden('#view-project'));
});

test('an Environment view that cannot reach the server says so instead of failing silently', async () => {
  const lost = []; const onReject = (e) => lost.push(String(e)); process.on('unhandledRejection', onReject);
  try {
    page.overrides['/api/doctor'] = async () => { throw new Error('connection lost'); };
    page.click(page.$('#nav-env')); await page.waitFor(() => /Environment: connection lost/.test(page.toasts()), 'the error toast'); await page.idle();
    assert.deepEqual(lost, [], 'nothing was left unhandled');
  } finally { process.off('unhandledRejection', onReject); }
});

test('no refresh path used a native popup', () => { assert.deepEqual(page.popups, []); });

test('a refresh with SVG elements on screen (the Map) does not throw on the scroll guard', async () => {
  await page.eval('openProject("infect")'); page.click(page.$('.tab[data-tab="map"]'));
  await page.waitFor(() => page.$('#map-svg'), 'the map');
  page.$('#map-svg').innerHTML = '<defs class="x y"></defs><g class="node"><rect/></g>';
  const svg = page.$('#map-svg defs'); Object.defineProperty(svg, 'scrollTop', {value: 3, configurable: true});   // a scrolled SVG node, as the guard sees it
  let threw = null; try { await page.eval('Guard.snapshot()'); } catch (e) { threw = e; }
  assert.equal(threw, null, 'Guard.snapshot must not throw on SVG class names');
});
