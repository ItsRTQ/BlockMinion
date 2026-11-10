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
const RUNTIME_LABELS = { "claude-code": "Claude Code", "gemini-cli": "Gemini CLI", "antigravity-cli": "Antigravity CLI" };
let runtimeId = "claude-code";
const runtimeName = () => RUNTIME_LABELS[runtimeId] || runtimeId;
let toastTimer = null;
function toast(msg, kind) { const t = qs("toast"); t.textContent = msg; t.className = "toast " + (kind || ""); clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.add("hidden"), kind === "bad" ? 9000 : 5000); }

// ---------- navigation ----------
function show(view) { for (const v of document.querySelectorAll(".view")) v.classList.add("hidden"); qs("view-" + view).classList.remove("hidden"); }
qs("nav-new").onclick = () => { show("new"); selected = null; renderProjectList(); };
qs("nav-env").onclick = async () => { show("env"); try { await renderEnv(); } catch (e) { toast("Environment: " + e.message, "bad"); } };
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
    b.dataset.pid = p.id;
    const work = el("div", null, "pwork"); work.hidden = true;
    const left = el("div"); left.append(el("div", p.name, "pname"), el("div", p.status.toLowerCase().replace(/_/g, " "), "pstage"), work);
    const dot = el("span", null, "dot"); dot.style.background = p.status === "GAME_VERIFIED" ? "var(--ok)" : p.status.startsWith("BUILD_PASSED") ? "var(--info)" : p.status === "BUILD_FAILED" ? "var(--bad)" : "var(--dim)";
    b.append(left, dot); b.onclick = () => openProject(p.id); list.append(b);
  }
  Activity.render();   // the markers of what is running or just finished
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
  grid.append(item("Claude Code (agent runtime)", [["executable", d.claude_code?.executable || "NOT FOUND — install Claude Code or set CRAFTCTL_CLAUDE_BIN"], ["note", d.claude_code?.note]]));
  grid.append(item("Gemini CLI (agent runtime)", [["executable", d.gemini_cli?.executable || "not found — install Gemini CLI or set CRAFTCTL_GEMINI_BIN"], ["note", d.gemini_cli?.note]]));
  grid.append(item("Antigravity CLI (agent runtime)", [["executable", d.antigravity_cli?.executable || "not found — install agy from antigravity.google or set CRAFTCTL_AGY_BIN"], ["version", d.antigravity_cli?.version], ["note", d.antigravity_cli?.note]]));
  grid.append(item("Git", [["executable", d.git?.executable || "—"], ["version", d.git?.version]]));
  await renderRuntime();
}

async function renderRuntime() {
  const sel = qs("env-provider"), note = qs("env-provider-note");
  let s; try { s = await api("/api/settings"); } catch (e) { note.textContent = e.message; return; }
  runtimeId = s.provider || runtimeId;
  const labels = { "claude-code": "Claude Code", "gemini-cli": "Gemini CLI", "antigravity-cli": "Antigravity CLI (agy)" };
  sel.replaceChildren();
  for (const name of s.choices) { const o = el("option", (labels[name] || name) + (s.available[name] ? "" : " — not installed")); o.value = name; sel.append(o); }
  sel.value = s.provider;
  const describe = () => { note.textContent = s.saved ? "saved on this machine" : s.env ? "from CRAFTCTL_PROVIDER in this terminal (choose one here to save it)" : "default; choose one here to save it"; };
  describe();
  const modelRow = qs("env-model-row"), modelInput = qs("env-model"), modelSave = qs("env-model-save");
  const syncModel = () => {
    modelRow.classList.toggle("hidden", s.provider === "claude-code");   // Claude Code uses your account's own default
    modelInput.value = s.model || "";
    modelInput.placeholder = s.model_env ? `Model (optional) — ${s.model_env} is set in this terminal; save one here to override it` : "Model (optional) — leave empty to let the CLI choose; list yours with: agy models";
  };
  syncModel();
  sel.onchange = async () => {
    try { s = { ...s, ...(await api("/api/settings", { provider: sel.value })) }; runtimeId = s.provider || runtimeId; toast("Agent runtime: " + (labels[s.provider] || s.provider), "ok"); describe(); s = { ...s, ...(await api("/api/settings")) }; syncModel(); }
    catch (e) { toast(e.message, "bad"); sel.value = s.provider; }
  };
  modelSave.onclick = async () => {
    try { s = { ...s, ...(await api("/api/settings", { model: modelInput.value })) }; toast(s.model ? "Model saved: " + s.model : "Model cleared (the CLI picks its own)", "ok"); syncModel(); }
    catch (e) { toast(e.message, "bad"); }
  };
}

// ---------- project ----------
let lastFp = null, deferredRefresh = null, lastRefreshAt = 0;
const isProjectView = () => !qs("view-project").classList.contains("hidden");
// what the page shows depends on this payload; the job's elapsed time moves on its own, so it is left out
const fingerprint = (p) => JSON.stringify({ ...p, job: p.job ? { job: p.job.job, running: p.job.running, error: p.job.error } : null });

// The user opens a project: navigate to it and draw everything.
async function openProject(id) {
  selected = id; show("project");
  let p; try { p = await api("/api/project/" + encodeURIComponent(id)); } catch (e) { toast(e.message, "bad"); return; }
  await renderProject(p);
  Activity.seen(id);
}
// Draw a project's payload without moving the user: the scroll, the open sections and the focus survive the rebuild.
async function renderProject(p) {
  const id = p.id, snap = Guard.snapshot(); Guard.hold(snap);
  try {
    lastProject = p; lastFp = fingerprint(p);
    await renderProjectList();
    qs("p-id").textContent = p.id + " · " + p.spec.package; qs("p-name").textContent = p.name;
    const st = qs("p-status"); st.textContent = p.status.replace(/_/g, " "); st.className = "pill " + (p.status === "GAME_VERIFIED" ? "ok" : p.status === "BUILD_FAILED" ? "bad" : p.status.startsWith("BUILD_PASSED") ? "info" : "warn");
    qs("p-cost").textContent = p.guidance.runs ? `${p.guidance.runs} agent run${p.guidance.runs === 1 ? "" : "s"} · ${fmtMoney(p.guidance.cost_usd)} spent` : "no agent runs yet";
    const pending = [];
    for (const [name, fn] of [["stepper", renderStepper], ["now", renderNow], ["spec", renderSpec], ["map", renderMap], ["mobs", renderGallery], ["items", renderFeatures], ["worldgen", renderWorldgen], ["runs", renderRuns], ["events", renderEvents], ["verification", renderVerify], ["tasks", renderTasks]]) {
      try { const r = fn(name === "stepper" ? p.guidance : p); if (r && r.catch) pending.push(r.catch(e => toast(`${name}: ${e.message}`, "bad"))); } catch (e) { toast(`${name} failed to render: ${e.message} (try a hard reload: Ctrl+F5)`, "bad"); }
    }
    await Promise.allSettled(pending);
  } finally { Guard.restore(snap); }
}
// The poll's way of updating: never navigates, skips unchanged data, and waits while the user is typing or has a dialog open.
async function refreshProject(id) {
  if (selected !== id || !isProjectView()) return;
  let p; try { p = await api("/api/project/" + encodeURIComponent(id)); } catch (e) { return; }
  if (selected !== id || !isProjectView() || fingerprint(p) === lastFp) return;
  if (Guard.busy()) { clearTimeout(deferredRefresh); deferredRefresh = setTimeout(() => refreshProject(id), 2500); return; }
  await renderProject(p);
}
// Where a banner link goes: the project, the tab, the sub-tab and the mob or card.
async function goTo(pid, target = {}) {
  if (selected !== pid || !isProjectView()) await openProject(pid);
  if (target.tab) { const t = document.querySelector(`.tab[data-tab="${target.tab}"]`); if (t) t.click(); }
  if (target.sub) { const t = document.querySelector(`.subtab[data-sub="${target.sub}"]`); if (t) t.click(); }
  const focus = target.focus || "";
  if (focus.startsWith("mob:")) {
    const n = document.querySelector(`[data-focus="${focus}"]`);
    if (n) { n.scrollIntoView({ block: "center", behavior: "smooth" }); n.classList.add("flash"); setTimeout(() => n.classList.remove("flash"), 1800); }
  } else if (focus && target.tab === "map" && mapState.data && mapState.data.cards.some(c => c.id === focus)) {
    mapState.sel = focus; drawMap(lastProject); openCard(lastProject, focus);
  }
}

function renderStepper(g) {
  const box = qs("stepper"); box.replaceChildren();
  const idx = g.stages.indexOf(g.stage);
  g.stages.forEach((s, i) => { const d = el("div", null, "step " + (i < idx ? "done" : i === idx ? "current" : "")); d.append(el("div", (i < idx ? "✓ " : "") + (i + 1), "sn"), el("div", s, "st")); box.append(d); });
}

