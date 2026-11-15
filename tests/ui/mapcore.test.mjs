import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import path from 'node:path';

// The Mod Map's logic on its own (no page, no server): what is filed where, where it sits, when a folder is entered, what a filter hides.
const C = createRequire(import.meta.url)(path.resolve(import.meta.dirname, '../../src/mod_orchestra/static/mapcore.js'));
const VP = {w: 1000, h: 600};

// A small firearms mod, the shape RTQ's `weponry` has: guns, their ammo, two systems, vanilla ingredients.
const weapons = () => {
  const cards = [{id: '__tab', kind: 'tab', title: 'Creative tab'}], edges = [];
  for (const g of ['ak47', 'm16', 'barrett', 'glock', 'rpg']) {
    cards.push({id: g, kind: 'item', title: g.toUpperCase(), description: `The ${g}.`}, {id: g + '_ammo', kind: 'item', title: g.toUpperCase() + ' Ammo'});
    edges.push({from: 'vanilla:minecraft:iron_ingot', to: g, kind: 'crafts', label: g}, {from: 'vanilla:minecraft:gunpowder', to: g + '_ammo', kind: 'crafts', label: g + '_ammo'},
               {from: g, to: 'ballistics', kind: 'uses'}, {from: g, to: 'ammo_use', kind: 'uses'}, {from: g + '_ammo', to: 'ammo_use', kind: 'uses'});
  }
  cards.push({id: 'ballistics', kind: 'custom', title: 'Firearm Ballistics', status: 'generated'}, {id: 'ammo_use', kind: 'custom', title: 'Ammo Consumption', status: 'generated'},
             {id: 'vanilla:minecraft:iron_ingot', kind: 'vanilla', title: 'iron_ingot'}, {id: 'vanilla:minecraft:gunpowder', kind: 'vanilla', title: 'gunpowder'});
  edges.push({from: 'ak47', to: 'ballistics', kind: 'uses'}, {from: 'ghost', to: 'ak47', kind: 'uses'}, {from: '__tab', to: 'ak47', kind: 'related'});   // a duplicate, a dangling one, the tab's
  return {cards, edges, edge_labels: {smelts_into: 'smelts into'}};
};
const world = (meta = C.emptyMeta(), data = weapons(), slots = {}) => {
  const index = C.buildIndex(data), inferred = C.inferTags(index), tree = C.buildTree(index, meta, inferred), lay = C.layout(tree, meta, slots, index);
  return {index, inferred, tree, lay, meta, slots};
};
const folderWith = (meta, name, parent, extra) => { const out = C.createFolder(meta, name, parent, extra); return [out.meta, out.id]; };

test('the index is the canonical graph: one record per feature, one per relation, nothing invented', () => {
  const {index} = world();
  assert.equal(index.cards.size, 14); assert.ok(!index.cards.has('__tab'));
  assert.equal(index.edges.length, 25, 'the duplicate edge is one edge');
  assert.deepEqual(index.dangling.map((e) => e.from), ['ghost'], 'a relation to something that is not a card is kept apart, not drawn');
  assert.equal(index.out.get('ak47').length, 2); assert.equal(index.inc.get('ammo_use').length, 10);
});

