import test from 'node:test';
import assert from 'node:assert/strict';
import {startServer, loadPage} from './harness.mjs';

// The chat at hand from every tab: a button opens a small panel with the SAME conversation and message box as the Chat tab.
let server, page;
const posts = (suffix) => page.calls.filter((c) => c.method === 'POST' && c.path.endsWith(suffix));
const btnOf = (root, label) => [...root.querySelectorAll('button')].find((b) => b.textContent.trim() === label);
const tab = (name) => page.click(page.$(`.tab[data-tab="${name}"]`));
const inDock = (sel) => page.$('#chat-dock').contains(page.$(sel)), inTab = (sel) => page.$('#tab-chat').contains(page.$(sel));
const T = 'infect:CHANGE:runner:1';
const view = (extra = {}) => ({messages: [{id: 1, role: 'user', text: 'pools'}, {id: 2, role: 'coordinator', text: 'An acid pool. Launch when ready.'}], thinking: false, designer_cost: {runs: 0}, waiting_files: [], plan: null, ...extra});

test.before(async () => {
  server = await startServer(); page = await loadPage(server); page.overrides['/api/project/infect/dispatch'] = {started: true};
  page.overrides['/api/project/infect/chat'] = (init) => (init && init.method === 'POST') ? {task: 'infect:CHAT:1', message: 3} : view();
  await page.eval('openProject("infect")'); await page.idle();
});
test.after(async () => { if (page) await page.close(); if (server) server.stop(); });

test('on the Chat tab there is no button: the chat is already there', () => {
  assert.ok(page.hidden('#chat-fab')); assert.ok(page.hidden('#chat-dock')); assert.ok(inTab('#chat-text') && inTab('#chat-messages'));
});

test('on any other tab a Chat button waits in the corner; it opens the panel with the same conversation, ready to type', async () => {
  tab('map'); assert.ok(!page.hidden('#chat-fab')); assert.ok(page.hidden('#chat-dock')); assert.equal(page.$('#chat-fab').getAttribute('aria-label'), 'Open the chat');
  page.click(page.$('#chat-fab'));
  assert.ok(!page.hidden('#chat-dock')); assert.ok(page.hidden('#chat-fab')); assert.ok(inDock('#chat-text') && inDock('#chat-messages') && inDock('#chat-attach'));
  assert.equal(page.w.document.activeElement.id, 'chat-text'); assert.match(page.$('#chat-dock #chat-messages').textContent, /An acid pool\. Launch when ready\./);
  assert.equal(page.$$('#chat-text').length, 1, 'one message box, moved, not copied'); assert.equal(page.$('.tab.active').dataset.tab, 'map');
});

test('a message sent from the panel is the same message: sent, dispatched, and the panel stays open', async () => {
  page.$('#chat-text').value = 'make the runner faster'; page.click(page.$('#chat-send'));
  await page.waitFor(() => posts('/chat').length === 1 && posts('/dispatch').length === 1, 'sent from the panel'); assert.equal(posts('/chat')[0].body.text, 'make the runner faster');
  await page.idle(); assert.ok(!page.hidden('#chat-dock')); assert.ok(inDock('#chat-text')); assert.equal(page.$('.tab.active').dataset.tab, 'map');
});

test('the panel follows the user across tabs, steps aside on the Chat tab, and comes back after it', async () => {
  tab('tasks'); assert.ok(!page.hidden('#chat-dock')); assert.ok(inDock('#chat-text'));
  tab('chat'); assert.ok(page.hidden('#chat-dock')); assert.ok(page.hidden('#chat-fab')); assert.ok(inTab('#chat-text') && inTab('#chat-messages'));
  assert.deepEqual([...page.$('.chat-left').children].map((n) => n.id || n.tagName).slice(-2), ['chat-messages', 'chat-drop'], 'back in their place, in order');
  tab('map'); assert.ok(!page.hidden('#chat-dock')); assert.ok(inDock('#chat-text'));
});

test('Open chat goes to the tab; closing the panel leaves the button', async () => {
  page.click(page.$('#chat-dock-open')); assert.equal(page.$('.tab.active').dataset.tab, 'chat'); assert.ok(inTab('#chat-text'));
  tab('map'); page.click(page.$('#chat-dock-close')); assert.ok(page.hidden('#chat-dock')); assert.ok(!page.hidden('#chat-fab')); assert.ok(inTab('#chat-text'), 'the box went home');
  tab('features'); assert.ok(page.hidden('#chat-dock'), 'closed stays closed'); assert.ok(!page.hidden('#chat-fab'));
});

