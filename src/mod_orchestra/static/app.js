"use strict";
// Minecraft Mod Orchestra — local UI. Vanilla JS, no dependencies. The token lives only in memory.
const token = (location.hash || "").slice(1);
let selected = null, pollTimer = null, activeTab = "activity", lastProject = null;
const openLogs = new Set();  // run ids whose worker log the user keeps open across refreshes

const qs = (id) => document.getElementById(id);
const el = (tag, text, cls) => { const n = document.createElement(tag); if (text != null) n.textContent = text; if (cls) n.className = cls; return n; };
const btn = (label, onClick, cls) => { const b = el("button", label, cls); b.onclick = async (e) => { e.preventDefault(); b.disabled = true; try { await onClick(); } catch (err) { toast(err.message, "bad"); } finally { b.disabled = false; } }; return b; };
const fmtMoney = (v) => v == null ? "" : "$" + Number(v).toFixed(2);
const fmtDur = (s) => s == null ? "" : (s >= 60 ? Math.floor(s / 60) + "m " + Math.round(s % 60) + "s" : Math.round(s) + "s");
const ago = (t) => { const d = Date.now() / 1000 - t; return d < 60 ? "just now" : d < 3600 ? Math.floor(d / 60) + " min ago" : d < 86400 ? Math.floor(d / 3600) + " h ago" : Math.floor(d / 86400) + " d ago"; };
function codeLine(text) { const w = el("div", null, "codeline"); const c = el("code", text); const b = el("button", "copy", "mini secondary"); b.onclick = async (e) => { e.preventDefault(); try { await navigator.clipboard.writeText(text); b.textContent = "copied"; setTimeout(() => (b.textContent = "copy"), 1500); } catch { toast("Clipboard blocked; select and copy manually", "bad"); } }; w.append(c, b); return w; }
const fileUrl = (pid, rel) => `/api/project/${encodeURIComponent(pid)}/file?path=${encodeURIComponent(rel)}&token=${encodeURIComponent(token)}&v=${Date.now()}`;

async function api(path, payload) {
  const options = { headers: { Authorization: "Bearer " + token } };
  if (payload !== undefined) { options.method = "POST"; options.headers["Content-Type"] = "application/json"; options.body = JSON.stringify(payload); }
  const r = await fetch(path, options);
  const body = await r.json().catch(() => ({ error: "Bad response" }));
  if (!r.ok) throw new Error(body.error || r.statusText);
  return body;
}
let toastTimer = null;
function toast(msg, kind) { const t = qs("toast"); t.textContent = msg; t.className = "toast " + (kind || ""); clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.add("hidden"), kind === "bad" ? 9000 : 5000); }