test('tags: inferred from what a feature is, corrected by the user, one spelling each', () => {
  const {index, inferred} = world(); let meta = C.emptyMeta();
  const names = (id) => C.tagsFor(id, inferred, meta).map((t) => t.tag + (t.inferred ? '' : '*'));
  assert.deepEqual(names('ak47'), ['Item', 'Craftable']); assert.deepEqual(names('vanilla:minecraft:iron_ingot'), ['Vanilla', 'Ingredient']);
  meta = C.addTag(meta, 'ak47', '  Ranged '); meta = C.addTag(meta, 'ak47', 'RANGED'); meta = C.addTag(meta, 'ak47', 'heavy   weapon');
  assert.deepEqual(names('ak47'), ['Item', 'Craftable', 'Ranged*', 'heavy weapon*'], 'the same tag in another case is not a second tag');
  meta = C.removeTag(meta, 'ak47', 'craftable', inferred); assert.deepEqual(names('ak47'), ['Item', 'Ranged*', 'heavy weapon*'], 'an inferred tag the user removed stays removed');
  assert.deepEqual(meta.tags.ak47.remove, ['craftable']);
  meta = C.removeTag(meta, 'ak47', 'Ranged', inferred); assert.deepEqual(names('ak47'), ['Item', 'heavy weapon*']);
  meta = C.addTag(meta, 'ak47', 'Craftable'); assert.deepEqual(names('ak47'), ['Item', 'heavy weapon*', 'Craftable*'], 'adding it back makes it the user\'s');
  assert.throws(() => C.addTag(meta, 'ak47', '   '));
  assert.equal(C.allTags(index, inferred, meta).get('item').count, 10);
});

test('with no folders, every feature is still reachable in the automatic group of its kind', () => {
  const {tree} = world();
  assert.deepEqual(tree.folders.get('').children, ['auto:custom', 'auto:item', 'auto:vanilla'].sort((a, b) => tree.folders.get(a).name < tree.folders.get(b).name ? -1 : 1));
  assert.equal(tree.folders.get('auto:item').total, 10); assert.equal(tree.folders.get('auto:item').name, 'Items'); assert.ok(tree.folders.get('auto:item').virtual);
  assert.equal(tree.folders.get('').total, 14, 'nothing is lost');
});

test('folders: the user\'s assignment wins, AUTO files by rule, SUGGEST only proposes, MANUAL takes nothing by itself', () => {
  let meta = C.emptyMeta(), weaponsId, ammoId, sysId, favId;
  [meta, weaponsId] = folderWith(meta, 'Weapons'); [meta, ammoId] = folderWith(meta, 'Ammunition', weaponsId); [meta, sysId] = folderWith(meta, 'Combat Systems'); [meta, favId] = folderWith(meta, 'Favourites');
  meta = C.setFolder(meta, weaponsId, {mode: 'auto', rules: {kinds: ['item']}}); meta = C.setFolder(meta, ammoId, {mode: 'auto', rules: {kinds: ['item'], words: ['ammo']}});
  meta = C.setFolder(meta, sysId, {mode: 'suggest', rules: {kinds: ['custom']}});
  let w = world(meta);
  assert.equal(w.tree.primaryOf.get('ak47_ammo'), ammoId, 'the most specific folder that matches is where it lives');
  assert.deepEqual(w.tree.foldersOf.get('ak47_ammo').map((m) => m.fid), [ammoId], 'being in Ammunition already puts it inside Weapons: the outer rule adds no second copy'); assert.equal(w.tree.folders.get(weaponsId).refs.length, 0);
  assert.equal(w.tree.primaryOf.get('ak47'), weaponsId); assert.equal(w.tree.folders.get(weaponsId).total, 10, 'a folder counts what is inside its subfolders');
  assert.equal(w.tree.primaryOf.get('ballistics'), 'auto:custom', 'SUGGEST places nothing'); assert.deepEqual(w.tree.suggestions.get(sysId), ['ammo_use', 'ballistics']);
  assert.equal(w.tree.folders.get(favId).total, 0, 'an empty folder exists'); assert.ok(w.tree.folders.get('').children.includes(favId));
  // the user moves the AK47 to Favourites: the rule must not pull it back, now or after the project is indexed again
  meta = C.assign(meta, 'ak47', favId, {from: weaponsId}); w = world(meta);
  assert.equal(w.tree.primaryOf.get('ak47'), favId); assert.deepEqual(w.tree.foldersOf.get('ak47').map((m) => m.fid), [favId]);
  assert.equal(world(meta, weapons()).tree.primaryOf.get('ak47'), favId, 're-indexing does not undo it');
  // accepting and dismissing suggestions
  meta = C.assign(meta, 'ballistics', sysId, {primary: true}); meta = C.dismissSuggestion(meta, 'ammo_use', sysId); w = world(meta);
  assert.equal(w.tree.primaryOf.get('ballistics'), sysId); assert.equal(w.tree.suggestions.has(sysId), false, 'a dismissed suggestion is not offered again');
  // one feature in two folders is one feature
  meta = C.assign(meta, 'ballistics', favId, {primary: false}); w = world(meta);
  assert.deepEqual(w.tree.foldersOf.get('ballistics').map((m) => m.fid), [sysId, favId]); assert.equal(w.tree.folders.get('').total, 14, 'still fourteen features');
  assert.ok(w.lay.nodes.has('ballistics') && w.lay.nodes.has('ballistics@' + favId)); assert.equal(w.lay.nodes.get('ballistics@' + favId).id, 'ballistics', 'the reference is the same card');
  assert.equal(w.index.cards.size, 14);
});

