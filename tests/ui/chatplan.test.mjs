import test from 'node:test';
import assert from 'node:assert/strict';
import {startServer, loadPage} from './harness.mjs';

// A launched plan in the chat: each step says where it stands; the one that can run has Start, right there; the end offers Test in game.
// The chat view is scripted here (the server's own progress is covered by tests/test_chat_progress.py).
let server, page;
const posts = (suffix) => page.calls.filter((c) => c.method === 'POST' && c.path.endsWith(suffix));
const btnOf = (root, label) => [...root.querySelectorAll('button')].find((b) => b.textContent.trim() === label);
const plan = () => page.$('#chat-plan');
const rows = () => page.$$('#chat-plan .plan-steps > li').map((li) => [li.className, li.querySelector('.plan-state')?.textContent, [...li.querySelectorAll('button')].map((b) => b.textContent)]);
const T = (n) => `infect:CHANGE:runner:${n}`;
const step = (n, status, extra = {}) => ({step: n, action: 'change', status, tasks: [{id: T(n), state: 'X'}], done_tasks: status === 'done' ? 1 : 0, start: status === 'ready' ? T(n) : null, retry: null, waiting_for: [], blockers: [], error: null, ...extra});
const view = (steps, state, messages = [], busy = false) => ({messages: [{id: 1, role: 'user', text: 'pools'}, ...messages], thinking: false, designer_cost: {runs: 0}, waiting_files: [],
  plan: {result: 'Acid pools.', problems: [], launched: {applied: [], skipped: [], first: T(1)}, steps: [1, 2, 3].map((n) => ({step: n, action: 'change', card: 'runner', text: `part ${n}`})),
         progress: {state, done: steps.filter((s) => s.status === 'done').length, total: 3, busy, steps}}});
const show = async (v) => { page.overrides['/api/project/infect/chat'] = v; await page.eval('chatRefresh("infect")'); await page.idle(); };
const note = (id, text, state, n) => ({id, role: 'system', text, meta: {plan_turn: 'infect:CHAT:1', plan_note: `${state}:${n}`, plan_step: n, plan_state: state}});

test.before(async () => {
  server = await startServer(); page = await loadPage(server); page.overrides['/api/project/infect/dispatch'] = {started: true};
  page.overrides['/api/project/infect/run-client'] = {started: true}; page.overrides[`/api/task/${encodeURIComponent(T(2))}/requeue`] = {state: 'READY'};
  page.overrides['/api/project/infect/chat'] = view([step(1, 'running'), step(2, 'waiting', {waiting_for: [1]}), step(3, 'waiting', {waiting_for: [2]})], 'running', [], true);
  await page.eval('openProject("infect")'); await page.idle();
});
test.after(async () => { if (page) await page.close(); if (server) server.stop(); });

test('while step 1 runs, the others wait and nothing can be started', () => {
  assert.deepEqual(rows(), [['step-running', 'running…', []], ['step-waiting', 'waiting', []], ['step-waiting', 'waiting', []]]);
  assert.match(page.$$('#chat-plan .plan-steps > li')[1].textContent, /waiting\s*for step 1/); assert.match(plan().textContent, /0 of 3 steps finished · a step is running\./);
  assert.equal(btnOf(plan(), 'Launch'), undefined); assert.equal(btnOf(plan(), 'Test in game'), undefined);
});

test('a finished step is marked, the next one gets Start here, and the ones behind it still have no button', async () => {
  await show(view([step(1, 'done'), step(2, 'ready'), step(3, 'waiting', {waiting_for: [2]})], 'ready', [note(5, 'Step 1 of 3 finished: 2 files changed\nStep 2 is ready: press Start in the plan when you want it to run.', 'done', 1)]));
  assert.deepEqual(rows(), [['step-done', 'done', []], ['step-ready', 'ready', ['Start']], ['step-waiting', 'waiting', []]]);
  assert.match(plan().textContent, /1 of 3 steps finished · the next step waits for you: press Start\./);
  assert.match(page.toasts(), /Step 1 of 3 finished: 2 files changed/, 'the chat says it happened');
  const n = posts('/dispatch').length; page.click(btnOf(plan(), 'Start'));
  await page.waitFor(() => posts('/dispatch').length === n + 1, 'the step started from the chat'); assert.deepEqual({...posts('/dispatch').at(-1).body}, {task: T(2)});
});

test('the news marks the Chat tab when the user is elsewhere, and looking clears it', async () => {
  const tab = page.$('.tab[data-tab="chat"]'); assert.ok(!tab.classList.contains('has-news'), 'not while the chat is in front');
  page.click(page.$('.tab[data-tab="tasks"]'));
  await show(view([step(1, 'done'), step(2, 'stopped', {retry: T(2), error: 'gradle build failed', can_skip: true}), step(3, 'waiting', {waiting_for: [2]})], 'stopped',
    [note(5, 'Step 1 of 3 finished', 'done', 1), note(6, 'Step 2 of 3 stopped: gradle build failed\nThe steps after it wait.', 'stopped', 2)]));
  assert.ok(tab.classList.contains('has-news')); assert.match(page.$('#chat-bubble').textContent, /Step 2 of 3 stopped: gradle build failed/, 'away from the chat, its button says it');
  page.click(tab); assert.ok(!tab.classList.contains('has-news'));
});