test('the panel says where the plan stands and can start the step that is ready', async () => {
  const step = (n, status) => ({step: n, action: 'change', status, tasks: [{id: T, state: 'X'}], done_tasks: 0, start: status === 'ready' ? T : null, retry: null, waiting_for: [], blockers: [], error: null});
  page.overrides['/api/project/infect/chat'] = view({plan: {result: 'r', problems: [], launched: {applied: [], skipped: [], first: T}, steps: [{step: 1, action: 'change', card: 'runner', text: 'a'}, {step: 2, action: 'change', card: 'runner', text: 'b'}],
    progress: {state: 'ready', done: 1, total: 2, busy: false, steps: [step(1, 'done'), step(2, 'ready')]}}});
  page.click(page.$('#chat-fab')); await page.eval('chatRefresh("infect")'); await page.idle();
  assert.match(page.$('#chat-dock-status').textContent, /plan: 1 of 2 steps/); const n = posts('/dispatch').length;
  page.click(btnOf(page.$('#chat-dock-status'), 'Start step 2')); await page.waitFor(() => posts('/dispatch').length === n + 1, 'started from the panel'); assert.deepEqual({...posts('/dispatch').at(-1).body}, {task: T});
});

test('news marks the button when the panel is closed, and opening it clears the mark', async () => {
  page.click(page.$('#chat-dock-close')); const v = view(); v.messages.push({id: 9, role: 'system', text: 'Step 1 of 2 finished', meta: {plan_note: 'done:1', plan_state: 'done'}});
  page.overrides['/api/project/infect/chat'] = v; await page.eval('chatRefresh("infect")'); await page.idle();
  assert.ok(page.$('#chat-fab').classList.contains('has-news')); assert.ok(page.$('.tab[data-tab="chat"]').classList.contains('has-news'));
  page.click(page.$('#chat-fab')); assert.ok(!page.$('#chat-fab').classList.contains('has-news')); assert.ok(!page.$('.tab[data-tab="chat"]').classList.contains('has-news'));
});

test('the button says the news itself, offers to start the step that is ready, and shows when someone is working', async () => {
  page.click(page.$('#chat-dock-close')); const step = (n, status) => ({step: n, action: 'change', status, tasks: [{id: T, state: 'X'}], done_tasks: 0, start: status === 'ready' ? T : null, retry: null, waiting_for: [], blockers: [], error: null});
  const v = view({plan: {result: 'r', problems: [], launched: {applied: [], skipped: [], first: T}, steps: [{step: 1, action: 'change', card: 'runner', text: 'a'}, {step: 2, action: 'change', card: 'runner', text: 'b'}],
    progress: {state: 'ready', done: 1, total: 2, busy: false, steps: [step(1, 'done'), step(2, 'ready')]}}});
  v.messages.push({id: 20, role: 'system', text: 'Step 1 of 2 finished: 2 files changed\nStep 2 is ready', meta: {plan_note: 'done:1b', plan_state: 'done'}});
  page.overrides['/api/project/infect/chat'] = v; await page.eval('chatRefresh("infect")'); await page.idle();
  const bubble = page.$('#chat-bubble'); assert.ok(!page.hidden('#chat-bubble')); assert.equal(bubble.getAttribute('role'), 'status');
  assert.equal(bubble.querySelector('.bubble-text').textContent, 'Step 1 of 2 finished: 2 files changed'); assert.ok(page.$('#chat-fab').classList.contains('hop'));
  assert.ok(!/Step 1 of 2 finished/.test(page.toasts().split('Step 1 of 2 finished').slice(2).join('')), 'said once, by the button');
  const n = posts('/dispatch').length; page.click(btnOf(bubble, 'Start step 2')); await page.waitFor(() => posts('/dispatch').length === n + 1, 'started from the bubble'); assert.ok(page.hidden('#chat-bubble'));
  v.messages.push({id: 21, role: 'system', text: 'Step 2 of 2 stopped: boom', meta: {plan_note: 'stopped:2', plan_state: 'stopped'}}); v.plan.progress.steps[1] = step(2, 'ready');
  await page.eval('chatRefresh("infect")'); await page.idle(); assert.ok(page.$('#chat-bubble').classList.contains('bad')); assert.equal(btnOf(page.$('#chat-bubble'), 'Start step 2'), undefined, 'bad news offers no Start');
  page.click(page.$('#chat-bubble .bubble-text')); assert.ok(!page.hidden('#chat-dock'), 'the words open the chat'); assert.ok(page.hidden('#chat-bubble')); page.click(page.$('#chat-dock-close'));
  page.overrides['/api/project/infect/chat'] = view({thinking: true}); await page.eval('chatRefresh("infect")'); await page.idle(); assert.equal(page.$('#chat-fab').dataset.state, 'thinking');
  const busy = view({plan: {...v.plan, progress: {state: 'running', done: 1, total: 2, busy: true, steps: [step(1, 'done'), step(2, 'running')]}}});
  page.overrides['/api/project/infect/chat'] = busy; await page.eval('chatRefresh("infect")'); await page.idle(); assert.equal(page.$('#chat-fab').dataset.state, 'working');
  page.overrides['/api/project/infect/chat'] = view(); await page.eval('chatRefresh("infect")'); await page.idle(); assert.equal(page.$('#chat-fab').dataset.state, '');
});

test('a project that has no chat yet has no button', async () => {
  await page.eval('openProject("draft")'); await page.idle(); tab('tasks'); assert.ok(page.hidden('#chat-fab')); assert.ok(page.hidden('#chat-dock'));
});

test('no native popup was used', () => assert.deepEqual(page.popups, []));