test('a feature created later is filed by the folder\'s rule (and that is all the rule does)', () => {
  let meta = C.emptyMeta(), id; [meta, id] = folderWith(meta, 'Weapons', null, {mode: 'auto', rules: {kinds: [], tags: [], words: ['sniper']}});
  assert.equal(world(meta).tree.folders.get(id).total, 0, 'empty for now');
  const data = weapons(); data.cards.push({id: 'sniper_x', kind: 'item', title: 'Sniper X'});
  const w = world(meta, data); assert.equal(w.tree.primaryOf.get('sniper_x'), id); assert.equal(w.tree.folders.get(id).total, 1);
  assert.deepEqual(data.cards.at(-1), {id: 'sniper_x', kind: 'item', title: 'Sniper X'}, 'the card itself is untouched');
});

test('deleting, renaming and nesting folders never loses a feature and never makes a loop', () => {
  let meta = C.emptyMeta(), a, b, c; [meta, a] = folderWith(meta, 'Weapons'); [meta, b] = folderWith(meta, 'Rifles', a); [meta, c] = folderWith(meta, 'Weapons');
  assert.notEqual(a, c, 'two folders may share a name; their ids differ');
  meta = C.assign(meta, 'ak47', b); meta = C.assign(meta, 'm16', a); meta = C.setPos(meta, b, 'ak47', 40, 50);
  assert.throws(() => C.moveFolder(meta, a, b), /inside itself/); assert.throws(() => C.moveFolder(meta, a, a), /inside itself/); assert.throws(() => C.createFolder(meta, '  '), /name/);
  meta = C.renameFolder(meta, b, 'Assault  Rifles'); assert.equal(meta.folders[b].name, 'Assault Rifles');
  const gone = C.deleteFolder(meta, a), w = world(gone);
  assert.equal(gone.folders[b].parent, null, 'its subfolder moves up'); assert.equal(w.tree.primaryOf.get('ak47'), b); assert.equal(w.tree.primaryOf.get('m16'), 'auto:item', 'its features go back to the automatic group');
  assert.equal(w.index.cards.size, 14); assert.equal(w.tree.folders.get('').total, 14);
  assert.equal(meta.folders[a].name, 'Weapons', 'operations return a new document; the old one is untouched');
  meta = C.moveFolder(meta, c, b); assert.equal(world(meta).tree.folders.get(c).depth, 3);
  const un = C.unassign(meta, 'ak47', b); assert.equal(un.members.ak47, undefined); assert.equal(un.pos[b].ak47, undefined);
});

