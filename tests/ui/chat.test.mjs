import test from 'node:test';
import assert from 'node:assert/strict';
import {startServer, loadPage} from './harness.mjs';

// Chat: the project's main panel. Left the conversation, right the plan, one button: Launch.
let server, page;
test.before(async () => { server = await startServer(); page = await loadPage(server); await page.eval('openProject("infect")'); await page.idle(); });
test.after(async () => { if (page) await page.close(); if (server) server.stop(); });
const posts = (path) => page.calls.filter((c) => c.method === 'POST' && c.path.endsWith(path));
const btnOf = (root, label) => [...root.querySelectorAll('button')].find((b) => b.textContent.trim() === label);

test('Chat is the first tab and the default; a message is sent and its turn dispatched', async () => {
  page.overrides['/api/project/infect/chat'] = {messages: [], plan: null, thinking: false, designer_cost: {runs: 0}};
  page.overrides['/api/project/infect/dispatch'] = {started: true};
  assert.equal(page.$('.tab.active').dataset.tab, 'chat'); assert.ok(!page.$('#tab-chat').classList.contains('hidden'));
  page.$('#chat-text').value = 'I want the runner to leave acid pools';
  page.overrides['/api/project/infect/chat'] = (init) => (init && init.method === 'POST') ? {task: 'infect:CHAT:1', message: 1} : {messages: [{id: 1, role: 'user', text: 'I want the runner to leave acid pools'}], plan: null, thinking: true, designer_cost: {runs: 0}};
  page.click(page.$('#chat-send')); await page.waitFor(() => posts('/chat').length === 1, 'the message'); assert.equal(posts('/chat')[0].body.text, 'I want the runner to leave acid pools');
  await page.waitFor(() => posts('/dispatch').some((r) => r.body.task === 'infect:CHAT:1'), 'the turn dispatched');
  await page.waitFor(() => /Coordinator is thinking/.test(page.$('#chat-messages').textContent), 'thinking shown (the chat refreshes on its own)');
});

test('the plan shows on the right; Launch runs it and dispatches the first task', async () => {
  page.overrides['/api/project/infect/chat'] = {messages: [{id: 1, role: 'user', text: 'pools'}, {id: 2, role: 'coordinator', text: 'An acid pool for 5 seconds. Launch when ready.'}],
    plan: {result: 'Runner spit leaves acid pools.', steps: [{step: 1, action: 'change', card: 'runner', text: 'acid pool entity, 5 s, 1 dmg/s'}], problems: [], launched: null}, thinking: false, designer_cost: {runs: 2, avg_usd: 1.2}};
  page.overrides['/api/project/infect/chat-launch'] = {applied: [{step: 1, action: 'change', tasks: ['infect:CHANGE:runner:1']}], skipped: [], first: 'infect:CHANGE:runner:1'};
  await page.eval('chatRefresh("infect")'); await page.waitFor(() => /Runner spit leaves acid pools/.test(page.$('#chat-plan').textContent), 'the plan');
  assert.match(page.$('#chat-plan').textContent, /1 step\(s\): 1 coder, 0 designer/);
  page.click(btnOf(page.$('#chat-plan'), 'Launch')); await page.waitFor(() => posts('/chat-launch').length === 1, 'launch');
  await page.waitFor(() => posts('/dispatch').some((r) => r.body.task === 'infect:CHANGE:runner:1'), 'first task dispatched');
});

test('the navbar sits under the header; the stages and Now live in Activity; a project without source opens on Activity', async () => {
  const head = page.$('#view-project .project-head'); assert.equal(head.nextElementSibling.id, 'tabs', 'tabs right after the header');
  assert.ok(page.$('#tab-activity #stepper') && page.$('#tab-activity #now'), 'stages and Now inside Activity');
  assert.equal(page.$('.brand-name').textContent, 'BlockMinion');
  await page.eval('openProject("quiet")'); await page.idle();   // generated: chat
  assert.equal(page.$('.tab.active').dataset.tab, 'chat');
});