if (qs("theme-text")) qs("theme-text").addEventListener("input", (e) => { if (e.isTrusted) e.target.dataset.dirty = "1"; });
const POLICY_KEYS = ["approve_spec", "generate", "build", "gametest", "server_smoke"];
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
  if (job === "gametest") return `GameTests: ${r.status} · ${r.junit?.tests ?? 0} test(s), ${r.junit?.failures ?? 0} failure(s)` + (r.junit?.failed?.length ? " — " + r.junit.failed.map(f => f.name).join(", ") : "") + (r.repair?.task ? ` · repair ${r.repair.task} opened` : "");
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
    case "dispatch": return btn(s.who === "agent" ? "Run agent" : "Run", async () => { if (!await confirmBox(`Start ONE ${runtimeName()} worker for ${s.payload.task || "the next task"}?\nUses your installed ${runtimeName()} and your session. It cannot approve, decide or build.`, { title: "Run an agent", ok: "Run agent" })) return; await api(`/api/project/${id}/dispatch`, { task: s.payload.task }); toast("Agent started. The banner at the bottom follows it; this page stays where it is.", "ok"); await openProject(id); }, "primary");
    case "answer": return btn("Answer", async () => { const text = await promptBox(s.label.replace(/^Answer: /, ""), "", { title: "Answer the interpreter", ok: "Send answer", multiline: true, required: true }); if (!text) return; await run(() => api(`/api/project/${id}/answer`, { text }), "Answer added. Run the interpreter again from Now."); }, "primary");
    case "approve": { const wrap = el("div", null, "actions"); wrap.style.marginTop = "0";
      wrap.append(btn("Approve spec", () => run(() => api(`/api/project/${id}/approve`, {}), "Spec approved."), "primary"));
      wrap.append(btn("Approve & continue Autopilot", async () => { const budget = await promptBox("Maximum spend for this Autopilot session, in dollars. It also stops after 5 agent runs.", "5", { title: "Autopilot budget", ok: "Approve and run", multiline: false }); if (budget == null) return; await api(`/api/project/${id}/approve`, { autopilot: true, max_runs: 5, max_cost_usd: Math.max(0.5, Math.min(50, Number(budget) || 5)) }); toast("Approved. Autopilot running; it stops when it needs you.", "ok"); await openProject(id); }, "secondary"));
      return wrap; }
    case "generate": return btn("Generate source", () => run(() => api(`/api/project/${id}/generate`, {}), "Source generated (unverified)."), "primary");
    case "request-build": return btn("Request build approval", () => run(() => api(`/api/project/${id}/request-build`, {}), "Approval requested. Grant it in Now."), "primary");
    case "request-smoke": return btn("Request server smoke", () => run(() => api(`/api/project/${id}/request-smoke`, {}), "Approval requested. Grant it in Now."), "primary");
    case "request-gametest": return btn("Request GameTests", () => run(() => api(`/api/project/${id}/request-gametest`, {}), "Approval requested. Grant it in Now."), "secondary");
    case "gametest": return btn("Run GameTests", async () => { await api(`/api/project/${id}/gametest`, s.payload); toast("GameTests running (2–5 min)…", "ok"); await openProject(id); }, "primary");
    case "decide": return btn(s.payload.grant ? "Grant" : "Deny", () => run(() => api(`/api/project/${id}/decide`, s.payload), s.payload.grant ? "Granted. Run it from Now." : "Denied."), "primary");
    case "build": return btn("Run trusted build", async () => { await api(`/api/project/${id}/build-bg`, s.payload); toast("Build started.", "ok"); await openProject(id); }, "primary");
    case "server-smoke": return btn("Run server smoke", async () => { await api(`/api/project/${id}/server-smoke`, s.payload); toast("Server starting…", "ok"); await openProject(id); }, "primary");
    case "run-client": return btn("Launch game client", async () => { if (!await confirmBox("Opens Minecraft with only this mod (isolated run/ folder). Close the game when done.")) return; await api(`/api/project/${id}/run-client`, {}); toast("Client launching. Come back here when you close it.", "ok"); await openProject(id); }, "primary");
    case "evidence": return btn("Record evidence", () => { activeTab = "verify"; document.querySelector('[data-tab="verify"]').click(); qs("evidence-note").focus(); });
    case "orchestrate": return btn("Autopilot", async () => {
      const budget = await promptBox("Maximum spend for this Autopilot session, in dollars. It also stops after 5 agent runs.", String(s.payload.max_cost_usd), { title: "Autopilot budget", ok: "Continue", multiline: false });
      if (budget == null) return; const max_cost_usd = Math.max(0.5, Math.min(50, Number(budget) || 5));
      await api(`/api/project/${id}/orchestrate`, { max_runs: s.payload.max_runs, max_cost_usd }); toast(`Autopilot running (budget $${max_cost_usd}). It stops when it needs you.`, "ok"); await openProject(id); }, "primary");
    case "requeue": return btn("Requeue", () => run(() => api(`/api/task/${encodeURIComponent(s.payload.task)}/requeue`, {}), "Task back to READY."));
    default: return el("span");
  }
}

// ---------- spec ----------
function renderSpec(p) {
  const s = p.spec;
  if (qs("theme-text") && qs("theme-text").dataset.dirty !== "1") qs("theme-text").value = s.theme || "";
  if (qs("theme-save")) qs("theme-save").onclick = async () => { try { await api(`/api/project/${p.id}/theme`, { theme: qs("theme-text").value }); delete qs("theme-text").dataset.dirty; toast("Theme saved; designer runs from now on follow it.", "ok"); } catch (e) { toast(e.message, "bad"); } }; qs("spec-state").textContent = `Spec ${p.spec_state} · schema ${s.schema_version}`;
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
  if ((s.behaviors || []).length) {
    const wrap = el("div", null, "spec-box"); wrap.style.marginTop = "10px"; wrap.append(el("h4", `Behaviors the coder builds after generation (${s.behaviors.length})`));
    wrap.append(el("div", "Each becomes a feature card with a coder task; every acceptance criterion becomes a GameTest. Say what to change in the answer box if one is wrong.", "muted"));
    for (const b of s.behaviors) {
      const d = el("div", null, "behavior"); d.append(el("b", b.title), ...(b.kind === "capability" ? [el("span", "capability", "art-source authored")] : []), el("div", b.description, "art-concept"));
      const ul = el("ul"); for (const a of b.acceptance || []) ul.append(el("li", a)); d.append(ul);
      const meta = []; if (b.kind !== "capability" && (b.affects || []).length) meta.push("about: " + b.affects.join(", ")); if ((b.after || []).length) meta.push("after: " + b.after.join(", "));
      if (meta.length) d.append(el("small", meta.join(" · "), "muted"));
      if (b.kind === "capability") {   // who carries it: every mob as a toggle, so a wrong guess is one click away
        const bid = b.title.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 40) || "feature";
        const row = el("div", null, "carriers"); row.append(el("span", "Carried by:", "muted"));
        for (const m of s.mobs || []) {
          const on = (b.affects || []).includes(m.identifier);
          row.append(btn((on ? "✓ " : "") + m.label, async () => {
            const next = on ? b.affects.filter(x => x !== m.identifier) : [...b.affects, m.identifier];
            if (!next.length) return toast("A capability needs at least one carrier", "bad");
            try {
              const r = await api(`/api/project/${p.id}/behavior-carriers`, { behavior: bid, carriers: next });
              toast(r.task ? `Carriers saved. Coder task ${r.task}: ${r.how || "planned"}` : "Carriers saved; the spec returns to draft, approve it again", "ok");
              await openProject(p.id);
            } catch (e) { toast(e.message, "bad"); }
          }, "mini " + (on ? "primary" : "secondary")));
        }
        d.append(row);
      }
      wrap.append(d);
    }
    body.append(wrap);
  }
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
async function renderGallery(p) {
  const g = qs("gallery"); g.replaceChildren();
  if (!p.gallery.length) { g.append(el("p", "This mod has no mobs. Add one with craftctl add-mob before generating, or describe it in the idea.", "muted")); return; }
  await loadArt(p.id);
  for (const m of p.gallery) {
    const card = el("div", null, "mob"); card.dataset.focus = "mob:" + m.mob;
    const head = el("div", null, "mob-head"); head.append(el("h4", `${m.label} · ${m.behavior} · ${m.body_plan || "quadruped"}`));
    const meta = el("div", null, "mob-meta");
    meta.append(el("span", m.placeholder ? "placeholder model" : "designer model", "pill " + (m.placeholder ? "warn" : "purple")));
    if (m.task_state) meta.append(el("span", "MODEL task " + m.task_state, "pill " + (m.task_state === "DONE" ? "ok" : m.task_state === "FAILED" ? "bad" : "info")));
    if (m.bbmodel) meta.append(el("span", ".bbmodel ✓", "pill ok")); if (m.geo && m.animation) meta.append(el("span", "geo + animation ✓", "pill ok"));
    meta.append(btn("Art", () => editArt(p.id, "mob", m.identifier, () => openProject(p.id)), "mini secondary"));
    head.append(meta); card.append(head); card.append(artLine(artMap[`mob:${m.identifier}`]));
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
    const size = el("div", null, "drops-inline size-inline"); size.append(el("span", "Size:", "muted"));
    size.append(el("span", m.scale && m.scale !== 1 ? `${m.scale}× the model` : "as modeled", m.scale && m.scale !== 1 ? "drop-chip" : "dim"));
    size.append(btn("Resize", async () => {
      const v = await promptBox("How big, compared with the model as it is? 1 = as modeled, 2 = twice as big, 0.5 = half (0.0625 to 16). The hitbox grows with it; the shape, skin and animations stay as they are, and no agent runs.",
                                String(m.scale || 1), { title: `Size — ${m.label}`, ok: "Resize", multiline: false, required: true });
      if (v == null) return;
      const out = await api(`/api/project/${p.id}/mob-scale`, { mob: m.mob, scale: Number(v) });
      toast(!out.changed ? "Same size: nothing to change." : out.how === "patched" ? out.note : out.how === "coder task" ? `Resize sent to the coder (${out.why}). Dispatch it from Now.` : "Size saved. The spec is back to draft: approve it again to generate.", "ok");
      await refreshProject(p.id);
    }, "mini secondary"));
    card.append(size);
    const moodText = (mood) => Object.entries(mood || {}).sort((x, y) => y[1] - x[1]).map(([k, v]) => `${k} ${v}`).join(" · ");
    if (moodText(m.mood)) card.append(el("div", "mood: " + moodText(m.mood), "art-ref"));
    if (m.design_notes) {   // what the designer explored before building: a record, and a menu for a redesign
      const det = document.createElement("details"); det.className = "design-notes"; det.append(el("summary", "Designer's notes: the ideas it explored"));
      const ol = el("ol"); m.design_notes.takes.forEach((t, i) => { const li = el("li", t); if (m.design_notes.chosen === i + 1) li.className = "chosen"; ol.append(li); });
      det.append(ol); if (m.design_notes.why) det.append(el("small", "It built the highlighted one: " + m.design_notes.why, "muted")); card.append(det);
    }
    if (m.feedback.length) {
      const ul = el("ul", null, "feedback-list");
      for (const f of m.feedback) ul.append(el("li", "you: " + [f.text, f.scope && f.scope !== "all" ? `(only the ${f.scope})` : "", f.take ? `(take ${f.take})` : "", f.mood ? `(mood: ${moodText(f.mood)})` : ""].filter(Boolean).join(" ")));
      card.append(el("div", "Feedback sent to the designer:", "muted")); card.append(ul);
    }
    card.append(modifyPanel(p, m), ownModelPanel(p, m));
    if (!m.placeholder && m.geo) card.append(animatePanel(p, "mob", m.mob, "Animate this mob (new moves, movement states)"));
    const fb = el("form", null, "feedback"); const ta = el("textarea");
    ta.placeholder = m.placeholder ? "Describe the creature you want, in your own words. It goes to the designer's first run, exactly as you write it" : "What should change? Leave it empty if the options below say it";
    fb.append(ta);
    // ---- everything below is optional: a redesign works with just the text, and the first design needs nothing at all
    const opts = { scope: "all", take: null, mood: { ...(m.mood || {}) } };
    const more = document.createElement("details"); more.className = "redesign-options"; more.append(el("summary", "Redesign options (all optional)"));
    const labelled = (text, control) => { const w = el("label", null, "opt-field"); w.append(el("span", text, "dlg-label"), control); return w; };
    if (!m.placeholder) {
      const scope = el("select"); for (const [v, t] of [["all", "Everything"], ["shape", "Only the shape (keep the skin's look)"], ["skin", "Only the skin (keep the shape and animations)"]]) { const o = el("option", t); o.value = v; scope.append(o); }
      scope.onchange = () => { opts.scope = scope.value; }; more.append(labelled("What to change", scope));
    }
    if (m.design_notes) {
      const box = el("div", null, "takes"); box.append(el("span", "Try another of its ideas", "dlg-label"));
      const choices = [["", "Keep going with the current one"], ...m.design_notes.takes.map((t, i) => [String(i + 1), `Take ${i + 1}${m.design_notes.chosen === i + 1 ? " (the one it built)" : ""}: ${t}`])];
      for (const [v, t] of choices) { const r = el("label", null, "take-choice"); const inp = el("input"); inp.type = "radio"; inp.name = "take-" + m.mob; inp.value = v; inp.checked = v === ""; inp.onchange = () => { opts.take = v ? Number(v) : null; }; r.append(inp, el("span", " " + t)); box.append(r); }
      more.append(box);
    }
    const moodBox = el("div", null, "mood-dials"); more.append(el("span", "Mood: how it should feel (suggestions for the artists, not rules)", "dlg-label"), moodBox);
    const drawMood = () => {
      moodBox.replaceChildren();
      for (const k of Object.keys(opts.mood)) {
        const r = el("div", null, "mood-dial"); const out = el("output", String(opts.mood[k])); const inp = el("input"); inp.type = "range"; inp.min = 0; inp.max = 1; inp.step = 0.05; inp.value = opts.mood[k];
        inp.oninput = () => { opts.mood[k] = Number(inp.value); out.textContent = String(opts.mood[k]); };
        const del = el("button", "×", "mini secondary"); del.type = "button"; del.title = "Remove this dial"; del.onclick = () => { delete opts.mood[k]; drawMood(); };
        r.append(el("span", k, "mood-name"), inp, out, del); moodBox.append(r);
      }
      const add = el("div", null, "mood-add"); const name = el("input"); name.placeholder = "add a dial: eerie, gore, cute, toon..."; name.maxLength = 24;
      const go = el("button", "Add", "mini secondary"); go.type = "button";
      go.onclick = () => { const k = name.value.trim().toLowerCase(); if (!/^[a-z][a-z '\-]{1,23}$/.test(k)) return toast("A dial is a word or two, 2 to 24 letters", "bad"); if (!(k in opts.mood)) opts.mood[k] = 0.5; drawMood(); };
      name.onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); go.click(); } }; add.append(name, go); moodBox.append(add);
    };
    drawMood();
    const refs = el("div", null, "refs"); refs.append(el("span", "Reference images (optional): pictures to say 'like this'", "dlg-label"));
    const thumbs = el("div", null, "ref-thumbs");
    for (const rel of m.references || []) {
      const t = el("div", null, "ref-thumb"); const img = el("img"); img.src = fileUrl(p.id, rel); img.alt = rel; img.onclick = () => openLightbox(img.src, rel);
      const del = el("button", "×", "mini secondary"); del.type = "button"; del.title = "Remove this reference";
      del.onclick = async () => { try { await api(`/api/project/${p.id}/remove-reference`, { mob: m.mob, name: rel.split("/").pop() }); await openProject(p.id); } catch (e) { toast(e.message, "bad"); } };
      t.append(img, del); thumbs.append(t);
    }
    const pick = el("input"); pick.type = "file"; pick.accept = "image/png,image/jpeg,image/webp"; pick.className = "ref-input";
    pick.onchange = async () => {
      const f = pick.files && pick.files[0]; if (!f) return;
      try {
        const data = await new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(String(r.result).split(",")[1]); r.onerror = () => rej(new Error("Could not read the image")); r.readAsDataURL(f); });
        await api(`/api/project/${p.id}/reference`, { mob: m.mob, data }); toast("Reference attached. The designer will be told about it.", "ok"); await openProject(p.id);
      } catch (e) { toast(e.message, "bad"); }
    };
    refs.append(thumbs, pick); more.append(refs); fb.append(more);
    const row = el("div", null, "actions");
    row.append(btn(m.placeholder && !m.feedback.length ? "Send and run designer" : "Send feedback and rerun designer", async () => {
      const body = { mob: m.mob, text: ta.value.trim() };
      if (opts.scope !== "all") body.scope = opts.scope;
      if (opts.take) body.take = opts.take;
      if (JSON.stringify(opts.mood) !== JSON.stringify(m.mood || {})) body.mood = opts.mood;
      if (!body.text && !body.scope && !body.take && !body.mood && (m.references || []).length) body.text = "Take the attached reference images into account.";
      if (!body.text && !body.scope && !body.take && !body.mood) throw new Error("Write what should change, or open the options and pick one");
      const out = await api(`/api/project/${p.id}/feedback`, body);
      if (!await confirmBox("Feedback saved. Start the designer now? (about $12 and 24 minutes)", { title: "Start the designer", ok: "Start designer", cancel: "Not now" })) { await openProject(p.id); return; }
      await api(`/api/project/${p.id}/dispatch`, { task: out.task }); toast("Designer started with your feedback.", "ok"); await openProject(p.id);
    }, "primary"));
    if (m.task_state === "READY") row.append(btn("Run designer as is", async () => { await api(`/api/project/${p.id}/dispatch`, { task: m.task }); toast("Designer started.", "ok"); await openProject(p.id); }));
    if (m.bbmodel) {
      row.append(btn("Open in Blockbench", async () => { const out = await api(`/api/project/${p.id}/open-model`, { mob: m.mob }); toast(out.note || `Opening ${out.opened.split(/[\\/]/).pop()} in ${out.app ? "Blockbench" : "the default app"}…`, "ok"); }, "secondary"));
      row.append(btn("Install my Blockbench edits", async () => {
        if (!await confirmBox(`Install what you saved to models/${m.mob}.bbmodel as this mob's model? It is checked like a designer's model first; nothing changes if it does not pass.`, { title: "Install your edits", ok: "Install" })) return;
        const out = await api(`/api/project/${p.id}/model-reinstall`, { mob: m.mob }); toast(out.note, "ok"); await refreshProject(p.id);
      }, "secondary"));
      row.append(el("span", `models/${m.mob}.bbmodel: edit and save it in Blockbench, then install your edits`, "muted"));
    }
    fb.append(row); card.append(fb); g.append(card);
  }
}