test('layout: nothing overlaps, everything is inside its folder, and positions do not move unless something moved them', () => {
  let meta = C.emptyMeta(), wid, rid; [meta, wid] = folderWith(meta, 'Weapons', null, {mode: 'auto', rules: {kinds: ['item']}}); [meta, rid] = folderWith(meta, 'Rifles', wid);
  meta = C.assign(meta, 'ak47', rid); meta = C.assign(meta, 'm16', rid);
  const slots = {}, w = world(meta, weapons(), slots), at = (lay, key) => ({x: lay.nodes.get(key).x, y: lay.nodes.get(key).y});
  for (const [fid, list] of w.lay.byFolder) {
    const c = w.lay.folders.get(fid);
    for (let i = 0; i < list.length; i++) {
      assert.ok(Math.hypot(list[i].x - c.x, list[i].y - c.y) <= c.r, `${list[i].key} is inside ${fid || 'the root'}`);
      for (let j = i + 1; j < list.length; j++) assert.ok(Math.abs(list[i].x - list[j].x) >= C.NODE_W + 4 || Math.abs(list[i].y - list[j].y) >= C.NODE_H + 4, `${list[i].key} and ${list[j].key} do not overlap`);
    }
  }
  for (const f of w.tree.folders.values()) {
    const kids = f.children.map((id) => w.lay.folders.get(id)), me = w.lay.folders.get(f.id);
    kids.forEach((k, i) => { assert.ok(Math.hypot(k.x - me.x, k.y - me.y) + k.r <= me.r + 0.01, 'a subfolder is inside its parent'); for (const o of kids.slice(i + 1)) assert.ok(Math.hypot(k.x - o.x, k.y - o.y) >= k.r + o.r, 'siblings do not overlap'); });
  }
  const again = C.layout(w.tree, meta, slots, w.index); for (const key of w.lay.nodes.keys()) assert.deepEqual(at(again, key), at(w.lay, key), 'the same layout twice');
  // a new feature arrives: the ones already there in its folder keep their places
  const data = weapons(); data.cards.push({id: 'aa12', kind: 'item', title: 'AA12'});
  const w2 = world(meta, data, slots), base = w.lay.folders.get(wid), base2 = w2.lay.folders.get(wid);
  for (const n of w.lay.byFolder.get(wid)) assert.deepEqual({x: Math.round(w2.lay.nodes.get(n.key).x - base2.x), y: Math.round(w2.lay.nodes.get(n.key).y - base2.y)}, {x: Math.round(n.x - base.x), y: Math.round(n.y - base.y)}, n.key + ' did not move');
  // the user's own positions win, for cards and for folders
  const moved = C.setFolderPos(C.setPos(meta, rid, 'ak47', 500, -300), rid, 900, 0), w3 = world(moved, weapons(), slots), r3 = w3.lay.folders.get(rid), p3 = w3.lay.folders.get(wid);
  assert.deepEqual({x: Math.round(r3.x - p3.x), y: Math.round(r3.y - p3.y)}, {x: 900, y: 0}); assert.deepEqual({x: Math.round(w3.lay.nodes.get('ak47').x - r3.x), y: Math.round(w3.lay.nodes.get('ak47').y - r3.y)}, {x: 500, y: -300});
});

test('the camera: zooming keeps the point under the cursor, and a wild wheel is still one small step', () => {
  const cam = {cx: 100, cy: -50, k: 0.5}, before = C.toWorld(cam, VP, 700, 200), next = C.zoomAt(cam, VP, 1.4, 700, 200), after = C.toWorld(next, VP, 700, 200);
  assert.ok(Math.abs(before.x - after.x) < 1e-6 && Math.abs(before.y - after.y) < 1e-6);
  const s = C.toScreen(next, VP, after.x, after.y); assert.ok(Math.abs(s.x - 700) < 1e-6 && Math.abs(s.y - 200) < 1e-6);
  assert.ok(C.wheelFactor(-100) > 1 && C.wheelFactor(100) < 1); assert.equal(C.wheelFactor(-100000), C.wheelFactor(-240), 'clamped'); assert.ok(C.wheelFactor(-100000) < 1.6);
  assert.deepEqual([0.1, 0.4, 0.7, 1].map(C.lodOf), [0, 1, 2, 3], 'dot, dot with name, compact card, full card');
});