// ---------- navigation ----------
function show(view) { for (const v of document.querySelectorAll(".view")) v.classList.add("hidden"); qs("view-" + view).classList.remove("hidden"); }
qs("nav-new").onclick = () => { show("new"); selected = null; renderProjectList(); };
qs("nav-env").onclick = async () => { show("env"); await renderEnv(); };
for (const t of document.querySelectorAll(".subtab")) t.onclick = () => { for (const x of document.querySelectorAll(".subtab")) x.classList.toggle("active", x === t); for (const p of document.querySelectorAll(".subpane")) p.classList.toggle("hidden", p.id !== "sub-" + t.dataset.sub); };
for (const t of document.querySelectorAll(".tab")) t.onclick = () => { activeTab = t.dataset.tab; for (const x of document.querySelectorAll(".tab")) x.classList.toggle("active", x === t); for (const p of document.querySelectorAll(".tabpane")) p.classList.toggle("hidden", p.id !== "tab-" + activeTab); };
qs("lightbox-close").onclick = () => qs("lightbox").classList.add("hidden");
for (const b of document.querySelectorAll("[data-modal]")) b.onclick = () => { if (!selected) return toast("Open a project first", "bad"); qs(b.dataset.modal).classList.remove("hidden"); const first = qs(b.dataset.modal).querySelector("input,select,textarea"); if (first) first.focus(); };
for (const x of document.querySelectorAll(".modal-close")) x.onclick = () => x.closest(".lightbox").classList.add("hidden");
for (const m of document.querySelectorAll(".lightbox")) m.addEventListener("click", (e) => { if (e.target === m && m.id !== "picker") m.classList.add("hidden"); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") for (const m of document.querySelectorAll(".lightbox:not(.hidden)")) if (m.id !== "picker") m.classList.add("hidden"); });
const closeModal = (id) => qs(id).classList.add("hidden");
qs("p-delete").onclick = () => { if (!lastProject) return; qs("del-confirm").value = ""; qs("del-name").textContent = lastProject.name; qs("del-id").textContent = lastProject.id; qs("del-path").textContent = lastProject.root || ""; qs("modal-delete").classList.remove("hidden"); qs("del-confirm").focus(); };
qs("del-go").onclick = async () => {
  if (!lastProject) return;
  if (qs("del-confirm").value.trim().toUpperCase() !== "DELETE") return toast("Type DELETE to confirm", "bad");
  try {
    const out = await api(`/api/project/${lastProject.id}/delete`, { confirm: lastProject.id, workspace: qs("del-workspace").checked });
    closeModal("modal-delete"); toast(`Deleted ${lastProject.id}${out.workspace_removed ? " and its workspace" : ""}.`, "ok");
    selected = null; lastProject = null; await renderProjectList();
    const projects = await api("/api/projects").catch(() => []);
    if (projects.length) await openProject(projects[0].id); else show("new");
  } catch (err) { toast(err.message, "bad"); }
};
qs("lightbox").onclick = (e) => { if (e.target.id === "lightbox") qs("lightbox").classList.add("hidden"); };
function openLightbox(src, caption) { qs("lightbox-img").src = src; qs("lightbox-cap").textContent = caption || ""; qs("lightbox").classList.remove("hidden"); }

// ---------- projects list ----------
const STAGE_CLASS = { verified: "ok", client: "info", server: "info", build: "warn", model: "purple", source: "warn", spec: "warn", idea: "" };
async function renderProjectList() {
  const list = qs("project-list"); list.replaceChildren();
  let projects = []; try { projects = await api("/api/projects"); } catch (e) { toast(e.message, "bad"); return; }
  if (!projects.length) list.append(el("div", "No projects yet", "dim"));
  for (const p of projects) {
    const b = el("button", null, "proj" + (p.id === selected ? " active" : ""));
    const left = el("div"); left.append(el("div", p.name, "pname"), el("div", p.status.toLowerCase().replace(/_/g, " "), "pstage"));
    const dot = el("span", null, "dot"); dot.style.background = p.status === "GAME_VERIFIED" ? "var(--ok)" : p.status.startsWith("BUILD_PASSED") ? "var(--info)" : p.status === "BUILD_FAILED" ? "var(--bad)" : "var(--dim)";
    b.append(left, dot); b.onclick = () => openProject(p.id); list.append(b);
  }
}

// ---------- new project ----------
qs("new-form").onsubmit = async (e) => {
  e.preventDefault();
  try {
    const p = await api("/api/projects", { name: qs("new-name").value.trim(), id: qs("new-id").value.trim(), package: qs("new-package").value.trim(), idea: qs("new-idea").value.trim() });
    toast("Project created. Next: let the interpreter propose a spec, or approve it if the grammar already produced one.", "ok");
    qs("new-form").reset(); await renderProjectList(); await openProject(p.id);
  } catch (err) { toast(err.message, "bad"); }
};
qs("new-name").oninput = () => { if (!qs("new-id").dataset.touched) qs("new-id").value = qs("new-name").value.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 40); };
qs("new-id").oninput = () => { qs("new-id").dataset.touched = "1"; };

// ---------- environment ----------
async function renderEnv() {
  const grid = qs("env-grid"); grid.replaceChildren();
  const d = await api("/api/doctor");
  const item = (title, kv) => { const c = el("div", null, "env-item"); c.append(el("h4", title)); const k = el("div", null, "kv"); for (const [a, b] of kv) { k.append(el("span", a, "k"), el("span", String(b ?? "—"))); } c.append(k); return c; };
  grid.append(item("Java", [["executable", d.java?.executable], ["version", d.java?.version], ["compatible", d.java?.compatible ? "yes" : "no — " + (d.java?.note || "")]]));
  grid.append(item("Gradle wrapper (shipped)", [["gradle", d.wrapper?.gradle], ["integrity", d.wrapper?.ok ? "verified" : "MISMATCH"]]));
  grid.append(item("Profile", [["id", d.profile?.id], ["minecraft", d.profile?.minecraft], ["loom", d.profile?.loom], ["fabric api", d.profile?.fabric_api], ["status", d.profile?.status]]));
  grid.append(item("State DB", [["schema", (d.schema?.version ?? "?") + " / " + (d.schema?.current ?? "?")], ["path", d.schema?.path]]));
  grid.append(item("Staging", [["pending", (d.stagings?.pending || []).length]]));
  grid.append(item("Node.js (designer worker)", [["executable", d.node?.executable || "NOT FOUND"], ["version", d.node?.version], ["note", d.node?.note]]));
  grid.append(item("Blockbench (optional)", [["executable", d.blockbench?.executable || "not found — .bbmodel files open with the system association if any"], ["note", d.blockbench?.note]]));
  grid.append(item("Claude Code (agent runs)", [["executable", d.claude_code?.executable || "NOT FOUND — install Claude Code or set CRAFTCTL_CLAUDE_BIN"], ["note", d.claude_code?.note]]));
  grid.append(item("Git", [["executable", d.git?.executable || "—"]]));
}

// ---------- project ----------
async function openProject(id) {
  selected = id; show("project");
  let p; try { p = await api("/api/project/" + encodeURIComponent(id)); } catch (e) { toast(e.message, "bad"); return; }
  lastProject = p;
  await renderProjectList();
  qs("p-id").textContent = p.id + " · " + p.spec.package; qs("p-name").textContent = p.name;
  const st = qs("p-status"); st.textContent = p.status.replace(/_/g, " "); st.className = "pill " + (p.status === "GAME_VERIFIED" ? "ok" : p.status === "BUILD_FAILED" ? "bad" : p.status.startsWith("BUILD_PASSED") ? "info" : "warn");
  qs("p-cost").textContent = p.guidance.runs ? `${p.guidance.runs} agent run${p.guidance.runs === 1 ? "" : "s"} · ${fmtMoney(p.guidance.cost_usd)} spent` : "no agent runs yet";
  for (const [name, fn] of [["stepper", renderStepper], ["now", renderNow], ["spec", renderSpec], ["mobs", renderGallery], ["items", renderFeatures], ["runs", renderRuns], ["events", renderEvents], ["verification", renderVerify], ["tasks", renderTasks]]) {
    try { const r = fn(name === "stepper" ? p.guidance : p); if (r && r.catch) r.catch(e => toast(`${name}: ${e.message}`, "bad")); } catch (e) { toast(`${name} failed to render: ${e.message} (try a hard reload: Ctrl+F5)`, "bad"); }
  }
  if (p.dispatching) pollUntilIdle(id);
}

function renderStepper(g) {
  const box = qs("stepper"); box.replaceChildren();
  const idx = g.stages.indexOf(g.stage);
  g.stages.forEach((s, i) => { const d = el("div", null, "step " + (i < idx ? "done" : i === idx ? "current" : "")); d.append(el("div", (i < idx ? "✓ " : "") + (i + 1), "sn"), el("div", s, "st")); box.append(d); });
}

const POLICY_KEYS = ["approve_spec", "generate", "build", "server_smoke"];
async function savePolicy(pid) {
  const policy = Object.fromEntries(POLICY_KEYS.map(k => [k, qs("pol-" + k).checked]));
  try { await api(`/api/project/${pid}/autopilot`, policy); renderPolicySummary(policy); toast("Autopilot permissions saved.", "ok"); } catch (e) { toast(e.message, "bad"); }
}
function renderPolicySummary(policy) {
  const on = POLICY_KEYS.filter(k => policy[k]);
  qs("policy-summary").textContent = on.length === POLICY_KEYS.length ? "— everything up to the client" : on.length ? "— " + on.map(k => k.replace("_", " ")).join(", ") : "— asks you at every gate";
}
function renderPolicy(p) {
  const policy = p.guidance.autopilot || {};
  for (const k of POLICY_KEYS) { const box = qs("pol-" + k); box.checked = !!policy[k]; box.onchange = () => savePolicy(p.id); }
  qs("pol-all").onclick = () => { for (const k of POLICY_KEYS) qs("pol-" + k).checked = true; savePolicy(p.id); };
  qs("pol-none").onclick = () => { for (const k of POLICY_KEYS) qs("pol-" + k).checked = false; savePolicy(p.id); };
  renderPolicySummary(policy);
}
function renderNow(p) {
  const g = p.guidance; renderPolicy(p);
  qs("now-headline").textContent = g.headline; qs("now-detail").textContent = g.detail || "";
  const busy = qs("now-busy"); busy.classList.toggle("hidden", !p.dispatching);
  if (p.dispatching && p.job) qs("now-busy-text").textContent = `${p.job.job} running · ${fmtDur(p.job.elapsed_s)}`;
  const steps = qs("now-steps"); steps.replaceChildren();
  const jr = qs("now-job"); jr.classList.add("hidden");
  if (p.job && !p.job.running && (p.job.result || p.job.error)) {
    jr.classList.remove("hidden"); jr.className = "job-result " + (p.job.error ? "bad" : "ok");
    jr.textContent = p.job.error ? `${p.job.job} failed: ${p.job.error}` : summarizeJob(p.job.job, p.job.result);
  }
  if (p.dispatching) return;
  for (const s of g.steps) steps.append(stepCard(p, s));
  if (!g.steps.length) steps.append(el("div", "Nothing pending.", "muted"));
}

function summarizeJob(job, r) {
  if (!r) return job + " finished";
  if (job === "dispatch") return `${r.role} on ${r.task} → ${r.task_state}${r.cost_usd ? " · " + fmtMoney(r.cost_usd) : ""}${r.duration_s ? " · " + fmtDur(r.duration_s) : ""}${r.error ? "\n" + r.error : ""}`;
  if (job === "orchestrate") return `Autopilot: ${r.runs.length} agent run(s)${r.gates?.length ? ", gates: " + r.gates.map(g => g.gate + (g.status ? " → " + g.status : "")).join(", ") : ""} · ${fmtMoney(r.total_cost_usd)}\nstopped because: ${r.stopped_because}`;
  if (job === "build") return `build → ${r.status} (exit ${r.exit_code}, ${fmtDur(r.duration_s)})${r.repair ? "\nrepair task opened: " + (r.repair.task || r.repair.error) : ""}`;
  if (job === "server-smoke") return `server smoke → ${r.status} (${fmtDur(r.duration_s)})${r.mod_errors?.length ? "\n" + r.mod_errors.join("\n") : ""}${r.repair ? "\nrepair task opened: " + (r.repair.task || r.repair.error) : ""}`;
  if (job === "run-client") return `client closed after ${fmtDur(r.duration_s)} · mod loaded: ${r.mod_loaded ? "yes" : "NO"} (${r.mods_loaded ?? "?"} mods)\nNow record what you saw in Verification.`;
  return JSON.stringify(r, null, 1).slice(0, 600);
}

function stepCard(p, s) {
  const c = el("div", null, "stepcard");
  c.append(el("span", s.who, "who " + s.who));
  const mid = el("div"); mid.append(el("div", s.label, "lbl")); if (s.detail) mid.append(el("div", s.detail, "det")); if (s.command) mid.append(codeLine(s.command)); c.append(mid);
  const right = el("div");
  if (s.action) right.append(actionButton(p, s));
  c.append(right); return c;
}

function actionButton(p, s) {
  const id = p.id;
  const run = async (fn, msg) => { await fn(); if (msg) toast(msg, "ok"); await openProject(id); };
  switch (s.action) {
    case "dispatch": return btn(s.who === "agent" ? "Run agent" : "Run", async () => { if (!confirm("Start ONE Claude Code worker for " + (s.payload.task || "the next task") + "?\nUses your installed Claude Code and your session. It cannot approve, decide or build.")) return; await api(`/api/project/${id}/dispatch`, { task: s.payload.task }); toast("Worker started. This page refreshes until it finishes.", "ok"); await openProject(id); }, "primary");
    case "answer": return btn("Answer", async () => { const text = prompt(s.label.replace(/^Answer: /, "")); if (!text) return; await run(() => api(`/api/project/${id}/answer`, { text }), "Answer added. Run the interpreter again from Now."); }, "primary");
    case "approve": { const wrap = el("div", null, "actions"); wrap.style.marginTop = "0";
      wrap.append(btn("Approve spec", () => run(() => api(`/api/project/${id}/approve`, {}), "Spec approved."), "primary"));
      wrap.append(btn("Approve & continue Autopilot", async () => { const budget = prompt("Autopilot budget in dollars (max 5 runs):", "5"); if (budget == null) return; await api(`/api/project/${id}/approve`, { autopilot: true, max_runs: 5, max_cost_usd: Math.max(0.5, Math.min(50, Number(budget) || 5)) }); toast("Approved. Autopilot running; it stops when it needs you.", "ok"); await openProject(id); }, "secondary"));
      return wrap; }
    case "generate": return btn("Generate source", () => run(() => api(`/api/project/${id}/generate`, {}), "Source generated (unverified)."), "primary");
    case "request-build": return btn("Request build approval", () => run(() => api(`/api/project/${id}/request-build`, {}), "Approval requested. Grant it in Now."), "primary");
    case "request-smoke": return btn("Request server smoke", () => run(() => api(`/api/project/${id}/request-smoke`, {}), "Approval requested. Grant it in Now."), "primary");
    case "decide": return btn(s.payload.grant ? "Grant" : "Deny", () => run(() => api(`/api/project/${id}/decide`, s.payload), s.payload.grant ? "Granted. Run it from Now." : "Denied."), "primary");
    case "build": return btn("Run trusted build", async () => { await api(`/api/project/${id}/build-bg`, s.payload); toast("Build started.", "ok"); await openProject(id); }, "primary");
    case "server-smoke": return btn("Run server smoke", async () => { await api(`/api/project/${id}/server-smoke`, s.payload); toast("Server starting…", "ok"); await openProject(id); }, "primary");
    case "run-client": return btn("Launch game client", async () => { if (!confirm("Opens Minecraft with only this mod (isolated run/ folder). Close the game when done.")) return; await api(`/api/project/${id}/run-client`, {}); toast("Client launching. Come back here when you close it.", "ok"); await openProject(id); }, "primary");
    case "evidence": return btn("Record evidence", () => { activeTab = "verify"; document.querySelector('[data-tab="verify"]').click(); qs("evidence-note").focus(); });
    case "orchestrate": return btn("Autopilot", async () => {
      const budget = prompt("Autopilot budget — max dollars for this session (max 5 runs):", String(s.payload.max_cost_usd));
      if (budget == null) return; const max_cost_usd = Math.max(0.5, Math.min(50, Number(budget) || 5));
      await api(`/api/project/${id}/orchestrate`, { max_runs: s.payload.max_runs, max_cost_usd }); toast(`Autopilot running (budget $${max_cost_usd}). It stops when it needs you.`, "ok"); await openProject(id); }, "primary");
    case "requeue": return btn("Requeue", () => run(() => api(`/api/task/${encodeURIComponent(s.payload.task)}/requeue`, {}), "Task back to READY."));
    default: return el("span");
  }
}

// ---------- spec ----------
function renderSpec(p) {
  const s = p.spec;
  if (qs("theme-text")) qs("theme-text").value = s.theme || "";
  if (qs("theme-save")) qs("theme-save").onclick = async () => { try { await api(`/api/project/${p.id}/theme`, { theme: qs("theme-text").value }); toast("Theme saved; designer runs from now on follow it.", "ok"); } catch (e) { toast(e.message, "bad"); } }; qs("spec-state").textContent = `Spec ${p.spec_state} · schema ${s.schema_version}`;
  const body = qs("spec-body"); body.replaceChildren();
  const grid = el("div", null, "spec-grid");
  const box = (title, items) => { const b = el("div", null, "spec-box"); b.append(el("h4", title)); const ul = el("ul"); if (!items.length) ul.append(el("li", "none", "dim")); for (const i of items) ul.append(el("li", i)); b.append(ul); return b; };
  grid.append(box("Items", s.features.filter(f => f.kind === "item").map(f => f.label)));
  grid.append(box("Blocks", s.features.filter(f => f.kind === "block").map(f => f.label)));
  grid.append(box("Mobs", (s.mobs || []).map(m => `${m.label} (${m.behavior})`)));
  grid.append(box("Recipes", (s.recipes || []).map(r => `${r.id}: ${r.kind} → ${r.result} ×${r.count}`)));
  grid.append(box("Drops", (s.drops || []).map(d => `${d.block} → ${d.item} (${d.count_min}-${d.count_max}${d.fortune ? ", fortune" : ""}${d.silk_touch ? ", silk touch" : ""})`)));
  grid.append(box("Creative tab", s.tab ? [s.tab + (s.tab_icon ? " (icon: " + s.tab_icon + ")" : "")] : []));
  body.append(grid);
  const idea = el("div", null, "spec-box"); idea.style.marginTop = "10px"; idea.append(el("h4", "Idea")); idea.append(el("div", s.idea)); body.append(idea);
  if (s.assumptions?.length) { const a = el("div", null, "spec-box"); a.style.marginTop = "10px"; a.append(el("h4", "Assumptions")); const ul = el("ul"); for (const x of s.assumptions) ul.append(el("li", x)); a.append(ul); body.append(a); }
  const qbox = qs("spec-questions"); qbox.replaceChildren();
  for (const q of (s.questions || [])) {
    const qd = el("div", null, "question"); qd.append(el("div", q, "q"));
    const f = el("form", null, "form inline"); const inp = el("input"); inp.placeholder = "Your answer"; inp.required = true; const b = el("button", "Answer", "primary"); f.append(inp, b);
    f.onsubmit = async (e) => { e.preventDefault(); try { await api(`/api/project/${p.id}/answer`, { text: inp.value }); toast("Answer added. Run the interpreter again from Now.", "ok"); await openProject(p.id); } catch (err) { toast(err.message, "bad"); } };
    qd.append(f); qbox.append(qd);
  }
}

// ---------- gallery ----------
function renderGallery(p) {
  const g = qs("gallery"); g.replaceChildren();
  if (!p.gallery.length) { g.append(el("p", "This mod has no mobs. Add one with craftctl add-mob before generating, or describe it in the idea.", "muted")); return; }
  for (const m of p.gallery) {
    const card = el("div", null, "mob");
    const head = el("div", null, "mob-head"); head.append(el("h4", `${m.label} · ${m.behavior}`));
    const meta = el("div", null, "mob-meta");
    meta.append(el("span", m.placeholder ? "placeholder model" : "designer model", "pill " + (m.placeholder ? "warn" : "purple")));
    if (m.task_state) meta.append(el("span", "MODEL task " + m.task_state, "pill " + (m.task_state === "DONE" ? "ok" : m.task_state === "FAILED" ? "bad" : "info")));
    if (m.bbmodel) meta.append(el("span", ".bbmodel ✓", "pill ok")); if (m.geo && m.animation) meta.append(el("span", "geo + animation ✓", "pill ok"));
    head.append(meta); card.append(head);
    const prev = el("div", null, "previews");
    for (const rel of m.previews) { const pv = el("div", null, "preview"); const img = el("img"); img.src = fileUrl(p.id, rel); img.alt = rel; pv.append(img, el("small", rel.split("/").pop())); pv.onclick = () => openLightbox(img.src, rel); prev.append(pv); }
    if (m.texture) { const pv = el("div", null, "preview tex"); const img = el("img"); img.src = fileUrl(p.id, m.texture); pv.append(img, el("small", "texture")); pv.onclick = () => openLightbox(img.src, m.texture); prev.append(pv); }
    if (!m.previews.length && !m.texture) prev.append(el("div", m.placeholder ? "No previews yet: the designer has not run for this mob. Dispatch its MODEL task from Now." : "No previews written by the designer.", "placeholder-note"));
    card.append(prev);
    if (m.versions && m.versions.length > 1) {
      const det = document.createElement("details"); det.append(el("summary", `Earlier versions (${m.versions.length - 1}) — compare after feedback`));
      for (const v of m.versions.slice(0, -1).reverse()) {
        const row = el("div", null, "previews"); row.append(el("div", `run ${v.run}${v.cost_usd != null ? " · " + fmtMoney(v.cost_usd) : ""}${v.created_at ? " · " + ago(v.created_at) : ""}`, "placeholder-note"));
        for (const rel of v.previews) { const pv = el("div", null, "preview"); const img = el("img"); img.src = fileUrl(p.id, rel); pv.append(img, el("small", rel.split("/").pop())); pv.onclick = () => openLightbox(img.src, rel); row.append(pv); }
        det.append(row);
      }
      card.append(det);
    }
    const dl = el("div", null, "drops-inline"); dl.append(el("span", "Drops on death:", "muted"));
    const drops = (m.drops || []).map(d => typeof d === "string" ? { item: d, count_min: 1, count_max: 1, chance: 1 } : d);
    if (!drops.length) dl.append(el("span", "nothing", "dim"));
    for (const d of drops) { const chip = el("span", null, "drop-chip"); const img = el("img"); img.src = dropIcon(p.id, d.item); img.alt = ""; chip.append(img, el("span", `${d.item} ×${d.count_min}${d.count_max !== d.count_min ? "–" + d.count_max : ""}${d.chance < 1 ? " @" + Math.round(d.chance * 100) + "%" : ""}`)); dl.append(chip); }
    dl.append(btn("Edit drops", () => openPicker(p.id, drops, `Drops on death — ${m.label}`, async (table) => { const out = await api(`/api/project/${p.id}/mob-drops`, { mob: m.mob, drops: table }); toast(out.note || "Drops saved.", "ok"); await openProject(p.id); }), "mini secondary"));
    card.append(dl);
    if (m.feedback.length) { const ul = el("ul", null, "feedback-list"); for (const f of m.feedback) ul.append(el("li", "you: " + f.text)); card.append(el("div", "Feedback sent to the designer:", "muted")); card.append(ul); }
    const fb = el("form", null, "feedback"); const ta = el("textarea"); ta.placeholder = m.placeholder ? "Describe the creature you want (shape, colours, size) — this goes to the designer's first run" : "What should change? e.g. “wings too big, make the body rounder, darker blue”"; fb.append(ta);
    const row = el("div", null, "actions");
    row.append(btn(m.placeholder && !m.feedback.length ? "Send and run designer" : "Send feedback and rerun designer", async () => {
      if (!ta.value.trim()) throw new Error("Write the feedback first");
      const out = await api(`/api/project/${p.id}/feedback`, { mob: m.mob, text: ta.value.trim() });
      if (!confirm("Feedback saved. Start the designer now? (~$1–2, 2–4 min)")) { await openProject(p.id); return; }
      await api(`/api/project/${p.id}/dispatch`, { task: out.task }); toast("Designer started with your feedback.", "ok"); await openProject(p.id);
    }, "primary"));
    if (m.task_state === "READY") row.append(btn("Run designer as is", async () => { await api(`/api/project/${p.id}/dispatch`, { task: m.task }); toast("Designer started.", "ok"); await openProject(p.id); }));
    if (m.bbmodel) { row.append(btn("Open in Blockbench", async () => { const out = await api(`/api/project/${p.id}/open-model`, { mob: m.mob }); toast(out.note || `Opening ${out.opened.split(/[\\/]/).pop()} in ${out.app ? "Blockbench" : "the default app"}…`, "ok"); }, "secondary")); row.append(el("span", `models/${m.mob}.bbmodel — edit it there; the controller keeps using this file as the source`, "muted")); }
    fb.append(row); card.append(fb); g.append(card);
  }
}

// ---------- drop picker ----------
let pickerState = { catalog: null, selected: new Set(), table: [], onSave: null, pid: null };
const vanillaIcon = (pid, kind, name) => `/api/project/${encodeURIComponent(pid)}/vanilla-texture?kind=${kind}&name=${encodeURIComponent(name)}&token=${encodeURIComponent(token)}`;
const modIcon = (pid, kind, name) => fileUrl(pid, `src/main/resources/assets/${pid}/textures/${kind}/${name}.png`);
function dropIcon(pid, id) {
  if (id.startsWith("minecraft:")) { const n = id.slice(10); const c = pickerState.catalog; const kind = c && c.vanilla.items.includes(n) ? "item" : "block"; return vanillaIcon(pid, kind, n); }
  const n = id.includes(":") ? id.split(":")[1] : id; const c = pickerState.catalog; const kind = c && c.mod.blocks.includes(n) && !c.mod.items.includes(n) ? "block" : "item"; return modIcon(pid, kind, n);
}
async function openPicker(pid, initial, title, onSave) {
  pickerState = { catalog: null, selected: new Set(), table: (initial || []).map(d => typeof d === "string" ? { item: d, count_min: 1, count_max: 1, chance: 1 } : { ...d }), onSave, pid };
  qs("picker-title").textContent = title; qs("picker-search").value = ""; qs("picker").classList.remove("hidden");
  qs("picker-grid").replaceChildren(el("div", "Loading items…", "muted")); renderDropTable();
  try { pickerState.catalog = await api(`/api/project/${pid}/items`); } catch (e) { toast(e.message, "bad"); pickerState.catalog = { mod: { items: [], blocks: [] }, vanilla: { items: [], blocks: [] }, note: e.message }; }
  qs("picker-note").textContent = pickerState.catalog.note || ""; renderPickerGrid();
}
function pickerEntries() {
  const c = pickerState.catalog; if (!c) return [];
  const q = qs("picker-search").value.trim().toLowerCase();
  const all = [...c.mod.items.map(n => ({ id: n, kind: "item", mod: true })), ...c.mod.blocks.map(n => ({ id: n, kind: "block", mod: true })),
               ...c.vanilla.items.map(n => ({ id: "minecraft:" + n, kind: "item" })), ...c.vanilla.blocks.map(n => ({ id: "minecraft:" + n, kind: "block" }))];
  return q ? all.filter(e => e.id.includes(q)) : all;
}
function renderPickerGrid() {
  const grid = qs("picker-grid"); grid.replaceChildren();
  const entries = pickerEntries(); qs("picker-count").textContent = `(${entries.length})`;
  const frag = document.createDocumentFragment();
  for (const e of entries.slice(0, 400)) {
    const d = el("div", null, "pick" + (e.mod ? " mod" : "") + (pickerState.selected.has(e.id) ? " sel" : "")); const img = el("img"); img.loading = "lazy"; img.alt = "";
    img.src = e.mod ? modIcon(pickerState.pid, e.kind, e.id) : vanillaIcon(pickerState.pid, e.kind, e.id.slice(10));
    d.append(img, el("div", e.mod ? e.id + " (mod)" : e.id.slice(10)));
    d.onclick = () => { if (pickerState.selected.has(e.id)) pickerState.selected.delete(e.id); else pickerState.selected.add(e.id); d.classList.toggle("sel"); };
    frag.append(d);
  }
  if (entries.length > 400) frag.append(el("div", `${entries.length - 400} more — refine the search`, "muted"));
  grid.append(frag);
}
function renderDropTable() {
  const t = qs("picker-table"); t.replaceChildren();
  const head = el("div", null, "drop-head"); for (const h of ["", "item", "min", "max", "chance", ""]) head.append(el("span", h)); t.append(head);
  if (!pickerState.table.length) t.append(el("div", "Empty — select items on the left and add them.", "muted"));
  pickerState.table.forEach((d, i) => {
    const row = el("div", null, "drop-row"); const img = el("img"); img.src = dropIcon(pickerState.pid, d.item); img.alt = "";
    const num = (key, min, max, step) => { const inp = el("input"); inp.type = "number"; inp.min = min; inp.max = max; inp.step = step; inp.value = d[key]; inp.oninput = () => { d[key] = Number(inp.value); }; return inp; };
    const x = el("button", "×", "x"); x.type = "button"; x.onclick = () => { pickerState.table.splice(i, 1); renderDropTable(); };
    row.append(img, el("span", d.item, "mono"), num("count_min", 0, 64, 1), num("count_max", 0, 64, 1), num("chance", 0.01, 1, 0.05), x); t.append(row);
  });
}
qs("picker-search").oninput = renderPickerGrid;
qs("picker-add").onclick = () => { for (const id of pickerState.selected) if (!pickerState.table.some(d => d.item === id)) pickerState.table.push({ item: id, count_min: 1, count_max: 1, chance: 1 }); pickerState.selected.clear(); renderPickerGrid(); renderDropTable(); };
qs("picker-cancel").onclick = () => qs("picker").classList.add("hidden");
qs("picker-save").onclick = async () => {
  for (const d of pickerState.table) { if (!(d.count_min <= d.count_max)) return toast(`${d.item}: min must be ≤ max`, "bad"); if (!(d.chance > 0 && d.chance <= 1)) return toast(`${d.item}: chance must be between 0 and 1`, "bad"); }
  try { await pickerState.onSave(pickerState.table.map(d => ({ ...d }))); qs("picker").classList.add("hidden"); } catch (e) { toast(e.message, "bad"); }
};
function dropsSummary(drops) { return drops.length ? drops.map(d => `${d.item} ×${d.count_min}${d.count_max !== d.count_min ? "–" + d.count_max : ""}${d.chance < 1 ? " @" + Math.round(d.chance * 100) + "%" : ""}`).join(", ") : "nothing"; }

let addMobDrops = [];
qs("am-drops-btn").onclick = () => openPicker(selected, addMobDrops, "Drops on death — new mob", async (table) => { addMobDrops = table; qs("am-drops-summary").textContent = dropsSummary(table); });
qs("addmob-form").onsubmit = async (e) => {
  e.preventDefault(); if (!selected) return;
  const drops = addMobDrops;
  try {
    const out = await api(`/api/project/${selected}/add-mob`, { identifier: qs("am-id").value.trim(), label: qs("am-label").value.trim(), behavior: qs("am-behavior").value, drops });
    const desc = qs("am-desc").value.trim();
    if (desc) await api(`/api/project/${selected}/feedback`, { mob: qs("am-id").value.trim(), text: desc }).catch(() => {});
    qs("addmob-form").reset(); addMobDrops = []; qs("am-drops-summary").textContent = "nothing"; closeModal("modal-mob");
    toast(out.tasks ? `Mob added. Files written; the coder registers it (${out.tasks[0]}), then the designer models it.` : "Mob added to the spec (re-approve before generating).", "ok");
    await openProject(selected);
  } catch (err) { toast(err.message, "bad"); }
};
qs("am-label").oninput = () => { if (!qs("am-id").dataset.touched) qs("am-id").value = qs("am-label").value.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 50); };
qs("am-id").oninput = () => { qs("am-id").dataset.touched = "1"; };


