import test from 'node:test';
import assert from 'node:assert/strict';
import {startServer, loadPage} from './harness.mjs';

// Mod Map 2.0 in the real page: Zoom = travel, Click = inspect, Expand = understand, Focus = investigate, Modify = an explicit request.
// jsdom has no layout and no canvas: the viewport is the fallback 1000x600, and what is asserted is state and the SVG/HTML the user touches.
let server, page;
const VP = '{w: 1000, h: 600}';
const ev = (code) => page.eval(code);
const frame = () => ev('MapView.frame()');
const posts = (suffix) => page.calls.filter((c) => c.method === 'POST' && c.path.endsWith(suffix));
const coderCalls = () => page.calls.filter((c) => c.method === 'POST' && /\/(change|dispatch|feature|art-pass|animate|card)$/.test(c.path)).length;
const btnOf = (root, label) => [...root.querySelectorAll('button')].find((b) => b.textContent.trim() === label);
const insp = () => page.$('#map-inspector');
const folderEl = (fid) => page.$(`#map-svg .folder[data-fid="${fid}"]`);
const node = (id) => page.$(`#map-svg .layer-cards .node[data-id="${id}"]`);
const tap = (el) => { el.dispatchEvent(new page.w.Event('pointerdown', {bubbles: true})); el.dispatchEvent(new page.w.Event('pointerup', {bubbles: true})); };
const open = () => ev('JSON.stringify([...mapState.open].sort())');
const cam = () => JSON.parse(ev('JSON.stringify(mapState.cam)'));
const screenOf = (fid) => JSON.parse(ev(`(() => { const c = mapState.lay.folders.get("${fid}"), s = MapCore.toScreen(mapState.cam, ${VP}, c.x, c.y); return JSON.stringify([s.x, s.y]); })()`));
const settle = () => { for (let i = 0; i < 400 && ev('!!mapState.zoom || [...mapState.amt.values()].some((a) => a !== 1)'); i++) frame(); frame(); };
const landed = async () => { await page.waitFor(() => !ev('!!mapState.fly'), 'the camera to arrive'); settle(); };
const wheel = (x, y, deltaY, times = 1) => { for (let i = 0; i < times; i++) { page.$('#map-wrap').dispatchEvent(new page.w.WheelEvent('wheel', {deltaY, clientX: x, clientY: y, bubbles: true, cancelable: true})); settle(); } };
const drag = (dx, dy) => { const svg = page.$('#map-svg'), P = (type, x, y) => { const e = new page.w.Event(type, {bubbles: true}); e.clientX = x; e.clientY = y; svg.dispatchEvent(e); }; P('pointerdown', 400, 300); P('pointermove', 400 + dx / 2, 300 + dy / 2); P('pointermove', 400 + dx, 300 + dy); P('pointerup', 400 + dx, 300 + dy); frame(); };
const universe = async () => { page.click(page.$('#map-home')); await landed(); if (insp().querySelector('.insp-close')) page.click(insp().querySelector('.insp-close')); frame(); };
const dlg = () => page.$('#dlg'), dlgOpen = () => !page.hidden('#dlg');

test.before(async () => {
  server = await startServer(); page = await loadPage(server); await ev('openProject("infect")');
  page.click(page.$('.tab[data-tab="map"]')); await page.waitFor(() => ev('typeof mapState !== "undefined" && !!mapState.index'), 'the map'); frame();
});
test.after(async () => { if (page) await page.close(); if (server) server.stop(); });

test('it opens on the universe: folders as dots with a name and a count, no wall of cards', () => {
  assert.deepEqual(page.$$('#map-svg .folder').map((n) => `${n.querySelector('.fname').textContent} ${n.querySelector('.fcount').textContent}`).sort(), ['Features 5', 'Mobs 3', 'Vanilla resources 3']);
  assert.equal(page.$$('#map-svg .node').length, 0, 'no cards yet'); assert.equal(open(), '[""]');
  assert.equal(page.$('#map-crumbs').textContent, 'Infectious Zombies'); assert.match(page.$('#map-count').textContent, /^11 \/ 11 features visible/); assert.match(page.$('#map-count').textContent, /11 inside folders/);
  assert.ok(page.hidden('#map-inspector') && page.hidden('#map-side') && page.hidden('#map-focusbar'), 'the canvas has the whole space');
  assert.match(folderEl('auto:mob').getAttribute('aria-label'), /Mobs, folder, 3 features/); assert.equal(folderEl('auto:mob').getAttribute('tabindex'), '0');
});