test('zoom is travel: a folder is entered by zooming INTO it, never by panning, and left with hysteresis', () => {
  let meta = C.emptyMeta(), wid, rid, mid; [meta, wid] = folderWith(meta, 'Weapons', null, {mode: 'auto', rules: {kinds: ['item']}}); [meta, rid] = folderWith(meta, 'Rifles', wid); [meta, mid] = folderWith(meta, 'Magic');
  meta = C.assign(meta, 'ak47', rid);
  const {tree, lay} = world(meta), open = new Set(['']), W = lay.folders.get(wid), R = lay.folders.get(rid), M = lay.folders.get(mid), short = 600;
  const enterK = (c) => (C.ENTER * short) / c.r, exitK = (c) => (C.EXIT * short) / c.r, cam = (c, k) => ({cx: c.x, cy: c.y, k});
  // far away: nothing is entered whatever we do
  assert.equal(C.updateOpen(open, tree, lay, cam(W, enterK(W) * 0.5), VP, W, 1), false); assert.deepEqual([...open], ['']);
  // close enough, but the camera only PANNED over it (no zoom direction): still not entered
  assert.equal(C.updateOpen(open, tree, lay, cam(W, enterK(W) * 1.2), VP, null, 0), false); assert.equal(C.updateOpen(open, tree, lay, cam(W, enterK(W) * 1.2), VP, W, 0), false);
  // zooming in, but the cursor is over empty space / over another folder: Weapons is not entered
  assert.equal(C.updateOpen(open, tree, lay, cam(W, enterK(W) * 1.2), VP, {x: W.x + W.r * 3 + 1e5, y: 0}, 1), false);
  C.updateOpen(open, tree, lay, cam(W, enterK(W) * 1.2), VP, M, 1); assert.ok(!open.has(wid), 'the folder nearest the camera is not entered when the zoom is aimed elsewhere');
  // zooming in on it: entered, one level at a time even when the zoom is already deep enough for the next
  const deep = cam(R, enterK(R) * 1.5); open.delete(mid);
  assert.equal(C.updateOpen(open, tree, lay, deep, VP, R, 1), true); assert.ok(open.has(wid) && !open.has(rid), 'one level per step');
  assert.equal(C.updateOpen(open, tree, lay, deep, VP, R, 1), true); assert.ok(open.has(rid));
  assert.equal(C.activeFolder(open, tree, lay, deep), rid); assert.deepEqual(C.pathOf(tree, rid).map((f) => f.name), ['Weapons', 'Rifles']);
  // hysteresis: between the two thresholds it stays as it is, in both directions
  const between = cam(R, (enterK(R) + exitK(R)) / 2);
  assert.equal(C.updateOpen(open, tree, lay, between, VP, R, -1), false); assert.ok(open.has(rid), 'zooming out a little does not leave');
  const fresh = new Set(['', wid]); assert.equal(C.updateOpen(fresh, tree, lay, between, VP, R, 1), false, 'and zooming in a little does not enter');
  // zooming out past the exit threshold leaves; leaving a folder leaves what is inside it
  C.updateOpen(open, tree, lay, cam(R, exitK(R) * 0.9), VP, R, -1); assert.ok(!open.has(rid) && open.has(wid));
  open.add(rid); C.updateOpen(open, tree, lay, cam(W, exitK(W) * 0.9), VP, W, -1); assert.deepEqual([...open], [''], 'back to the universe');
  // the accessible way in (Enter on a folder, search, a breadcrumb) opens the whole path
  C.openPath(open, tree, rid); assert.ok(open.has(wid) && open.has(rid));
  assert.ok(C.fitCircle(R, VP).k >= enterK(R), 'fitting a folder puts the camera inside it');
});