test('a stopped step says why and offers Retry; what waits behind it stays without a button', async () => {
  assert.deepEqual(rows(), [['step-done', 'done', []], ['step-stopped', 'stopped', ['Retry', 'Ask the coordinator', 'Skip']], ['step-waiting', 'waiting', []]]);
  assert.match(page.$('#chat-plan .plan-error').textContent, /gradle build failed/); assert.match(plan().textContent, /a step stopped; the ones after it wait/);
  const n = posts('/dispatch').length; page.click(btnOf(plan(), 'Retry'));
  await page.waitFor(() => posts('/dispatch').length === n + 1, 'retried'); assert.equal(posts('/requeue').length, 1, 'put back first, then started');
});

test('Skip asks first and says what it risks; Ask the coordinator points the chat at the task that stopped', async () => {
  page.overrides['/api/project/infect/chat-skip'] = {skipped: 2};
  page.click(btnOf(plan(), 'Skip')); await page.waitFor(() => !page.hidden('#dlg'), 'it asks'); assert.match(page.$('#dlg').textContent, /a later step may need what it was going to make/);
  assert.equal(posts('/chat-skip').length, 0); page.click(btnOf(page.$('#dlg'), 'Skip it')); await page.waitFor(() => posts('/chat-skip').length === 1, 'skipped'); assert.deepEqual({...posts('/chat-skip')[0].body}, {step: 2});
  await page.idle(); page.click(btnOf(plan(), 'Ask the coordinator')); await page.idle();
  assert.equal(page.$('#chat-text').value, 'Step 2 stopped. What went wrong, and what do we do?'); assert.equal(page.$('#chat-points .task-chip').dataset.task, T(2));
  page.overrides['/api/project/infect/chat'] = (init) => (init && init.method === 'POST') ? {task: 'infect:CHAT:2', message: 9} : view([step(1, 'done'), step(2, 'stopped', {retry: T(2), error: 'x'}), step(3, 'waiting')], 'stopped');
  const n = posts('/chat').length; page.click(page.$('#chat-send')); await page.waitFor(() => posts('/chat').length === n + 1, 'sent');
  assert.deepEqual({...posts('/chat').at(-1).body}, {text: 'Step 2 stopped. What went wrong, and what do we do?', tasks: [T(2)]}); await page.idle();
  assert.equal(page.$$('#chat-points .task-chip').length, 0, 'the box is clean again');
});

test('work an agent asked for is shown under the step that waits for it, with its own Start; one task at a time', async () => {
  const blocker = {task: 'infect:CHANGE:brute:7', title: 'Change: Brute', state: 'READY', start: 'infect:CHANGE:brute:7', retry: null};
  await show(view([step(1, 'done'), step(2, 'waiting', {blockers: [blocker]}), step(3, 'waiting', {waiting_for: [2]})], 'ready'));
  assert.match(page.$('#chat-plan .plan-blocker').textContent, /needs first: Change: Brute \(ready\)/); assert.deepEqual(rows()[1][2], ['Start it']);
  await show(view([step(1, 'done'), step(2, 'ready'), step(3, 'waiting', {waiting_for: [2]})], 'ready', [], true));
  assert.equal(btnOf(plan(), 'Start').disabled, true); assert.match(btnOf(plan(), 'Start').title, /one at a time/);
});

test('when every step is done the plan says so, says what that does not mean, and offers Test in game', async () => {
  await show(view([step(1, 'done'), step(2, 'done'), step(3, 'done')], 'done', [note(9, 'All 3 steps finished. The workers handed in their work; nothing has been tried in the game yet.', 'all', 0)]));
  assert.match(plan().textContent, /Done: 3 of 3 steps finished\./); assert.match(plan().textContent, /Nothing has been tried in the game yet/);
  assert.match(page.toasts(), /All 3 steps finished/);
  page.click(btnOf(plan(), 'Test in game')); await page.waitFor(() => !page.hidden('#dlg'), 'it asks first'); assert.match(page.$('#dlg').textContent, /Opens Minecraft with only this mod/);
  assert.equal(posts('/run-client').length, 0); page.click(btnOf(page.$('#dlg'), 'Open the game'));
  await page.waitFor(() => posts('/run-client').length === 1, 'the client'); assert.equal(page.$('#chat-text').placeholder, 'What did you see in the game?');
});

test('a plan launched by an older version (no progress) still reads as launched', async () => {
  const v = view([], 'done'); delete v.plan.progress; await show(v);
  assert.match(plan().textContent, /Launched\. Follow the tasks in Now\./); assert.equal(page.$$('#chat-plan .plan-run').length, 0);
});

test('no native popup was used', () => assert.deepEqual(page.popups, []));