test('zooming into empty space only zooms, and panning over a folder never enters it', () => {
  wheel(5, 5, -100, 14); assert.ok(cam().k > 0.6, 'zoomed in'); assert.equal(open(), '[""]', 'nothing entered: the zoom was aimed at empty space');
  const [x, y] = screenOf('auto:mob'); drag(500 - x, 300 - y);
  const [nx, ny] = screenOf('auto:mob'); assert.ok(Math.abs(nx - 500) < 2 && Math.abs(ny - 300) < 2, 'Mobs is now under the middle of the screen, large');
  assert.equal(open(), '[""]', 'and still not entered'); assert.equal(page.$$('#map-svg .node').length, 0);
});

test('one more notch aimed at the folder enters it: its features appear, the breadcrumb follows, nothing was double-clicked', () => {
  wheel(500, 300, -100, 1); assert.equal(open(), '["","auto:mob"]');
  assert.deepEqual(page.$$('#map-svg .layer-cards .node').map((n) => n.dataset.id).sort(), ['brute', 'runner', 'spitter']);
  assert.equal(page.$('#map-crumbs').textContent, 'Infectious Zombies›Mobs'); assert.ok(folderEl('auto:mob').classList.contains('entered'));
  assert.match(page.$('#map-count').textContent, /3 on screen/);
  const k = cam().k; wheel(500, 300, 100000, 1); assert.ok(cam().k > k / 1.6, 'a wild wheel gesture is one small step, not a jump out of the folder'); assert.equal(open(), '["","auto:mob"]');
});

test('cards morph with distance: full card, compact card, dot; the feature is the same one throughout', () => {
  ev('mapState.cam.k = 1; mapState.cam.cx = mapState.lay.nodes.get("runner").x; mapState.cam.cy = mapState.lay.nodes.get("runner").y'); frame();
  assert.ok(node('runner') && !node('runner').classList.contains('compact')); assert.equal(node('runner').querySelector('.title').textContent, 'Runner');
  ev('mapState.cam.k = 0.7'); frame(); assert.ok(node('runner').classList.contains('compact'), 'farther: a compact card');
  ev('mapState.cam.k = 0.4'); frame(); assert.equal(node('runner'), null, 'farther still: a dot on the canvas'); assert.equal(ev('mapState.index.cards.size'), 11, 'and still eleven features');
  ev('mapState.cam.k = 1'); frame(); assert.ok(node('runner'));
});

test('zooming out is the inverse: cards fold back into their folder and the universe returns', () => {
  wheel(500, 300, 100, 40); assert.equal(open(), '[""]'); assert.equal(page.$$('#map-svg .node').length, 0);
  assert.equal(page.$$('#map-svg .folder').length, 3); assert.equal(page.$('#map-crumbs').textContent, 'Infectious Zombies'); assert.ok(!folderEl('auto:mob').classList.contains('entered'));
});

test('keyboard: Enter on a folder goes in, Backspace goes out; the navigation buttons do the same', async () => {
  folderEl('auto:custom').dispatchEvent(new page.w.KeyboardEvent('keydown', {key: 'Enter', bubbles: true, cancelable: true})); await landed();
  assert.equal(open(), '["","auto:custom"]'); assert.equal(page.$('#map-crumbs').textContent, 'Infectious Zombies›Features'); assert.equal(page.$('#map-up').disabled, false);
  page.key(page.$('#map-wrap'), 'Backspace'); await landed(); assert.equal(open(), '[""]');
  page.click(page.$('#map-back')); await landed(); assert.equal(open(), '["","auto:custom"]', 'Back returns to where we were');
  page.click(page.$('#map-fwd')); await landed(); assert.equal(open(), '[""]'); await universe();
});