test('relations by scale: closed folders share one line that keeps every relation whole; entering splits it', () => {
  let meta = C.emptyMeta(), wid, sid; [meta, wid] = folderWith(meta, 'Weapons', null, {mode: 'auto', rules: {kinds: ['item']}}); [meta, sid] = folderWith(meta, 'Combat Systems', null, {mode: 'auto', rules: {kinds: ['custom']}});
  const {index, tree} = world(meta), open = new Set(['']);
  let b = C.bundles(index, tree, open); const key = (x) => (x.a.folder ?? 'n:' + x.a.node) + '>' + (x.b.folder ?? 'n:' + x.b.node);
  assert.deepEqual(b.map(key).sort(), ['auto:vanilla>' + wid, wid + '>' + sid].sort());
  const ws = b.find((x) => x.a.folder === wid); assert.equal(ws.edges.length, 15, 'fifteen relations travel as one line');
  assert.ok(ws.edges.every((e) => index.edges.includes(e) && e.kind === 'uses' && e.from && e.to), 'each keeps its source, target, direction and kind');
  assert.equal(b.reduce((n, x) => n + x.edges.length, 0), index.edges.length, 'no relation is dropped (none here is internal to one folder)');
  open.add(wid); b = C.bundles(index, tree, open);
  const ak = b.find((x) => x.a.node === 'ak47' && x.b.folder === sid); assert.equal(ak.edges.length, 2, 'from inside Weapons, the AK47 points at the closed Combat Systems folder');
  assert.deepEqual(C.repOf(tree, open, 'ballistics'), {folder: sid}); assert.deepEqual(C.repOf(tree, open, 'ak47'), {node: 'ak47'});
  open.add(sid); b = C.bundles(index, tree, open); assert.ok(b.find((x) => x.a.node === 'ak47' && x.b.node === 'ballistics'));
  const noRecipes = C.bundles(index, tree, open, (e) => e.kind !== 'crafts'); assert.ok(noRecipes.every((x) => x.edges.every((e) => e.kind !== 'crafts')));
});

test('filters hide, they never delete; turning recipes off takes the ingredients that only existed for them', () => {
  const {index, inferred} = world(), meta = C.emptyMeta(), f = C.noFilters();
  assert.equal(C.applyFilters(index, inferred, meta, f).active, false); assert.equal(C.applyFilters(index, inferred, meta, f).match.size, 14);
  f.rels = [...C.RECIPE_KINDS]; let r = C.applyFilters(index, inferred, meta, f);
  assert.ok(r.active); assert.equal(r.match.size, 12); assert.ok(!r.match.has('vanilla:minecraft:iron_ingot')); assert.ok(r.match.has('ak47'));
  assert.equal(r.edgeOk({kind: 'crafts'}), false); assert.equal(r.edgeOk({kind: 'uses'}), true);
  assert.equal(index.cards.size, 14); assert.equal(index.edges.length, 25, 'the graph is exactly what it was');
  f.rels = []; f.kinds = ['vanilla', 'custom']; assert.equal(C.applyFilters(index, inferred, meta, f).match.size, 10);
  f.kinds = []; f.tags = ['craftable', 'item']; assert.equal(C.applyFilters(index, inferred, meta, f).match.size, 10);
  f.tags = ['craftable', 'ranged']; assert.equal(C.applyFilters(index, inferred, C.addTag(meta, 'ak47', 'Ranged'), f).match.size, 1, 'every selected tag is required');
  assert.equal(C.applyFilters(index, inferred, meta, C.noFilters()).match.size, 14, 'and everything comes back');
});

test('search finds features, folders and tags, says where they are, and can stay inside a folder', () => {
  let meta = C.emptyMeta(), wid, rid; [meta, wid] = folderWith(meta, 'Weapons'); [meta, rid] = folderWith(meta, 'Rifles', wid);
  meta = C.assign(meta, 'ak47', rid); meta = C.addTag(meta, 'm16', 'Ranged');
  const {index, inferred, tree} = world(meta), find = (q, scope) => C.search(index, tree, inferred, meta, q, scope);
  assert.deepEqual(find('ak47').map((r) => r.id), ['ak47', 'ak47_ammo']); assert.equal(find('ak47')[0].where, 'Weapons / Rifles');
  assert.equal(find('ballis')[0].id, 'ballistics'); assert.equal(find('minecraft:gun')[0].id, 'vanilla:minecraft:gunpowder', 'by id');
  assert.deepEqual(find('rifl').map((r) => [r.type, r.id]), [['folder', rid]]); assert.deepEqual(find('#ranged').map((r) => r.id), ['m16']); assert.equal(find('ranged')[0].why, '#Ranged');
  assert.deepEqual(find('a', rid).map((r) => r.id), ['ak47'], 'scoped to a folder'); assert.deepEqual(find('ak', wid).map((r) => r.id), ['ak47'], 'and to what is inside its subfolders');
  assert.deepEqual(find(''), []); assert.deepEqual(find('zzz'), []);
});

