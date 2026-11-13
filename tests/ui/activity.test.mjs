import test from 'node:test';
import assert from 'node:assert/strict';
import {startServer, loadPage} from './harness.mjs';

let server, page;
const now = () => Date.now() / 1000;
const step = (o = {}) => ({task: 'infect:MODEL:brute', role: 'designer', runtime: 'antigravity-cli', label: 'Designer · model of brute', target: {tab: 'features', sub: 'mobs', focus: 'mob:brute'}, since: now() - 70, ...o});
const runningFeed = (o = {}) => ({now: now(), projects: {infect: {running: true, job: 'dispatch', job_label: 'Agent', elapsed_s: 72, name: 'Infectious Zombies', step: step(o)}}, recent: []});
const idleFeed = (recent = []) => ({now: now(), projects: {}, recent});
const finished = (state, o = {}) => ({project: 'infect', name: 'Infectious Zombies', job: 'dispatch', job_label: 'Agent', state, finished_at: now() - 4, elapsed_s: 90, step: step(), error: null, ...o});
const poll = () => page.eval('Activity.poll()');
const pill = () => page.$('#activity-pill'), bar = () => page.$('#activity-bar'), panel = () => page.$('#activity-panel');
const row = (pid) => page.$(`#project-list .proj[data-pid="${pid}"]`);

test.before(async () => { server = await startServer(); page = await loadPage(server); });
test.after(async () => { if (page) await page.close(); if (server) server.stop(); });
test.beforeEach(async () => { page.overrides['/api/activity'] = idleFeed(); await page.eval('openProject("infect")'); await poll(); });

test('with nothing going on the banner is hidden and no project is marked', () => {
  assert.ok(bar().classList.contains('hidden')); assert.ok(page.$$('#project-list .pwork').every((n) => n.hidden)); assert.ok(!page.doc.title.startsWith('●'));
});

test('a running agent marks its project in the sidebar and shows the banner with project, step, runtime and time', async () => {
  page.overrides['/api/activity'] = runningFeed(); await poll();
  assert.ok(row('infect').classList.contains('working')); assert.ok(!row('quiet').classList.contains('working'));
  const tag = row('infect').querySelector('.pwork'); assert.equal(tag.hidden, false); assert.match(tag.textContent, /designer working/); assert.equal(tag.title, 'Designer · model of brute');
  assert.ok(!bar().classList.contains('hidden')); assert.ok(pill().classList.contains('running'));
  assert.match(pill().textContent, /Infectious Zombies · Designer · model of brute · 1m \d\ds/);
  assert.ok(page.doc.title.startsWith('● working'));
});

test('the pill opens a panel that names the runtime and offers a link to the work', async () => {
  page.overrides['/api/activity'] = runningFeed(); await poll(); page.click(pill());
  assert.ok(!panel().classList.contains('hidden')); assert.equal(pill().getAttribute('aria-expanded'), 'true');
  const text = panel().textContent; for (const needle of ['Working now', 'RUNNING', 'Infectious Zombies', 'Designer · model of brute', 'Antigravity', 'Watch it']) assert.ok(text.includes(needle), needle);
  page.click(pill()); assert.ok(panel().classList.contains('hidden'));
});

test('"Watch it" takes you to the mob: Features, Mobs and the card, highlighted', async () => {
  page.overrides['/api/activity'] = runningFeed(); await poll(); page.click(pill());
  page.click([...panel().querySelectorAll('button')].find((b) => b.textContent === 'Watch it'));
  await page.waitFor(() => page.$('.tab[data-tab="features"]').classList.contains('active') && page.$('.subtab[data-sub="mobs"]').classList.contains('active'), 'the Mobs tab');
  const card = page.$('[data-focus="mob:brute"]'); assert.ok(card, 'the brute card exists'); await page.waitFor(() => card.classList.contains('flash')); assert.equal(page.w.__scrolledTo, card);
  assert.ok(panel().classList.contains('hidden'), 'the panel closed');
});

test('a coder step takes you to its card on the Map', async () => {
  page.overrides['/api/activity'] = runningFeed({task: 'infect:FEATURE:infection', role: 'coder', label: 'Coder · infection', target: {tab: 'map', focus: 'infection'}});
  await poll(); page.click(pill()); page.click([...panel().querySelectorAll('button')].find((b) => b.textContent === 'Watch it'));
  await page.waitFor(() => page.$('.tab[data-tab="map"]').classList.contains('active'), 'the Map tab');
  await page.waitFor(() => page.eval('mapState.sel') === 'infection', 'the card selected'); assert.ok(!page.hidden('#map-inspector'), 'its details are open');
});