test('Click = inspect: a small note beside the card, the camera does not move, nothing is sent', async () => {
  ev('MapView.reveal("runner", {instant: true}); mapState.sel = null'); frame(); const before = cam(), n0 = coderCalls();
  tap(node('runner')); frame();
  assert.ok(!page.hidden('#map-inspector')); assert.ok(insp().classList.contains('quick')); assert.equal(insp().querySelector('h3').textContent, 'Runner'); assert.match(insp().querySelector('.insp-type').textContent, /^Mob • /);
  assert.deepEqual([...insp().querySelectorAll('.insp-actions button')].map((b) => b.textContent), ['Modify with Minion', 'Expand', 'Focus']);
  assert.deepEqual(cam(), before, 'the camera stayed'); assert.equal(coderCalls(), n0); assert.equal(ev('mapState.focus'), null, 'a click is not Focus');
  assert.ok(node('runner').classList.contains('sel')); assert.ok(insp().style.left && insp().style.top, 'placed beside the card, in screen space');
});

test('Expand = understand: description, properties, tags, folders, relations and files, in the same note', () => {
  page.click(btnOf(insp(), 'Expand')); assert.ok(insp().classList.contains('full'));
  const sections = [...insp().querySelectorAll('.insp-sec > summary')].map((s) => s.textContent.replace(/ \(\d+\)/, ''));
  for (const want of ['Properties', 'Tags', 'Folders', 'Relationships', 'Modify with Minion']) assert.ok(sections.includes(want), want);
  assert.match(insp().textContent, /Mobs · not filed \(automatic group\)/); assert.ok([...insp().querySelectorAll('.tag')].some((t) => /^Entity/.test(t.textContent)));
  page.click(btnOf(insp(), 'Collapse')); assert.ok(insp().classList.contains('quick'));
});

test('Modify = an explicit request: the button only opens the request; a coder is asked when the user sends their own words', async () => {
  const n0 = coderCalls(); page.click(btnOf(insp(), 'Modify with Minion'));
  const ta = insp().querySelector('textarea'); assert.ok(ta, 'the request box'); assert.equal(coderCalls(), n0, 'opening it sent nothing');
  page.click(btnOf(insp(), 'Send to a coder')); await page.waitFor(() => /Describe the change first/.test(page.toasts()), 'refused without words'); assert.equal(coderCalls(), n0);
  page.overrides['/api/project/infect/change'] = {card: 'runner', task: 'infect:CHANGE:runner:1'};
  ta.value = 'make it walk faster'; page.click(btnOf(insp(), 'Send to a coder')); await page.waitFor(() => posts('/change').length === 1, 'the request');
  assert.deepEqual({...posts('/change')[0].body}, {card: 'runner', request: 'make it walk faster'}, 'exactly the card and the words: no folder, no tag');
  await page.waitFor(dlgOpen); page.click(btnOf(dlg(), 'Cancel')); await page.waitFor(() => !dlgOpen()); assert.equal(posts('/dispatch').length, 0);
  delete page.overrides['/api/project/infect/change']; await page.idle(); frame();
});

test('a relation is a way to travel: following it moves the camera to the other feature, and Back returns', async () => {
  ev('openCard(lastProject, "runner")'); frame();
  const links = [...insp().querySelectorAll('.rel-list button.linklike')]; const link = links.find((b) => b.textContent === 'Infection'); assert.ok(link, 'the relation to Infection');
  const n0 = coderCalls(); page.click(link); await landed();
  assert.equal(ev('mapState.sel'), 'infection'); assert.ok(JSON.parse(open()).includes('auto:custom'), 'the camera entered Features'); assert.equal(page.$('#map-crumbs').textContent, 'Infectious Zombies›Features'); assert.ok(node('infection'));
  assert.equal(insp().querySelector('h3').textContent, 'Infection'); assert.ok(insp().classList.contains('quick'), 'inspected, not modified'); assert.equal(coderCalls(), n0);
  page.click(page.$('#map-back')); await landed(); assert.equal(ev('mapState.sel'), 'runner'); assert.ok(node('runner'), 'back at the Runner');
});