test('focus: the features around one feature, by depth and direction, safe on cycles and bounded', () => {
  const {index} = world();
  let g = C.ego(index, 'ak47', {depth: 1});
  assert.deepEqual([...g.nodes.keys()].sort(), ['ak47', 'ammo_use', 'ballistics', 'vanilla:minecraft:iron_ingot']); assert.equal(g.nodes.get('ballistics').side, 'out'); assert.equal(g.nodes.get('vanilla:minecraft:iron_ingot').side, 'in');
  assert.ok(g.edges.every((e) => e.from === 'ak47' || e.to === 'ak47'), 'direct: only its own relations');
  g = C.ego(index, 'ak47', {depth: 2}); assert.equal(g.nodes.size, 13, 'extended reaches the neighbours\' neighbours (gunpowder is three steps away)'); assert.equal(g.nodes.get('m16').depth, 2); assert.equal(C.ego(index, 'ak47', {depth: 3}).nodes.size, 14);
  assert.deepEqual([...C.ego(index, 'ak47', {depth: 1, inbound: false}).nodes.keys()].sort(), ['ak47', 'ammo_use', 'ballistics']);
  assert.deepEqual([...C.ego(index, 'ak47', {depth: 3, edgeOk: (e) => e.kind !== 'uses'}).nodes.keys()].sort(), ['ak47', 'vanilla:minecraft:iron_ingot'].concat(['barrett', 'glock', 'm16', 'rpg']).sort());
  assert.deepEqual([...C.ego(index, 'ak47', {depth: 2, allowed: new Set(['ak47', 'ballistics'])}).nodes.keys()], ['ak47', 'ballistics']);
  const cut = C.ego(index, 'ak47', {depth: 5, limit: 6}); assert.equal(cut.nodes.size, 6); assert.equal(cut.truncated, true);
  const ring = C.buildIndex({cards: ['a', 'b', 'c'].map((id) => ({id, kind: 'item'})), edges: [{from: 'a', to: 'b', kind: 'uses'}, {from: 'b', to: 'c', kind: 'uses'}, {from: 'c', to: 'a', kind: 'uses'}, {from: 'a', to: 'a', kind: 'uses'}]});
  const loop = C.ego(ring, 'a', {depth: 50}); assert.equal(loop.nodes.size, 3, 'a cycle ends'); assert.equal(loop.nodes.get('b').side, 'out'); assert.equal(loop.nodes.get('c').side, 'in');
  const lay = C.focusLayout(C.ego(index, 'ak47', {depth: 2})), spots = new Set([...lay.pos.values()].map((p) => Math.round(p.x) + ',' + Math.round(p.y)));
  assert.equal(lay.pos.size, 13); assert.ok(lay.box.x0 < -300 && lay.box.x1 > 300); assert.ok(C.fitBox(lay.box, VP, 1.15).k <= 1.15); assert.equal(spots.size, 13, 'no two cards on the same spot'); assert.deepEqual(lay.pos.get('ak47'), {x: 0, y: 0});
  assert.ok(lay.pos.get('vanilla:minecraft:iron_ingot').x < 0 && lay.pos.get('ballistics').x > 0, 'what it is made from on the left, what it uses on the right');
});