// ---------- items & blocks ----------
async function renderFeatures(p) {
  const list = qs("features-list"); list.replaceChildren();
  let feats = []; try { feats = await api(`/api/project/${p.id}/features`); } catch (e) { list.append(el("p", e.message, "muted")); return; }
  featureCache = feats;
  const bar = document.querySelector("#sub-items .add-bar");
  if (bar && !bar.querySelector("#restore-sprites-btn")) { const rb = btn("Restore designer icons", async () => { const out = await api(`/api/project/${p.id}/restore-sprites`, {}); toast(`Restored ${out.installed.length} file(s)${Object.keys(out.rejected || {}).length ? "; rejected: " + Object.keys(out.rejected).join(", ") : ""}. Rebuild to apply.`, "ok"); await openProject(p.id); }, "secondary"); rb.id = "restore-sprites-btn"; bar.append(rb); }
  try { const sheet = await api(`/api/project/${p.id}/contact-sheet`); const box = qs("sheet-box"); if (sheet.path) { box.classList.remove("hidden"); qs("sheet-img").src = fileUrl(p.id, sheet.path); qs("sheet-preview").onclick = () => openLightbox(qs("sheet-img").src, "sprites contact sheet"); } else box.classList.add("hidden"); } catch {}
  const generated = ["SOURCE_GENERATED_UNVERIFIED", "BUILD_PASSED_GAME_UNTESTED", "BUILD_FAILED", "GAME_VERIFIED"].includes(p.status);
  const uploadInput = (onFile) => { const up = el("input"); up.type = "file"; up.accept = "image/png"; up.style.display = "none"; up.onchange = async () => { const file = up.files[0]; if (!file) return; const b64 = await new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(r.result.split(",")[1]); r.onerror = rej; r.readAsDataURL(file); }); try { await onFile(b64); } catch (err) { toast(err.message, "bad"); } up.value = ""; }; return up; };
  const featureRow = (f) => {
    const row = el("div", null, "feature"); const img = el("img"); img.alt = "";
    if (f.texture) img.src = fileUrl(p.id, f.texture); else img.style.visibility = "hidden";
    const mid = el("div"); const nm = el("div", null, "fname"); nm.append(document.createTextNode(f.label), el("span", f.kind, "fk")); mid.append(nm, el("div", `${p.id}:${f.identifier}`, "fid"));
    const bits = []; if (f.recipes?.length) bits.push("recipes: " + f.recipes.join(", ")); if (f.drop) bits.push(`drops ${f.drop.item} ${f.drop.count_min}-${f.drop.count_max}`);
    if (f.food) bits.push(`nutrition ${f.food.nutrition} · saturation ${f.food.saturation}` + (f.food.effects?.length ? " · " + f.food.effects.map(e => e.effect.replace("minecraft:", "")).join(", ") : ""));
    if (bits.length) mid.append(el("small", bits.join(" · ")));
    const right = el("div", null, "actions"); right.style.marginTop = "0";
    const up = uploadInput(async (b64) => { const out = await api(`/api/project/${p.id}/set-texture`, { kind: f.kind === "block" ? "block" : "item", identifier: f.identifier, png_base64: b64 }); toast(out.note, "ok"); await openProject(p.id); });
    right.append(up, btn("Upload icon", () => up.click(), "mini secondary"));
    right.append(btn("Rename", async () => { const label = prompt("Display name for " + f.identifier + ":", f.label); if (!label || label === f.label) return; const out = await api(`/api/project/${p.id}/rename-feature`, { identifier: f.identifier, label }); toast(out.note || "Renamed.", "ok"); await openProject(p.id); }, "mini secondary"));
    if (!f.material) { if (!generated) right.append(btn("Remove", async () => { if (!confirm(`Remove ${f.identifier} from the spec?`)) return; await api(`/api/project/${p.id}/remove-feature`, { identifier: f.identifier }); toast("Removed.", "ok"); await openProject(p.id); }, "mini secondary")); else { const nb = btn("Remove", () => {}, "mini secondary"); nb.disabled = true; nb.title = "Removing content after generation needs a coder task (coming later)"; right.append(nb); } }
    row.append(img, mid, right); return row;
  };
  // Material sets: one card per material with the set-level actions once, pieces inside.
  const materials = [...new Set(feats.filter(f => f.material).map(f => f.material))];
  for (const mat of materials) {
    const pieces = feats.filter(f => f.material === mat); const hasArmor = pieces.some(f => f.kind === "armor");
    const card = el("div", null, "mob"); const head = el("div", null, "mob-head"); head.append(el("h4", `${mat} set · ${pieces.length} piece(s)`));
    const acts = el("div", null, "actions"); acts.style.marginTop = "0";
    if (hasArmor) {
      const helmet = pieces.find(f => f.armor_previews) || pieces.find(f => f.kind === "armor");
      acts.append(btn("Design worn armor", async () => { const notes = prompt(`Notes for the designer about the ${mat} worn armor (style, motifs, colours), or leave empty:`, ""); if (notes === null) return; const out = await api(`/api/project/${p.id}/armor-design`, { material: mat, notes }); if (confirm(`Task ${out.task} created. Start the designer now? (~$1, 2–4 min)`)) { await api(`/api/project/${p.id}/dispatch`, { task: out.task }); toast("Designer painting the worn armor; renders appear here when done.", "ok"); } await openProject(p.id); }, "mini primary"));
      acts.append(btn("Retint worn armor", async () => { const choice = prompt(`Worn armor for "${mat}":\n• leave EMPTY = match the icon's colours automatically\n• or type a colour like #2a9d8f`, ""); if (choice === null) return; const payload = choice.trim() ? { material: mat, color: choice.trim() } : { material: mat, match_icon: true }; const out = await api(`/api/project/${p.id}/retint-armor`, payload); toast(out.note, "ok"); await openProject(p.id); }, "mini secondary"));
      for (const layer of ["1", "2"]) { const upA = uploadInput(async (b64) => { const out = await api(`/api/project/${p.id}/set-texture`, { kind: "armor_layer_" + layer, identifier: mat, png_base64: b64 }); toast(out.note, "ok"); await openProject(p.id); }); acts.append(upA, btn(`Upload layer ${layer} (64×32)`, () => upA.click(), "mini secondary")); }
      head.append(acts); card.append(head);
      const previews = (pieces.find(f => f.armor_previews)?.armor_previews) || [];
      if (previews.length) { const pv = el("div", null, "previews"); for (const rel of previews) { const box = el("div", null, "preview"); const img = el("img"); img.src = fileUrl(p.id, rel); img.alt = rel; img.style.width = "140px"; img.style.height = "140px"; box.append(img, el("small", rel.split("/").pop())); box.onclick = () => openLightbox(img.src, rel); pv.append(box); } card.append(pv); }
      else card.append(el("div", "Worn armor: tinted placeholder. Use Design worn armor (designer, renders it worn) or upload your own layers.", "placeholder-note"));
    } else { head.append(acts); card.append(head); }
    for (const f of pieces) card.append(featureRow(f));
    list.append(card);
  }
  const plain = feats.filter(f => !f.material);
  if (!plain.length && !materials.length) list.append(el("p", "No items or blocks yet.", "muted"));
  for (const f of plain) list.append(featureRow(f));
  const addForm = qs("addfeature-form");
  addForm.onsubmit = async (e) => {
    e.preventDefault();
    try {
      const out = await api(`/api/project/${p.id}/add-feature`, { kind: qs("af-kind").value, label: qs("af-label").value.trim(), identifier: qs("af-id").value.trim(), shape: qs("af-shape").value, color: qs("af-color-hex").value });
      addForm.reset(); delete qs("af-id").dataset.touched; closeModal("modal-feat");
      toast(out.generated ? `Added. Files written; the coder registers it (${out.task}) — see Now.` : "Added to the spec. Re-approve before generating.", "ok");
      await openProject(p.id);
    } catch (err) { toast(err.message, "bad"); }
  };
}
let featureCache = [];
qs("sprites-btn").onclick = () => {
  if (!selected) return;
  const list = qs("sprites-list"); list.replaceChildren();
  for (const f of featureCache) { const l = el("label"); const c = el("input"); c.type = "checkbox"; c.value = f.identifier; c.checked = true; l.append(c, document.createTextNode(` ${f.label} (${f.kind})`)); list.append(l); }
  const mats = [...new Set(featureCache.filter(f => f.kind === "armor").map(f => f.material))];
  if (mats.length) { list.append(el("div", "Worn-armor layers (64×32, what you see on the body):", "muted")); for (const m of mats) { const l = el("label"); const c = el("input"); c.type = "checkbox"; c.value = m; c.dataset.armor = "1"; c.checked = true; l.append(c, document.createTextNode(` ${m} armor set`)); list.append(l); } }
  qs("sprites-notes").value = ""; qs("modal-sprites").classList.remove("hidden");
};
qs("sprites-all").onclick = () => { for (const c of qs("sprites-list").querySelectorAll("input")) c.checked = true; };
qs("sprites-none").onclick = () => { for (const c of qs("sprites-list").querySelectorAll("input")) c.checked = false; };
qs("sprites-go").onclick = async () => {
  const identifiers = [...qs("sprites-list").querySelectorAll("input:checked:not([data-armor])")].map(c => c.value);
  const armor = [...qs("sprites-list").querySelectorAll("input:checked[data-armor]")].map(c => c.value);
  if (!identifiers.length && !armor.length) return toast("Pick at least one item or armor set", "bad");
  try {
    const out = await api(`/api/project/${selected}/sprites`, { identifiers, notes: qs("sprites-notes").value, armor });
    closeModal("modal-sprites");
    if (confirm(`Task ${out.task} created for ${identifiers.length} sprite(s)${armor.length ? " + " + armor.length + " armor set(s)" : ""}. Start the designer now?`)) { await api(`/api/project/${selected}/dispatch`, { task: out.task }); toast("Designer painting… the contact sheet appears in Items when done.", "ok"); }
    await openProject(selected);
  } catch (err) { toast(err.message, "bad"); }
};
for (const [c, h] of [["mt-color", "mt-color-hex"], ["mt-accent", "mt-accent-hex"], ["fd-color", "fd-color-hex"], ["af-color", "af-color-hex"]]) { qs(c).oninput = () => { qs(h).value = qs(c).value; }; qs(h).oninput = () => { if (/^#[0-9a-fA-F]{6}$/.test(qs(h).value)) qs(c).value = qs(h).value; }; }
qs("mt-color").addEventListener("input", () => { const hex = qs("mt-color").value; const n = parseInt(hex.slice(1), 16); const l = [16, 8, 0].map(s => Math.min(255, ((n >> s) & 255) + Math.round((255 - ((n >> s) & 255)) * 0.35))); const acc = "#" + l.map(x => x.toString(16).padStart(2, "0")).join(""); qs("mt-accent").value = acc; qs("mt-accent-hex").value = acc; });
const MAT_PRESETS = { iron: [250, 6, 2, "iron", 14, "2 6 5 2", 15, 0, 0], diamond: [1561, 8, 3, "diamond", 10, "3 8 6 3", 33, 2, 0], netherite: [2031, 9, 4, "netherite", 15, "3 8 6 3", 37, 3, 0.1] };
qs("mt-preset").onchange = () => { const v = MAT_PRESETS[qs("mt-preset").value]; if (!v) return; [qs("mt-durability").value, qs("mt-speed").value, qs("mt-attack").value, qs("mt-level").value, qs("mt-ench").value, qs("mt-defense").value, qs("mt-adur").value, qs("mt-tough").value, qs("mt-kb").value] = v; };
for (const id of ["mt-durability", "mt-speed", "mt-attack", "mt-level", "mt-ench", "mt-defense", "mt-adur", "mt-tough", "mt-kb"]) qs(id).oninput = () => { qs("mt-preset").value = "custom"; };
qs("mt-label").oninput = () => { if (!qs("mt-id").dataset.touched) qs("mt-id").value = qs("mt-label").value.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 40); };
qs("mt-id").oninput = () => { qs("mt-id").dataset.touched = "1"; };
qs("addmat-form").onsubmit = async (e) => {
  e.preventDefault(); if (!selected) return;
  const checked = (box) => [...qs(box).querySelectorAll("input:checked")].map(i => i.value);
  const defense = qs("mt-defense").value.trim().split(/\s+/).map(Number);
  try {
    const out = await api(`/api/project/${selected}/add-material`, { identifier: qs("mt-id").value.trim(), label: qs("mt-label").value.trim(), ingredient: qs("mt-ingredient").value.trim(),
      tools: checked("mt-tools"), armor: checked("mt-armor"), durability: Number(qs("mt-durability").value), mining_speed: Number(qs("mt-speed").value), attack_damage_bonus: Number(qs("mt-attack").value),
      mining_level: qs("mt-level").value, enchantability: Number(qs("mt-ench").value), armor_defense: defense, armor_durability: Number(qs("mt-adur").value), toughness: Number(qs("mt-tough").value),
      knockback_resistance: Number(qs("mt-kb").value), recipes: qs("mt-recipes").checked, color: qs("mt-color-hex").value, accent: qs("mt-accent-hex").value });
    qs("addmat-form").reset(); delete qs("mt-id").dataset.touched; qs("mt-preset").onchange(); closeModal("modal-mat");
    toast(out.generated ? `Set added. Files written; the coder registers it (${out.task}) — see Now.` : `Set added to the spec (${(out.items || []).length} items). Re-approve before generating.`, "ok");
    await openProject(selected);
  } catch (err) { toast(err.message, "bad"); }
};
qs("fd-label").oninput = () => { if (!qs("fd-id").dataset.touched) qs("fd-id").value = qs("fd-label").value.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 50); };
qs("fd-id").oninput = () => { qs("fd-id").dataset.touched = "1"; };
qs("addfood-form").onsubmit = async (e) => {
  e.preventDefault(); if (!selected) return;
  const effects = qs("fd-effect").value ? [{ effect: qs("fd-effect").value, duration: Number(qs("fd-duration").value), amplifier: Number(qs("fd-amplifier").value), chance: 1.0 }] : [];
  try {
    const out = await api(`/api/project/${selected}/add-food`, { identifier: qs("fd-id").value.trim(), label: qs("fd-label").value.trim(), nutrition: Number(qs("fd-nutrition").value), saturation: Number(qs("fd-saturation").value), effects, always_edible: qs("fd-always").checked, fast: qs("fd-fast").checked, color: qs("fd-color-hex").value });
    qs("addfood-form").reset(); delete qs("fd-id").dataset.touched; closeModal("modal-food");
    toast(out.generated ? `Food added. Files written; the coder registers it (${out.task}) — see Now.` : "Food added to the spec. Re-approve before generating.", "ok");
    await openProject(selected);
  } catch (err) { toast(err.message, "bad"); }
};
qs("af-label").oninput = () => { if (!qs("af-id").dataset.touched) qs("af-id").value = qs("af-label").value.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 50); };
qs("af-id").oninput = () => { qs("af-id").dataset.touched = "1"; };