// ---------- Hold: how a 3D item sits in the hand, computed from three facts; previews before any build ----------
function holdPanel(p, f) {
  const box = document.createElement("details"); box.className = "hold-panel"; box.dataset.item = f.identifier;
  const h = f.hold || {};
  box.append(el("summary", `Hold: ${h.style || "not declared"}${h.front ? ` · front ${h.front}` : ""}`));
  const prev = el("div", null, "previews");
  for (const rel of f.hold_previews || []) { const pv = el("div", null, "preview"); const img = el("img"); img.src = fileUrl(p.id, rel); img.alt = rel; pv.append(img, el("small", rel.includes("firstperson") ? "first person" : "in the hand")); pv.onclick = () => openLightbox(img.src, rel); prev.append(pv); }
  if (!(f.hold_previews || []).length) prev.append(el("div", "No in-hand preview yet.", "placeholder-note"));
  box.append(prev);
  const sel = (cls, opts, cur) => { const s = el("select"); s.className = cls; for (const o of opts) { const op = el("option", o); op.value = o; if (o === cur) op.selected = true; s.append(op); } return s; };
  const style = sel("hold-style", ["aim", "wield", "carry"], h.style || "carry"), front = sel("hold-front", ["-z", "+z", "+x", "-x", "+y", "-y"], h.front || "-z"), top = sel("hold-top", ["auto", "+y", "-y", "+x", "-x", "+z", "-z"], h.top || "auto");
  const row = el("div", null, "hold-row"); row.append(el("span", "style", "dlg-label"), style, el("span", "front points", "dlg-label"), front, el("span", "top points", "dlg-label"), top);
  row.append(btn("Apply", async () => {
    const out = await api(`/api/project/${p.id}/hold`, { item: f.identifier, style: style.value, front: front.value, top: top.value === "auto" ? null : top.value });
    toast(`Held as ${out.hold.style}, front ${out.hold.front}. F3+T in the game reloads it.`, "ok"); await refreshProject(p.id);
  }, "mini"));
  box.append(el("div", "aim: pointed at something (a gun, a wand). wield: swung or carried upright (a sword, a staff). carry: anything else. The front is where the muzzle or tip points; the top is where its sights or back face.", "muted"), row);
  return box;
}

// Project-wide fine tuning of a hold style: offsets added to the computed pose for every item held that way.
function holdStylePanel(p, data) {
  const box = document.createElement("details"); box.className = "hold-style-panel";
  box.append(el("summary", "Fine-tune how a hold style sits (all items of that style)"));
  const style = el("select"); style.className = "hs-style"; for (const s of data.all) { const o = el("option", s); o.value = s; style.append(o); }
  const ctx = el("select"); ctx.className = "hs-context"; for (const c of ["thirdperson_righthand", "firstperson_righthand", "ground", "fixed", "head"]) { const o = el("option", c); o.value = c; ctx.append(o); }
  const nums = {}; const row = el("div", null, "hold-row"); row.append(style, ctx);
  for (const key of ["rotation", "translation"]) for (const ax of "xyz") { const i = el("input"); i.type = "number"; i.step = key === "rotation" ? "5" : "0.5"; i.className = `hs-${key}-${ax}`; i.placeholder = `${key[0]}${ax}`; i.style.width = "4.5em"; nums[`${key}-${ax}`] = i; row.append(i); }
  const sc = el("input"); sc.type = "number"; sc.step = "0.05"; sc.className = "hs-scale"; sc.placeholder = "×scale"; sc.style.width = "5em"; row.append(sc);
  const load = () => { const t = ((data.styles || {})[style.value] || {})[ctx.value] || {}; for (const key of ["rotation", "translation"]) "xyz".split("").forEach((ax, i) => { nums[`${key}-${ax}`].value = t[key] ? t[key][i] : ""; }); sc.value = t.scale ?? ""; };
  style.onchange = load; ctx.onchange = load; load();
  row.append(btn("Apply", async () => {
    const tweaks = JSON.parse(JSON.stringify((data.styles || {})[style.value] || {}));
    const t = {}; for (const key of ["rotation", "translation"]) { const v = "xyz".split("").map((ax) => Number(nums[`${key}-${ax}`].value || 0)); if (v.some((x) => x !== 0)) t[key] = v; }
    if (sc.value) t.scale = Number(sc.value);
    if (Object.keys(t).length) tweaks[ctx.value] = t; else delete tweaks[ctx.value];
    const out = await api(`/api/project/${p.id}/hold-style`, { style: style.value, tweaks });
    toast(`${style.value} tuned; ${out.recomputed.length} item(s) recomputed. F3+T in the game reloads them.`, "ok"); await refreshProject(p.id);
  }, "mini"), btn("Reset style", async () => { const out = await api(`/api/project/${p.id}/hold-style`, { style: style.value, tweaks: {} }); toast(`${style.value} back to the computed pose (${out.recomputed.length} item(s)).`, "ok"); await refreshProject(p.id); }, "mini secondary"));
  box.append(el("div", "Offsets on top of the computed pose: degrees, pixels, and a scale factor. Leave a field empty for no change.", "muted"), row);
  return box;
}