test('it works from another view too: Environment is left for the project', async () => {
  page.click(page.$('#nav-env')); await page.waitFor(() => !page.hidden('#view-env'));
  page.overrides['/api/activity'] = runningFeed({task: 'infect:SPEC', role: 'interpreter', label: 'Interpreter · reading your idea and proposing the spec', target: {tab: 'spec'}});
  await poll(); page.click(pill()); assert.ok(!page.hidden('#view-env'), 'a running job does not move you by itself');
  page.click([...panel().querySelectorAll('button')].find((b) => b.textContent === 'Watch it'));
  await page.waitFor(() => !page.hidden('#view-project') && page.$('.tab[data-tab="spec"]').classList.contains('active'), 'the Spec tab');
});

test('when it finishes: a toast, a green banner and a marker on the project you are not looking at', async () => {
  page.overrides['/api/activity'] = runningFeed(); await poll();
  page.click(row('quiet')); await page.waitFor(() => page.$('#p-name').textContent === 'Quiet Gems');
  page.overrides['/api/activity'] = idleFeed([finished('done')]); await poll();
  assert.match(page.toasts(), /Infectious Zombies: Designer · model of brute finished/);
  assert.ok(pill().classList.contains('done')); assert.match(pill().textContent, /finished/); assert.ok(page.doc.title.startsWith('✓ done'));
  const tag = row('infect').querySelector('.pwork'); assert.equal(tag.hidden, false); assert.match(tag.textContent, /✓ finished/); assert.ok(!row('infect').classList.contains('working'));
  page.click(row('infect')); await page.waitFor(() => page.$('#p-name').textContent === 'Infectious Zombies');
  await page.waitFor(() => bar().classList.contains('hidden'), 'the banner to clear once the project is open'); assert.ok(row('infect').querySelector('.pwork').hidden, 'opening the project clears the marker too');
});

test('a failure is red, says why, and can be dismissed', async () => {
  page.overrides['/api/activity'] = runningFeed(); await poll();
  page.overrides['/api/activity'] = idleFeed([finished('failed', {error: 'interpreter proposal rejected: art.silhouette'})]); await poll();
  assert.ok(pill().classList.contains('failed')); assert.match(page.toasts(), /failed.*art\.silhouette/); page.click(pill());
  assert.match(panel().textContent, /FAILED/); assert.match(panel().textContent, /art\.silhouette/);
  page.click([...panel().querySelectorAll('button')].find((b) => b.textContent === 'Dismiss')); assert.ok(bar().classList.contains('hidden'));
});

test('an agent that needs you is amber', async () => {
  page.overrides['/api/activity'] = idleFeed([finished('waiting', {step: step({label: 'Interpreter · reading your idea and proposing the spec', target: {tab: 'spec'}})})]); await poll();
  assert.ok(pill().classList.contains('waiting')); assert.match(pill().textContent, /needs you/);
});

test('a job finishing on the project you are looking at refreshes it once, without moving you', async () => {
  page.overrides['/api/activity'] = runningFeed(); await poll();
  const real = async () => (await fetch(`${server.base}/api/project/infect`, {headers: {Authorization: 'Bearer ' + server.token}})).json();
  page.overrides['/api/project/infect'] = async () => ({...(await real()), status: 'BUILD_FAILED'});
  page.w.scrollTo(0, 300); page.overrides['/api/activity'] = idleFeed([finished('done')]); await poll();
  await page.waitFor(() => page.$('#p-status').textContent === 'BUILD FAILED', 'the refresh'); assert.equal(page.w.__y, 300);
});

test('several jobs show how many more there are', async () => {
  const feed = runningFeed(); feed.projects.quiet = {running: true, job: 'build', job_label: 'Building with Gradle', elapsed_s: 5, name: 'Quiet Gems', step: step({task: null, role: 'controller', runtime: null, label: 'Building with Gradle', target: {tab: 'verify'}})};
  page.overrides['/api/activity'] = feed; await poll(); assert.match(pill().textContent, /\+1/); page.click(pill());
  assert.equal(panel().querySelectorAll('.act-row').length, 2); assert.match(panel().textContent, /Building with Gradle/);
});

test('no popup of the browser was used', () => { assert.deepEqual(page.popups, []); });