// ---------- activity ----------
function renderRuns(p) {
  const list = qs("runs-list"); list.replaceChildren();
  const runs = (p.runs_all || []).slice().reverse();
  if (!runs.length) { list.append(el("p", "No agent runs yet.", "muted")); return; }
  list.append(el("p", "History of what each worker did and asked for. Anything still pending for you is in the Now panel at the top, as buttons.", "muted"));
  const lastEvidenceAt = Math.max(0, ...(p.evidence || []).map(e => e.created_at));
  for (const r of runs) {
    const card = el("div", null, "run"); card.dataset.run = r.id; const head = el("div", null, "head");
    head.append(el("span", r.state, "state " + r.state), el("b", `${r.role} → ${r.task_id}`), el("small", [r.duration_s != null ? fmtDur(r.duration_s) : "running", r.turns != null ? r.turns + " turns" : null, r.cost_usd != null ? fmtMoney(r.cost_usd) : null, ago(r.created_at)].filter(Boolean).join(" · "), "muted"));
    card.append(head);
    const h = r.handoff;
    if (h) {
      if (h.scope) card.append(el("div", h.scope, "muted"));
      if (h.changed_files?.length) card.append(el("div", "changed: " + h.changed_files.join(", "), "risk"));
      if (h.evidence) card.append(el("div", "evidence claimed: " + h.evidence.level + (h.evidence.pointer ? " — " + h.evidence.pointer : ""), "risk"));
      if (h.needs_user?.length) {
        const superseded = (r.finished_at || r.created_at) < lastEvidenceAt || r.task_id.endsWith(":SPEC") && p.spec_state === "APPROVED";
        const n = el("div", null, "needs" + (superseded ? " past" : "")); n.append(el("b", superseded ? "The worker asked you for (already handled since):" : "The worker asked you for — see Now for the button:"));
        for (const c of h.needs_user) n.append(codeLine(c)); card.append(n);
      }
      if (h.risks?.length) card.append(el("div", "risks: " + h.risks.join(" · "), "risk"));
      if (h.sprites) { const sp = h.sprites; const d = el("div", null, "needs"); d.append(el("b", `Sprites installed: ${sp.installed.length}` + (Object.keys(sp.rejected || {}).length ? ` · rejected: ${Object.keys(sp.rejected).length}` : ""))); for (const rel of sp.installed) d.append(el("code", rel.split("/").pop())); for (const [k, why] of Object.entries(sp.rejected || {})) d.append(el("code", `✗ ${k}: ${why}`)); card.append(d); }
      if (h.model) card.append(el("div", `model installed: ${h.model.bones.length} bones, ${h.model.cubes} cubes, ${h.model.animations.length} animations`, "risk"));
      if (h.questions?.length) card.append(el("div", "questions: " + h.questions.join(" · "), "risk"));
    }
    if (r.error) card.append(el("div", "⚠ " + r.error, "needs"));
    const render = (d) => (d.live && d.live.length) ? d.live.join("\n") + (d.state === "RUNNING" ? "\n…" : "") : (d.log_tail || (r.state === "RUNNING" ? "(waiting for the worker's first output…)" : "(empty)"));
    const showLog = async (raw) => { const d = await api("/api/run/" + r.id); let box = card.querySelector(".log"); if (!box) { box = el("pre", null, "log"); card.append(box); } box.classList.remove("hidden"); box.textContent = raw ? (d.log_tail || "(empty)") : render(d); lb.textContent = "Hide log"; if (!raw) { const atBottom = true; if (atBottom) box.scrollTop = box.scrollHeight; } };
    const lb = btn(openLogs.has(r.id) ? "Hide log" : "Worker log", async () => { if (openLogs.has(r.id)) { openLogs.delete(r.id); const box = card.querySelector(".log"); if (box) box.classList.add("hidden"); lb.textContent = "Worker log"; return; } openLogs.add(r.id); await showLog(false); }, "mini secondary"); card.append(lb);
    if (r.state === "RUNNING") card.append(btn("Raw log", () => { openLogs.add(r.id); return showLog(true); }, "mini secondary"));
    if (openLogs.has(r.id)) showLog(false);
    list.append(card);
  }
}
function renderEvents(p) {
  const box = qs("events-list"); box.replaceChildren();
  for (const ev of p.events) { const pl = ev.payload || {}; const extra = pl.state || pl.level || pl.status || pl.error || pl.reason || pl.task || pl.mob || ""; const row = el("div", null, "event"); row.append(el("span", ev.kind, "ek"), el("span", ev.actor + " · " + ago(ev.created_at), "ea"), el("span", String(extra).slice(0, 160))); box.append(row); }
}