// ---------- Animate: what it does (designer) and when it plays (coder); the model's shape and texture stay locked ----------
function animatePanel(p, kind, ident, title) {
  const box = document.createElement("details"); box.className = "animate-panel"; box.dataset.target = `${kind}:${ident}`;
  box.append(el("summary", title || "Animate"));
  box.append(el("div", "Describe each animation: what it does (the designer animates it; the model's shape and texture stay as they are) and when it plays (a coder makes it play then).", "muted"));
  const rows = el("div", null, "anim-rows"); box.append(rows);
  const addRow = () => {
    const r = el("div", null, "anim-row");
    const name = el("input"); name.placeholder = "name"; name.className = "anim-name"; name.maxLength = 24;
    const what = el("textarea"); what.placeholder = "what it does"; what.className = "anim-what"; what.rows = 2; what.maxLength = 800;
    const when = el("input"); when.placeholder = "when it plays"; when.className = "anim-when"; when.maxLength = 300;
    const loopL = el("label", null, "part-choice"); const loop = el("input"); loop.type = "checkbox"; loop.className = "anim-loop"; loopL.append(loop, el("span", " lasts while it happens (loops)"));
    r.append(name, what, when, loopL);
    if (kind === "item") { const body = el("textarea"); body.placeholder = "the player's body during it (optional): arms, torso, head"; body.className = "anim-player"; body.rows = 2; body.maxLength = 800; r.append(body); }
    rows.append(r);
  };
  addRow();
  const remove = el("input"); remove.placeholder = "clips to remove (names, comma separated), optional"; remove.className = "anim-remove";
  box.append(btn("Add another", () => addRow(), "mini secondary"), remove);
  box.append(btn("Animate", async () => {
    const anims = [...rows.querySelectorAll(".anim-row")].map((r) => ({ name: r.querySelector(".anim-name").value.trim(), what: r.querySelector(".anim-what").value.trim(),
      when: r.querySelector(".anim-when").value.trim(), loop: r.querySelector(".anim-loop").checked,
      ...(r.querySelector(".anim-player")?.value.trim() ? { player: r.querySelector(".anim-player").value.trim() } : {}) })).filter((a) => a.name || a.what || a.when);
    const rm = remove.value.split(",").map((x) => x.trim()).filter(Boolean);
    if (!anims.length && !rm.length) throw new Error("Describe at least one animation");
    const out = await api(`/api/project/${p.id}/animate`, { kind, ident, anims, remove: rm });
    if (await confirmBox("Saved. Start the designer now? It only animates; the model's shape and texture are locked.", { title: "Start the designer", ok: "Start designer", cancel: "Not now" })) {
      await api(`/api/project/${p.id}/dispatch`, { task: out.task }); toast("Designer animating…", "ok");
    }
    await refreshProject(p.id);
  }, "primary"));
  return box;
}

// ---------- open a model's .bbmodel in the user's Blockbench (mob, 3D item or 3D projectile) ----------
async function openModel(p, which) {
  const out = await api(`/api/project/${p.id}/open-model`, which);
  toast(out.note || `Opening ${out.opened.split(/[\\/]/).pop()} in ${out.app ? "Blockbench" : "the default app"}…`, "ok");
}

// ---------- 3D model for one item ----------
// Opt-in, one item at a time: it costs a designer run, so the dialog says what earlier designer runs cost before anything starts.
async function make3d(p, f) {
  const est = await api(`/api/project/${p.id}/item3d-estimate`, {});
  const cost = est.runs ? `Your ${est.runs} earlier designer run(s) averaged $${est.avg_usd} and ${est.avg_minutes} min (the most expensive: $${est.max_usd}). A 3D model usually takes more than an icon.`
                        : "There are no earlier designer runs to estimate from yet; a 3D model takes more than an icon.";
  const notes = await formBox({ title: `3D model — ${f.label}`, message: (f.projectile ? `The designer builds a 3D model of ${f.label} that flies nose first; then a coder switches its renderer. `
           : f.kind === "block" ? `The designer builds a 3D model of ${f.label}; in the world it replaces the cube (its item keeps the icon). ` : `The designer builds a 3D model of ${f.label}: in the hand, on the ground and in frames it replaces the flat icon; the inventory keeps the icon. `) + cost,
    fields: [{ name: "notes", label: f.model3d ? "What should change in the current model? (and what should animate when it is used, hits or is drawn)" : "Notes for the designer (optional): how it looks, and what should animate when it is used, hits or is drawn", value: "", multiline: true }], ok: "Ask the designer" });
  if (notes == null) return;
  const out = f.projectile ? await api(`/api/project/${p.id}/proj3d`, { projectile: f.identifier, notes: (notes.notes || "").trim() })
            : f.kind === "block" ? await api(`/api/project/${p.id}/block3d`, { block: f.identifier, notes: (notes.notes || "").trim() })
                           : await api(`/api/project/${p.id}/item3d`, { item: f.identifier, notes: (notes.notes || "").trim() });
  if (await confirmBox("Request saved. Start the designer now?", { title: "Start the designer", ok: "Start designer", cancel: "Not now" })) {
    await api(`/api/project/${p.id}/dispatch`, { task: out.task }); toast("Designer building the 3D model…", "ok");
  }
  await refreshProject(p.id);
}

// ---------- modify an existing model / use your own ----------
// A modification keeps the model and changes only what is asked; the controller refuses the result if it touched a part that
// was not ticked here. Nothing is ticked by default: the designer may only add.
function modifyPanel(p, m) {
  const box = document.createElement("details"); box.className = "modify-panel";
  box.append(el("summary", "Modify this model (keep everything else)"));
  if (m.placeholder || !m.geo) { box.append(el("div", "There is no finished model yet: the first design comes from the designer, or use your own model.", "placeholder-note")); return box; }
  if (m.modification) {
    box.open = true;
    const pend = el("div", null, "modify-pending");
    pend.append(el("span", `Pending: “${m.modification.text}”` + (m.modification.may_change.length ? ` (may change: ${m.modification.may_change.join(", ")})` : " (it only adds)"), "art-ref"));
    pend.append(btn("Run designer", async () => { await api(`/api/project/${p.id}/dispatch`, { task: m.task }); toast("Designer started on the modification.", "ok"); await refreshProject(p.id); }, "mini"));
    pend.append(btn("Cancel modification", async () => { await api(`/api/project/${p.id}/model-edit-cancel`, { mob: m.mob }); toast("Modification cancelled. The model stays as it is.", "ok"); await refreshProject(p.id); }, "mini secondary"));
    box.append(pend);
    return box;
  }
  const ta = el("textarea"); ta.placeholder = "What to change, in your words: add a tail, a horn on the forehead, longer claws..."; ta.maxLength = 2000;
  const parts = el("div", null, "modify-parts"); parts.append(el("span", "Parts it may also change (leave all unticked and it only adds; everything unticked is protected)", "dlg-label"));
  for (const b of m.bones || []) { const l = el("label", null, "part-choice"); const c = el("input"); c.type = "checkbox"; c.value = b; l.append(c, el("span", " " + b)); parts.append(l); }
  const go = btn("Modify", async () => {
    const text = ta.value.trim(); if (!text) throw new Error("Write what to change on the model");
    const may_change = [...parts.querySelectorAll("input:checked")].map((c) => c.value);
    const out = await api(`/api/project/${p.id}/model-edit`, { mob: m.mob, text, may_change });
    if (await confirmBox("Modification saved. Start the designer now? It works on this model and only on what you asked.", { title: "Start the designer", ok: "Start designer", cancel: "Not now" })) {
      await api(`/api/project/${p.id}/dispatch`, { task: out.task }); toast("Designer started on the modification.", "ok");
    }
    await refreshProject(p.id);
  }, "primary");
  box.append(ta, parts, go);
  return box;
}

const readBase64 = (file) => new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(String(r.result).split(",")[1]); r.onerror = () => rej(new Error("Could not read " + file.name)); r.readAsDataURL(file); });

