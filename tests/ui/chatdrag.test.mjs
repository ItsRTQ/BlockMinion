import test from 'node:test';
import assert from 'node:assert/strict';
import {startServer, loadPage} from './harness.mjs';

// Dragging things of the page onto the chat points at them: a card or a folder of the map, a mob, an item, a task.
let server, page;
const posts = (suffix) => page.calls.filter((c) => c.method === 'POST' && c.path.endsWith(suffix));
const ta = () => page.$('#chat-text');
const tab = (name) => page.click(page.$(`.tab[data-tab="${name}"]`));
const transfer = () => { const data = {}; return {setData: (t, v) => { data[t] = v; }, getData: (t) => data[t] || '', get types() { return Object.keys(data); }, files: [], effectAllowed: ''}; };
const fire = (node, type, dt, extra = {}) => { const e = new page.w.Event(type, {bubbles: true, cancelable: true}); e.dataTransfer = dt; Object.assign(e, extra); node.dispatchEvent(e); return e; };
const P = (el, type, x, y) => { const e = new page.w.Event(type, {bubbles: true}); e.clientX = x; e.clientY = y; el.dispatchEvent(e); };
const reset = () => { ta().value = ''; page.eval('chatState.tasks = []; chatState.dock = false; syncDock(); renderChatPoints()'); };

test.before(async () => {
  server = await startServer(); page = await loadPage(server); page.overrides['/api/project/infect/dispatch'] = {started: true};
  await page.eval('openProject("infect")'); await page.idle();
});
test.after(async () => { if (page) await page.close(); if (server) server.stop(); });

test('a mob in Features can be dragged onto the chat button: it is pointed at, the panel opens, nothing is sent', async () => {
  tab('features'); await page.idle(); const handle = page.$('#gallery .mob-head h4.to-chat'); assert.ok(handle, 'the mob\'s name is a handle'); assert.equal(handle.draggable, true); assert.match(handle.title, /Drag onto the chat/);
  const dt = transfer(); fire(handle, 'dragstart', dt); assert.ok(page.w.document.body.classList.contains('dragging-to-chat'), 'the button shows it takes the drop');
  assert.match(dt.getData('text/plain'), /^@(runner|brute|spitter) $/, 'as plain text it is the mention, so dropping it in any text box works too');
  const over = fire(page.$('#chat-fab'), 'dragover', dt); assert.equal(over.defaultPrevented, true, 'the button accepts it');
  const drop = fire(page.$('#chat-fab'), 'drop', dt); assert.equal(drop.defaultPrevented, true); fire(handle, 'dragend', dt); await page.idle();
  assert.ok(!page.hidden('#chat-dock')); assert.equal(ta().value, dt.getData('text/plain')); assert.equal(page.$$('#chat-points .card-chip').length, 1);
  assert.ok(!page.w.document.body.classList.contains('dragging-to-chat')); assert.equal(posts('/chat').length, 0);
});

test('dropping on the message box itself points at it once (not twice as text)', async () => {
  reset(); tab('chat'); const dt = transfer(); dt.setData('application/x-blockminion', JSON.stringify({card: 'brute'})); dt.setData('text/plain', '@brute ');
  assert.equal(fire(page.$('#chat-drop'), 'dragover', dt).defaultPrevented, true); const drop = fire(ta(), 'drop', dt); await page.idle();
  assert.equal(drop.defaultPrevented, true); assert.equal(ta().value, '@brute ');
  const stray = transfer(); stray.setData('text/plain', 'hello'); assert.equal(fire(page.$('#chat-fab'), 'dragover', stray).defaultPrevented, false, 'something else being dragged is left alone');
});

test('a task that stopped can be dragged to the chat: the coordinator will be told about it', async () => {
  reset(); page.eval('chatPointTask({id: "infect:X:1", title: "Change: Runner", state: "FAILED"})'); await page.idle();   // the same path the drop takes
  reset(); const dt = transfer(); dt.setData('application/x-blockminion', JSON.stringify({task: {id: 'infect:X:1', title: 'Change: Runner', state: 'FAILED'}}));
  tab('tasks'); fire(page.$('#chat-fab'), 'drop', dt); await page.idle();
  assert.equal(page.$('#chat-points .task-chip').dataset.task, 'infect:X:1'); assert.equal(ta().value, 'This task stopped. What went wrong, and what do we do?');
  const handles = page.$$('#tab-tasks .task .state.to-chat'); assert.ok(handles.length > 0, 'every task row has a handle');
});

test('a card of the map dropped on the chat is pointed at and stays where it was; dropped anywhere else it only moves', async () => {
  reset(); tab('map'); await page.waitFor(() => page.eval('typeof mapState !== "undefined" && !!mapState.index'), 'the map');
  page.eval('MapView.reveal("runner", {instant: true}); mapState.sel = null; mapState.insp = null; MapView.frame()');
  const node = () => page.$('#map-svg .layer-cards .node[data-id="runner"]'), at = () => page.eval('JSON.stringify([mapState.lay.nodes.get("runner").x, mapState.lay.nodes.get("runner").y])');
  const before = at(), saves = posts('/map-meta').length; page.eval('chatState.dock = true; syncDock()');
  page.w.document.elementFromPoint = () => page.$('#chat-dock-slot');      // jsdom has no layout: say the pointer is over the panel
  P(node(), 'pointerdown', 100, 100); P(node(), 'pointermove', 160, 140); assert.ok(page.w.document.body.classList.contains('dragging-to-chat')); P(node(), 'pointermove', 300, 220); P(node(), 'pointerup', 300, 220); await page.idle();
  assert.equal(ta().value, '@runner '); assert.equal(at(), before, 'the card went back'); assert.ok(!page.w.document.body.classList.contains('dragging-to-chat'));
  await new Promise((r) => setTimeout(r, 700)); assert.equal(posts('/map-meta').length, saves, 'the map was not reorganised by it');
  page.w.document.elementFromPoint = () => page.$('#map-svg');
  P(node(), 'pointerdown', 100, 100); P(node(), 'pointermove', 120, 110); P(node(), 'pointermove', 130, 120); P(node(), 'pointerup', 130, 120); await page.idle();
  assert.notEqual(at(), before, 'an ordinary drag still moves the card'); assert.equal(ta().value, '@runner ');
});

test('a folder of the map dropped on the chat points at its cards', async () => {
  reset(); page.eval('chatState.dock = true; syncDock()'); page.click(page.$('#map-home')); await page.waitFor(() => !page.eval('!!mapState.fly'), 'the universe'); page.eval('MapView.frame()');
  const folder = page.$('#map-svg .folder[data-fid="auto:mob"]'); page.w.document.elementFromPoint = () => page.$('#chat-dock');
  P(folder, 'pointerdown', 100, 100); P(folder, 'pointermove', 150, 130); P(folder, 'pointermove', 220, 200); P(folder, 'pointerup', 220, 200); await page.idle();
  assert.equal(ta().value, '@brute @runner @spitter '); assert.match(page.toasts(), /3 cards added to your message/);
});

test('no native popup was used', () => assert.deepEqual(page.popups, []));