// ---------- verification ----------
function renderVerify(p) {
  const lv = qs("levels"); lv.replaceChildren();
  for (const L of ["BUILD_PASS", "SERVER_BOOT_PASS", "CLIENT_BOOT_PASS", "CONTENT_VERIFIED"]) lv.append(el("div", (p.guidance.levels.includes(L) ? "✓ " : "○ ") + L, "level " + (p.guidance.levels.includes(L) ? "on" : "")));
  const list = qs("evidence-list"); list.replaceChildren();
  const row = (e) => { const r = el("div", null, "evidence"); r.append(el("span", e.level, "state DONE"), el("span", e.note || ""), el("small", e.actor + " · " + ago(e.created_at) + (e.artifact_sha256 ? " · jar " + e.artifact_sha256.slice(0, 12) : ""))); return r; };
  const cur = p.evidence.filter(e => e.current), old = p.evidence.filter(e => !e.current);
  if (!cur.length) list.append(el("p", old.length ? "Nothing recorded on the current source yet (the source changed since the earlier evidence below)." : "No evidence recorded yet.", "muted"));
  for (const e of cur.slice().reverse()) list.append(row(e));
  if (old.length) { const det = document.createElement("details"); det.append(el("summary", `Earlier sources (${old.length}) — no longer counts; the code changed since`)); for (const e of old.slice().reverse()) det.append(row(e)); list.append(det); }
  qs("evidence-form").onsubmit = async (e) => { e.preventDefault(); try { await api(`/api/project/${p.id}/evidence`, { level: qs("evidence-level").value, note: qs("evidence-note").value }); qs("evidence-note").value = ""; toast("Recorded.", "ok"); await openProject(p.id); } catch (err) { toast(err.message, "bad"); } };
  const acts = qs("verify-actions"); acts.replaceChildren(); qs("validate-box").textContent = ""; qs("build-log").classList.add("hidden"); qs("diagnose-box").replaceChildren();
  const generated = ["SOURCE_GENERATED_UNVERIFIED", "BUILD_PASSED_GAME_UNTESTED", "BUILD_FAILED", "GAME_VERIFIED"].includes(p.status);
  if (!generated) { qs("validate-box").textContent = "Generate source first."; return; }
  acts.append(btn("Check files unchanged", async () => { const v = await api(`/api/project/${p.id}/validate`); qs("validate-box").textContent = v.status === "PASS" ? `PASS · ${v.checked} files intact · ${v.revisions} accepted revision(s)` : `${v.status} · ${(v.problems || []).join("; ")}`; qs("validate-box").className = v.status === "PASS" ? "ok" : "bad"; }));
  acts.append(btn("Build log", async () => { const r = await api(`/api/project/${p.id}/logs`); const b = qs("build-log"); b.textContent = r.text; b.classList.remove("hidden"); }));
  acts.append(btn("Launch game client", async () => { if (!confirm("Opens Minecraft with only this mod (isolated run/ folder). It compiles the current source first. Close the game when done.")) return; await api(`/api/project/${p.id}/run-client`, {}); toast("Client launching. Come back here when you close it.", "ok"); await openProject(p.id); }, "primary"));
  acts.append(btn("Diagnose last build", async () => { const d = await api(`/api/project/${p.id}/diagnose`); const box = qs("diagnose-box"); box.replaceChildren(); if (d.status === "NO_LOG") { box.append(el("p", d.note, "muted")); return; } if (!d.classifications.length) { box.append(el("p", "No known failure pattern matched.", "muted")); return; } for (const c of d.classifications) { const w = el("div", null, "warning"); w.append(el("b", c.kind), el("div", c.symptom), el("div", c.guidance, "muted")); box.append(w); } }));
}