function ownModelPanel(p, m) {
  const box = document.createElement("details"); box.className = "own-model";
  box.append(el("summary", "Use your own model"));
  box.append(el("div", "A Blockbench model you made or downloaded (.bbmodel, box UV). It replaces this mob's model after the same checks as a designer's model; then you can modify it like any other. No agent runs.", "muted"));
  const bb = el("input"); bb.type = "file"; bb.accept = ".bbmodel,application/json"; bb.className = "own-bbmodel";
  const png = el("input"); png.type = "file"; png.accept = "image/png"; png.className = "own-png";
  const field = (label, input) => { const w = el("label", null, "opt-field"); w.append(el("span", label, "dlg-label"), input); return w; };
  box.append(field(".bbmodel", bb), field("Its texture (PNG), only if it is not inside the .bbmodel", png));
  box.append(btn("Install this model", async () => {
    const f = bb.files && bb.files[0]; if (!f) throw new Error("Choose the .bbmodel file first");
    const body = { mob: m.mob, bbmodel_base64: await readBase64(f) };
    if (png.files && png.files[0]) body.png_base64 = await readBase64(png.files[0]);
    if (!m.placeholder && !await confirmBox(`Replace ${m.label}'s current model with ${f.name}?`, { title: "Use your own model", ok: "Replace" })) return;
    const out = await api(`/api/project/${p.id}/model-import`, body); toast(out.note, "ok"); await refreshProject(p.id);
  }, "secondary"));
  return box;
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
    const spawn = qs("am-spawn").checked ? { biomes: qs("am-biomes").value.split(",").map(s => s.trim()).filter(Boolean), weight: Number(qs("am-weight").value), min_group: Number(qs("am-gmin").value), max_group: Number(qs("am-gmax").value) } : null;
    const out = await api(`/api/project/${selected}/add-mob`, { identifier: qs("am-id").value.trim(), label: qs("am-label").value.trim(), behavior: qs("am-behavior").value, body_plan: qs("am-body-plan").value, drops, spawn });
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
// ---------- art direction ----------
let artMap = {};
async function loadArt(pid) { try { artMap = await api(`/api/project/${pid}/art`); } catch (e) { artMap = {}; } }
function artLine(a) {
  const wrap = el("div", null, "art-line");
  if (!a) return wrap;
  wrap.append(el("div", a.concept, "art-concept"));
  const tags = el("div", null, "art-tags");
  for (const t of (a.tags || []).slice(0, 8)) tags.append(el("span", t, "art-tag"));
  tags.append(el("span", a.source === "derived" ? "auto from theme" : "written", "art-source " + a.source));
  wrap.append(tags);
  if (a.reference) wrap.append(el("div", "like: " + a.reference, "art-ref"));
  if ((a.avoid || []).length) wrap.append(el("div", "not: " + a.avoid.join(", "), "art-ref art-avoid"));
  return wrap;
}
// kind: item | block | food | mob | set (concept + visual cues) | tool | armor (one piece: its own concept)
async function editArt(pid, kind, identifier, onDone) {
  const a = artMap[`${kind}:${identifier}`] || { concept: "", tags: [], silhouette: "", source: "derived", label: identifier };
  const pieceOnly = kind === "tool" || kind === "armor";
  const fields = [{ name: "concept", label: "What it looks like, and why", multiline: true, rows: 4, value: a.source === "derived" ? "" : a.concept,
                    help: "One or two sentences, concrete: shapes, materials, wear. Empty = derive from the theme." }];
  if (!pieceOnly) fields.push({ name: "tags", label: "Visual cues", multiline: true, rows: 2, value: a.source === "derived" ? "" : (a.tags || []).join(", "),
                                help: "Comma separated, e.g. serrated edge, bone teeth, hammered iron, rust red. Empty = derive from the theme." },
                              { name: "reference", label: "It should resemble", value: a.reference || "", help: "A creature or character the designer cannot see, e.g. the Tank from Left 4 Dead, a vanilla pig." },
                              { name: "avoid", label: "It must NOT look like", value: (a.avoid || []).join(", "), help: "Comma separated, e.g. cartoon, bright saturated colours, stripes. This wins over every default." });
  const out = await formBox({ title: `Art direction: ${a.label || identifier}`, fields, ok: "Save art direction" });
  if (out === null) return;
  const tags = pieceOnly ? [] : (out.tags || "").split(",").map(x => x.trim()).filter(Boolean);
  const avoid = pieceOnly ? [] : (out.avoid || "").split(",").map(x => x.trim()).filter(Boolean);
  await api(`/api/project/${pid}/set-art`, { kind, identifier, concept: out.concept.trim(), tags, silhouette: a.silhouette || "", reference: pieceOnly ? "" : (out.reference || "").trim(), avoid });
  toast("Art direction saved", "ok");
  if (onDone) await onDone();
}

async function renderFeatures(p) {
  const list = qs("features-list"); list.replaceChildren();
  let feats = []; try { feats = await api(`/api/project/${p.id}/features`); } catch (e) { list.append(el("p", e.message, "muted")); return; }
  featureCache = feats;
  await loadArt(p.id);
  const bar = document.querySelector("#sub-items .add-bar");
  if (bar && !bar.querySelector("#restore-sprites-btn")) { const rb = btn("Restore designer icons", async () => { const out = await api(`/api/project/${p.id}/restore-sprites`, {}); toast(`Restored ${out.installed.length} file(s)${Object.keys(out.rejected || {}).length ? "; rejected: " + Object.keys(out.rejected).join(", ") : ""}. Rebuild to apply.`, "ok"); await openProject(p.id); }, "secondary"); rb.id = "restore-sprites-btn"; bar.append(rb); }
  try { const sheet = await api(`/api/project/${p.id}/contact-sheet`); const box = qs("sheet-box"); if (sheet.path) { box.classList.remove("hidden"); qs("sheet-img").src = fileUrl(p.id, sheet.path); qs("sheet-preview").onclick = () => openLightbox(qs("sheet-img").src, "sprites contact sheet"); } else box.classList.add("hidden"); } catch {}
  const generated = ["SOURCE_GENERATED_UNVERIFIED", "BUILD_PASSED_GAME_UNTESTED", "BUILD_FAILED", "GAME_VERIFIED"].includes(p.status);
  if (generated && feats.some((f) => f.model3d && f.kind !== "block")) {   // at least one 3D item: offer the project-wide hold tuning
    try { list.append(holdStylePanel(p, await api(`/api/project/${p.id}/hold-styles`))); } catch (e) { /* the items still render */ }
  }
  const uploadInput = (onFile) => { const up = el("input"); up.type = "file"; up.accept = "image/png"; up.style.display = "none"; up.onchange = async () => { const file = up.files[0]; if (!file) return; const b64 = await new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(r.result.split(",")[1]); r.onerror = rej; r.readAsDataURL(file); }); try { await onFile(b64); } catch (err) { toast(err.message, "bad"); } up.value = ""; }; return up; };
  const featureRow = (f) => {
    const row = el("div", null, "feature"); const img = el("img"); img.alt = "";
    if (f.texture) img.src = fileUrl(p.id, f.texture); else img.style.visibility = "hidden";
    const mid = el("div"); const nm = el("div", null, "fname"); nm.append(document.createTextNode(f.label), el("span", f.kind, "fk")); mid.append(nm, el("div", `${p.id}:${f.identifier}`, "fid"));
    const bits = []; if (f.recipes?.length) bits.push("recipes: " + f.recipes.join(", ")); if (f.drop) bits.push(`drops ${f.drop.item} ${f.drop.count_min}-${f.drop.count_max}`);
    if (f.food) bits.push(`nutrition ${f.food.nutrition} · saturation ${f.food.saturation}` + (f.food.effects?.length ? " · " + f.food.effects.map(e => e.effect.replace("minecraft:", "")).join(", ") : ""));
    if (f.ore) bits.push(`worldgen: ${f.ore.vein_size}-block veins ×${f.ore.veins_per_chunk}/chunk, y ${f.ore.min_y}..${f.ore.max_y}`);
    if (bits.length) mid.append(el("small", bits.join(" · ")));
    mid.append(artLine(artMap[`${f.kind}:${f.identifier}`]));
    const right = el("div", null, "actions"); right.style.marginTop = "0";
    if (f.kind === "block" && !f.ore) right.append(btn("Generate in world", async () => { const spec = await promptBox(`Ore veins for ${f.identifier}: "size count minY maxY [biomes]" — e.g. "9 8 -64 64 overworld"`, "9 8 -64 64 overworld"); if (!spec) return; const [sz, cnt, mn, mx, ...bi] = spec.trim().split(/\s+/); const out = await api(`/api/project/${p.id}/add-ore`, { block: f.identifier, vein_size: Number(sz), veins_per_chunk: Number(cnt), min_y: Number(mn), max_y: Number(mx), biomes: bi.length ? bi : ["overworld"] }); toast(out.generated ? `Worldgen written; the coder registers it (${out.task}) — see Now.` : "Worldgen added to the spec.", "ok"); await openProject(p.id); }, "mini secondary"));
    const up = uploadInput(async (b64) => { const out = await api(`/api/project/${p.id}/set-texture`, { kind: f.kind === "block" ? "block" : "item", identifier: f.identifier, png_base64: b64 }); toast(out.note, "ok"); await openProject(p.id); });
    if (generated && f.can3d) right.append(btn(f.model3d ? "3D model…" : "Make it 3D", () => make3d(p, f), f.model3d ? "mini secondary" : "mini"));
    if (generated && f.model3d) right.append(btn("Open in Blockbench", () => openModel(p, f.kind === "block" ? { block: f.identifier } : { item: f.identifier }), "mini secondary"));
    if (generated && f.model3d && f.kind === "block") mid.append(animatePanel(p, "block", f.identifier, "Animate this block"));
    if (generated && f.model3d && f.kind !== "block") mid.append(holdPanel(p, f));
    if (generated && f.model3d && f.kind !== "block") {
      right.append(btn("Reinstall", async () => { const out = await api(`/api/project/${p.id}/reinstall-3d`, { item: f.identifier });
        toast(out.anim_task ? `Reinstalled; its actions (${out.actions.join(", ")}) go to a coder: ${out.anim_task}` : "Reinstalled.", "ok"); await refreshProject(p.id); }, "mini secondary"));
      mid.append(animatePanel(p, "item", f.identifier, "Animate this item"));
    }
    right.append(up, btn("Upload icon", () => up.click(), "mini secondary"), btn("Redesign", () => openSpritesDialog([f.identifier]), "mini secondary"), btn("Art", () => editArt(p.id, f.kind, f.identifier, () => openProject(p.id)), "mini secondary"));
    right.append(btn("Rename", async () => { const label = await promptBox("Display name for " + f.identifier + ":", f.label); if (!label || label === f.label) return; const out = await api(`/api/project/${p.id}/rename-feature`, { identifier: f.identifier, label }); toast(out.note || "Renamed.", "ok"); await openProject(p.id); }, "mini secondary"));
    if (!f.material) { if (!generated) right.append(btn("Remove", async () => { if (!await confirmBox(`Remove ${f.identifier} from the spec?`, { title: "Remove from the spec", ok: "Remove", danger: true })) return; await api(`/api/project/${p.id}/remove-feature`, { identifier: f.identifier }); toast("Removed.", "ok"); await openProject(p.id); }, "mini secondary")); else { const nb = btn("Remove", () => {}, "mini secondary"); nb.disabled = true; nb.title = "Removing content after generation needs a coder task (coming later)"; right.append(nb); } }
    row.append(img, mid, right); return row;
  };
  // Material sets: one card per material with the set-level actions once, pieces inside.
  const materials = [...new Set(feats.filter(f => f.material).map(f => f.material))];
  for (const mat of materials) {
    const pieces = feats.filter(f => f.material === mat); const hasArmor = pieces.some(f => f.kind === "armor");
    const card = el("div", null, "mob"); card.dataset.focus = "set:" + mat; const head = el("div", null, "mob-head"); head.append(el("h4", `${mat} set · ${pieces.length} piece(s)`));
    const acts = el("div", null, "actions"); acts.style.marginTop = "0";
    acts.append(btn("Set art", () => editArt(p.id, "set", mat, () => openProject(p.id)), "mini secondary"));
    card.append(artLine(artMap[`set:${mat}`]));
    if (hasArmor) {
      const helmet = pieces.find(f => f.armor_previews) || pieces.find(f => f.kind === "armor");
      const is3d = pieces.some(f => f.armor_style === "3d");
      head.append(el("span", is3d ? "3D GeckoLib armor" : "textured armor", "pill"));
      if (is3d) acts.append(btn("Design 3D armor", async () => { const notes = await promptBox(`Notes for the designer about the ${mat} 3D armor (silhouette, crest, pauldrons, colours), or leave empty:`, ""); if (notes === null) return; const out = await api(`/api/project/${p.id}/armor3d-design`, { material: mat, notes }); if (await confirmBox(`Task ${out.task} created. Start the designer now? (~$1–2, 3–6 min)`)) { await api(`/api/project/${p.id}/dispatch`, { task: out.task }); toast("Designer modelling the armor in Blockbench; renders appear here when done.", "ok"); } await openProject(p.id); }, "mini primary"));
      else acts.append(btn("Design worn armor", async () => { const notes = await promptBox(`Notes for the designer about the ${mat} worn armor (style, motifs, colours), or leave empty:`, ""); if (notes === null) return; const out = await api(`/api/project/${p.id}/armor-design`, { material: mat, notes }); if (await confirmBox(`Task ${out.task} created. Start the designer now? (~$1, 2–4 min)`)) { await api(`/api/project/${p.id}/dispatch`, { task: out.task }); toast("Designer painting the worn armor; renders appear here when done.", "ok"); } await openProject(p.id); }, "mini primary"));
      acts.append(btn("Retint worn armor", async () => { const choice = await promptBox(`Worn armor for "${mat}":\n• leave EMPTY = match the icon's colours automatically\n• or type a colour like #2a9d8f`, ""); if (choice === null) return; const payload = choice.trim() ? { material: mat, color: choice.trim() } : { material: mat, match_icon: true }; const out = await api(`/api/project/${p.id}/retint-armor`, payload); toast(out.note, "ok"); await openProject(p.id); }, "mini secondary"));
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
      const variants = [...qs("af-variants").querySelectorAll("input:checked")].map(i => i.value);
      const out = await api(`/api/project/${p.id}/add-feature`, { kind: qs("af-kind").value, label: qs("af-label").value.trim(), identifier: qs("af-id").value.trim(), shape: qs("af-shape").value, color: qs("af-color-hex").value, tool: qs("af-tool").value, mining_level: qs("af-level").value, variants });
      if (qs("af-kind").value === "block" && qs("af-ore").checked) { try { await api(`/api/project/${p.id}/add-ore`, { block: out.identifier, ...oreFromForm() }); } catch (e2) { toast("Block added but worldgen failed: " + e2.message, "bad"); } }
      addForm.reset(); delete qs("af-id").dataset.touched; closeModal("modal-feat"); qs("af-kind").onchange();
      toast(out.generated ? `Added. Files written; the coder registers it (${out.task}) — see Now.` : "Added to the spec. Re-approve before generating.", "ok");
      await openProject(p.id);
    } catch (err) { toast(err.message, "bad"); }
  };
}
let featureCache = [];
function openSpritesDialog(preselect = []) {
  if (!selected) return;
  const pre = new Set(preselect);
  const list = qs("sprites-list"); list.replaceChildren();
  for (const f of featureCache) { const l = el("label"); const c = el("input"); c.type = "checkbox"; c.value = f.identifier; c.checked = pre.has(f.identifier); l.append(c, document.createTextNode(` ${f.label} (${f.kind})`)); list.append(l); }
  const mats = [...new Set(featureCache.filter(f => f.kind === "armor").map(f => f.material))];
  if (mats.length) { list.append(el("div", "Worn-armor layers (64×32, what you see on the body):", "muted")); for (const m of mats) { const l = el("label"); const c = el("input"); c.type = "checkbox"; c.value = m; c.dataset.armor = "1"; c.checked = pre.has("armor:" + m); l.append(c, document.createTextNode(` ${m} armor set`)); list.append(l); } }
  qs("sprites-notes").value = ""; qs("modal-sprites").classList.remove("hidden"); qs("sprites-notes").focus();
}
qs("sprites-btn").onclick = () => openSpritesDialog([]);
qs("sprites-all").onclick = () => { for (const c of qs("sprites-list").querySelectorAll("input")) c.checked = true; };
qs("sprites-none").onclick = () => { for (const c of qs("sprites-list").querySelectorAll("input")) c.checked = false; };
qs("sprites-go").onclick = async () => {
  const identifiers = [...qs("sprites-list").querySelectorAll("input:checked:not([data-armor])")].map(c => c.value);
  const armor = [...qs("sprites-list").querySelectorAll("input:checked[data-armor]")].map(c => c.value);
  if (!identifiers.length && !armor.length) return toast("Pick at least one icon or armor set to redesign", "bad");
  try {
    const out = await api(`/api/project/${selected}/sprites`, { identifiers, notes: qs("sprites-notes").value, armor });
    closeModal("modal-sprites");
    if (await confirmBox(`Redesign ${out.task} created for ${identifiers.length} icon(s)${armor.length ? " + " + armor.length + " armor set(s)" : ""}. Start the designer now?`)) { await api(`/api/project/${selected}/dispatch`, { task: out.task }); toast("Designer painting… the contact sheet appears in Items when done.", "ok"); }
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
      knockback_resistance: Number(qs("mt-kb").value), recipes: qs("mt-recipes").checked, color: qs("mt-color-hex").value, accent: qs("mt-accent-hex").value, armor_style: qs("mt-style").value });
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
qs("af-kind").onchange = () => { const b = qs("af-kind").value === "block"; qs("af-block-row").style.display = b ? "" : "none"; qs("af-ore-row").style.display = b ? "" : "none"; qs("af-variants-row").style.display = b ? "" : "none"; }; qs("af-kind").onchange();
qs("en-label").oninput = () => { if (!qs("en-id").dataset.touched) qs("en-id").value = qs("en-label").value.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 50); };
qs("en-id").oninput = () => { qs("en-id").dataset.touched = "1"; };
qs("ench-form").onsubmit = async (e) => {
  e.preventDefault(); if (!selected) return;
  try {
    const out = await api(`/api/project/${selected}/add-enchantment`, { identifier: qs("en-id").value.trim(), label: qs("en-label").value.trim(), kind: qs("en-kind").value, max_level: Number(qs("en-level").value), items: qs("en-items").value || null, weight: Number(qs("en-weight").value) });
    qs("ench-form").reset(); delete qs("en-id").dataset.touched; closeModal("modal-ench");
    toast(out.generated ? out.note : "Enchantment added to the spec (re-approve before generating).", "ok"); await openProject(selected);
  } catch (err) { toast(err.message, "bad"); }
};
qs("af-ore").onchange = () => { qs("af-ore-fields").style.display = qs("af-ore").checked ? "" : "none"; };
const oreFromForm = () => ({ vein_size: Number(qs("af-ore-size").value), veins_per_chunk: Number(qs("af-ore-count").value), min_y: Number(qs("af-ore-miny").value), max_y: Number(qs("af-ore-maxy").value), biomes: qs("af-ore-biomes").value.split(",").map(s => s.trim()).filter(Boolean), discard_on_air: Number(qs("af-ore-discard").value) });
qs("am-spawn").onchange = () => { qs("am-spawn-row").style.display = qs("am-spawn").checked ? "" : "none"; };
// ---- World-Gen tab ----
async function renderWorldgen(p) {
  const list = qs("wg-list"); if (!list) return; list.replaceChildren();
  let wg; try { wg = await api(`/api/project/${p.id}/worldgen`); } catch (e) { list.append(el("p", e.message, "muted")); return; }
  const section = (title, items, fmt) => { if (!items.length) return; list.append(el("div", title, "eyebrow")); for (const it of items) { const row = el("div", null, "feature"); const mid = el("div"); const nm = el("div", null, "fname"); nm.append(document.createTextNode(it.label || it.identifier || it.block), el("span", title.replace(/s$/, ""), "fk")); mid.append(nm, el("small", fmt(it))); row.append(el("div"), mid); list.append(row); } };
  section("ores", wg.ores, o => `${o.block}: ${o.vein_size}-block veins ×${o.veins_per_chunk}/chunk, y ${o.min_y}..${o.max_y}, ${(o.biomes || []).join(", ")}`);
  section("structures", wg.structures, s => `${s.layers[0][0].length}×${s.layers.length}×${s.layers[0].length} · every ${s.spacing} chunks (min ${s.separation}) · ${(s.biomes || []).join(", ")} · ${s.step.replace("_structures", "")}`);
  section("biomes", wg.biomes, b => `${b.base}-based · temp ${b.temperature} · sky ${b.sky_color}${b.mobs?.length ? " · mobs: " + b.mobs.join(", ") : ""}`);
  section("dimensions", wg.dimensions, d => `${(d.biomes || []).join(", ") || "plains"} · ${d.sky} sky · ${d.noise.replace("minecraft:", "")} · key: ${d.key_item || d.identifier + "_key"}`);
  if (!wg.ores.length && !wg.structures.length && !wg.biomes.length && !wg.dimensions.length) list.append(el("p", "Nothing yet. Ores live on blocks (Items tab); add structures, biomes and dimensions below.", "muted"));
  const checks = (box, ids) => { const b = qs(box); b.replaceChildren(); for (const id of ids) { const l = el("label"); const c = el("input"); c.type = "checkbox"; c.value = id; l.append(c, document.createTextNode(" " + id)); b.append(l); } if (!ids.length) b.append(el("span", "none yet", "muted")); };
  checks("bi-mobs", wg.mobs); checks("dm-biomes", wg.biomes.map(b => b.identifier));
  for (const b of document.querySelectorAll('#sub-worldgen [data-modal]')) { b.disabled = !!wg.generated; b.title = wg.generated ? "After generation, request worldgen as a change on the Map" : ""; }
}
for (const [c, h] of [["bi-sky", "bi-sky-hex"], ["bi-fog", "bi-fog-hex"], ["bi-water", "bi-water-hex"]]) { qs(c).oninput = () => { qs(h).value = qs(c).value; }; qs(h).oninput = () => { if (/^#[0-9a-fA-F]{6}$/.test(qs(h).value)) qs(c).value = qs(h).value; }; }
const slugify = (label, id) => { if (!qs(id).dataset.touched) qs(id).value = qs(label).value.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 50); };
for (const [l, i] of [["st-label", "st-id"], ["bi-label", "bi-id"], ["dm-label", "dm-id"]]) { qs(l).oninput = () => slugify(l, i); qs(i).oninput = () => { qs(i).dataset.touched = "1"; }; }
qs("struct-form").onsubmit = async (e) => {
  e.preventDefault(); if (!selected) return;
  const layers = qs("st-layers").value.replace(/\r/g, "").split(/\n\s*\n/).map(b => b.split("\n").map(r => r.replace(/\s+$/, "")).filter(Boolean)).filter(b => b.length);
  const legend = Object.fromEntries(qs("st-legend").value.split(",").map(s => s.trim()).filter(Boolean).map(kv => { const [k, ...v] = kv.split("="); return [k.trim(), v.join("=").trim()]; }));
  try {
    await api(`/api/project/${selected}/add-structure`, { identifier: qs("st-id").value.trim(), label: qs("st-label").value.trim(), layers, legend, spacing: Number(qs("st-spacing").value), separation: Number(qs("st-sep").value), biomes: qs("st-biomes").value.split(",").map(s => s.trim()).filter(Boolean), step: qs("st-step").value });
    qs("struct-form").reset(); delete qs("st-id").dataset.touched; closeModal("modal-struct"); toast("Structure added to the spec (re-approve before generating).", "ok"); await openProject(selected);
  } catch (err) { toast(err.message, "bad"); }
};
qs("biome-form").onsubmit = async (e) => {
  e.preventDefault(); if (!selected) return;
  try {
    await api(`/api/project/${selected}/add-biome`, { identifier: qs("bi-id").value.trim(), label: qs("bi-label").value.trim(), base: qs("bi-base").value, temperature: Number(qs("bi-temp").value), downfall: Number(qs("bi-down").value), sky_color: qs("bi-sky-hex").value, fog_color: qs("bi-fog-hex").value, water_color: qs("bi-water-hex").value, grass_color: qs("bi-grass").value.trim(), foliage_color: qs("bi-foliage").value.trim(), mobs: [...qs("bi-mobs").querySelectorAll("input:checked")].map(c => c.value) });
    qs("biome-form").reset(); delete qs("bi-id").dataset.touched; closeModal("modal-biome"); toast("Biome added to the spec.", "ok"); await openProject(selected);
  } catch (err) { toast(err.message, "bad"); }
};
qs("dim-form").onsubmit = async (e) => {
  e.preventDefault(); if (!selected) return;
  try {
    await api(`/api/project/${selected}/add-dimension`, { identifier: qs("dm-id").value.trim(), label: qs("dm-label").value.trim(), biomes: [...qs("dm-biomes").querySelectorAll("input:checked")].map(c => c.value), sky: qs("dm-sky").value, noise: qs("dm-noise").value, fixed_time: Number(qs("dm-time").value) });
    qs("dim-form").reset(); delete qs("dm-id").dataset.touched; closeModal("modal-dim"); toast("Dimension added to the spec (a key item comes with it).", "ok"); await openProject(selected);
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
      if (h.model) card.append(el("div", `model installed: ${h.model.bones.length} bones, ${h.model.cubes} cubes, ${h.model.animations.length} animations` + (h.model.texture ? `, ${h.model.texture[0]}×${h.model.texture[1]} skin` : "") + (h.model.face ? (h.model.face.ok ? ", face reads well" : h.model.face.flat ? ", ⚠ face is flat (eyes and mouth do not stand out)" : ", face is weak") : ""), "risk"));
      if (h.questions?.length) card.append(el("div", "questions: " + h.questions.join(" · "), "risk"));
    }
    if (r.error) card.append(el("div", "⚠ " + r.error, "needs"));
    const render = (d) => (d.live && d.live.length) ? d.live.join("\n") + (d.state === "RUNNING" ? "\n…" : "") : (d.log_tail || (r.state === "RUNNING" ? "(waiting for the worker's first output…)" : "(empty)"));
    const showLog = async (raw) => { const d = await api("/api/run/" + r.id); let box = card.querySelector(".log"); if (!box) { box = el("pre", null, "log"); card.append(box); } box.classList.remove("hidden"); box.textContent = raw ? (d.log_tail || "(empty)") : render(d); lb.textContent = "Hide log"; if (!raw) { const atBottom = true; if (atBottom) box.scrollTop = box.scrollHeight; } };
    const lb = btn(openLogs.has(r.id) ? "Hide log" : "Worker log", async () => { if (openLogs.has(r.id)) { openLogs.delete(r.id); const box = card.querySelector(".log"); if (box) box.classList.add("hidden"); lb.textContent = "Worker log"; return; } openLogs.add(r.id); await showLog(false); }, "mini secondary"); card.append(lb);
    card.append(btn("Raw log", () => { openLogs.add(r.id); return showLog(true); }, "mini secondary"));
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
  acts.append(btn("Launch game client", async () => { if (!await confirmBox("Opens Minecraft with only this mod (isolated run/ folder). It compiles the current source first. Close the game when done.")) return; await api(`/api/project/${p.id}/run-client`, {}); toast("Client launching. Come back here when you close it.", "ok"); await openProject(p.id); }, "primary"));
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
    if (task.state === "READY" && !p.dispatching) right.append(btn("Run agent", async () => { if (!await confirmBox("Start ONE worker on " + task.id + "?")) return; await api(`/api/project/${p.id}/dispatch`, { task: task.id }); await openProject(p.id); }, "mini primary"));
    row.append(right); t.append(row);
  }
  const a = qs("approvals-list"); a.replaceChildren();
  if (!p.approvals.length) a.append(el("p", "No approvals yet.", "muted"));
  for (const ap of p.approvals) { const expired = ap.expires_at && ap.expires_at < Date.now() / 1000 && ap.state !== "CONSUMED"; const row = el("div", null, "task"); row.append(el("span", expired ? "EXPIRED" : ap.state, "state " + (expired ? "FAILED" : ap.state === "GRANTED" ? "READY" : ap.state === "CONSUMED" ? "DONE" : ap.state === "DENIED" ? "FAILED" : "WAITING_USER"))); const mid = el("div"); mid.append(el("div", ap.kind.replace(/_/g, " "), "ttl"), el("small", ap.description)); row.append(mid); const right = el("div"); if (ap.state === "PENDING" && !expired) { right.append(btn("Grant", async () => { await api(`/api/project/${p.id}/decide`, { approval_id: ap.id, grant: true }); await openProject(p.id); }, "mini primary"), btn("Deny", async () => { await api(`/api/project/${p.id}/decide`, { approval_id: ap.id, grant: false }); await openProject(p.id); }, "mini")); } row.append(right); a.append(row); }
}

// ---------- boot ----------
(async function boot() {
  if (!token) { toast("Missing local access token. Start with: craftctl ui", "bad"); return; }
  try { const d = await api("/api/doctor"); qs("sidebar-foot").textContent = `${d.profile.id} · ${d.os} · schema v${d.schema?.version ?? "?"}`; } catch (e) { toast("Cannot reach the local API: " + e.message, "bad"); }
  await renderProjectList();
  const projects = await api("/api/projects").catch(() => []);
  api("/api/settings").then((r) => { runtimeId = r.provider || runtimeId; }).catch(() => {});
  if (projects.length) await openProject(projects[0].id); else show("new");
  Activity.start({
    selected: () => selected, goTo,
    // while an agent works on the project you are looking at, bring the page up to date every few seconds, without moving you
    onTick: (running) => { if (selected && running.has(selected) && Date.now() - lastRefreshAt > 4000) { lastRefreshAt = Date.now(); refreshProject(selected); } },
    onFinished: (pid, entry) => {
      const name = entry ? entry.name : pid, what = entry ? entry.step.label : "the job";
      toast(entry && entry.state === "failed" ? `${name}: ${what} failed. ${entry.error || "See the banner or Now."}` : `${name}: ${what} ${entry && entry.state === "waiting" ? "needs you" : "finished"}.`, entry && entry.state === "failed" ? "bad" : "ok");
      if (pid === selected) refreshProject(pid);
    },
  });
})();

// ---------- mod map ----------
const mapState = { data: null, pid: null, sel: null, view: { x: 0, y: 0, k: 1 }, pos: {}, dirty: false };
const NODE_W = 190, NODE_H = 54, COL_GAP = 110, ROW_GAP = 26;
function layoutMap(cards, edges) {
  const ids = cards.map(c => c.id), inSet = new Set(ids);
  const preds = Object.fromEntries(ids.map(i => [i, []])); const succs = Object.fromEntries(ids.map(i => [i, []]));
  for (const e of edges) if (inSet.has(e.from) && inSet.has(e.to)) { preds[e.to].push(e.from); succs[e.from].push(e.to); }
  const depth = {}; const visiting = new Set();
  const d = (id) => { if (depth[id] != null) return depth[id]; if (visiting.has(id)) return 0; visiting.add(id); const v = preds[id].length ? 1 + Math.max(...preds[id].map(d)) : 0; visiting.delete(id); depth[id] = v; return v; };
  for (const id of ids) d(id);
  const cols = {}; for (const id of ids) { const isolated = !preds[id].length && !succs[id].length; const col = isolated ? -1 : depth[id]; (cols[col] ||= []).push(id); }
  const pos = {}; const colKeys = Object.keys(cols).map(Number).sort((a, b) => a - b);
  colKeys.forEach((col, ci) => { const list = cols[col].sort(); list.forEach((id, ri) => { pos[id] = { x: 40 + ci * (NODE_W + COL_GAP), y: 40 + ri * (NODE_H + ROW_GAP) }; }); });
  return pos;
}
function svgEl(tag, attrs = {}) { const n = document.createElementNS("http://www.w3.org/2000/svg", tag); for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v); return n; }
async function renderMap(p) {
  const svg = qs("map-svg"); if (!svg) return;
  let data; try { data = await api(`/api/project/${p.id}/map`); } catch (e) { toast("map: " + e.message, "bad"); return; }
  const cards = data.cards.filter(c => c.kind !== "tab"), edges = data.edges;
  if (mapState.pid !== p.id) { mapState.pid = p.id; mapState.view = { x: 0, y: 0, k: 1 }; mapState.sel = null; }
  mapState.data = data;
  const auto = layoutMap(cards, edges);
  mapState.pos = Object.fromEntries(cards.map(c => [c.id, (data.layout && data.layout[c.id]) || mapState.pos[c.id] || auto[c.id]]));
  drawMap(p);
  qs("map-fit").onclick = () => { mapState.view = { x: 0, y: 0, k: 1 }; drawMap(p); };
  qs("map-new-feature").onclick = () => { qs("modal-feature").classList.remove("hidden"); qs("ft-title").focus(); };
  if (mapState.sel) openCard(p, mapState.sel);
}
function drawMap(p) {
  const svg = qs("map-svg"); svg.replaceChildren();
  const { cards, edges } = { cards: mapState.data.cards.filter(c => c.kind !== "tab"), edges: mapState.data.edges };
  const g = svgEl("g", { transform: `translate(${mapState.view.x},${mapState.view.y}) scale(${mapState.view.k})` }); svg.append(g);
  const defs = svgEl("defs"); defs.innerHTML = '<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="var(--line-2)"/></marker>'; svg.prepend(defs);
  const byId = Object.fromEntries(cards.map(c => [c.id, c]));
  for (const e of edges) {
    const a = mapState.pos[e.from], b = mapState.pos[e.to]; if (!a || !b) continue;
    const x1 = a.x + NODE_W, y1 = a.y + NODE_H / 2, x2 = b.x, y2 = b.y + NODE_H / 2; const dx = Math.max(40, (x2 - x1) / 2);
    const path = svgEl("path", { d: `M${x1},${y1} C${x1 + dx},${y1} ${x2 - dx},${y2} ${x2},${y2}`, class: "edge " + e.kind, "marker-end": "url(#arrow)" }); g.append(path);
    const lbl = (mapState.data.edge_labels[e.kind] || e.kind) + (e.label ? " · " + e.label : ""); const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
    const t = svgEl("text", { x: mx, y: my - 4, "text-anchor": "middle", class: "edge-label" }); t.textContent = lbl;
    g.append(t); const bb = { w: lbl.length * 5.6 + 8, h: 14 }; const bg = svgEl("rect", { x: mx - bb.w / 2, y: my - 15, width: bb.w, height: bb.h, class: "edge-label-bg", rx: 3 }); g.insertBefore(bg, t);
  }
  for (const c of cards) {
    const pos = mapState.pos[c.id]; const node = svgEl("g", { class: "node " + c.kind + (c.id === mapState.sel ? " sel" : ""), transform: `translate(${pos.x},${pos.y})` });
    node.append(svgEl("rect", { width: NODE_W, height: NODE_H }));
    const kind = svgEl("text", { x: 12, y: 16, class: "kind" }); kind.textContent = (c.kind === "material" ? "TOOL & ARMOR SET" : c.kind.toUpperCase()) + (c.open_tasks?.length ? " · " + c.open_tasks.length + " task" : ""); node.append(kind);
    const title = svgEl("text", { x: 12, y: 34 }); title.textContent = (c.title || c.id).slice(0, 24); node.append(title);
    const sub = svgEl("text", { x: 12, y: 47, class: "sub" }); sub.textContent = c.pieces ? `${c.pieces.length} pieces` : c.kind === "custom" ? (c.status || "") : c.id; node.append(sub);
    node.append(svgEl("circle", { cx: NODE_W - 12, cy: 12, r: 4, class: "dot " + (c.status || "vanilla") }));
    let drag = null;
    node.addEventListener("pointerdown", (ev) => { ev.stopPropagation(); drag = { sx: ev.clientX, sy: ev.clientY, ox: pos.x, oy: pos.y, moved: false }; node.setPointerCapture(ev.pointerId); });
    node.addEventListener("pointermove", (ev) => { if (!drag) return; const k = mapState.view.k; const nx = drag.ox + (ev.clientX - drag.sx) / k, ny = drag.oy + (ev.clientY - drag.sy) / k; if (Math.abs(nx - drag.ox) + Math.abs(ny - drag.oy) > 2) drag.moved = true; mapState.pos[c.id] = { x: nx, y: ny }; node.setAttribute("transform", `translate(${nx},${ny})`); });
    node.addEventListener("pointerup", async (ev) => { if (!drag) return; const moved = drag.moved; drag = null; if (moved) { drawMap(p); api(`/api/project/${p.id}/map-layout`, { layout: mapState.pos }).catch(() => {}); } else { mapState.sel = c.id; drawMap(p); openCard(p, c.id); } });
    g.append(node);
  }
  let pan = null;
  svg.onpointerdown = (ev) => { pan = { sx: ev.clientX, sy: ev.clientY, ox: mapState.view.x, oy: mapState.view.y }; };
  svg.onpointermove = (ev) => { if (!pan) return; mapState.view.x = pan.ox + (ev.clientX - pan.sx); mapState.view.y = pan.oy + (ev.clientY - pan.sy); g.setAttribute("transform", `translate(${mapState.view.x},${mapState.view.y}) scale(${mapState.view.k})`); };
  svg.onpointerup = () => { pan = null; };
  svg.onwheel = (ev) => { ev.preventDefault(); const k = Math.max(0.3, Math.min(2.5, mapState.view.k * (ev.deltaY < 0 ? 1.1 : 0.9))); mapState.view.k = k; g.setAttribute("transform", `translate(${mapState.view.x},${mapState.view.y}) scale(${k})`); };
}
function openCard(p, cid) {
  const side = qs("map-side"); const c = mapState.data.cards.find(x => x.id === cid); if (!c) { side.classList.add("hidden"); return; }
  side.replaceChildren(); side.classList.remove("hidden");
  const close = btn("✕", () => { mapState.sel = null; side.classList.add("hidden"); drawMap(p); }, "mini secondary"); close.style.float = "right"; side.append(close);
  side.append(el("div", (c.kind === "material" ? "tool & armor set" : c.kind) + (c.status ? " · " + c.status : ""), "eyebrow"), el("h3", c.title || c.id), el("div", c.id, "fid"));
  const descBox = el("p", c.description || ""); side.append(descBox);
  if (c.pieces) { const ul = el("ul"); for (const pc of c.pieces) ul.append(el("li", `${pc.id} (${pc.kind})`)); side.append(el("div", "Pieces", "eyebrow"), ul); }
  const rel = mapState.data.edges.filter(e => e.from === cid || e.to === cid);
  if (rel.length) { const ul = el("ul"); for (const e of rel) ul.append(el("li", e.from === cid ? `→ ${mapState.data.edge_labels[e.kind] || e.kind}${e.label ? " (" + e.label + ")" : ""} → ${e.to}` : `← ${e.from} ${mapState.data.edge_labels[e.kind] || e.kind}${e.label ? " (" + e.label + ")" : ""}`)); side.append(el("div", "Relations", "eyebrow"), ul); }
  if (c.acceptance?.length) { const ul = el("ul"); for (const a of c.acceptance) ul.append(el("li", a)); side.append(el("div", "Acceptance criteria", "eyebrow"), ul); }
  if (c.files?.length) { const ul = el("ul", null, "files"); for (const f of c.files.slice(0, 12)) ul.append(el("li", f)); side.append(el("div", "Implemented in", "eyebrow"), ul); }
  if (c.open_tasks?.length) { const ul = el("ul"); for (const t of c.open_tasks) ul.append(el("li", `${t.id} · ${t.state}`)); side.append(el("div", "Open tasks", "eyebrow"), ul); }
  if (c.history?.length) { const ul = el("ul", null, "hist"); for (const h of c.history.slice(-5).reverse()) ul.append(el("li", `${ago(h.at)} · ${h.by}: ${h.what}`)); side.append(el("div", "History", "eyebrow"), ul); }
  if (c.kind !== "vanilla") {
    side.append(el("div", "Request a change", "eyebrow"));
    const ta = el("textarea"); ta.rows = 3; ta.placeholder = c.kind === "custom" ? "e.g. make the inventory 25 slots instead of 20" : c.kind === "mob" ? "e.g. make it drop 2 scrap instead of 1 and walk faster" : "e.g. 1500 durability instead of 1200";
    side.append(ta);
    const acts = el("div", null, "actions");
    acts.append(btn("Send to a coder", async () => { if (!ta.value.trim()) throw new Error("Describe the change first"); const out = await api(`/api/project/${p.id}/change`, { card: cid, request: ta.value.trim() }); if (await confirmBox(`Task ${out.task} created with this card's context. Start the coder now?`)) { await api(`/api/project/${p.id}/dispatch`, { task: out.task }); toast("Coder started on the change.", "ok"); } await openProject(p.id); }, "primary"));
    if (c.kind === "mob") acts.append(btn("Open in Mobs", () => document.querySelector('[data-tab="features"]').click(), "secondary"));
    if (c.kind === "material" || c.kind === "item" || c.kind === "block" || c.kind === "food") acts.append(btn("Open in Items", () => { document.querySelector('[data-tab="features"]').click(); document.querySelector('[data-sub="items"]').click(); }, "secondary"));
    if (c.kind === "custom") {   // its projectiles (once they have their own art) can fly as 3D models
      const box = el("div", null, "card-projectiles"); side.append(box);
      api(`/api/project/${p.id}/projectiles`).then((all) => {
        const mine = Object.entries(all || {}).filter(([, a]) => a.card === cid); if (!mine.length) return;
        box.append(el("div", "Projectiles", "eyebrow"));
        for (const [pid3, a] of mine) {
          const line = el("div", null, "proj-line"); line.append(el("span", `${pid3}: ${a.what}`, "muted"));
          line.append(btn(a.model3d ? "3D model…" : "Make it 3D", () => make3d(p, { identifier: pid3, label: pid3, model3d: a.model3d, projectile: true }), "mini"));
          if (a.model3d) line.append(btn("Open in Blockbench", () => openModel(p, { projectile: pid3 }), "mini secondary"));
          if (a.model3d) line.append(btn("Animate", async () => {
            const v = await promptBox("How does it move while it flies? (the designer animates it; its shape and texture stay as they are)", "", { title: `Animate ${pid3}`, ok: "Animate", multiline: true, required: true });
            if (v == null) return;
            const out = await api(`/api/project/${p.id}/animate`, { kind: "projectile", ident: pid3, anims: [{ name: "flight", what: v.trim() }] });
            if (await confirmBox("Saved. Start the designer now?", { title: "Start the designer", ok: "Start designer", cancel: "Not now" })) { await api(`/api/project/${p.id}/dispatch`, { task: out.task }); toast("Designer animating…", "ok"); }
          }, "mini secondary"));
          box.append(line);
        }
      }).catch(() => {});
    }
    if (c.kind === "custom") acts.append(btn("Give it its own art", async () => {
      if (!await confirmBox("A coder finds every visual this feature borrows from vanilla and gives it its own placeholder; then the designer paints them and the coder wires them in. Nothing else changes. Start the coder now?", { title: "Own art for this feature", ok: "Start coder", cancel: "Not now" })) return;
      const out = await api(`/api/project/${p.id}/art-pass`, { card: cid });
      await api(`/api/project/${p.id}/dispatch`, { task: out.task }); toast("Coder started: it lists what needs art; the designer follows.", "ok"); await refreshProject(p.id);
    }, "secondary"));
    if (c.kind === "custom") acts.append(btn("Edit description", async () => { const d = await promptBox("Description:", c.description || ""); if (d == null) return; await api(`/api/project/${p.id}/card`, { card: cid, description: d }); toast("Card updated.", "ok"); await openProject(p.id); }, "secondary"));
    side.append(acts);
  }
}
qs("feature-form").onsubmit = async (e) => {
  e.preventDefault(); if (!selected) return;
  const acceptance = qs("ft-accept").value.split("\n").map(s => s.trim()).filter(Boolean);
  const derived_from = qs("ft-from").value.split(",").map(s => s.trim()).filter(Boolean);
  try {
    const out = await api(`/api/project/${selected}/feature`, { title: qs("ft-title").value, description: qs("ft-desc").value, acceptance, derived_from });
    qs("feature-form").reset(); closeModal("modal-feature");
    if (await confirmBox(`Card "${out.card.title}" created and task ${out.task} queued. Start the coder now?`)) { await api(`/api/project/${selected}/dispatch`, { task: out.task }); toast("Coder implementing the feature; the card updates when it finishes.", "ok"); }
    await openProject(selected);
  } catch (err) { toast(err.message, "bad"); }
};
