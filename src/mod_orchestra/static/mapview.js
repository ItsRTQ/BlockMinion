"use strict";
// Mod Map 2.0 — the view. MapCore (mapcore.js) decides; this file draws and listens.
//   Zoom = travel · Click = inspect · Expand = understand · Focus = investigate · Modify = an explicit request to a coder.
// Nothing here starts a coder except the two "Send to a coder" buttons, and folders, tags and positions are saved as view
// metadata only (POST map-meta): no agent brief reads them.
//
// Drawing: a <canvas> for what there can be thousands of (feature dots, relations, far labels) and SVG for what the user
// touches (folder dots, the cards near the camera). Each frame draws only what the camera sees.
const mapState = { pid: null, project: null, data: null, sel: null, selFolder: null, multi: false, picked: new Set(), index: null, meta: null, tree: null, lay: null, inferred: null,
  slotsByPid: {}, cam: { cx: 0, cy: 0, k: 1 }, open: new Set([""]), amt: new Map(), filters: null, filt: null, ver: 0, zoom: null, fly: null, hist: [], histI: 0, focus: null,
  insp: null, pulse: null, hover: null, active: "", stats: null, drag: null };

const MapView = (() => {
  const C = MapCore, S = mapState, SVGNS = "http://www.w3.org/2000/svg", ROOT = C.ROOT;
  const KIND_COLOR = { item: "#19e6ff", block: "#7cd8ff", mob: "#ffb547", material: "#a391ff", food: "#2ef2a6", custom: "#c4b5ff", vanilla: "#5c7390" };
  const EDGE_COLOR = { crafts: "#19e6ff", smelts_into: "#19e6ff", drops: "#ffb547", drops_on_death: "#ffb547", made_of: "#a391ff", repairs: "#a391ff", uses: "#7cd8ff", related: "#7cd8ff" };
  const MAX_CARDS = 220, MAX_EDGES = 1800, MAX_FOLDER_ELS = 500;
  let wrap = null, svg = null, canvas = null, ctx = null, gFolders = null, gCards = null, gFocus = null, gOver = null, link = null, raf = 0, saveTimer = 0, unsaved = 0, bundleCache = null, regionCache = null;
  const els = { cards: new Map(), folders: new Map(), focus: new Map() };
  let hitDots = [], hitBundles = [];

  const svgEl = (tag, attrs) => { const n = document.createElementNS(SVGNS, tag); for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, v); return n; };
  const reduced = () => !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  const vp = () => ({ w: (wrap && wrap.clientWidth) || 1000, h: (wrap && wrap.clientHeight) || 600 });
  const invalidate = () => { if (!raf) raf = requestAnimationFrame(frame); };
  const kindName = (c) => (c.kind === "material" ? "tool & armor set" : c.kind);
  const title = (id) => { const c = S.index.cards.get(id); return c ? c.title || c.id : id; };
  const relName = (kind) => S.index.labels[kind] || kind.replace(/_/g, " ");
  const local = (ev) => { const r = wrap.getBoundingClientRect(); return { x: (ev.clientX || 0) - r.left, y: (ev.clientY || 0) - r.top }; };
  const camNow = () => (S.focus ? S.focus.cam : S.cam);

  // ---------- data ----------
  async function render(p) {
    wrap = qs("map-wrap"); if (!wrap) return;
    let data; try { data = await api(`/api/project/${p.id}/map`); } catch (e) { toast("map: " + e.message, "bad"); return; }
    const fresh = S.pid !== p.id; if (fresh) flushSave();
    S.project = p; S.data = data;
    if (fresh || !unsaved) S.meta = C.normMeta(data.meta);            // an organisation change still on its way to the server is newer than what just came back
    if (fresh) {
      S.pid = p.id; S.sel = null; S.selFolder = null; S.insp = null; S.focus = null; S.open = new Set([ROOT]); S.amt = new Map(); S.zoom = null; S.fly = null; S.picked.clear(); S.multi = false;
      const pf = S.meta.prefs || {}; S.filters = { kinds: pf.hiddenKinds || [], rels: pf.hiddenRels || [], tags: [], mode: pf.filterMode === "dim" ? "dim" : "hide" };
    }
    bind(); rebuild();
    if (fresh) { S.cam = C.fitCircle(S.lay.folders.get(ROOT), vp()); S.hist = [snapshot()]; S.histI = 0; qs("map-multi").classList.remove("active"); qs("map-side").classList.add("hidden"); }
    if (S.sel && !S.index.cards.has(S.sel)) { S.sel = null; S.insp = null; }
    if (S.insp && !qs("map-inspector").contains(document.activeElement)) buildInspector();
    if (S.focus) { if (S.index.cards.has(S.focus.id)) refocus(S.focus.id, true); else exitFocus(true); }
    buildChrome(); invalidate();
  }
  function rebuild() {
    S.index = C.buildIndex(S.data); S.inferred = C.inferTags(S.index);
    const kinds = new Set(S.index.kinds.keys()), rels = new Set(S.index.rels.keys());
    S.filters.kinds = S.filters.kinds.filter((k) => kinds.has(k)); S.filters.rels = S.filters.rels.filter((k) => rels.has(k));
    reorganize(false);
  }
  // After any change to folders, tags, positions or filters: where things are filed and where they sit. The graph itself is untouched.
  function reorganize(save) {
    S.tree = C.buildTree(S.index, S.meta, S.inferred);
    S.lay = C.layout(S.tree, S.meta, S.slotsByPid[S.pid] || (S.slotsByPid[S.pid] = {}), S.index);
    S.filt = C.applyFilters(S.index, S.inferred, S.meta, S.filters);
    for (const fid of [...S.open]) if (!S.tree.folders.has(fid)) S.open.delete(fid);
    S.open.add(ROOT); if (S.selFolder && !S.tree.folders.has(S.selFolder)) { S.selFolder = null; if (S.insp && S.insp.type === "folder") S.insp = null; }
    S.ver++; if (save) scheduleSave();
  }
  // Saved a moment after the last change (one request for a burst of them). Until the server has it, a refresh must not put the old one back.
  function scheduleSave() { clearTimeout(saveTimer); unsaved++; saveTimer = setTimeout(flushSave, 500); }
  async function flushSave() {
    if (!saveTimer) return; clearTimeout(saveTimer); saveTimer = 0; const pid = S.pid, mine = unsaved;
    S.meta.prefs = Object.assign({}, S.meta.prefs, { hiddenKinds: S.filters.kinds, hiddenRels: S.filters.rels, filterMode: S.filters.mode });
    try { await api(`/api/project/${pid}/map-meta`, { meta: S.meta }); } catch (e) { toast("The map's organisation was not saved: " + e.message, "bad"); }
    if (unsaved === mine) unsaved = 0;
  }
  function setMeta(meta, message) { S.meta = meta; reorganize(true); if (S.insp) buildInspector(); buildChrome(); invalidate(); if (message) toast(message, "ok"); }

  // ---------- one-time wiring ----------
  function bind() {
    if (svg) return;
    svg = qs("map-svg"); canvas = qs("map-canvas"); ctx = canvas && canvas.getContext ? canvas.getContext("2d") : null;
    svg.replaceChildren(); gFolders = svgEl("g", { class: "layer-folders" }); gCards = svgEl("g", { class: "layer-cards" }); gFocus = svgEl("g", { class: "layer-focus" }); gOver = svgEl("g", { class: "layer-over" });
    link = svgEl("line", { class: "insp-link" }); gOver.append(link); svg.append(gFolders, gCards, gFocus, gOver);
    wrap.addEventListener("wheel", onWheel, { passive: false });
    svg.addEventListener("pointerdown", onBackDown); svg.addEventListener("pointermove", onBackMove); svg.addEventListener("pointerup", onBackUp); svg.addEventListener("pointercancel", () => { S.drag = null; });
    wrap.addEventListener("keydown", onKey);
    if (window.ResizeObserver) new ResizeObserver(invalidate).observe(wrap); else window.addEventListener("resize", invalidate);
    qs("map-fit").onclick = () => travel({ cam: C.fitCircle(S.lay.folders.get(ROOT), vp()), fid: ROOT });
    qs("map-multi").onclick = () => { S.multi = !S.multi; if (!S.multi) S.picked.clear(); qs("map-multi").classList.toggle("active", S.multi); if (S.multi) { closeInspector(); openMulti(); } else qs("map-side").classList.add("hidden"); invalidate(); };
    qs("map-new-feature").onclick = () => { qs("modal-feature").classList.remove("hidden"); qs("ft-title").focus(); };
    qs("map-new-folder").onclick = () => newFolder(S.active && !C.isVirtual(S.active) ? S.active : null);
    qs("map-filter-btn").onclick = () => { const box = qs("map-filters"); if (box.classList.contains("hidden")) { buildFilters(); box.classList.remove("hidden"); } else box.classList.add("hidden"); };
    const input = qs("map-search");
    input.oninput = () => showResults(); input.onfocus = () => showResults();
    input.onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); const first = qs("map-results").querySelector("button"); if (first) first.click(); } else if (e.key === "Escape") { input.value = ""; showResults(); input.blur(); } };
    qs("map-scope").onchange = () => showResults();
    const nav = { "map-back": () => step(-1), "map-fwd": () => step(1), "map-up": () => goParent(), "map-home": () => travel({ cam: C.fitCircle(S.lay.folders.get(ROOT), vp()), fid: ROOT }),
                  "map-fit-region": () => enterFolder(S.active) };
    for (const [id, fn] of Object.entries(nav)) qs(id).onclick = fn;
  }

  // ---------- camera ----------
  function onWheel(ev) {
    if (ev.target.closest && ev.target.closest(".map-inspector, .map-side, .map-pop")) return;   // those scroll by themselves
    ev.preventDefault();
    const cam = camNow(), v = vp(), p = local(ev), lo = S.focus ? 0.15 : C.minZoom(S.lay, v);
    const from = S.zoom ? S.zoom.k : cam.k, k = Math.max(lo, Math.min(C.K_MAX, from * C.wheelFactor(ev.deltaY * (ev.deltaMode === 1 ? 33 : 1), ev.ctrlKey)));
    S.fly = null; S.zoom = { k, sx: p.x, sy: p.y }; invalidate();
  }
  function stepCamera(now, v) {
    const cam = camNow(); let moving = false;
    if (S.fly) {
      const f = S.fly, t = reduced() ? 1 : Math.min(1, (now - f.t0) / f.dur), e = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
      cam.k = Math.exp(Math.log(f.from.k) + (Math.log(f.to.k) - Math.log(f.from.k)) * e); cam.cx = f.from.cx + (f.to.cx - f.from.cx) * e; cam.cy = f.from.cy + (f.to.cy - f.from.cy) * e;
      if (t >= 1) { S.fly = null; if (!S.focus) { if (f.fid != null) C.openPath(S.open, S.tree, f.fid); C.updateOpen(S.open, S.tree, S.lay, cam, v, null, 0); S.ver++; } if (f.then) f.then(); } else moving = true;
    } else if (S.zoom) {
      const z = S.zoom, before = cam.k; let k = reduced() ? z.k : cam.k + (z.k - cam.k) * 0.3;
      if (Math.abs(k / z.k - 1) < 0.004) k = z.k;
      Object.assign(cam, C.zoomAt(cam, v, k, z.sx, z.sy));
      if (!S.focus && C.updateOpen(S.open, S.tree, S.lay, cam, v, C.toWorld(cam, v, z.sx, z.sy), Math.sign(k - before))) S.ver++;
      if (k === z.k) S.zoom = null; else moving = true;
    }
    return moving;
  }
  function stepOpen() {
    let moving = false; const snap = reduced();
    for (const fid of new Set([...S.open, ...S.amt.keys()])) {
      if (fid === ROOT) continue; const target = S.open.has(fid) ? 1 : 0; let a = S.amt.get(fid) || 0;
      if (a === target) continue; a = snap ? target : a + (target - a) * 0.22; if (Math.abs(a - target) < 0.02) a = target;
      if (a === 0) S.amt.delete(fid); else S.amt.set(fid, a); if (a !== target) moving = true;
    }
    return moving;
  }
  function flyTo(cam, fid, then) { S.zoom = null; S.fly = { from: Object.assign({}, camNow()), to: cam, t0: performance.now(), dur: 520, fid, then }; invalidate(); }
  // Travel with history: where we are is remembered, so Back returns to it.
  const snapshot = () => ({ cam: Object.assign({}, S.cam), sel: S.sel, selFolder: S.selFolder, fid: S.active });
  function travel(dest) {
    if (S.focus) exitFocus(true);
    S.hist = S.hist.slice(0, S.histI + 1); S.hist[S.histI] = snapshot(); S.hist.push(dest); S.histI = S.hist.length - 1; if (S.hist.length > 60) { S.hist.shift(); S.histI--; }
    arrive(dest);
  }
  function arrive(dest) {
    flyTo(dest.cam, dest.fid, () => { if (dest.pulse) S.pulse = { id: dest.pulse, until: performance.now() + 1600 }; buildChrome(); });
    if (dest.sel !== undefined) { S.sel = dest.sel; S.selFolder = null; S.insp = dest.sel ? { type: "card", id: dest.sel, full: false } : null; }
    if (dest.selFolder) { S.selFolder = dest.selFolder; S.sel = null; S.insp = { type: "folder", id: dest.selFolder, full: false }; }
    buildInspector(); buildChrome();
  }
  function step(d) { const i = S.histI + d; if (i < 0 || i >= S.hist.length) return; if (S.focus) exitFocus(true); S.hist[S.histI] = snapshot(); S.histI = i; arrive(S.hist[i]); }
  function enterFolder(fid) { if (!S.tree.folders.has(fid)) return; travel({ cam: C.fitCircle(S.lay.folders.get(fid), vp()), fid, sel: null }); }
  function goParent() { const f = S.tree.folders.get(S.active); enterFolder(f && f.id !== ROOT ? f.parent : ROOT); }
  // Take the camera to a card, close enough to read it, entering whatever folders hold it.
  function reveal(id, o) {
    const n = S.lay.nodes.get(id); if (!n) return; const v = vp(), fold = S.lay.folders.get(n.fid);
    const k = Math.min(C.K_MAX, Math.max(1, S.cam.k, (C.ENTER * Math.min(v.w, v.h) * 1.1) / fold.r)), dest = { cam: { cx: n.x, cy: n.y, k }, fid: n.fid, sel: id, pulse: id };
    if (o && o.instant) { S.cam = dest.cam; S.zoom = null; S.fly = null; C.openPath(S.open, S.tree, n.fid); for (const f of C.pathOf(S.tree, n.fid)) S.amt.set(f.id, 1); S.ver++; S.sel = id; S.selFolder = null; invalidate(); return; }
    travel(dest);
  }

  // ---------- pointer: background (pan, and clicks on what the canvas drew) ----------
  function onBackDown(ev) { const cam = camNow(); if (svg.setPointerCapture && ev.pointerId != null) try { svg.setPointerCapture(ev.pointerId); } catch (e) { /* not a real pointer */ } S.drag = { type: "pan", sx: ev.clientX || 0, sy: ev.clientY || 0, cx: cam.cx, cy: cam.cy, moved: false }; closePops(); }
  function onBackMove(ev) {
    const d = S.drag;
    if (!d) { if (hitDots.length) { const p = local(ev), h = dotAt(p); const id = h ? h.id : null; if (id !== S.hover) { S.hover = id; svg.classList.toggle("over-dot", !!id); invalidate(); } } return; }
    if (d.type !== "pan") return;
    const dx = (ev.clientX || 0) - d.sx, dy = (ev.clientY || 0) - d.sy; if (Math.abs(dx) + Math.abs(dy) > 3) d.moved = true;
    const cam = camNow(); cam.cx = d.cx - dx / cam.k; cam.cy = d.cy - dy / cam.k; S.zoom = null; S.fly = null; invalidate();   // panning moves the camera and nothing else: it never enters a folder
  }
  function onBackUp(ev) {
    const d = S.drag; S.drag = null; if (!d || d.type !== "pan" || d.moved) return;
    const p = local(ev), dot = dotAt(p);
    if (dot) return cardClicked(dot.id);
    const bun = bundleAt(p); if (bun) { S.insp = { type: "bundle", bun, at: p }; S.sel = null; S.selFolder = null; buildInspector(); invalidate(); return; }
    closeInspector();
  }
  const dotAt = (p) => { let best = null, bd = 1e9; for (const h of hitDots) { const d = Math.hypot(h.x - p.x, h.y - p.y) - h.r; if (d < 7 && d < bd) { bd = d; best = h; } } return best; };
  function bundleAt(p) {
    let best = null, bd = 7;
    for (const h of hitBundles) { const dx = h.x2 - h.x1, dy = h.y2 - h.y1, len = dx * dx + dy * dy || 1, t = Math.max(0, Math.min(1, ((p.x - h.x1) * dx + (p.y - h.y1) * dy) / len)), d = Math.hypot(p.x - (h.x1 + t * dx), p.y - (h.y1 + t * dy)); if (d < bd) { bd = d; best = h.bun; } }
    return best;
  }
  function onKey(ev) {
    if (ev.target.closest("input, textarea, select")) return;
    const cam = camNow(), v = vp(), stepPx = 80 / cam.k;
    if (ev.key === "Escape") { if (S.insp) closeInspector(); else if (S.focus) exitFocus(); else if (S.multi) qs("map-multi").click(); else return; ev.preventDefault(); return; }
    if (ev.target.closest(".map-inspector, .map-side, .map-pop, button")) return;
    const pan = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[ev.key];
    if (pan) { cam.cx += pan[0] * stepPx; cam.cy += pan[1] * stepPx; S.fly = null; S.zoom = null; }
    else if (ev.key === "+" || ev.key === "=") S.zoom = { k: Math.min(C.K_MAX, cam.k * 1.25), sx: v.w / 2, sy: v.h / 2 };
    else if (ev.key === "-" || ev.key === "_") S.zoom = { k: Math.max(S.focus ? 0.15 : C.minZoom(S.lay, v), cam.k / 1.25), sx: v.w / 2, sy: v.h / 2 };
    else if (ev.key === "Backspace") goParent();
    else if (ev.key === "0") qs("map-fit").click();
    else if (ev.key === "/") qs("map-search").focus();
    else return;
    ev.preventDefault(); invalidate();
  }

  // ---------- cards and folders as SVG ----------
  function cardEl(key, id, layer) {
    const g = svgEl("g", { "data-id": id, "data-key": key });
    g.append(svgEl("rect", { width: C.NODE_W, height: C.NODE_H }), svgEl("text", { x: 12, y: 16, class: "kind" }), svgEl("text", { x: 12, y: 34, class: "title" }), svgEl("text", { x: 12, y: 47, class: "sub" }), svgEl("circle", { cx: C.NODE_W - 12, cy: 12, r: 4 }));
    let d = null;
    g.addEventListener("pointerdown", (ev) => { ev.stopPropagation(); closePops(); d = { sx: ev.clientX || 0, sy: ev.clientY || 0, moved: false }; if (g.setPointerCapture && ev.pointerId != null) try { g.setPointerCapture(ev.pointerId); } catch (e) { /* not a real pointer */ } });
    g.addEventListener("pointermove", (ev) => {
      if (!d || layer === "focus") return; const dx = (ev.clientX || 0) - d.sx, dy = (ev.clientY || 0) - d.sy;
      if (!d.moved && Math.abs(dx) + Math.abs(dy) > 4) { d.moved = true; const n = S.lay.nodes.get(key); d.ox = n.x; d.oy = n.y; }
      if (d.moved) { const n = S.lay.nodes.get(key); n.x = d.ox + dx / S.cam.k; n.y = d.oy + dy / S.cam.k; invalidate(); }
    });
    g.addEventListener("pointerup", (ev) => { ev.stopPropagation(); const was = d; d = null; if (!was) return; if (was.moved) cardDropped(key, was); else cardClicked(id); });
    return g;
  }
  function fillCard(g, c, o) {
    const sig = (c.title || c.id) + "|" + (c.status || "") + "|" + ((c.open_tasks || []).length) + "|" + (c.pieces ? c.pieces.length : "") + "|" + !!o.ref + "|" + !!o.compact; if (g.__sig === sig) return; g.__sig = sig;
    const [, kind, ttl, sub, dot] = g.children;
    kind.textContent = (c.kind === "material" ? "TOOL & ARMOR SET" : c.kind.toUpperCase()) + (c.open_tasks && c.open_tasks.length ? " · " + c.open_tasks.length + " task" : "") + (o.ref ? " · REFERENCE" : "");
    const name = c.title || c.id, max = o.compact ? 17 : 24; ttl.textContent = name.length > max ? name.slice(0, max - 1) + "…" : name; sub.textContent = c.pieces ? `${c.pieces.length} pieces` : c.kind === "custom" ? c.status || "" : c.id;
    dot.setAttribute("class", "dot " + (c.status || "vanilla"));
  }
  function cardClicked(id) {
    if (S.multi) return mapPick(id);
    S.sel = id; S.selFolder = null; S.insp = { type: "card", id, full: false }; buildInspector(); invalidate();
  }
  // Which folder a world point is in: the deepest one, stopping at a folder the camera has not entered.
  function folderAt(x, y) {
    let cur = ROOT;
    for (let guard = 0; guard < 64; guard++) {
      const next = S.tree.folders.get(cur).children.find((cid) => { const c = S.lay.folders.get(cid); return Math.hypot(x - c.x, y - c.y) <= c.r; });
      if (!next) break; cur = next; if (!S.open.has(next)) break;
    }
    return cur;
  }
  // Dropping a card: inside its own folder it is only a position; on another folder it is filed there. Either way only the map's metadata changes.
  function cardDropped(key, was) {
    const n = S.lay.nodes.get(key), target = folderAt(n.x, n.y), c = S.lay.folders.get(target), name = title(n.id);
    if (target === n.fid) return setMeta(C.setPos(S.meta, n.fid, n.id, n.x - c.x, n.y - c.y));
    const how = (S.tree.foldersOf.get(n.id).find((m) => m.fid === n.fid) || {}).how;
    if (target === ROOT) { n.x = was.ox; n.y = was.oy; invalidate(); return toast("Drop it on a folder to file it there.", ""); }
    if (C.isVirtual(target)) {
      if (how === "unfiled") { n.x = was.ox; n.y = was.oy; invalidate(); return toast("That is an automatic group; create a folder to file cards yourself.", ""); }
      return setMeta(C.unassign(S.meta, n.id, n.fid), `"${name}" taken out of ${S.tree.folders.get(n.fid).name}. Only the map changed.`);
    }
    let meta = C.assign(S.meta, n.id, target, { from: how === "unfiled" ? null : n.fid, primary: !n.ref });
    if (S.open.has(target)) meta = C.setPos(meta, target, n.id, n.x - c.x, n.y - c.y);
    setMeta(meta, `"${name}" filed in ${S.tree.folders.get(target).name}. Only the map changed; the mod's files are untouched.`);
  }
  function folderEl(fid) {
    const g = svgEl("g", { class: "folder", "data-fid": fid, tabindex: "0", role: "button" });
    g.append(svgEl("circle", { class: "halo" }), svgEl("circle", { class: "core" }), svgEl("text", { class: "fname", "text-anchor": "middle" }), svgEl("text", { class: "fcount", "text-anchor": "middle" }));
    let d = null;
    g.addEventListener("pointerdown", (ev) => { ev.stopPropagation(); closePops(); d = { sx: ev.clientX || 0, sy: ev.clientY || 0, moved: false }; if (g.setPointerCapture && ev.pointerId != null) try { g.setPointerCapture(ev.pointerId); } catch (e) { /* not a real pointer */ } });
    g.addEventListener("pointermove", (ev) => {
      if (!d) return; const dx = ((ev.clientX || 0) - d.sx) / S.cam.k, dy = ((ev.clientY || 0) - d.sy) / S.cam.k;
      if (!d.moved && Math.abs(dx * S.cam.k) + Math.abs(dy * S.cam.k) > 4) { d.moved = true; d.last = { x: 0, y: 0 }; }
      if (d.moved) { shiftFolder(fid, dx - d.last.x, dy - d.last.y); d.last = { x: dx, y: dy }; invalidate(); }
    });
    g.addEventListener("pointerup", (ev) => {
      ev.stopPropagation(); const was = d; d = null; if (!was) return;
      if (was.moved) { const c = S.lay.folders.get(fid), pc = S.lay.folders.get(S.tree.folders.get(fid).parent); return setMeta(C.setFolderPos(S.meta, fid, c.x - pc.x, c.y - pc.y)); }
      selectFolder(fid);
    });
    g.addEventListener("dblclick", (ev) => { ev.stopPropagation(); enterFolder(fid); });
    g.addEventListener("keydown", (ev) => { if (ev.key === "Enter") { ev.preventDefault(); ev.stopPropagation(); enterFolder(fid); } else if (ev.key === " ") { ev.preventDefault(); ev.stopPropagation(); selectFolder(fid); } });
    return g;
  }
  function shiftFolder(fid, dx, dy) { for (const id of C.descendants(S.tree, fid)) { const c = S.lay.folders.get(id); c.x += dx; c.y += dy; for (const n of S.lay.byFolder.get(id) || []) { n.x += dx; n.y += dy; } } }
  function selectFolder(fid) { S.selFolder = fid; S.sel = null; S.insp = { type: "folder", id: fid, full: false }; buildInspector(); invalidate(); }

  // ---------- drawing ----------
  function frame(now) {
    raf = 0; if (!S.index || !wrap || !svg) return;
    if (gCards.parentNode !== svg) { for (const m of Object.values(els)) m.clear(); svg.replaceChildren(gFolders, gCards, gFocus, gOver); }   // something emptied the SVG: put the layers back
    const v = vp(); let more = stepCamera(now, v); more = stepOpen() || more;
    if (canvas) { const dpr = window.devicePixelRatio || 1; if (canvas.width !== Math.round(v.w * dpr) || canvas.height !== Math.round(v.h * dpr)) { canvas.width = Math.round(v.w * dpr); canvas.height = Math.round(v.h * dpr); } if (ctx) { ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, v.w, v.h); } }
    hitDots = []; hitBundles = [];
    drawUniverse(v, !!S.focus); if (S.focus) drawFocus(v); else sweep(els.focus, new Set());
    placeInspector(v);
    const active = S.focus ? S.active : C.activeFolder(S.open, S.tree, S.lay, S.cam); if (active !== S.active) { S.active = active; buildChrome(); }
    updateCount();
    if (S.pulse && now > S.pulse.until) S.pulse = null;
    if (more || S.pulse) invalidate();
  }
  function sweep(map, keep) { for (const [k, n] of map) if (!keep.has(k)) { n.remove(); map.delete(k); } }
  function bundlesNow() {
    if (!bundleCache || bundleCache.ver !== S.ver) bundleCache = { ver: S.ver, list: C.bundles(S.index, S.tree, S.open, S.filt.edgeOk) };
    return bundleCache.list;
  }
  function drawUniverse(v, dim) {
    const cam = S.cam, lod = C.lodOf(cam.k), keepCards = new Set(), keepFolders = new Set(), memo = new Map([[ROOT, 1]]), labels = [], dots = [], folderDraw = [];
    const stats = { drawn: 0, outside: 0, collapsed: 0 }, hideMode = S.filt.active && S.filters.mode === "hide", dimMode = S.filt.active && S.filters.mode === "dim";
    const half = { w: (C.NODE_W / 2) * cam.k, h: (C.NODE_H / 2) * cam.k }, dotR = Math.max(2.2, Math.min(7, C.NODE_H * cam.k * 0.3)); let cards = 0;
    gFolders.classList.toggle("dimmed", dim); gCards.classList.toggle("dimmed", dim);
    (function visit(fid, alpha) {
      const f = S.tree.folders.get(fid), c = S.lay.folders.get(fid), o = fid === ROOT ? 1 : S.amt.get(fid) || 0;
      if (fid !== ROOT) {
        const s = C.toScreen(cam, v, c.x, c.y), sr = Math.max(c.r * cam.k, 30);
        if (s.x + sr < 0 || s.x - sr > v.w || s.y + sr < 0 || s.y - sr > v.h) { stats.outside += f.total; return; }
        folderDraw.push({ f, s, sr: c.r * cam.k, o, alpha });
        if (o < 0.5) stats.collapsed += f.total;
      }
      const a = alpha * o; if (a <= 0.02) return;
      for (const n of S.lay.byFolder.get(fid)) {
        const match = S.filt.match.has(n.id); if (hideMode && !match) continue;
        const s = C.toScreen(cam, v, n.x, n.y);
        if (s.x < -half.w - 20 || s.x > v.w + half.w + 20 || s.y < -half.h - 20 || s.y > v.h + half.h + 20) { if (!n.ref) stats.outside++; continue; }
        if (!n.ref) stats.drawn++;
        const faded = dimMode && !match, card = S.index.cards.get(n.id), isSel = n.id === S.sel || S.picked.has(n.id);
        if (lod >= 2 && cards < MAX_CARDS) {
          cards++; keepCards.add(n.key); let g = els.cards.get(n.key);
          if (!g) { g = cardEl(n.key, n.id, "map"); els.cards.set(n.key, g); gCards.append(g); }
          fillCard(g, card, { ref: n.ref, compact: lod === 2 });
          g.setAttribute("class", "node " + card.kind + (n.id === S.sel ? " sel" : "") + (S.picked.has(n.id) ? " picked" : "") + (n.ref ? " ref" : "") + (lod === 2 ? " compact" : "") + (faded ? " faded" : "") + (S.pulse && S.pulse.id === n.id ? " pulse" : ""));
          g.setAttribute("transform", `translate(${(s.x - half.w).toFixed(1)},${(s.y - half.h).toFixed(1)}) scale(${cam.k.toFixed(4)})`); g.setAttribute("opacity", (a * (faded ? 0.25 : 1)).toFixed(2));
        } else {
          dots.push({ x: s.x, y: s.y, r: dotR, color: KIND_COLOR[card.kind] || "#8fa6c4", a: a * (faded ? 0.2 : n.ref ? 0.55 : 1), sel: isSel, pulse: S.pulse && S.pulse.id === n.id, ref: n.ref });
          hitDots.push({ id: n.id, x: s.x, y: s.y, r: dotR });
          if (!faded && (lod >= 1 || isSel || n.id === S.hover)) { const text = (card.title || card.id).slice(0, 28); labels.push({ x: s.x + dotR + 5, y: s.y - 7, w: text.length * 6.4 + 6, h: 14, text, a, pri: (isSel ? 1000 : n.id === S.hover ? 900 : 0) + (card.kind === "vanilla" ? 0 : 5) + Math.min(4, (S.index.out.get(n.id).length + S.index.inc.get(n.id).length) * 0.2) }); }
        }
      }
      for (const cid of f.children) visit(cid, a);
    })(ROOT, 1);
    // folders: the largest keep their names when there is no room for all of them
    folderDraw.sort((x, y) => y.f.total - x.f.total);
    const nameBoxes = C.cullLabels(folderDraw.map((d) => { const dr = C.dotRadius(d.f.total); return { x: d.s.x - 70, y: d.o > 0.5 ? Math.max(58, d.s.y - d.sr - 10) - 16 : d.s.y + dr + 2, w: 140, h: 32, pri: d.f.total + (d.f.id === S.selFolder ? 1e9 : 0) + (d.o > 0.5 ? 1e6 * (1 + d.f.depth) : 0), d }; }), 160);   // where two entered folders' names would meet, the inner one shows
    const named = new Set(nameBoxes.map((l) => l.d.f.id));
    folderDraw.forEach((d, i) => {
      const fid = d.f.id, dr = C.dotRadius(d.f.total), closed = 1 - d.o;
      if (ctx && d.sr > dr + 6) { ctx.globalAlpha = (dim ? 0.12 : 1) * d.alpha * (0.1 + 0.2 * d.o + (fid === S.selFolder ? 0.3 : 0)); ctx.strokeStyle = "#19e6ff"; ctx.lineWidth = 1; ctx.setLineDash(d.f.virtual ? [3, 6] : d.o > 0.5 ? [] : [2, 8]); ctx.beginPath(); ctx.arc(d.s.x, d.s.y, d.sr, 0, Math.PI * 2); ctx.stroke(); ctx.setLineDash([]); }
      if (i >= MAX_FOLDER_ELS) { if (ctx) { ctx.globalAlpha = (dim ? 0.12 : 1) * d.alpha * closed; ctx.fillStyle = "#19e6ff"; ctx.beginPath(); ctx.arc(d.s.x, d.s.y, Math.min(dr, 4), 0, Math.PI * 2); ctx.fill(); } return; }
      keepFolders.add(fid); let g = els.folders.get(fid); if (!g) { g = folderEl(fid); els.folders.set(fid, g); gFolders.append(g); }
      const [halo, core, name, count] = g.children, top = Math.max(58, d.s.y - d.sr - 10), ly = d.o > 0.5 ? top : d.s.y + dr + 16, big = Math.min(18, 12 + d.sr / 60);
      g.setAttribute("class", "folder" + (d.f.virtual ? " virtual" : "") + (fid === S.selFolder ? " sel" : "") + (d.o > 0.5 ? " entered" : "") + (S.tree.suggestions.has(fid) ? " has-suggest" : "") + (d.f.total === 0 ? " empty" : ""));
      g.setAttribute("opacity", d.alpha.toFixed(2)); g.setAttribute("aria-label", `${d.f.name}, folder, ${d.f.total} feature${d.f.total === 1 ? "" : "s"}${d.o > 0.5 ? ", entered" : ""}`);
      halo.setAttribute("cx", d.s.x); halo.setAttribute("cy", d.s.y); halo.setAttribute("r", dr + 6); halo.setAttribute("opacity", (closed * 0.9).toFixed(2));
      core.setAttribute("cx", d.s.x); core.setAttribute("cy", d.s.y); core.setAttribute("r", dr); core.setAttribute("opacity", closed.toFixed(2)); core.setAttribute("pointer-events", d.o > 0.5 ? "none" : "auto"); halo.setAttribute("pointer-events", d.o > 0.5 ? "none" : "auto");
      const show = named.has(fid); name.textContent = show ? d.f.name : ""; count.textContent = show ? (d.f.total + (d.f.children.length ? ` · ${d.f.children.length} folder${d.f.children.length === 1 ? "" : "s"}` : "")) : "";
      name.setAttribute("x", d.s.x); name.setAttribute("y", ly); name.setAttribute("font-size", big.toFixed(1)); count.setAttribute("x", d.s.x); count.setAttribute("y", ly + 13);
    });
    sweep(els.cards, keepCards); sweep(els.folders, keepFolders);
    S.stats = stats;
    if (!ctx) return;
    const alphas = { get: function at(fid) { let a = memo.get(fid); if (a == null) { const f = S.tree.folders.get(fid); a = f ? at(f.parent) * (S.amt.get(fid) || 0) : 0; memo.set(fid, a); } return a; } };
    drawEdges(v, cam, lod, alphas, dim, half, dotR, hideMode, dimMode, nameBoxes);
    for (const d of dots) {
      ctx.globalAlpha = (dim ? 0.12 : 1) * d.a; ctx.fillStyle = d.color; ctx.beginPath(); ctx.arc(d.x, d.y, d.r, 0, Math.PI * 2); if (d.ref) { ctx.strokeStyle = d.color; ctx.lineWidth = 1; ctx.stroke(); } else ctx.fill();
      if (d.sel || d.pulse) { ctx.globalAlpha = dim ? 0.12 : 1; ctx.strokeStyle = "#19e6ff"; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(d.x, d.y, d.r + (d.pulse ? 9 : 5), 0, Math.PI * 2); ctx.stroke(); }
    }
    ctx.font = '11px "Segoe UI", system-ui, sans-serif'; ctx.textBaseline = "top";
    for (const l of C.cullLabels(labels, 260)) { ctx.globalAlpha = (dim ? 0.12 : 1) * l.a * (l.pri >= 900 ? 1 : 0.85); ctx.fillStyle = l.pri >= 900 ? "#dfeaf7" : "#8fa6c4"; ctx.fillText(l.text, l.x, l.y); }
    ctx.globalAlpha = 1;
  }
  function endpoint(rep, cam, v, alphas, lod, half, dotR) {
    if (rep.node != null) { const n = S.lay.nodes.get(rep.node); if (!n) return null; const s = C.toScreen(cam, v, n.x, n.y); return { x: s.x, y: s.y, a: alphas.get(n.fid), card: lod >= 2 && els.cards.has(n.key), pad: dotR + 3, id: n.id }; }
    const c = S.lay.folders.get(rep.folder), f = S.tree.folders.get(rep.folder); if (!c) return null; const s = C.toScreen(cam, v, c.x, c.y);
    return { x: s.x, y: s.y, a: alphas.get(f.parent), pad: C.dotRadius(f.total) + 5, folder: rep.folder };
  }
  // Where a line leaves a card: the edge of its rectangle (or of its dot).
  function trim(p, q, half) {
    const dx = q.x - p.x, dy = q.y - p.y, len = Math.hypot(dx, dy) || 1; let t = p.pad / len;
    if (p.card) t = Math.min(Math.abs(dx) > 0.01 ? (half.w + 3) / Math.abs(dx) : 1e9, Math.abs(dy) > 0.01 ? (half.h + 3) / Math.abs(dy) : 1e9);
    return { x: p.x + dx * Math.min(t, 0.5), y: p.y + dy * Math.min(t, 0.5) };
  }
  // The middle of the part of a line that is on screen (a relation to something far away still gets its label where it can be read).
  function midVisible(p, q, v) {
    let t0 = 0, t1 = 1; const dx = q.x - p.x, dy = q.y - p.y;
    for (const [d, lo, hi] of [[dx, -p.x, v.w - p.x], [dy, -p.y, v.h - p.y]]) {
      if (Math.abs(d) < 1e-9) { if (lo > 0 || hi < 0) return null; continue; }
      const a = lo / d, b = hi / d; t0 = Math.max(t0, Math.min(a, b)); t1 = Math.min(t1, Math.max(a, b));
    }
    if (t0 > t1) return null; const t = (t0 + t1) / 2; return { x: p.x + dx * t, y: p.y + dy * t };
  }
  function line(x1, y1, x2, y2, arrow, width) {
    ctx.lineWidth = width; ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
    if (!arrow) return; const a = Math.atan2(y2 - y1, x2 - x1), s = 5 + width;
    ctx.beginPath(); ctx.moveTo(x2, y2); ctx.lineTo(x2 - s * Math.cos(a - 0.45), y2 - s * Math.sin(a - 0.45)); ctx.lineTo(x2 - s * Math.cos(a + 0.45), y2 - s * Math.sin(a + 0.45)); ctx.closePath(); ctx.fill();
  }
  function drawEdges(v, cam, lod, alphas, dim, half, dotR, hideMode, dimMode, nameBoxes) {
    const list = bundlesNow(), texts = [], lifted = new Map(); let drawn = 0; const base = dim ? 0.12 : 1;
    const near = (id) => id != null && (id === S.sel || id === S.hover || S.picked.has(id));
    // Inside a folder, relations between two things that are both elsewhere are background: kept, faint, unlabelled.
    if (!regionCache || regionCache.ver !== S.ver || regionCache.fid !== S.active) regionCache = { ver: S.ver, fid: S.active, set: S.active === ROOT ? null : C.descendants(S.tree, S.active) };
    const here = regionCache.set, local = (r) => !here || here.has(r.node != null ? S.tree.primaryOf.get(r.node) : r.folder);
    for (const pass of [1, 0]) {                                   // what touches the selection first, so the budget never cuts it
      for (const bun of list) {
        const hot = near(bun.a.node) || near(bun.b.node) || (S.selFolder != null && (bun.a.folder === S.selFolder || bun.b.folder === S.selFolder));
        if ((pass === 1) !== hot) continue; if (drawn >= MAX_EDGES) break;
        if (!hot && lod < 2 && (bun.a.node != null || bun.b.node != null)) {
          // Features drawn as dots do not each get their own lines: inside one folder they are skipped until names show (then drawn faint),
          // and towards anything outside, the folder speaks for them with one line. A selected or hovered dot still shows its own.
          const fa = bun.a.node != null ? S.tree.primaryOf.get(bun.a.node) : null, fb = bun.b.node != null ? S.tree.primaryOf.get(bun.b.node) : null;
          if (fa != null && fa === fb) { if (lod === 0) continue; }
          else {
            const A = fa != null ? { folder: fa, open: true } : bun.a, B = fb != null ? { folder: fb, open: true } : bun.b, key = A.folder + "\u0001" + B.folder;
            if (A.folder === B.folder) continue;
            let up = lifted.get(key); if (!up) { up = { key, a: A, b: B, edges: [] }; lifted.set(key, up); } for (const e of bun.edges) up.edges.push(e); continue;
          }
        }
        const p = endpoint(bun.a, cam, v, alphas, lod, half, dotR), q = endpoint(bun.b, cam, v, alphas, lod, half, dotR); if (!p || !q) continue;
        const a = Math.min(p.a == null ? 0 : p.a, q.a == null ? 0 : q.a); if (a <= 0.03) continue;
        if ((p.x < 0 && q.x < 0) || (p.x > v.w && q.x > v.w) || (p.y < 0 && q.y < 0) || (p.y > v.h && q.y > v.h)) continue;
        let fade = 1; const away = !hot && !local(bun.a) && !local(bun.b); if (away) fade = 0.3;
        if (S.filt.active) { const ma = bun.a.node == null || S.filt.match.has(bun.a.node), mb = bun.b.node == null || S.filt.match.has(bun.b.node); if (!(ma && mb)) { if (hideMode) continue; if (dimMode) fade = 0.2; } }
        const s = trim(p, q, half), e = trim(q, p, half), n = bun.edges.length, single = n === 1, isNode = bun.a.node != null && bun.b.node != null;
        if (isNode && lod < 2 && !hot) fade *= 0.45;
        const color = single ? EDGE_COLOR[bun.edges[0].kind] || "#3a6c9c" : "#3fb7d6";
        ctx.globalAlpha = base * a * fade * (hot ? 1 : 0.55); ctx.strokeStyle = color; ctx.fillStyle = color;
        line(s.x, s.y, e.x, e.y, lod >= 1 || !isNode, hot ? 1.8 : single ? 1 : Math.min(4, 1 + Math.log2(n) * 0.7)); drawn++;
        hitBundles.push({ bun, x1: s.x, y1: s.y, x2: e.x, y2: e.y });
        const text = single ? (lod >= 2 || hot ? relName(bun.edges[0].kind) + (bun.edges[0].label && lod >= 3 ? " · " + bun.edges[0].label : "") : "") : hot ? `${n} relationships` : `×${n}`;
        const m = text && !away && midVisible(s, e, v); if (m) texts.push({ x: m.x - text.length * 2.9 - 4, y: m.y - 8, w: text.length * 5.8 + 8, h: 15, text, pri: (hot ? 1000 : 0) + n, a: a * fade });
      }
    }
    for (const bun of lifted.values()) {
      const ends = [bun.a, bun.b].map((r, i) => { const o = i ? bun.a : bun.b, c = S.lay.folders.get(r.folder), oc = S.lay.folders.get(o.folder), s = C.toScreen(cam, v, c.x, c.y), f = S.tree.folders.get(r.folder);
        const holdsOther = Math.hypot(oc.x - c.x, oc.y - c.y) < c.r;   // the other end is inside this folder: start from its middle, not from its edge
        return { x: s.x, y: s.y, a: r.open ? alphas.get(r.folder) : alphas.get(f.parent), pad: r.open ? (holdsOther ? 0 : c.r * cam.k + 4) : C.dotRadius(f.total) + 5 }; });
      const [p, q] = ends, a = Math.min(p.a || 0, q.a || 0); if (a <= 0.03) continue;
      const s = trim(p, q, half), e = trim(q, p, half), n = bun.edges.length;
      if ((s.x < 0 && e.x < 0) || (s.x > v.w && e.x > v.w) || (s.y < 0 && e.y < 0) || (s.y > v.h && e.y > v.h)) continue;
      const away = !local(bun.a) && !local(bun.b);
      ctx.globalAlpha = base * a * (away ? 0.16 : 0.5); ctx.strokeStyle = "#3fb7d6"; ctx.fillStyle = "#3fb7d6"; line(s.x, s.y, e.x, e.y, true, Math.min(4, 1 + Math.log2(n) * 0.7)); hitBundles.push({ bun, x1: s.x, y1: s.y, x2: e.x, y2: e.y });
      const text = `×${n}`, m = !away && midVisible(s, e, v); if (m) texts.push({ x: m.x - text.length * 2.9 - 4, y: m.y - 8, w: text.length * 5.8 + 8, h: 15, text, pri: n, a });
    }
    ctx.font = '10px "Cascadia Mono", Consolas, ui-monospace, monospace'; ctx.textBaseline = "top";
    for (const t of C.cullLabels(texts, 140, nameBoxes)) { ctx.globalAlpha = base * t.a * 0.92; ctx.fillStyle = "#050b16"; ctx.fillRect(t.x, t.y, t.w, t.h); ctx.globalAlpha = base * t.a; ctx.fillStyle = t.pri >= 1000 ? "#dfeaf7" : "#8fa6c4"; ctx.fillText(t.text, t.x + 4, t.y + 2); }
    ctx.globalAlpha = 1;
  }

  // ---------- focus mode: one card and what it connects to, over the dimmed universe ----------
  function focusOptions(f) {
    const allowed = f.cross ? null : (() => { const path = C.pathOf(S.tree, S.tree.primaryOf.get(f.id)), top = path.length ? path[0].id : ROOT, inside = C.descendants(S.tree, top), ok = new Set(); for (const [id, fid] of S.tree.primaryOf) if (inside.has(fid)) ok.add(id); return ok; })();
    const hidden = new Set(f.rels);
    return { depth: f.mode === "direct" ? 1 : f.mode === "extended" ? 2 : f.depth, inbound: f.mode !== "custom" || f.inbound, outbound: f.mode !== "custom" || f.outbound, limit: 400, allowed,
             edgeOk: (e) => S.filt.edgeOk(e) && !(f.mode === "custom" && hidden.has(e.kind)), nodeOk: (id) => !S.filt.active || S.filt.match.has(id) };
  }
  function refocus(id, keepCam) {
    const f = S.focus; f.id = id; f.ego = C.ego(S.index, id, focusOptions(f)); f.layout = C.focusLayout(f.ego);
    if (!keepCam) { const to = C.fitBox(f.layout.box, vp(), 1.15); f.cam = f.cam || { cx: to.cx, cy: to.cy, k: to.k * 0.7 }; flyTo(to, null); }
    buildFocusBar(); invalidate();
  }
  function enterFocus(id) {
    if (!S.index.cards.has(id)) return;
    if (S.focus) { if (S.focus.id === id) return; S.focus.trail.push(S.focus.id); S.sel = id; S.insp = null; S.focus.cam = null; refocus(id); buildInspector(); return; }
    S.focus = { id, mode: "direct", depth: 3, inbound: true, outbound: true, rels: [], cross: true, trail: [], cam: null, saved: { cam: Object.assign({}, S.cam), open: [...S.open], amt: [...S.amt], sel: S.sel, selFolder: S.selFolder, insp: S.insp, active: S.active } };
    S.zoom = null; S.fly = null; S.sel = id; S.selFolder = null; S.insp = null;      // the note steps aside: click any card in the focus to bring it back
    wrap.classList.add("focusing"); refocus(id); buildInspector();
  }
  // Leaving puts back exactly what was there: camera, entered folders, selection. Focus never changed the graph or anyone's position.
  function exitFocus(silent) {
    const f = S.focus; if (!f) return; S.focus = null; S.fly = null; S.zoom = null;
    S.cam = f.saved.cam; S.open = new Set(f.saved.open); S.amt = new Map(f.saved.amt); S.sel = f.saved.sel; S.selFolder = f.saved.selFolder; S.insp = f.saved.insp; S.active = f.saved.active; S.ver++;
    wrap.classList.remove("focusing"); qs("map-focusbar").classList.add("hidden");
    if (!silent) { buildInspector(); buildChrome(); } invalidate();
  }
  function drawFocus(v) {
    const f = S.focus, cam = f.cam, keep = new Set(), half = { w: (C.NODE_W / 2) * cam.k, h: (C.NODE_H / 2) * cam.k }, at = (id) => { const p = f.layout.pos.get(id); return C.toScreen(cam, v, p.x, p.y); };
    if (ctx) {
      const texts = []; ctx.font = '10px "Cascadia Mono", Consolas, ui-monospace, monospace'; ctx.textBaseline = "top";
      for (const e of f.ego.edges) {
        const a = at(e.from), b = at(e.to), p = { x: a.x, y: a.y, card: true, pad: 0 }, q = { x: b.x, y: b.y, card: true, pad: 0 }, s = trim(p, q, half), t = trim(q, p, half), direct = e.from === f.id || e.to === f.id;
        const color = EDGE_COLOR[e.kind] || "#3a6c9c"; ctx.globalAlpha = direct ? 0.95 : 0.5; ctx.strokeStyle = color; ctx.fillStyle = color; ctx.setLineDash(direct ? [] : [5, 5]); line(s.x, s.y, t.x, t.y, true, direct ? 1.6 : 1); ctx.setLineDash([]);
        const text = relName(e.kind) + (e.label && cam.k > 0.8 ? " · " + e.label : ""); texts.push({ x: (s.x + t.x) / 2 - text.length * 2.9 - 4, y: (s.y + t.y) / 2 - 8, w: text.length * 5.8 + 8, h: 15, text, pri: direct ? 10 : 1 });
      }
      for (const t of C.cullLabels(texts, 200)) { ctx.globalAlpha = 0.92; ctx.fillStyle = "#050b16"; ctx.fillRect(t.x, t.y, t.w, t.h); ctx.globalAlpha = 1; ctx.fillStyle = t.pri > 1 ? "#dfeaf7" : "#8fa6c4"; ctx.fillText(t.text, t.x + 4, t.y + 2); }
      ctx.globalAlpha = 1;
    }
    for (const n of f.ego.nodes.values()) {
      const s = at(n.id); if (s.x < -half.w - 20 || s.x > v.w + half.w + 20 || s.y < -half.h - 20 || s.y > v.h + half.h + 20) continue;
      const key = "focus:" + n.id, c = S.index.cards.get(n.id); keep.add(key); let g = els.focus.get(key);
      if (!g) { g = cardEl(key, n.id, "focus"); els.focus.set(key, g); gFocus.append(g); }
      fillCard(g, c, {}); g.setAttribute("class", "node " + c.kind + (n.depth === 0 ? " center" : "") + (n.id === S.sel ? " sel" : "") + (n.depth > 1 ? " far" : ""));
      const scale = cam.k * (n.depth === 0 ? 1.15 : 1); g.setAttribute("transform", `translate(${(s.x - (C.NODE_W / 2) * scale).toFixed(1)},${(s.y - (C.NODE_H / 2) * scale).toFixed(1)}) scale(${scale.toFixed(4)})`);
    }
    sweep(els.focus, keep);
  }
  function buildFocusBar() {
    const f = S.focus, bar = qs("map-focusbar"); bar.replaceChildren(); bar.classList.remove("hidden");
    bar.append(el("span", "FOCUS", "eyebrow"), el("b", title(f.id)));
    const modes = el("span", null, "seg");
    for (const [m, label, tip] of [["direct", "Direct", "What it connects to directly"], ["extended", "Extended", "Those, and what they connect to"], ["custom", "Custom", "Choose depth, direction and relation types"]]) {
      const b = btn(label, () => { f.mode = m; refocus(f.id); }, "mini " + (f.mode === m ? "primary" : "secondary")); b.title = tip; b.setAttribute("aria-pressed", String(f.mode === m)); modes.append(b);
    }
    bar.append(modes);
    if (f.mode === "custom") {
      const box = el("span", null, "focus-custom"), depth = el("input"); depth.type = "number"; depth.min = 1; depth.max = 12; depth.value = f.depth; depth.className = "focus-depth"; depth.setAttribute("aria-label", "Depth");
      depth.onchange = () => { f.depth = Math.max(1, Math.min(12, Number(depth.value) || 1)); refocus(f.id); };
      const check = (label, key) => { const l = el("label", null, "chk"), i = el("input"); i.type = "checkbox"; i.checked = f[key]; i.onchange = () => { f[key] = i.checked; refocus(f.id); }; l.append(i, document.createTextNode(" " + label)); return l; };
      box.append(el("span", "depth", "muted"), depth, check("inbound", "inbound"), check("outbound", "outbound"), check("other folders", "cross"));
      for (const kind of S.index.rels.keys()) { const l = el("label", null, "chk"), i = el("input"); i.type = "checkbox"; i.checked = !f.rels.includes(kind); i.onchange = () => { f.rels = i.checked ? f.rels.filter((k) => k !== kind) : [...f.rels, kind]; refocus(f.id); }; l.append(i, document.createTextNode(" " + relName(kind))); box.append(l); }
      bar.append(box);
    }
    const n = f.ego.nodes.size - 1; bar.append(el("span", `${n} connected feature${n === 1 ? "" : "s"}`, "muted"));
    if (f.ego.truncated) bar.append(el("span", "Showing the first 400: lower the depth or filter to see the rest.", "warn-text"));
    if (f.trail.length) bar.append(btn("← " + title(f.trail[f.trail.length - 1]), () => { const prev = f.trail.pop(); S.sel = prev; S.insp = null; f.cam = null; refocus(prev); buildInspector(); }, "mini secondary"));
    bar.append(btn("Exit focus", () => exitFocus(), "mini secondary"));
  }

  // ---------- chrome: breadcrumb, navigation, counter ----------
  function buildChrome() {
    if (!S.tree) return; const crumbs = qs("map-crumbs"); crumbs.replaceChildren();
    const rootBtn = btn(S.project ? S.project.name : "My mod", () => qs("map-home").click(), "crumb"); crumbs.append(rootBtn);
    for (const f of C.pathOf(S.tree, S.active)) { crumbs.append(el("span", "›", "crumb-sep")); crumbs.append(btn(f.name, () => enterFolder(f.id), "crumb")); }
    qs("map-back").disabled = S.histI <= 0; qs("map-fwd").disabled = S.histI >= S.hist.length - 1; qs("map-up").disabled = S.active === ROOT; qs("map-fit-region").disabled = S.active === ROOT;
    qs("map-empty").classList.toggle("hidden", S.index.cards.size > 0 || Object.keys(S.meta.folders).length > 0);
    qs("map-filter-btn").classList.toggle("active", S.filt.active); qs("map-filter-btn").textContent = S.filt.active ? `Filters · ${S.filters.kinds.length + S.filters.rels.length + S.filters.tags.length}` : "Filters";
  }
  let countText = "";
  function updateCount() {
    const total = S.filt.total, st = S.stats || { drawn: 0, outside: 0, collapsed: 0 };
    const text = `${S.filt.active ? S.filt.match.size : total} / ${total} features ${S.filt.active && S.filters.mode === "dim" ? "match" : "visible"}`;
    const detail = `${st.drawn} on screen · ${st.collapsed} inside folders · ${st.outside} outside the view` + (S.filt.active ? ` · ${total - S.filt.match.size} ${S.filters.mode === "dim" ? "dimmed" : "hidden"} by filters` : "");
    if (text + detail === countText) return; countText = text + detail;
    const box = qs("map-count"); box.replaceChildren(el("b", text), el("span", detail, "muted"));
    if (S.filt.active) box.append(btn("Reset filters", () => resetFilters(), "mini secondary"));
  }

  // ---------- search ----------
  function showResults() {
    const box = qs("map-results"), q = qs("map-search").value; box.replaceChildren();
    if (!q.trim()) { box.classList.add("hidden"); return; }
    const scope = qs("map-scope").value === "here" ? S.active : ROOT, hits = C.search(S.index, S.tree, S.inferred, S.meta, q, scope), needle = q.trim().replace(/^#/, "").toLowerCase();
    const tags = [...C.allTags(S.index, S.inferred, S.meta).values()].filter((t) => needle && t.tag.toLowerCase().includes(needle)).slice(0, 4);
    for (const t of tags) { const b = btn("", () => { toggleTag(t.tag); qs("map-search").value = ""; showResults(); }, "result"); b.append(el("span", "#" + t.tag, "r-title"), el("span", `tag · ${t.count} feature${t.count === 1 ? "" : "s"} · ${S.filters.tags.includes(C.tagKey(t.tag)) ? "stop filtering by it" : "filter by it"}`, "r-where")); box.append(b); }
    for (const h of hits) {
      const b = btn("", () => { box.classList.add("hidden"); if (h.type === "folder") { enterFolder(h.id); selectFolder(h.id); } else reveal(h.id); }, "result");
      b.append(el("span", h.title, "r-title"), el("span", [h.type === "folder" ? "folder" : h.kind, h.where || (h.type === "folder" ? "top level" : ""), h.why].filter(Boolean).join(" · "), "r-where")); box.append(b);
    }
    if (!hits.length && !tags.length) box.append(el("div", scope === ROOT ? "Nothing in this mod matches." : "Nothing in this folder matches. Try the entire mod.", "muted r-none"));
    box.classList.remove("hidden");
  }

  // ---------- filters ----------
  function refilter() { S.filt = C.applyFilters(S.index, S.inferred, S.meta, S.filters); S.ver++; if (S.focus) refocus(S.focus.id, true); scheduleSave(); buildChrome(); if (!qs("map-filters").classList.contains("hidden")) buildFilters(); invalidate(); }
  function resetFilters() { S.filters = Object.assign(C.noFilters(), { mode: S.filters.mode }); refilter(); }
  function toggleTag(tag) { const k = C.tagKey(tag); S.filters.tags = S.filters.tags.includes(k) ? S.filters.tags.filter((x) => x !== k) : [...S.filters.tags, k]; refilter(); }
  function buildFilters() {
    const box = qs("map-filters"); box.replaceChildren();
    const head = el("div", null, "pop-head"); head.append(el("b", "Filters"), btn("✕", () => box.classList.add("hidden"), "mini secondary")); box.append(head);
    box.append(el("div", "Filtering only changes what you see. Nothing is deleted and no coder is told anything.", "muted"));
    const toggle = (label, on, fn) => { const l = el("label", null, "chk"), i = el("input"); i.type = "checkbox"; i.checked = on; i.onchange = () => fn(i.checked); l.append(i, document.createTextNode(" " + label)); return l; };
    const list = (key, name, show) => (name, count) => toggle(`${show(name)} (${count})`, !S.filters[key].includes(name), (on) => { S.filters[key] = on ? S.filters[key].filter((k) => k !== name) : [...S.filters[key], name]; refilter(); });
    const recipes = C.RECIPE_KINDS.filter((k) => S.index.rels.has(k));
    if (recipes.length) { box.append(el("div", "Recipes", "eyebrow")); box.append(toggle("Show recipes (crafting and smelting)", !recipes.every((k) => S.filters.rels.includes(k)), (on) => { S.filters.rels = S.filters.rels.filter((k) => !recipes.includes(k)); if (!on) S.filters.rels.push(...recipes); refilter(); })); }
    box.append(el("div", "Feature types", "eyebrow")); const kinds = el("div", null, "chk-grid"); for (const [k, n] of S.index.kinds) kinds.append(list("kinds", k, (x) => C.KIND_PLURAL[x] || C.cap(x))(k, n)); box.append(kinds);
    if (S.index.rels.size) { box.append(el("div", "Relationships", "eyebrow")); const rels = el("div", null, "chk-grid"); for (const [k, n] of S.index.rels) rels.append(list("rels", k, relName)(k, n)); box.append(rels); }
    const tags = [...C.allTags(S.index, S.inferred, S.meta).values()].sort((a, b) => b.count - a.count).slice(0, 40);
    if (tags.length) { box.append(el("div", "Tags (a feature must have all the selected ones)", "eyebrow")); const row = el("div", null, "tag-row"); for (const t of tags) { const b = btn(`${t.tag} ${t.count}`, () => toggleTag(t.tag), "tag" + (S.filters.tags.includes(C.tagKey(t.tag)) ? " on" : "")); b.setAttribute("aria-pressed", String(S.filters.tags.includes(C.tagKey(t.tag)))); row.append(b); } box.append(row); }
    box.append(el("div", "What does not match", "eyebrow")); const seg = el("div", null, "seg");
    for (const [m, label] of [["hide", "Hide it"], ["dim", "Dim it"]]) { const b = btn(label, () => { S.filters.mode = m; refilter(); }, "mini " + (S.filters.mode === m ? "primary" : "secondary")); b.setAttribute("aria-pressed", String(S.filters.mode === m)); seg.append(b); }
    box.append(seg); const acts = el("div", null, "actions"); acts.append(btn("Reset filters", () => resetFilters(), "secondary")); box.append(acts);
  }
  function closePops() { qs("map-results").classList.add("hidden"); }

  // ---------- folders: management ----------
  async function newFolder(parent) {
    const where = parent ? ` inside ${S.tree.folders.get(parent).name}` : "";
    const name = await promptBox(`A folder only organises the map${where}. It never moves or changes the mod's files, and its name is never an instruction to a coder.`, "", { title: "New folder", ok: "Create", label: "Name", required: true, multiline: false });
    if (name == null) return; const out = C.createFolder(S.meta, name, parent); setMeta(out.meta); selectFolder(out.id); S.pulse = { id: out.id, until: performance.now() + 1600 };
  }
  function folderInspector(box, fid, full) {
    const f = S.tree.folders.get(fid), stored = S.meta.folders[fid], sug = S.tree.suggestions.get(fid) || [];
    box.append(el("div", f.virtual ? "automatic group" : "folder · " + (f.mode === "auto" ? "automatic" : f.mode === "suggest" ? "suggests" : "manual"), "eyebrow"), el("h3", f.name));
    const path = C.pathLabel(S.tree, f.parent); box.append(el("div", `${f.total} feature${f.total === 1 ? "" : "s"}` + (f.children.length ? ` · ${f.children.length} subfolder${f.children.length === 1 ? "" : "s"}` : "") + (f.refs.length ? ` · ${f.refs.length} reference${f.refs.length === 1 ? "" : "s"}` : "") + (path ? ` · in ${path}` : ""), "muted"));
    const acts = el("div", null, "actions insp-actions"); box.append(acts);
    acts.append(btn("Enter", () => enterFolder(fid), "primary"));
    if (sug.length && !full) acts.append(btn(`${sug.length} suggestion${sug.length === 1 ? "" : "s"}`, () => { S.insp.full = true; buildInspector(); }, "secondary"));
    acts.append(btn(full ? "Collapse" : "Expand", () => { S.insp.full = !full; buildInspector(); }, "secondary"));
    if (!full) return;
    if (f.virtual) {
      box.append(el("p", "Features of this kind that you have not filed in a folder are shown here automatically. Drag a card onto a folder to file it, or keep this group as a folder of your own.", "muted"));
      const a = el("div", null, "actions"); a.append(btn("Keep as a folder", () => { const out = C.createFolder(S.meta, f.name, null, { mode: "auto", rules: { kinds: f.rules.kinds, tags: [], words: [] } }); setMeta(out.meta, `"${f.name}" is now your folder; it keeps collecting ${f.name.toLowerCase()} automatically.`); selectFolder(out.id); }, "secondary")); box.append(a); return;
    }
    if (sug.length) {
      box.append(el("div", "Suggested for this folder", "eyebrow")); const ul = el("div", null, "sug-list");
      for (const id of sug.slice(0, 30)) { const row = el("div", null, "sug-row"); row.append(el("span", title(id)), btn("Accept", () => setMeta(C.assign(S.meta, id, fid, { primary: true })), "mini"), btn("Dismiss", () => setMeta(C.dismissSuggestion(S.meta, id, fid)), "mini secondary")); ul.append(row); }
      box.append(ul); if (sug.length > 1) { const a = el("div", null, "actions"); a.append(btn(`Accept all ${sug.length}`, () => { let m = S.meta; for (const id of sug) m = C.assign(m, id, fid, { primary: true }); setMeta(m); }, "secondary")); box.append(a); }
    }
    box.append(el("div", "How features get here", "eyebrow"));
    const mode = el("select"); for (const [v, label] of [["manual", "Manual: only what I put here"], ["suggest", "Suggest: propose matches, I approve"], ["auto", "Auto: file matches for me"]]) { const o = el("option", label); o.value = v; o.selected = stored.mode === v; mode.append(o); }
    mode.setAttribute("aria-label", "Organisation mode"); box.append(mode);
    const rules = el("div", null, "rules"); box.append(rules);
    const kinds = el("div", null, "chk-grid"), kindBoxes = [];
    for (const k of S.index.kinds.keys()) { const l = el("label", null, "chk"), i = el("input"); i.type = "checkbox"; i.value = k; i.checked = (stored.rules.kinds || []).includes(k); kindBoxes.push(i); l.append(i, document.createTextNode(" " + (C.KIND_PLURAL[k] || C.cap(k)))); kinds.append(l); }
    const tagsIn = el("input"), wordsIn = el("input"); tagsIn.placeholder = "tags, comma separated"; wordsIn.placeholder = "words in the name, comma separated"; tagsIn.value = (stored.rules.tags || []).join(", "); wordsIn.value = (stored.rules.words || []).join(", ");
    tagsIn.setAttribute("aria-label", "Rule: tags"); wordsIn.setAttribute("aria-label", "Rule: words in the name");
    rules.append(el("div", "A feature matches when it is one of these types, has one of these tags and has one of these words (rules left empty do not count).", "muted"), kinds, tagsIn, wordsIn);
    rules.append(el("div", "Rules decide where a feature is shown, nothing else: they never change what a coder builds.", "muted"));
    const split = (s) => s.split(",").map((x) => x.trim()).filter(Boolean);
    const saveRules = () => setMeta(C.setFolder(S.meta, fid, { mode: mode.value, rules: { kinds: kindBoxes.filter((i) => i.checked).map((i) => i.value), tags: split(tagsIn.value), words: split(wordsIn.value) } }));
    mode.onchange = saveRules; const ra = el("div", null, "actions"); ra.append(btn("Save rules", saveRules, "secondary")); rules.append(ra); rules.classList.toggle("hidden", stored.mode === "manual");
    box.append(el("div", "Folder", "eyebrow")); const a = el("div", null, "actions");
    a.append(btn("Rename", async () => { const name = await promptBox("New name:", f.name, { title: "Rename folder", ok: "Rename", required: true, multiline: false }); if (name != null) setMeta(C.renameFolder(S.meta, fid, name)); }, "secondary"));
    a.append(btn("New subfolder", () => newFolder(fid), "secondary"));
    a.append(btn("Delete", async () => {
      if (!await confirmBox(`Delete the folder "${f.name}"? Its ${f.total} feature${f.total === 1 ? "" : "s"} stay in the mod and on the map, and its subfolders move up one level. No file of the mod changes.`, { title: "Delete folder", ok: "Delete folder", danger: true })) return;
      S.selFolder = null; S.insp = null; setMeta(C.deleteFolder(S.meta, fid), `Folder "${f.name}" deleted. Its features are still here.`);
    }, "secondary")); box.append(a);
    const inside = C.descendants(S.tree, fid), others = [...S.tree.folders.values()].filter((o) => o.id !== ROOT && !o.virtual && !inside.has(o.id));
    if (others.length || stored.parent) {
      const move = el("select"); move.setAttribute("aria-label", "Move this folder into"); const top = el("option", "Move into… (top level)"); top.value = ""; move.append(top);
      for (const o of others) { const op = el("option", C.pathLabel(S.tree, o.id)); op.value = o.id; op.selected = stored.parent === o.id; move.append(op); }
      move.onchange = () => { try { setMeta(C.moveFolder(S.meta, fid, move.value || null)); } catch (e) { toast(e.message, "bad"); } }; box.append(move);
    }
  }

  // ---------- the floating inspector ----------
  function closeInspector() { S.insp = null; S.sel = null; S.selFolder = null; buildInspector(); invalidate(); }
  function section(box, name, open) { const d = el("details", null, "insp-sec"); d.open = !!open; d.append(el("summary", name)); box.append(d); return d; }
  function buildInspector() {
    const box = qs("map-inspector"); box.replaceChildren(); const i = S.insp;
    if (!i || S.multi) { box.classList.add("hidden"); link.setAttribute("opacity", "0"); return; }
    box.className = "map-inspector " + (i.full ? "full" : "quick"); box.setAttribute("role", "dialog"); box.setAttribute("aria-label", "Details");
    const close = btn("✕", () => closeInspector(), "mini secondary insp-close"); close.title = "Close (Esc)"; close.setAttribute("aria-label", "Close"); box.append(close);
    if (i.type === "folder") folderInspector(box, i.id, i.full);
    else if (i.type === "bundle") bundleInspector(box, i.bun);
    else cardInspector(box, i.id, i.full, i.modify);
    invalidate();
  }
  function bundleInspector(box, bun) {
    const name = (r) => (r.node != null ? title(r.node) : S.tree.folders.get(r.folder).name);
    box.append(el("div", "relationships", "eyebrow"), el("h3", `${name(bun.a)} → ${name(bun.b)}`), el("div", `${bun.edges.length} relationship${bun.edges.length === 1 ? "" : "s"} share this line`, "muted"));
    const ul = el("ul", null, "rel-list");
    for (const e of bun.edges.slice(0, 80)) { const li = el("li"); li.append(relLink(e.from), el("span", ` ${relName(e.kind)}${e.label ? " (" + e.label + ")" : ""} → `, "muted"), relLink(e.to)); ul.append(li); }
    box.append(ul); if (bun.edges.length > 80) box.append(el("div", `…and ${bun.edges.length - 80} more. Enter the folder to see them all.`, "muted"));
  }
  // Following a relation is travel: the camera goes there and the way back is kept. Inside Focus it re-centres the focus instead.
  function relLink(id) { const b = btn(title(id), () => { if (S.focus) enterFocus(id); else reveal(id); }, "linklike"); b.title = C.pathLabel(S.tree, S.tree.primaryOf.get(id)) || ""; return b; }
  function cardInspector(box, cid, full, modify) {
    const p = S.project, c = S.index.cards.get(cid); if (!c) { S.insp = null; box.classList.add("hidden"); return; }
    const tags = C.tagsFor(cid, S.inferred, S.meta), canChange = c.kind !== "vanilla";
    box.append(el("div", kindName(c) + (c.status ? " · " + c.status : ""), "eyebrow"), el("h3", c.title || c.id));
    box.append(el("div", [C.cap(kindName(c)), ...tags.filter((t) => t.tag !== (S.inferred.get(cid) || [])[0]).slice(0, 2).map((t) => t.tag)].join(" • "), "muted insp-type"));
    const acts = el("div", null, "actions insp-actions"); box.append(acts);
    if (canChange) { const m = btn("Modify with Minion", () => { S.insp.full = true; S.insp.modify = true; buildInspector(); }, "primary"); m.title = "Write the change you want; nothing is sent until you press Send"; acts.append(m); }
    acts.append(btn(full ? "Collapse" : "Expand", () => { S.insp.full = !full; S.insp.modify = false; buildInspector(); }, "secondary"));
    if (!(S.focus && S.focus.id === cid)) acts.append(btn("Focus", () => enterFocus(cid), "secondary"));
    if (!full) return;
    box.append(el("div", c.id, "fid"));
    if (c.description) section(box, "Description", true).append(el("p", c.description));
    const props = [["Type", kindName(c)], ["Id", c.id], ["Status", c.status], ["Owner", c.owner], ["Pieces", c.pieces && c.pieces.length], ["Produces", (c.produces || []).join(", ")], ["Builds on", (c.derived_from || []).join(", ")]].filter(([, v]) => v);
    const ps = section(box, "Properties", false), dl = el("dl", null, "props"); for (const [k, v] of props) dl.append(el("dt", k), el("dd", String(v))); ps.append(dl);
    if (c.pieces) { const ul = el("ul"); for (const pc of c.pieces) ul.append(el("li", `${pc.id} (${pc.kind})`)); ps.append(el("div", "Pieces", "eyebrow"), ul); }
    // tags: what the graph says it is (dashed) and what the user says (solid). Neither is an instruction to a coder.
    const ts = section(box, `Tags (${tags.length})`, true), row = el("div", null, "tag-row");
    for (const t of tags) { const chip = el("span", t.tag, "tag" + (t.inferred ? " inferred" : "")); chip.title = t.inferred ? "Inferred from what this feature is and connects to" : "Added by you"; const x = btn("×", () => setMeta(C.removeTag(S.meta, cid, t.tag, S.inferred)), "tag-x"); x.setAttribute("aria-label", "Remove tag " + t.tag); chip.append(x); row.append(chip); }
    const add = el("input"); add.placeholder = "add a tag…"; add.className = "tag-add"; add.setAttribute("aria-label", "Add a tag"); add.onkeydown = (e) => { if (e.key === "Enter" && add.value.trim()) { e.preventDefault(); try { setMeta(C.addTag(S.meta, cid, add.value)); } catch (err) { toast(err.message, "bad"); } } };
    row.append(add); ts.append(row);
    const removed = ((S.meta.tags[cid] || {}).remove || []); if (removed.length) { const r = el("div", "Removed by you: ", "muted"); for (const t of removed) r.append(btn(t + " ↺", () => setMeta(C.addTag(S.meta, cid, t)), "linklike")); ts.append(r); }
    // folders
    const mem = S.tree.foldersOf.get(cid), fs = section(box, "Folders", true), ful = el("ul", null, "rel-list");
    mem.forEach((m, n) => { const li = el("li"); li.append(btn(C.pathLabel(S.tree, m.fid), () => enterFolder(m.fid), "linklike"), el("span", m.how === "unfiled" ? " · not filed (automatic group)" : (n === 0 ? " · lives here" : " · also shown here") + (m.how === "auto" ? " (by the folder's rules)" : ""), "muted")); if (m.how !== "unfiled") li.append(btn("×", () => setMeta(C.unassign(S.meta, cid, m.fid)), "tag-x")); ful.append(li); });
    fs.append(ful);
    const real = [...S.tree.folders.values()].filter((f) => f.id !== ROOT && !f.virtual && !mem.some((m) => m.fid === f.id));
    if (real.length) {
      const pick = el("select"); pick.setAttribute("aria-label", "Folder"); for (const f of real) { const o = el("option", C.pathLabel(S.tree, f.id)); o.value = f.id; pick.append(o); }
      const fa = el("div", null, "actions"); fa.append(btn("Move here", () => setMeta(C.assign(S.meta, cid, pick.value, { from: mem[0].how === "unfiled" ? null : mem[0].fid, primary: true })), "secondary"), btn("Also show here", () => setMeta(C.assign(S.meta, cid, pick.value, { primary: false })), "secondary"));
      fs.append(pick, fa);
    } else if (!Object.keys(S.meta.folders).length) fs.append(el("div", "Create a folder (＋ Folder) to file this feature yourself.", "muted"));
    // relationships: each one is a way to travel
    const rel = S.index.out.get(cid).concat(S.index.inc.get(cid));
    if (rel.length) {
      const rs = section(box, `Relationships (${rel.length})`, true), ul = el("ul", null, "rel-list");
      for (const e of rel) { const outward = e.from === cid, other = outward ? e.to : e.from, li = el("li"), where = C.pathLabel(S.tree, S.tree.primaryOf.get(other)); li.append(el("span", `${outward ? "→" : "←"} ${relName(e.kind)}${e.label ? " (" + e.label + ")" : ""} `, "muted"), relLink(other)); if (where) li.append(el("span", " · " + where, "muted")); ul.append(li); }
      rs.append(ul);
    }
    if (c.acceptance && c.acceptance.length) { const ul = el("ul"); for (const a of c.acceptance) ul.append(el("li", a)); section(box, "Acceptance criteria", false).append(ul); }
    if (c.files && c.files.length) { const ul = el("ul", null, "files"); for (const f of c.files.slice(0, 12)) ul.append(el("li", f)); section(box, `Implemented in (${c.files.length})`, false).append(ul); }
    if (c.open_tasks && c.open_tasks.length) { const ul = el("ul"); for (const t of c.open_tasks) ul.append(el("li", `${t.id} · ${t.state}`)); section(box, "Open tasks", true).append(ul); }
    if (c.history && c.history.length) { const ul = el("ul", null, "hist"); for (const h of c.history.slice(-5).reverse()) ul.append(el("li", `${ago(h.at)} · ${h.by}: ${h.what}`)); section(box, "History", false).append(ul); }
    if (!canChange) return;
    // Modify with Minion: the only place a coder is asked for anything, and only with the user's own words.
    const ms = section(box, "Modify with Minion", true); ms.append(el("div", "Request a change", "eyebrow"));
    const ta = el("textarea"); ta.rows = 3; ta.placeholder = c.kind === "custom" ? "e.g. make the inventory 25 slots instead of 20" : c.kind === "mob" ? "e.g. make it drop 2 scrap instead of 1 and walk faster" : "e.g. 1500 durability instead of 1200"; ms.append(ta);
    ms.append(el("div", "The coder gets this card's description, files and relations with your words. Folders and tags are not sent.", "muted"));
    const a2 = el("div", null, "actions");
    a2.append(btn("Send to a coder", async () => { if (!ta.value.trim()) throw new Error("Describe the change first"); const out = await api(`/api/project/${p.id}/change`, { card: cid, request: ta.value.trim() }); if (await confirmBox(`Task ${out.task} created with this card's context. Start the coder now?`)) { await api(`/api/project/${p.id}/dispatch`, { task: out.task }); toast("Coder started on the change.", "ok"); } await openProject(p.id); }, "primary"));
    if (c.kind === "mob") a2.append(btn("Open in Mobs", () => document.querySelector('[data-tab="features"]').click(), "secondary"));
    if (c.kind === "material" || c.kind === "item" || c.kind === "block" || c.kind === "food") a2.append(btn("Open in Items", () => { document.querySelector('[data-tab="features"]').click(); document.querySelector('[data-sub="items"]').click(); }, "secondary"));
    if (c.kind === "custom") {   // its projectiles (once they have their own art) can fly as 3D models
      const pbox = el("div", null, "card-projectiles"); ms.append(pbox);
      api(`/api/project/${p.id}/projectiles`).then((all) => {
        const mine = Object.entries(all || {}).filter(([, a]) => a.card === cid); if (!mine.length) return;
        pbox.append(el("div", "Projectiles", "eyebrow"));
        for (const [pid3, a] of mine) {
          const row2 = el("div", null, "proj-line"); row2.append(el("span", `${pid3}: ${a.what}`, "muted"));
          row2.append(btn(a.model3d ? "3D model…" : "Make it 3D", () => make3d(p, { identifier: pid3, label: pid3, model3d: a.model3d, projectile: true }), "mini"));
          if (a.model3d) row2.append(btn("Open in Blockbench", () => openModel(p, { projectile: pid3 }), "mini secondary"));
          if (a.model3d) row2.append(btn("Animate", async () => {
            const v = await promptBox("How does it move while it flies? (the designer animates it; its shape and texture stay as they are)", "", { title: `Animate ${pid3}`, ok: "Animate", multiline: true, required: true });
            if (v == null) return;
            const out = await api(`/api/project/${p.id}/animate`, { kind: "projectile", ident: pid3, anims: [{ name: "flight", what: v.trim() }] });
            if (await confirmBox("Saved. Start the designer now?", { title: "Start the designer", ok: "Start designer", cancel: "Not now" })) { await api(`/api/project/${p.id}/dispatch`, { task: out.first || out.task }); toast("Designer animating…", "ok"); }
          }, "mini secondary"));
          pbox.append(row2);
        }
      }).catch(() => {});
      a2.append(btn("Give it its own art", async () => {
        if (!await confirmBox("A coder finds every visual this feature borrows from vanilla and gives it its own placeholder; then the designer paints them and the coder wires them in. Nothing else changes. Start the coder now?", { title: "Own art for this feature", ok: "Start coder", cancel: "Not now" })) return;
        const out = await api(`/api/project/${p.id}/art-pass`, { card: cid });
        await api(`/api/project/${p.id}/dispatch`, { task: out.task }); toast("Coder started: it lists what needs art; the designer follows.", "ok"); await refreshProject(p.id);
      }, "secondary"));
      a2.append(btn("Edit description", async () => { const d = await promptBox("Description:", c.description || ""); if (d == null) return; await api(`/api/project/${p.id}/card`, { card: cid, description: d }); toast("Card updated.", "ok"); await openProject(p.id); }, "secondary"));
    }
    ms.append(a2);
    if (modify) { S.insp.modify = false; setTimeout(() => { ta.focus(); if (ms.scrollIntoView) ms.scrollIntoView({ block: "nearest" }); }, 0); }
  }
  // The inspector lives in screen space: always readable, beside what it describes, inside the window.
  function placeInspector(v) {
    const box = qs("map-inspector"), i = S.insp; if (!i || box.classList.contains("hidden")) { link.setAttribute("opacity", "0"); return; }
    let ax, ay, half = 14, halfH = 14;
    if (i.type === "bundle") { ax = i.at.x; ay = i.at.y; }
    else if (i.type === "folder") { const c = S.lay.folders.get(i.id); if (!c) return; const s = C.toScreen(S.cam, v, c.x, c.y), entered = (S.amt.get(i.id) || 0) > 0.5; ax = s.x; ay = entered ? Math.max(58, s.y - c.r * S.cam.k - 10) : s.y; half = entered ? 60 : C.dotRadius(S.tree.folders.get(i.id).total) + 6; halfH = half; }
    else if (S.focus && S.focus.layout.pos.has(i.id)) { const p = S.focus.layout.pos.get(i.id), s = C.toScreen(S.focus.cam, v, p.x, p.y); ax = s.x; ay = s.y; half = (C.NODE_W / 2) * S.focus.cam.k; halfH = (C.NODE_H / 2) * S.focus.cam.k; }
    else {
      const rep = C.repOf(S.tree, S.open, i.id);
      if (rep.node != null) { const n = S.lay.nodes.get(i.id), s = C.toScreen(S.cam, v, n.x, n.y), isCard = els.cards.has(n.key); ax = s.x; ay = s.y; half = isCard ? (C.NODE_W / 2) * S.cam.k : 9; halfH = isCard ? (C.NODE_H / 2) * S.cam.k : 9; }
      else { const c = S.lay.folders.get(rep.folder), s = C.toScreen(S.cam, v, c.x, c.y); ax = s.x; ay = s.y; half = halfH = C.dotRadius(S.tree.folders.get(rep.folder).total) + 6; }
    }
    const w = box.offsetWidth || (i.full ? 360 : 270), h = box.offsetHeight || (i.full ? 420 : 130), gap = 18, fits = (x, y) => x >= 8 && y >= 8 && x + w <= v.w - 8 && y + h <= v.h - 8;
    const cy = Math.max(8, Math.min(v.h - h - 8, ay - Math.min(h / 2, 60))), cx = Math.max(8, Math.min(v.w - w - 8, ax - w / 2));
    const spots = [[ax + half + gap, cy], [ax - half - gap - w, cy], [cx, ay + halfH + gap], [cx, ay - halfH - gap - h]];
    let [x, y] = spots.find(([px, py]) => fits(px, py)) || [Math.max(8, Math.min(v.w - w - 8, ax + half + gap)), cy];
    x = Math.max(8, Math.min(Math.max(8, v.w - w - 8), x)); y = Math.max(8, Math.min(Math.max(8, v.h - h - 8), y));
    box.style.left = Math.round(x) + "px"; box.style.top = Math.round(y) + "px";
    const offscreen = ax < -40 || ax > v.w + 40 || ay < -40 || ay > v.h + 40, tx = Math.max(x, Math.min(x + w, ax)), ty = Math.max(y, Math.min(y + h, ay));
    link.setAttribute("x1", ax); link.setAttribute("y1", ay); link.setAttribute("x2", tx); link.setAttribute("y2", ty); link.setAttribute("opacity", offscreen || (tx === ax && ty === ay) ? "0" : "1");
  }

  // ---------- Select cards: click several cards, then send ONE change to all of them (one coder task with every card's context) ----------
  function mapPick(cid) {
    const c = S.index.cards.get(cid); if (!c || c.kind === "vanilla") { toast("Vanilla and tab cards cannot be changed.", "bad"); return; }
    if (S.picked.has(cid)) S.picked.delete(cid); else S.picked.add(cid);
    invalidate(); openMulti();
  }
  function openMulti() {
    const p = S.project, side = qs("map-side"); side.replaceChildren(); side.classList.remove("hidden");
    const ids = [...S.picked], cards = ids.map((id) => S.index.cards.get(id)).filter(Boolean);
    side.append(el("div", "SELECT CARDS", "eyebrow"), el("h3", ids.length ? `${ids.length} card${ids.length === 1 ? "" : "s"} selected` : "Click cards on the map"));
    side.append(el("div", "Every card you click joins the selection; click again to drop it. Zoom into a folder to reach its cards; the selection stays as you travel. One change request goes to all of them as a single coder task, with each card's files and relations.", "muted"));
    const list = el("div", null, "picked-list");
    for (const c of cards) { const row = el("div", null, "picked-row"); row.append(el("span", `${c.title || c.id} `), el("small", c.kind, "muted"), btn("×", () => mapPick(c.id), "mini secondary")); list.append(row); }
    side.append(list);
    const ta = el("textarea"); ta.placeholder = "the change, once, for all of them"; ta.rows = 4; ta.className = "multi-request"; side.append(el("div", "Request a change", "eyebrow"), ta);
    const acts = el("div", null, "actions");
    acts.append(btn(ids.length ? `Send to a coder (${ids.length})` : "Send to a coder", async () => {
      if (!ids.length) throw new Error("Click at least one card on the map first"); if (!ta.value.trim()) throw new Error("Describe the change first");
      const out = await api(`/api/project/${p.id}/change`, { card: ids[0], request: ta.value.trim(), cards: ids.slice(1) });
      if (await confirmBox(`Task ${out.task} created for ${ids.length} card(s). Start the coder now?`)) { await api(`/api/project/${p.id}/dispatch`, { task: out.task }); toast("Coder started on the change.", "ok"); }
      S.picked.clear(); S.multi = false; qs("map-multi").classList.remove("active"); side.classList.add("hidden"); await openProject(p.id);
    }, "primary"));
    acts.append(btn("Clear", () => { S.picked.clear(); invalidate(); openMulti(); }, "secondary"));
    side.append(acts);
  }
  // Opens a card's details wherever it is (used by the activity banner and other tabs).
  function openCard(p, cid) {
    if (!S.index || !S.index.cards.has(cid)) return; if (S.focus) exitFocus(true);
    reveal(cid, { instant: true }); S.insp = { type: "card", id: cid, full: true }; buildInspector(); buildChrome(); invalidate();
  }
  return { render, openCard, reveal, enterFolder, enterFocus, exitFocus, selectFolder, invalidate, setMeta, frame: () => frame(performance.now()) };
})();
const renderMap = (p) => MapView.render(p);
const openCard = (p, cid) => MapView.openCard(p, cid);