test('Focus = investigate: the feature and what it connects to, over the dimmed universe; leaving restores everything', async () => {
  ev('openCard(lastProject, "infection")'); frame(); page.click(btnOf(insp(), 'Collapse'));
  const before = {cam: cam(), open: open(), sel: ev('mapState.sel')}, n0 = coderCalls();
  page.click(btnOf(insp(), 'Focus')); await landed();
  assert.ok(!page.hidden('#map-focusbar')); assert.match(page.$('#map-focusbar').textContent, /^FOCUSInfection/);
  const shown = () => page.$$('#map-svg .layer-focus .node').map((n) => n.dataset.id).sort();
  assert.deepEqual(shown(), ['brute', 'infection', 'runner', 'spitter'], 'Direct: its immediate neighbours'); assert.ok(page.$('.layer-focus .node.center[data-id="infection"]'));
  assert.ok(page.$('.layer-cards').classList.contains('dimmed') && page.$('.layer-folders').classList.contains('dimmed'), 'the rest of the map is still there, subdued');
  assert.equal(btnOf(page.$('#map-focusbar'), 'Direct').getAttribute('aria-pressed'), 'true');
  page.click(btnOf(page.$('#map-focusbar'), 'Extended')); await landed(); assert.ok(shown().length > 4, 'Extended: one level more'); assert.ok(page.$('.layer-focus .node.far'));
  page.click(btnOf(page.$('#map-focusbar'), 'Custom')); await landed(); const depth = page.$('#map-focusbar .focus-depth'); assert.ok(depth, 'Custom: a depth');
  const all = shown().length; const inbound = [...page.$$('#map-focusbar .chk')].find((l) => /inbound/.test(l.textContent)).querySelector('input'); inbound.checked = false; inbound.dispatchEvent(new page.w.Event('change')); await landed();
  assert.ok(shown().length < all, 'without inbound relations there is less to show');
  inbound.checked = true; inbound.dispatchEvent(new page.w.Event('change')); await landed(); page.click(btnOf(page.$('#map-focusbar'), 'Direct')); await landed();
  tap(page.$('.layer-focus .node[data-id="runner"]')); frame(); assert.equal(insp().querySelector('h3').textContent, 'Runner', 'a connected feature can be inspected inside Focus');
  page.key(page.$('#map-wrap'), 'Escape'); assert.ok(page.hidden('#map-inspector'), 'Escape closes the note first'); assert.ok(ev('!!mapState.focus'));
  page.key(page.$('#map-wrap'), 'Escape'); frame();
  assert.equal(ev('mapState.focus'), null); assert.ok(page.hidden('#map-focusbar')); assert.equal(page.$$('.layer-focus .node').length, 0); assert.ok(!page.$('.layer-cards').classList.contains('dimmed'));
  assert.deepEqual({cam: cam(), open: open(), sel: ev('mapState.sel')}, before, 'the camera, the entered folders and the selection are exactly as before');
  assert.equal(coderCalls(), n0, 'Focus asked no coder for anything');
});

test('filters change what is seen and nothing else; the counter says how many', async () => {
  await universe(); page.click(page.$('#map-filter-btn')); const box = page.$('#map-filters'); assert.ok(!page.hidden('#map-filters'));
  const toggle = (label) => { const i = [...box.querySelectorAll('.chk')].find((l) => l.textContent.trim().startsWith(label)).querySelector('input'); i.checked = !i.checked; i.dispatchEvent(new page.w.Event('change')); frame(); };
  toggle('Vanilla resources'); assert.match(page.$('#map-count').textContent, /^8 \/ 11 features visible/); assert.match(page.$('#map-count').textContent, /3 hidden by filters/);
  assert.equal(folderEl('auto:vanilla') && folderEl('auto:vanilla').querySelector('.fcount').textContent, '3', 'the folder still holds its three features'); assert.equal(ev('mapState.index.cards.size'), 11);
  assert.equal(page.$('#map-filter-btn').textContent, 'Filters · 1');
  page.click(btnOf(box, 'Dim it')); frame(); assert.match(page.$('#map-count').textContent, /^8 \/ 11 features match/);
  page.click(btnOf(page.$('#map-count'), 'Reset filters')); frame(); assert.match(page.$('#map-count').textContent, /^11 \/ 11 features/); assert.equal(page.$('#map-filter-btn').textContent, 'Filters');
  page.click(page.$('#map-filter-btn')); assert.ok(page.hidden('#map-filters')); await page.idle();
});