// ---------- tasks ----------
function renderTasks(p) {
  const t = qs("task-list"); t.replaceChildren();
  for (const task of p.tasks) {
    const row = el("div", null, "task"); row.append(el("span", task.state, "state " + task.state));
    const mid = el("div"); mid.append(el("div", task.title, "ttl"), el("small", task.id + " · " + task.role + (task.last_error ? " · " + task.last_error : ""))); row.append(mid);
    const right = el("div");
    if (["FAILED", "WAITING_USER", "BLOCKED"].includes(task.state)) right.append(btn("Requeue", async () => { await api(`/api/task/${encodeURIComponent(task.id)}/requeue`, {}); await openProject(p.id); }, "mini"));
    if (task.state === "READY" && !p.dispatching) right.append(btn("Run agent", async () => { if (!confirm("Start ONE worker on " + task.id + "?")) return; await api(`/api/project/${p.id}/dispatch`, { task: task.id }); await openProject(p.id); }, "mini primary"));
    row.append(right); t.append(row);
  }
  const a = qs("approvals-list"); a.replaceChildren();
  if (!p.approvals.length) a.append(el("p", "No approvals yet.", "muted"));
  for (const ap of p.approvals) { const expired = ap.expires_at && ap.expires_at < Date.now() / 1000 && ap.state !== "CONSUMED"; const row = el("div", null, "task"); row.append(el("span", expired ? "EXPIRED" : ap.state, "state " + (expired ? "FAILED" : ap.state === "GRANTED" ? "READY" : ap.state === "CONSUMED" ? "DONE" : ap.state === "DENIED" ? "FAILED" : "WAITING_USER"))); const mid = el("div"); mid.append(el("div", ap.kind.replace(/_/g, " "), "ttl"), el("small", ap.description)); row.append(mid); const right = el("div"); if (ap.state === "PENDING" && !expired) { right.append(btn("Grant", async () => { await api(`/api/project/${p.id}/decide`, { approval_id: ap.id, grant: true }); await openProject(p.id); }, "mini primary"), btn("Deny", async () => { await api(`/api/project/${p.id}/decide`, { approval_id: ap.id, grant: false }); await openProject(p.id); }, "mini")); } row.append(right); a.append(row); }
}

// ---------- polling ----------
function pollUntilIdle(id) {
  clearTimeout(pollTimer);
  pollTimer = setTimeout(async () => {
    try { const p = await api("/api/project/" + encodeURIComponent(id)); if (selected !== id) return;
      await openProject(id); if (p.dispatching) pollUntilIdle(id); else toast(p.job?.error ? `${p.job.job} failed — see Now.` : `${p.job?.job || "Job"} finished — see Now.`, p.job?.error ? "bad" : "ok"); }
    catch (e) { toast(e.message, "bad"); }
  }, 4000);
}

// ---------- boot ----------
(async function boot() {
  if (!token) { toast("Missing local access token. Start with: craftctl ui", "bad"); return; }
  try { const d = await api("/api/doctor"); qs("sidebar-foot").textContent = `${d.profile.id} · ${d.os} · schema v${d.schema?.version ?? "?"}`; } catch (e) { toast("Cannot reach the local API: " + e.message, "bad"); }
  await renderProjectList();
  const projects = await api("/api/projects").catch(() => []);
  if (projects.length) await openProject(projects[0].id); else show("new");
})();