test('labels never pile up: the important ones win', () => {
  const items = []; for (let i = 0; i < 300; i++) items.push({x: (i % 20) * 30, y: Math.floor(i / 20) * 6, w: 80, h: 14, pri: i === 150 ? 999 : i % 7});
  const kept = C.cullLabels(items, 400); assert.ok(kept.includes(items[150])); assert.ok(kept.length < 80);
  for (let i = 0; i < kept.length; i++) for (let j = i + 1; j < kept.length; j++) { const a = kept[i], b = kept[j]; assert.ok(a.x >= b.x + b.w || a.x + a.w <= b.x || a.y >= b.y + b.h || a.y + a.h <= b.y); }
  const name = {x: 0, y: 0, w: 200, h: 40}; assert.ok(C.cullLabels(items, 400, [name]).every((a) => a.x >= 200 || a.y >= 40), 'and none covers a folder\'s name');
  assert.ok(C.dotRadius(1000) < C.dotRadius(20) * 2 && C.dotRadius(1000) > C.dotRadius(20), 'a big folder is bigger, not overwhelming');
});

test('ten thousand features: built, filed, laid out and searched in well under a second each (measured, printed)', () => {
  const N = 10000, cards = [], edges = [], kinds = ['item', 'block', 'mob', 'custom', 'food'];
  for (let i = 0; i < N; i++) cards.push({id: 'c' + i, kind: kinds[i % 5], title: 'Feature ' + i});
  for (let i = 0; i < N * 2; i++) edges.push({from: 'c' + i % N, to: 'c' + (i * 37 + (i < N ? 11 : 5003)) % N, kind: ['crafts', 'uses', 'drops'][i % 3], label: 'r' + i});
  let meta = C.emptyMeta(); const ids = [];
  for (let i = 0; i < 40; i++) { let id; [meta, id] = folderWith(meta, 'Folder ' + i, i % 4 ? ids[i - 1] : null); ids.push(id); meta.folders[id].mode = 'auto'; meta.folders[id].rules = {kinds: [], tags: [], words: ['feature ' + i + '5']}; }   // deep nesting, rule-filed
  const time = (name, fn) => { const t = performance.now(), out = fn(), ms = performance.now() - t; console.log(`    ${name}: ${ms.toFixed(0)} ms`); assert.ok(ms < 3000, name + ' took ' + ms.toFixed(0) + ' ms'); return out; };
  const index = time('index 10,000 cards / 20,000 relations', () => C.buildIndex({cards, edges})), inferred = time('infer tags', () => C.inferTags(index));
  const tree = time('file into 40 nested rule folders + automatic groups', () => C.buildTree(index, meta, inferred)), slots = {};
  const lay = time('first layout', () => C.layout(tree, meta, slots, index)); time('layout again (cells remembered)', () => C.layout(tree, meta, slots, index));
  assert.equal(tree.folders.get('').total, N); assert.equal(lay.nodes.size >= N, true);
  const open = new Set(['']), far = time('relations at universe level', () => C.bundles(index, tree, open));
  assert.ok(far.length <= tree.folders.get('').children.length ** 2, `the universe shows ${far.length} lines for 20,000 relations`);
  assert.ok(tree.folders.get('').children.length <= 20, 'and a handful of dots for 10,000 features');
  for (const f of tree.folders.keys()) open.add(f); time('relations with every folder entered (worst case)', () => C.bundles(index, tree, open));
  assert.ok(time('search', () => C.search(index, tree, inferred, meta, 'feature 99', '')).length > 0);
  time('filter', () => C.applyFilters(index, inferred, meta, {kinds: ['mob'], rels: ['crafts'], tags: ['craftable'], mode: 'hide'}));
  const g = time('focus, depth 12 (bounded)', () => C.ego(index, 'c5', {depth: 12, limit: 400})); assert.equal(g.nodes.size, 400); assert.ok(g.truncated);
  const cam = C.fitCircle(lay.folders.get(''), VP); time('enter/leave decision', () => { for (let i = 0; i < 1000; i++) C.updateOpen(new Set(['']), tree, lay, cam, VP, {x: 0, y: 0}, 1); });
});