test('search takes the camera to the result and highlights it; it never modifies or focuses', async () => {
  const input = page.$('#map-search'), n0 = coderCalls(); input.value = 'spit'; input.dispatchEvent(new page.w.Event('input'));
  const rows = page.$$('#map-results button.result'); assert.deepEqual(rows.map((r) => r.querySelector('.r-title').textContent), ['Spitter', 'Spitter acid spit']);
  assert.match(rows[0].querySelector('.r-where').textContent, /mob · Mobs/, 'each result says where it is');
  page.click(rows[0]); await landed();
  assert.equal(ev('mapState.sel'), 'spitter'); assert.ok(node('spitter')); assert.equal(open(), '["","auto:mob"]'); assert.ok(page.hidden('#map-results'));
  assert.ok(insp().classList.contains('quick')); assert.equal(ev('mapState.focus'), null); assert.equal(coderCalls(), n0);
  page.$('#map-scope').value = 'here'; input.value = 'infection'; input.dispatchEvent(new page.w.Event('input'));
  assert.match(page.$('#map-results').textContent, /Nothing in this folder matches/, 'scoped to the folder we are in'); input.value = ''; input.dispatchEvent(new page.w.Event('input')); page.$('#map-scope').value = 'all';
});

test('folders: create one, file a feature in it, see it counted; only the map\'s metadata is saved', async () => {
  await universe(); const n0 = coderCalls(), saves = posts('/map-meta').length;
  page.click(page.$('#map-new-folder')); await page.waitFor(dlgOpen, 'the name dialog'); assert.match(dlg().textContent, /never an instruction to a coder/);
  dlg().querySelector('input').value = 'Powerful Weapons'; page.click(btnOf(dlg(), 'Create')); await page.waitFor(() => folderEl('f-powerful-weapons') || (frame(), false), 'the new folder on the map');
  assert.equal(folderEl('f-powerful-weapons').querySelector('.fcount').textContent, '0', 'an empty folder is visible'); assert.ok(folderEl('f-powerful-weapons').classList.contains('empty'));
  await page.waitFor(() => posts('/map-meta').length > saves, 'the save'); assert.equal(posts('/map-meta').at(-1).body.meta.folders['f-powerful-weapons'].name, 'Powerful Weapons');
  ev('openCard(lastProject, "brute")'); frame(); const pick = insp().querySelector('select[aria-label="Folder"]'); pick.value = 'f-powerful-weapons'; page.click(btnOf(insp(), 'Move here')); frame();
  assert.equal(ev('mapState.tree.primaryOf.get("brute")'), 'f-powerful-weapons'); assert.match(insp().textContent, /Powerful Weapons · lives here/);
  await universe(); assert.equal(folderEl('f-powerful-weapons').querySelector('.fcount').textContent, '1'); assert.equal(folderEl('auto:mob').querySelector('.fcount').textContent, '2');
  assert.equal(ev('mapState.index.cards.size'), 11, 'still eleven features: nothing was duplicated'); assert.equal(coderCalls(), n0, 'organising asked no coder for anything');
  await page.waitFor(() => (posts('/map-meta').at(-1).body.meta.members.brute || [])[0] === 'f-powerful-weapons', 'the membership saved');
});

