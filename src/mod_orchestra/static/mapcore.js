"use strict";
// Mod Map 2.0 — the logic, with no DOM in it (mapview.js draws; tests/ui/mapcore.test.mjs runs this file on its own).
//
// One canonical graph (the cards and edges the server sends) and several ways of looking at it:
//   index   what exists and what connects to what
//   tree    where the USER filed each card (folders are view metadata; no file of the mod is ever touched)
//   layout  where everything sits in one world coordinate space (folders are circles inside their parent's circle)
//   open    which folders the camera has entered (decided by zoom, with hysteresis; never by panning)
// A card keeps the same id in every representation: a dot, a compact card, a full card, a reference in a second folder.
const MapCore = (() => {
  const VIRTUAL = "auto:";               // ids of the automatic groups for cards the user has not filed
  const ROOT = "";
  const NODE_W = 190, NODE_H = 54;       // a full card, in world units (1 world unit = 1 px at zoom 1)
  const CELL_W = 250, CELL_H = 96;       // the staggered grid features settle on inside a folder
  const K_MAX = 3;
  const LOD = { LABEL: 0.3, COMPACT: 0.55, FULL: 0.85 };   // zoom at which a feature dot gains a name, becomes a compact card, a full card
  const ENTER = 0.24, EXIT = 0.15;       // a folder is entered when its radius covers this share of the viewport's short side; left below EXIT
  const KIND_PLURAL = { item: "Items", block: "Blocks", mob: "Mobs", material: "Tool & armor sets", food: "Foods", custom: "Features", vanilla: "Vanilla resources" };
  const KIND_TAG = { item: "Item", block: "Block", mob: "Entity", material: "Gear", food: "Food", custom: "Feature", vanilla: "Vanilla" };
  const RECIPE_KINDS = ["crafts", "smelts_into"];

  const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1).replace(/_/g, " ") : s);
  const cleanTag = (t) => String(t == null ? "" : t).replace(/\s+/g, " ").trim().slice(0, 32).trim();
  const tagKey = (t) => cleanTag(t).toLowerCase();
  const clone = (o) => JSON.parse(JSON.stringify(o));
  function hash(str) { let h = 2166136261; for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); } return ((h >>> 0) % 100000) / 100000; }   // 0..1, the same for the same id
  const emptyMeta = () => ({ version: 1, folders: {}, members: {}, excluded: {}, tags: {}, fpos: {}, pos: {}, prefs: {} });
  function normMeta(m) { const out = emptyMeta(); for (const k of Object.keys(out)) if (m && m[k] != null && typeof m[k] === "object") out[k] = m[k]; return out; }

  // ---------- index: the canonical graph ----------
  function buildIndex(data) {
    const cards = new Map(), out = new Map(), inc = new Map(), edges = [], dangling = [], seen = new Set();
    for (const c of (data && data.cards) || []) if (c && c.id != null && c.kind !== "tab" && !cards.has(c.id)) { cards.set(c.id, c); out.set(c.id, []); inc.set(c.id, []); }
    for (const e of (data && data.edges) || []) {
      const key = e.from + "\u0001" + e.to + "\u0001" + e.kind + "\u0001" + (e.label || "");
      if (seen.has(key)) continue; seen.add(key);
      if (!cards.has(e.from) || !cards.has(e.to)) { if (e.from !== "__tab" && e.to !== "__tab") dangling.push(e); continue; }   // a relation to something that is not a card is kept apart, never drawn as real
      edges.push(e); out.get(e.from).push(e); inc.get(e.to).push(e);
    }
    const kinds = new Map(), rels = new Map();
    for (const c of cards.values()) kinds.set(c.kind, (kinds.get(c.kind) || 0) + 1);
    for (const e of edges) rels.set(e.kind, (rels.get(e.kind) || 0) + 1);
    return { cards, out, inc, edges, dangling, kinds, rels, labels: (data && data.edge_labels) || {} };
  }

  // ---------- tags: what a card IS (inferred from the graph, never guessed) plus what the user says ----------
  function inferTags(index) {
    const tags = new Map();
    for (const c of index.cards.values()) {
      const t = [KIND_TAG[c.kind] || cap(c.kind)];
      const inK = new Set(index.inc.get(c.id).map((e) => e.kind)), outK = new Set(index.out.get(c.id).map((e) => e.kind));
      if (inK.has("crafts")) t.push("Craftable");
      if (inK.has("smelts_into")) t.push("Smeltable");
      if (outK.has("crafts") || outK.has("smelts_into") || outK.has("made_of") || outK.has("repairs")) t.push("Ingredient");
      if (outK.has("drops") || outK.has("drops_on_death")) t.push("Drops loot");
      if (inK.has("drops") || inK.has("drops_on_death")) t.push("Loot");
      tags.set(c.id, t);
    }
    return tags;
  }
  // -> [{tag, inferred}] : inferred ones the user did not remove, then the user's own (an explicit tag equal to an inferred one makes it explicit)
  function tagsFor(id, inferred, meta) {
    const user = (meta.tags && meta.tags[id]) || {}, removed = new Set((user.remove || []).map(tagKey)), added = (user.add || []).map(cleanTag).filter(Boolean);
    const addedKeys = new Set(added.map(tagKey)), out = [], seen = new Set();
    for (const t of inferred.get(id) || []) if (!removed.has(tagKey(t)) && !addedKeys.has(tagKey(t)) && !seen.has(tagKey(t))) { seen.add(tagKey(t)); out.push({ tag: t, inferred: true }); }
    for (const t of added) if (!seen.has(tagKey(t))) { seen.add(tagKey(t)); out.push({ tag: t, inferred: false }); }
    return out;
  }
  function allTags(index, inferred, meta) {
    const map = new Map();
    for (const id of index.cards.keys()) for (const t of tagsFor(id, inferred, meta)) { const k = tagKey(t.tag), cur = map.get(k); if (cur) cur.count++; else map.set(k, { tag: t.tag, count: 1 }); }
    return map;
  }

  // ---------- folders ----------
  const hasRules = (r) => !!(r && ((r.kinds || []).length || (r.tags || []).length || (r.words || []).length));
  // Every kind of rule that is filled in must match (kind AND tag AND word); inside one kind of rule any value is enough.
  function matchRules(card, tagKeys, rules) {
    if (!hasRules(rules)) return false;
    if ((rules.kinds || []).length && !rules.kinds.includes(card.kind)) return false;
    if ((rules.tags || []).length && !rules.tags.some((t) => tagKeys.has(tagKey(t)))) return false;
    if ((rules.words || []).length) { const hay = ((card.title || "") + " " + card.id).toLowerCase(); if (!rules.words.some((w) => hay.includes(tagKey(w)))) return false; }
    return true;
  }
  function depthOf(folders, fid) { let d = 0, cur = folders[fid]; const seen = new Set(); while (cur && cur.parent && !seen.has(cur.id)) { seen.add(cur.id); cur = folders[cur.parent]; d++; } return d; }

  // Where every card is shown. Priority: (1) the user's own assignments, (2) AUTO folders whose rules match, (3) the automatic group of its kind.
  // SUGGEST folders never place anything: their matches come back as `suggestions` for the user to accept or dismiss.
  function buildTree(index, meta, inferred) {
    meta = normMeta(meta);
    const folders = new Map();
    const add = (f) => { folders.set(f.id, Object.assign({ children: [], features: [], refs: [], total: 0, depth: 0, virtual: false }, f)); return folders.get(f.id); };
    add({ id: ROOT, name: "", parent: null, mode: "manual", rules: {} });
    for (const f of Object.values(meta.folders)) add({ id: f.id, name: f.name, parent: f.parent && meta.folders[f.parent] ? f.parent : ROOT, mode: f.mode || "manual", rules: f.rules || {}, order: f.order || 0 });
    const ruled = Object.values(meta.folders).filter((f) => f.mode !== "manual" && hasRules(f.rules))
      .sort((a, b) => depthOf(meta.folders, b.id) - depthOf(meta.folders, a.id) || (a.order || 0) - (b.order || 0) || (a.id < b.id ? -1 : 1));   // the most specific folder first
    const primaryOf = new Map(), foldersOf = new Map(), suggestions = new Map();
    for (const c of index.cards.values()) {
      const user = ((meta.members[c.id]) || []).filter((fid) => folders.has(fid) && fid !== ROOT), excluded = new Set(meta.excluded[c.id] || []);
      const list = user.map((fid) => ({ fid, how: "user" }));
      if (ruled.length) {
        let keys = null;
        for (const f of ruled) {
          if (excluded.has(f.id) || user.includes(f.id)) continue;
          if (!keys) keys = new Set(tagsFor(c.id, inferred, meta).map((t) => tagKey(t.tag)));
          if (!matchRules(c, keys, f.rules)) continue;
          if (f.mode === "auto") list.push({ fid: f.id, how: "auto" });
          else { if (!suggestions.has(f.id)) suggestions.set(f.id, []); suggestions.get(f.id).push(c.id); }
        }
      }
      if (list.length > 1) {                                    // a card inside Rifles is already inside Weapons: the rule of an outer folder adds nothing
        const inner = new Set(); for (const m of list) for (let cur = folders.get(m.fid).parent; cur && cur !== ROOT; cur = folders.get(cur).parent) inner.add(cur);
        for (let i = list.length - 1; i >= 0; i--) if (list[i].how !== "user" && inner.has(list[i].fid)) list.splice(i, 1);
      }
      if (!list.length) {
        const vid = VIRTUAL + c.kind;
        if (!folders.has(vid)) add({ id: vid, name: KIND_PLURAL[c.kind] || cap(c.kind) + "s", parent: ROOT, mode: "auto", rules: { kinds: [c.kind] }, virtual: true, order: 1e6 });
        list.push({ fid: vid, how: "unfiled" });
      }
      primaryOf.set(c.id, list[0].fid); foldersOf.set(c.id, list);
      folders.get(list[0].fid).features.push(c.id);
      for (let i = 1; i < list.length; i++) folders.get(list[i].fid).refs.push(c.id);
    }
    for (const list of suggestions.values()) list.sort();
    for (const f of folders.values()) if (f.id !== ROOT) folders.get(f.parent).children.push(f.id);
    const byOrder = (a, b) => { const A = folders.get(a), B = folders.get(b); return (A.order || 0) - (B.order || 0) || (A.name.toLowerCase() < B.name.toLowerCase() ? -1 : A.name.toLowerCase() > B.name.toLowerCase() ? 1 : a < b ? -1 : 1); };
    const post = [];
    (function walk(fid, depth) { const f = folders.get(fid); f.depth = depth; f.children.sort(byOrder); for (const c of f.children) walk(c, depth + 1); post.push(fid); })(ROOT, 0);
    for (const fid of post) { const f = folders.get(fid); f.features.sort(); f.refs.sort(); f.total = f.features.length + f.children.reduce((n, c) => n + folders.get(c).total, 0); }
    return { folders, primaryOf, foldersOf, suggestions, post };
  }
  function pathOf(tree, fid) { const out = []; let f = tree.folders.get(fid); while (f && f.id !== ROOT) { out.unshift(f); f = tree.folders.get(f.parent); } return out; }
  const pathLabel = (tree, fid) => pathOf(tree, fid).map((f) => f.name).join(" / ");
  function descendants(tree, fid) { const out = new Set([fid]); (function walk(id) { for (const c of tree.folders.get(id).children) { out.add(c); walk(c); } })(fid); return out; }

  // ---------- operations on the metadata (each returns a NEW document; none touches a card or a file) ----------
  const isVirtual = (fid) => typeof fid === "string" && fid.startsWith(VIRTUAL);
  function newFolderId(meta, name) {
    const base = "f-" + (String(name).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40) || "folder");
    let id = base, n = 2; while (meta.folders[id]) id = base + "-" + n++;
    return id;
  }
  function createFolder(meta, name, parent, extra) {
    const m = clone(normMeta(meta)); name = String(name || "").replace(/\s+/g, " ").trim().slice(0, 60);
    if (!name) throw new Error("A folder needs a name");
    if (parent && !m.folders[parent]) throw new Error("That parent folder does not exist");
    const id = newFolderId(m, name), order = 1 + Math.max(0, ...Object.values(m.folders).map((f) => f.order || 0));
    m.folders[id] = Object.assign({ id, name, parent: parent || null, mode: "manual", rules: { kinds: [], tags: [], words: [] }, order }, extra || {});
    return { meta: m, id };
  }
  function renameFolder(meta, fid, name) { const m = clone(meta); name = String(name || "").replace(/\s+/g, " ").trim().slice(0, 60); if (!name) throw new Error("A folder needs a name"); if (!m.folders[fid]) throw new Error("No such folder"); m.folders[fid].name = name; return m; }
  // Deleting a folder deletes the folder: its cards stay in the mod (they fall back to another of their folders or to the automatic group), its subfolders move up.
  function deleteFolder(meta, fid) {
    const m = clone(meta); const f = m.folders[fid]; if (!f) throw new Error("No such folder");
    for (const c of Object.values(m.folders)) if (c.parent === fid) c.parent = f.parent || null;
    delete m.folders[fid]; delete m.fpos[fid]; delete m.pos[fid];
    for (const key of ["members", "excluded"]) for (const [card, list] of Object.entries(m[key])) { const keep = list.filter((x) => x !== fid); if (keep.length) m[key][card] = keep; else delete m[key][card]; }
    return m;
  }
  function moveFolder(meta, fid, parent) {
    const m = clone(meta); if (!m.folders[fid]) throw new Error("No such folder"); parent = parent || null;
    if (parent && !m.folders[parent]) throw new Error("That parent folder does not exist");
    for (let cur = parent, guard = 0; cur && guard < 100; cur = m.folders[cur].parent, guard++) if (cur === fid) throw new Error("A folder cannot go inside itself");
    m.folders[fid].parent = parent; delete m.fpos[fid];
    return m;
  }
  function setFolder(meta, fid, patch) { const m = clone(meta); if (!m.folders[fid]) throw new Error("No such folder"); if (patch.mode) m.folders[fid].mode = patch.mode; if (patch.rules) m.folders[fid].rules = { kinds: patch.rules.kinds || [], tags: (patch.rules.tags || []).map(cleanTag).filter(Boolean), words: (patch.rules.words || []).map(cleanTag).filter(Boolean) }; return m; }
  const without = (list, x) => (list || []).filter((v) => v !== x);
  // File a card in a folder. `from` set: it moves (that membership is replaced). `primary`: the folder becomes where the card lives.
  function assign(meta, card, fid, opts) {
    const m = clone(meta), o = opts || {}; if (!m.folders[fid]) throw new Error("No such folder");
    let list = without(m.members[card], fid);
    if (o.from) { list = without(list, o.from); if (!isVirtual(o.from) && m.folders[o.from] && m.folders[o.from].mode !== "manual") m.excluded[card] = [...new Set([...(m.excluded[card] || []), o.from])]; if (m.pos[o.from]) delete m.pos[o.from][card]; }
    if (o.primary === false) list.push(fid); else list.unshift(fid);
    m.members[card] = list;
    if (m.excluded[card]) { const keep = without(m.excluded[card], fid); if (keep.length) m.excluded[card] = keep; else delete m.excluded[card]; }
    return m;
  }
  // Take a card out of a folder. If the folder would put it back by rule, remember the user's "no" so re-indexing never undoes it.
  function unassign(meta, card, fid) {
    const m = clone(meta); const keep = without(m.members[card], fid);
    if (keep.length) m.members[card] = keep; else delete m.members[card];
    if (m.folders[fid] && m.folders[fid].mode !== "manual") m.excluded[card] = [...new Set([...(m.excluded[card] || []), fid])];
    if (m.pos[fid]) delete m.pos[fid][card];
    return m;
  }
  const dismissSuggestion = (meta, card, fid) => { const m = clone(meta); m.excluded[card] = [...new Set([...(m.excluded[card] || []), fid])]; return m; };
  function addTag(meta, card, tag) {
    const m = clone(meta), t = cleanTag(tag); if (!t) throw new Error("A tag needs a name");
    const cur = m.tags[card] || { add: [], remove: [] };
    cur.remove = (cur.remove || []).filter((x) => tagKey(x) !== tagKey(t));
    if (!(cur.add || []).some((x) => tagKey(x) === tagKey(t))) cur.add = [...(cur.add || []), t];
    m.tags[card] = cur; return m;
  }
  function removeTag(meta, card, tag, inferred) {
    const m = clone(meta), k = tagKey(tag), cur = m.tags[card] || { add: [], remove: [] };
    cur.add = (cur.add || []).filter((x) => tagKey(x) !== k);
    if ((inferred.get(card) || []).some((x) => tagKey(x) === k) && !(cur.remove || []).some((x) => tagKey(x) === k)) cur.remove = [...(cur.remove || []), cleanTag(tag)];
    if (cur.add.length || (cur.remove || []).length) m.tags[card] = cur; else delete m.tags[card];
    return m;
  }
  function setPos(meta, fid, card, x, y) { const m = clone(meta); (m.pos[fid] = m.pos[fid] || {})[card] = { x: Math.round(x * 10) / 10, y: Math.round(y * 10) / 10 }; return m; }
  function setFolderPos(meta, fid, x, y) { const m = clone(meta); m.fpos[fid] = { x: Math.round(x * 10) / 10, y: Math.round(y * 10) / 10 }; return m; }

  // ---------- layout: one world space, computed bottom-up (sizes) then top-down (positions) ----------
  // Features settle on a staggered grid, nearest cells first, each with a small offset that depends only on its id: a constellation, but the same one every time.
  // `slots` remembers which cell each card took, so adding a card never reshuffles the others. The user's own positions always win.
  function cellsFor(n) {
    const R = Math.sqrt((n + 4) * CELL_W * CELL_H / Math.PI) * 1.2 + CELL_W, cells = [];
    const J = Math.ceil(R / CELL_H) + 1, I = Math.ceil(R / CELL_W) + 1;
    for (let j = -J; j <= J; j++) for (let i = -I; i <= I; i++) { const x = (i + (j & 1 ? 0.5 : 0)) * CELL_W, y = j * CELL_H, d = x * x + y * y; if (d <= R * R) cells.push({ i, j, x, y, d }); }
    cells.sort((a, b) => a.d - b.d || a.j - b.j || a.i - b.i);
    return cells;
  }
  function layout(tree, meta, slots, index) {
    meta = normMeta(meta); slots = slots || {};
    const local = new Map();
    for (const fid of tree.post) {
      const f = tree.folders.get(fid), manual = meta.pos[fid] || {}, mine = slots[fid] || (slots[fid] = {});
      const items = f.features.map((id) => ({ id, key: id })).concat(f.refs.map((id) => ({ id, key: id + "@" + fid, ref: true })));
      const feat = new Map(), taken = new Set(), present = new Set(items.map((it) => it.id));
      for (const id of Object.keys(mine)) if (!present.has(id) || manual[id]) delete mine[id];
      for (const [id, p] of Object.entries(manual)) {          // cells under a hand-placed card are not offered to anyone else
        if (!present.has(id)) continue; const j = Math.round(p.y / CELL_H), i = Math.round(p.x / CELL_W - (j & 1 ? 0.5 : 0));
        for (let dj = -1; dj <= 1; dj++) for (let di = -1; di <= 1; di++) taken.add((i + di) + "," + (j + dj));
      }
      for (const cell of Object.values(mine)) taken.add(cell);
      const waiting = items.filter((it) => !manual[it.id] && !mine[it.id]);
      if (waiting.length) {
        if (index) waiting.sort((a, b) => { const A = index.cards.get(a.id), B = index.cards.get(b.id); return (A.kind < B.kind ? -1 : A.kind > B.kind ? 1 : 0) || (a.id < b.id ? -1 : 1); });
        const cells = cellsFor(items.length + taken.size); let ci = 0;
        for (const it of waiting) { while (ci < cells.length && taken.has(cells[ci].i + "," + cells[ci].j)) ci++; const c = cells[ci] || { i: ci, j: 0 }; const key = c.i + "," + c.j; taken.add(key); mine[it.id] = key; }
      }
      let featR = 0;
      for (const it of items) {
        let x, y;
        if (manual[it.id]) { x = manual[it.id].x; y = manual[it.id].y; }
        else { const [i, j] = mine[it.id].split(",").map(Number); x = (i + (j & 1 ? 0.5 : 0)) * CELL_W + (hash(it.id) - 0.5) * 36; y = j * CELL_H + (hash(it.id + "y") - 0.5) * 20; }
        feat.set(it.key, { id: it.id, ref: !!it.ref, x, y }); featR = Math.max(featR, Math.hypot(x, y) + 135);
      }
      // subfolders: circles packed around the features, the user's own positions first
      const kids = new Map(), placed = []; let r = featR;
      const clear = (x, y, rad) => placed.every((p) => Math.hypot(p.x - x, p.y - y) >= p.r + rad + Math.max(60, 0.12 * Math.min(p.r, rad)));
      for (const cid of f.children) if (meta.fpos[cid]) { const p = { x: meta.fpos[cid].x, y: meta.fpos[cid].y, r: local.get(cid).r }; kids.set(cid, p); placed.push(p); }
      let turn = 0; const start = hash(fid || "root") * Math.PI * 2;
      for (const cid of f.children) {
        if (kids.has(cid)) continue;                              // each next folder starts a golden angle further round, so they spread instead of lining up
        const rad = local.get(cid).r, base = featR > 0 ? featR + 70 + rad : 0, a0 = start + turn++ * 2.399963, step = Math.max(60, rad * 0.35); let spot = null;
        if (base === 0 && clear(0, 0, rad)) spot = { x: 0, y: 0 };
        for (let ring = 0; !spot && ring < 400; ring++) {
          const dist = Math.max(base, rad + 60) + ring * step, n = Math.max(8, Math.floor(2 * Math.PI * dist / Math.max(40, rad * 0.8)));
          for (let q = 0; q < n && !spot; q++) { const a = a0 + q * 2 * Math.PI / n, x = Math.cos(a) * dist, y = Math.sin(a) * dist * 0.82; if (Math.hypot(x, y) >= base && clear(x, y, rad)) spot = { x, y }; }
        }
        const p = { x: spot ? spot.x : 0, y: spot ? spot.y : 0, r: rad }; kids.set(cid, p); placed.push(p);
      }
      for (const p of placed) r = Math.max(r, Math.hypot(p.x, p.y) + p.r);
      local.set(fid, { r: Math.max(170, r + 70), feat, kids });
    }
    const folders = new Map(), nodes = new Map(), byFolder = new Map();
    (function place(fid, x, y) {
      const l = local.get(fid); folders.set(fid, { x, y, r: l.r }); const list = [];
      for (const [key, p] of l.feat) { const n = { key, id: p.id, fid, ref: p.ref, x: x + p.x, y: y + p.y }; nodes.set(key, n); list.push(n); }
      byFolder.set(fid, list);
      for (const [cid, p] of l.kids) place(cid, x + p.x, y + p.y);
    })(ROOT, 0, 0);
    return { folders, nodes, byFolder };
  }

  // ---------- camera: screen = (world - c) * k + viewport/2 ----------
  const toScreen = (cam, vp, x, y) => ({ x: (x - cam.cx) * cam.k + vp.w / 2, y: (y - cam.cy) * cam.k + vp.h / 2 });
  const toWorld = (cam, vp, sx, sy) => ({ x: (sx - vp.w / 2) / cam.k + cam.cx, y: (sy - vp.h / 2) / cam.k + cam.cy });
  // Zoom keeping the world point under (sx, sy) where it is.
  function zoomAt(cam, vp, k, sx, sy) { const w = toWorld(cam, vp, sx, sy); return { k, cx: w.x - (sx - vp.w / 2) / k, cy: w.y - (sy - vp.h / 2) / k }; }
  function fitBox(b, vp, kMax) { return { cx: (b.x0 + b.x1) / 2, cy: (b.y0 + b.y1) / 2, k: Math.min(kMax || K_MAX, (vp.w * 0.84) / Math.max(1, b.x1 - b.x0), (vp.h * 0.7) / Math.max(1, b.y1 - b.y0)) }; }
  function fitCircle(c, vp, share) { const k = Math.min(K_MAX, (Math.min(vp.w, vp.h) * (share || 0.46)) / Math.max(1, c.r)); return { cx: c.x, cy: c.y, k }; }
  const minZoom = (lay, vp) => fitCircle(lay.folders.get(ROOT), vp).k * 0.6;
  // One wheel notch is one small step however large the device says the gesture was, so a flick cannot jump several levels.
  function wheelFactor(deltaY, pinch) { const d = Math.max(-240, Math.min(240, deltaY)); return Math.exp(-d * (pinch ? 0.01 : 0.0018)); }
  const lodOf = (k) => (k >= LOD.FULL ? 3 : k >= LOD.COMPACT ? 2 : k >= LOD.LABEL ? 1 : 0);

  // ---------- which folders the camera is inside ----------
  // Entering needs intent: the camera zooms IN and the point it zooms toward is inside the folder, which by then is large on screen.
  // Leaving is the inverse with a lower threshold (hysteresis), so a folder near the limit does not flicker. Panning calls neither.
  // One level per call. Returns true when `open` changed.
  function updateOpen(open, tree, lay, cam, vp, anchor, dir) {
    const short = Math.min(vp.w, vp.h); let changed = false;
    for (const fid of [...open]) {
      if (fid === ROOT) continue; const f = tree.folders.get(fid), c = lay.folders.get(fid);
      if (!f || !c || !open.has(f.parent) || c.r * cam.k < EXIT * short) { open.delete(fid); changed = true; }
    }
    if (changed) for (const fid of [...open]) { const f = tree.folders.get(fid); if (fid !== ROOT && (!f || !open.has(f.parent))) open.delete(fid); }   // a closed folder closes what is inside it
    if (dir > 0 && anchor) {
      let cur = ROOT;
      for (let guard = 0; guard < 64; guard++) {
        const next = tree.folders.get(cur).children.find((cid) => { const c = lay.folders.get(cid); return Math.hypot(anchor.x - c.x, anchor.y - c.y) <= c.r; });
        if (!next) break;
        if (open.has(next)) { cur = next; continue; }
        if (lay.folders.get(next).r * cam.k >= ENTER * short) { open.add(next); changed = true; }
        break;
      }
    }
    return changed;
  }
  function openPath(open, tree, fid) { for (const f of pathOf(tree, fid)) open.add(f.id); open.add(ROOT); }
  // The region the user is in: the deepest entered folder under the centre of the screen (what the breadcrumb says).
  function activeFolder(open, tree, lay, cam) {
    let cur = ROOT;
    for (let guard = 0; guard < 64; guard++) {
      const next = tree.folders.get(cur).children.find((cid) => { const c = lay.folders.get(cid); return open.has(cid) && Math.hypot(cam.cx - c.x, cam.cy - c.y) <= c.r; });
      if (!next) break; cur = next;
    }
    return cur;
  }
  // What stands for a card on screen right now: the card itself, or the outermost folder on its path that is not entered.
  function repOf(tree, open, id) {
    const path = pathOf(tree, tree.primaryOf.get(id));
    for (const f of path) if (!open.has(f.id)) return { folder: f.id };
    return { node: id };
  }

  // ---------- relations by scale ----------
  // Every edge is drawn between what currently stands for its two ends. Edges that end up between the same two things travel as one bundle;
  // the bundle keeps each edge whole (source, target, direction, kind), it only shares the line.
  function bundles(index, tree, open, edgeOk) {
    const map = new Map(), reps = new Map();
    const rep = (id) => { let r = reps.get(id); if (!r) { r = repOf(tree, open, id); reps.set(id, r); } return r; };
    for (const e of index.edges) {
      if (edgeOk && !edgeOk(e)) continue;
      const a = rep(e.from), b = rep(e.to), ak = a.node != null ? "n:" + a.node : "f:" + a.folder, bk = b.node != null ? "n:" + b.node : "f:" + b.folder;
      if (ak === bk) continue;                                  // both ends are inside the same closed folder
      const key = ak + "\u0001" + bk; let bun = map.get(key);
      if (!bun) { bun = { key, a, b, edges: [] }; map.set(key, bun); }
      bun.edges.push(e);
    }
    return [...map.values()];
  }

  // ---------- filters ----------
  // f = {kinds: hidden card kinds, rels: hidden relation kinds, tags: tag keys a card must ALL have, mode: "dim" | "hide"}
  const noFilters = () => ({ kinds: [], rels: [], tags: [], mode: "hide" });
  const filtersActive = (f) => !!(f && (f.kinds.length || f.rels.length || f.tags.length));
  function applyFilters(index, inferred, meta, f) {
    const hiddenK = new Set(f.kinds), hiddenR = new Set(f.rels), need = f.tags.map(tagKey), match = new Set();
    const edgeOk = (e) => !hiddenR.has(e.kind);
    for (const c of index.cards.values()) {
      if (hiddenK.has(c.kind)) continue;
      if (need.length) { const keys = new Set(tagsFor(c.id, inferred, meta).map((t) => tagKey(t.tag))); if (!need.every((k) => keys.has(k))) continue; }
      if (hiddenR.size && c.kind === "vanilla") {               // a vanilla resource that only existed for hidden relations goes with them
        const all = index.out.get(c.id).concat(index.inc.get(c.id)); if (all.length && !all.some(edgeOk)) continue;
      }
      match.add(c.id);
    }
    return { match, edgeOk, active: filtersActive(f), total: index.cards.size };
  }

  // ---------- search ----------
  function search(index, tree, inferred, meta, query, scope) {
    let q = String(query || "").trim().toLowerCase(); if (!q) return [];
    const tagOnly = q.startsWith("#"); if (tagOnly) q = q.slice(1).trim(); if (!q) return [];
    const within = scope && scope !== ROOT ? descendants(tree, scope) : null, out = [];
    for (const c of index.cards.values()) {
      const fid = tree.primaryOf.get(c.id);
      if (within && !tree.foldersOf.get(c.id).some((m) => within.has(m.fid))) continue;
      const title = (c.title || c.id).toLowerCase(), id = String(c.id).toLowerCase(); let score = -1, why = "";
      if (!tagOnly) {
        if (title === q || id === q) score = 0; else if (title.startsWith(q)) score = 1; else if (title.split(/[\s_\-:]+/).some((w) => w.startsWith(q))) score = 2;
        else if (title.includes(q)) score = 3; else if (id.includes(q)) { score = 4; why = c.id; } else if (c.kind.toLowerCase().includes(q) || (KIND_PLURAL[c.kind] || "").toLowerCase().includes(q)) { score = 6; why = c.kind; }
      }
      if (score < 0 || score > 4) { const t = tagsFor(c.id, inferred, meta).find((x) => tagKey(x.tag).includes(q)); if (t && (score < 0 || score > 5)) { score = 5; why = "#" + t.tag; } }
      if (score < 0 && !tagOnly && (c.description || "").toLowerCase().includes(q)) { score = 7; why = "description"; }
      if (score >= 0) out.push({ type: "feature", id: c.id, title: c.title || c.id, kind: c.kind, where: pathLabel(tree, fid), why, score });
    }
    if (!tagOnly) for (const f of tree.folders.values()) {
      if (f.id === ROOT || (within && !within.has(f.id))) continue; const name = f.name.toLowerCase();
      if (name.includes(q)) out.push({ type: "folder", id: f.id, title: f.name, kind: "folder", where: pathLabel(tree, f.parent), why: f.total + " features", score: name.startsWith(q) ? 0.5 : 3.5 });
    }
    out.sort((a, b) => a.score - b.score || (a.title.toLowerCase() < b.title.toLowerCase() ? -1 : 1));
    return out.slice(0, 40);
  }

  // ---------- focus: the graph around one card ----------
  // Breadth-first from the card; a visited set makes cycles harmless. `limit` stops an explosion and says so (`truncated`).
  // o = {depth, inbound, outbound, edgeOk, nodeOk, sameFolderOnly: Set of allowed ids or null, limit}
  function ego(index, id, o) {
    const depth = Math.max(1, o.depth || 1), limit = o.limit || 400, nodes = new Map([[id, { id, depth: 0, side: "center" }]]), edges = [], seenE = new Set();
    let frontier = [id], truncated = false;
    for (let d = 1; d <= depth && frontier.length; d++) {
      const next = [];
      for (const cur of frontier) {
        const side = nodes.get(cur).side, steps = [];
        if (o.outbound !== false) for (const e of index.out.get(cur) || []) steps.push([e, e.to, "out"]);
        if (o.inbound !== false) for (const e of index.inc.get(cur) || []) steps.push([e, e.from, "in"]);
        for (const [e, other, dirn] of steps) {
          if (o.edgeOk && !o.edgeOk(e)) continue;
          if (!nodes.has(other)) {
            if ((o.nodeOk && !o.nodeOk(other)) || (o.allowed && !o.allowed.has(other))) continue;
            if (nodes.size >= limit) { truncated = true; continue; }
            nodes.set(other, { id: other, depth: d, side: d === 1 ? dirn : side, via: cur }); next.push(other);
          } else if (d === 1 && other !== id && nodes.get(other).depth === 1 && nodes.get(other).side !== dirn) nodes.get(other).side = "both";
          if (!seenE.has(e)) { seenE.add(e); edges.push(e); }
        }
      }
      frontier = next;
    }
    for (const e of index.edges) if (!seenE.has(e) && nodes.has(e.from) && nodes.has(e.to) && (!o.edgeOk || o.edgeOk(e)) && depth > 1) { seenE.add(e); edges.push(e); }   // relations among the neighbours themselves
    return { center: id, nodes, edges, truncated };
  }
  // What the card depends on to the left, what it leads to on the right, things related both ways above and below; farther levels farther out.
  function focusLayout(g) {
    const pos = new Map([[g.center, { x: 0, y: 0 }]]), groups = new Map();
    for (const n of g.nodes.values()) { if (n.depth === 0) continue; const key = n.side + ":" + n.depth; if (!groups.has(key)) groups.set(key, []); groups.get(key).push(n.id); }
    const COL = 330, ROW = 86, PER = 12;
    for (const [key, ids] of groups) {
      const [side, d] = key.split(":"), depth = Number(d); ids.sort();
      if (side === "both") { ids.forEach((id, i) => { const row = Math.floor(i / 2) + 1, up = i % 2 === 0; pos.set(id, { x: (depth - 1) * 120 * (up ? 1 : -1), y: (up ? -1 : 1) * (70 + row * ROW) }); }); continue; }
      const sign = side === "in" ? -1 : 1;
      ids.forEach((id, i) => { const col = Math.floor(i / PER), inCol = Math.min(PER, ids.length - col * PER), row = i % PER; pos.set(id, { x: sign * (depth * COL + col * 230), y: (row - (inCol - 1) / 2) * ROW }); });
    }
    const box = { x0: -NODE_W / 2, y0: -NODE_H / 2, x1: NODE_W / 2, y1: NODE_H / 2 };
    for (const p of pos.values()) { box.x0 = Math.min(box.x0, p.x - NODE_W / 2); box.x1 = Math.max(box.x1, p.x + NODE_W / 2); box.y0 = Math.min(box.y0, p.y - NODE_H / 2); box.y1 = Math.max(box.y1, p.y + NODE_H / 2); }
    return { pos, box };
  }

  // ---------- labels: the most important first, no two on top of each other ----------
  // items: [{x, y, w, h, pri}] in screen space; returns the ones that fit (higher `pri` wins a contested spot).
  // `blocked`: boxes already taken by something more important (a folder's name), which no label may cover.
  function cullLabels(items, max, blocked) {
    const kept = [], grid = new Map(), S = 64;
    for (const b of blocked || []) for (let gx = Math.floor(b.x / S); gx <= Math.floor((b.x + b.w) / S); gx++) for (let gy = Math.floor(b.y / S); gy <= Math.floor((b.y + b.h) / S); gy++) { const k = gx + "," + gy; if (!grid.has(k)) grid.set(k, []); grid.get(k).push(b); }
    for (const it of [...items].sort((a, b) => b.pri - a.pri)) {
      if (kept.length >= (max || 400)) break;
      const x0 = Math.floor(it.x / S), x1 = Math.floor((it.x + it.w) / S), y0 = Math.floor(it.y / S), y1 = Math.floor((it.y + it.h) / S); let hit = false;
      for (let gx = x0; gx <= x1 && !hit; gx++) for (let gy = y0; gy <= y1 && !hit; gy++) for (const o of grid.get(gx + "," + gy) || []) if (it.x < o.x + o.w && it.x + it.w > o.x && it.y < o.y + o.h && it.y + it.h > o.y) { hit = true; break; }
      if (hit) continue; kept.push(it);
      for (let gx = x0; gx <= x1; gx++) for (let gy = y0; gy <= y1; gy++) { const k = gx + "," + gy; if (!grid.has(k)) grid.set(k, []); grid.get(k).push(it); }
    }
    return kept;
  }
  // A folder's dot grows with what it holds, slowly: a thousand features must not drown twenty.
  const dotRadius = (total) => Math.min(26, 8 + 5 * Math.log10(1 + total));

  return { VIRTUAL, ROOT, NODE_W, NODE_H, K_MAX, LOD, ENTER, EXIT, KIND_PLURAL, RECIPE_KINDS, cap, cleanTag, tagKey, hash, emptyMeta, normMeta, buildIndex, inferTags, tagsFor, allTags, hasRules, matchRules,
    buildTree, pathOf, pathLabel, descendants, isVirtual, createFolder, renameFolder, deleteFolder, moveFolder, setFolder, assign, unassign, dismissSuggestion, addTag, removeTag, setPos, setFolderPos,
    layout, toScreen, toWorld, zoomAt, fitCircle, fitBox, minZoom, wheelFactor, lodOf, updateOpen, openPath, activeFolder, repOf, bundles, noFilters, filtersActive, applyFilters, search, ego, focusLayout, cullLabels, dotRadius };
})();
if (typeof module !== "undefined" && module.exports) module.exports = MapCore;