test('the organisation survives a reload, and the graph the server sends is unchanged', async () => {
  await page.idle(); const again = await loadPage(server);
  try {
    await again.eval('openProject("infect")'); again.click(again.$('.tab[data-tab="map"]')); await again.waitFor(() => again.eval('typeof mapState !== "undefined" && !!mapState.index'), 'the map again'); again.eval('MapView.frame()');
    const f = again.$('#map-svg .folder[data-fid="f-powerful-weapons"]'); assert.ok(f, 'the folder is back'); assert.equal(f.querySelector('.fname').textContent, 'Powerful Weapons'); assert.equal(f.querySelector('.fcount').textContent, '1');
    assert.equal(again.eval('mapState.index.cards.get("brute").description'), ev('mapState.index.cards.get("brute").description'));
    assert.equal(again.eval('JSON.stringify(mapState.data.cards.map((c) => Object.keys(c).sort()))').includes('folder'), false, 'no card carries a folder or a tag');
  } finally { await again.close(); }
});

test('dragging: inside its folder a card only changes place; dropped on another folder it is filed there', async () => {
  const P = (el, type, x, y) => { const e = new page.w.Event(type, {bubbles: true}); e.clientX = x; e.clientY = y; el.dispatchEvent(e); };
  const dragCard = (id, dx, dy) => { const n = node(id); P(n, 'pointerdown', 100, 100); P(n, 'pointermove', 100 + dx / 2, 100 + dy / 2); P(n, 'pointermove', 100 + dx, 100 + dy); P(n, 'pointerup', 100 + dx, 100 + dy); frame(); };
  const n0 = coderCalls();
  ev('MapView.reveal("runner", {instant: true}); mapState.sel = null; mapState.insp = null'); frame();
  dragCard('runner', 30, 20); assert.equal(ev('mapState.tree.primaryOf.get("runner")'), 'auto:mob', 'a short drag keeps it in its folder');
  assert.ok(ev('!!mapState.meta.pos["auto:mob"].runner'), 'and its new place is remembered'); assert.equal(ev('mapState.insp'), null, 'a drag is not a click');
  // put the Runner and the folder on screen together, then drop the card on the folder's dot
  ev('(() => { const n = mapState.lay.nodes.get("runner"), c = mapState.lay.folders.get("f-powerful-weapons"); mapState.cam = {cx: (n.x + c.x) / 2, cy: (n.y + c.y) / 2, k: 0.6}; })()'); frame();
  const [dx, dy] = JSON.parse(ev(`(() => { const n = mapState.lay.nodes.get("runner"), c = mapState.lay.folders.get("f-powerful-weapons"); return JSON.stringify([(c.x - n.x) * mapState.cam.k, (c.y - n.y) * mapState.cam.k]); })()`));
  dragCard('runner', dx, dy);
  assert.equal(ev('mapState.tree.primaryOf.get("runner")'), 'f-powerful-weapons'); assert.match(page.toasts(), /"Runner" filed in Powerful Weapons\. Only the map changed/);
  assert.equal(ev('mapState.index.cards.size'), 11); assert.equal(coderCalls(), n0, 'moving cards around asks no coder for anything');
  ev('MapView.setMeta(MapCore.unassign(mapState.meta, "runner", "f-powerful-weapons"))'); frame(); assert.equal(ev('mapState.tree.primaryOf.get("runner")'), 'auto:mob');
  await universe(); await page.idle();
});

test('deleting a folder deletes the folder: its features stay', async () => {
  tap(folderEl('f-powerful-weapons')); frame(); assert.equal(insp().querySelector('h3').textContent, 'Powerful Weapons'); assert.match(insp().textContent, /folder · manual/);
  page.click(btnOf(insp(), 'Expand')); page.click(btnOf(insp(), 'Delete')); await page.waitFor(dlgOpen); assert.match(dlg().textContent, /Its 1 feature stay in the mod/);
  page.click(btnOf(dlg(), 'Delete folder')); await page.waitFor(() => (frame(), !folderEl('f-powerful-weapons')), 'the folder to go');
  assert.equal(folderEl('f-powerful-weapons'), null); assert.equal(ev('mapState.tree.primaryOf.get("brute")'), 'auto:mob', 'the Brute is back with the other mobs');
  assert.equal(ev('mapState.index.cards.size'), 11); assert.equal(folderEl('auto:mob').querySelector('.fcount').textContent, '3'); await page.idle();
});

test('no native popup was used, and nothing here ever started an agent by itself', () => { assert.deepEqual(page.popups, []); assert.equal(posts('/dispatch').length, 0); });
