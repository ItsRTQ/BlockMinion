"use strict";
// BlockMinion — UI kit, loaded before app.js. Vanilla JS, no dependencies.
//   1. Dialogs: confirmBox / promptBox / formBox / noticeBox replace the browser's confirm(), prompt() and alert() with ones in the page's own style.
//   2. Refresh guard: Guard.busy() says when a re-render would hurt the user (typing, a dialog or a modal is open); snapshot()/restore() keep the scroll,
//      the open <details> and the focus around a render that does go ahead.
//   3. Activity: the dots in the sidebar and the floating banner that says what the tool is working on, in which step, and takes you to the result.

const kitEl = (tag, text, cls) => { const n = document.createElement(tag); if (text != null) n.textContent = text; if (cls) n.className = cls; return n; };

// ---------------------------------------------------------------------------------------------------- dialogs
const Dlg = (() => {
  let chain = Promise.resolve();
  const FOCUSABLE = "button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex='-1'])";

  function show({ title = "", message = "", fields = [], ok = "OK", cancel = "Cancel", danger = false, hideCancel = false, cancelValue = null }) {
    const job = chain.then(() => new Promise((resolve) => {
      const root = document.getElementById("dlg"), box = root.querySelector(".dlg-box");
      const body = root.querySelector("#dlg-body"), actions = root.querySelector("#dlg-actions"), heading = root.querySelector("#dlg-title");
      const previous = document.activeElement;
      heading.textContent = title; heading.parentElement.classList.toggle("hidden", !title);
      body.replaceChildren();
      for (const line of String(message).split("\n")) if (line.trim()) body.append(kitEl("p", line, "dlg-line"));
      const inputs = {};
      fields.forEach((f, i) => {
        const wrap = kitEl("label", null, "dlg-field");
        if (f.label) wrap.append(kitEl("span", f.label, "dlg-label"));
        const c = f.multiline ? kitEl("textarea") : kitEl("input"); if (!f.multiline) c.type = f.type || "text";
        if (f.multiline) c.rows = f.rows || 3;
        c.value = f.value == null ? "" : String(f.value); if (f.placeholder) c.placeholder = f.placeholder; c.id = "dlg-f-" + i; c.name = f.name;
        wrap.append(c); if (f.help) wrap.append(kitEl("span", f.help, "dlg-help"));
        inputs[f.name] = c; body.append(wrap);
      });
      const error = kitEl("div", "", "dlg-error hidden"); body.append(error);
      actions.replaceChildren();
      let done = false;
      const finish = (value) => {
        if (done) return; done = true;
        root.classList.add("hidden"); document.body.classList.remove("dlg-open"); root.onkeydown = null; root.onmousedown = null;
        if (previous && previous.focus && document.contains(previous)) previous.focus();
        resolve(value);
      };
      const submit = () => {
        const values = {};
        for (const f of fields) {
          const v = inputs[f.name].value;
          if (f.required && !v.trim()) { error.textContent = `${f.label || f.name} cannot be empty.`; error.classList.remove("hidden"); inputs[f.name].focus(); return; }
          values[f.name] = v;
        }
        finish(fields.length ? values : true);
      };
      const okBtn = kitEl("button", ok, danger ? "danger" : "primary"); okBtn.type = "button"; okBtn.onclick = submit;
      if (!hideCancel) { const c = kitEl("button", cancel, "secondary"); c.type = "button"; c.onclick = () => finish(cancelValue); actions.append(c); }
      actions.append(okBtn);
      root.onkeydown = (e) => {
        if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); finish(hideCancel ? undefined : cancelValue); return; }
        if (e.key === "Enter") {
          const t = e.target;
          if (t.tagName === "BUTTON" && t !== okBtn) return;                                   // Enter on Cancel presses Cancel
          if (t.tagName === "TEXTAREA" && !(e.ctrlKey || e.metaKey)) return;                    // a new line; Ctrl+Enter sends
          e.preventDefault(); submit(); return;
        }
        if (e.key === "Tab") {                                                                    // keep the focus inside the dialog
          const items = [...box.querySelectorAll(FOCUSABLE)].filter((n) => !n.closest(".hidden")); if (!items.length) return;
          const first = items[0], last = items[items.length - 1];
          if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
          else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
        }
      };
      root.onmousedown = (e) => { if (e.target === root) finish(hideCancel ? undefined : cancelValue); };
      root.classList.remove("hidden"); document.body.classList.add("dlg-open");
      const firstField = fields.length ? inputs[fields[0].name] : null;
      (firstField || okBtn).focus(); if (firstField && firstField.select && !firstField.rows) firstField.select();
    }));
    chain = job.catch(() => {});
    return job;
  }
  return { show };
})();

// confirm(): resolves true / false
const confirmBox = (message, o = {}) => Dlg.show({ title: o.title || "Please confirm", message, ok: o.ok || "OK", cancel: o.cancel || "Cancel", danger: !!o.danger, cancelValue: false });
// prompt(): resolves the text, or null when cancelled
const promptBox = async (message, value = "", o = {}) => {
  const r = await Dlg.show({ title: o.title || "", message, ok: o.ok || "OK", cancel: "Cancel", cancelValue: null,
                             fields: [{ name: "v", value, multiline: o.multiline != null ? o.multiline : (String(value).length > 70 || String(message).length > 140), placeholder: o.placeholder, required: !!o.required, label: o.label }] });
  return r === null ? null : r.v;
};
// several fields at once: fields = [{name, label, value, multiline, placeholder, help, required}]; resolves {name: text} or null
const formBox = (o) => Dlg.show({ ...o, cancelValue: null });
// alert(): resolves when closed
const noticeBox = (message, o = {}) => Dlg.show({ title: o.title || "Notice", message, ok: "OK", hideCancel: true });

// ---------------------------------------------------------------------------------------------------- refresh guard
const Guard = (() => {
  let lastTyped = 0;
  document.addEventListener("input", (e) => { if (e.isTrusted && e.target.matches && e.target.matches("input, textarea, select")) lastTyped = Date.now(); }, true);
  const inField = () => { const a = document.activeElement; return !!(a && a.matches && a.matches("input, textarea, select") && a.closest("#view-project")); };
  // true when re-rendering the project would hurt the user: a dialog or a modal is open, a field has the focus, or they typed in the last 8 seconds
  function busy() {
    if (!document.getElementById("dlg").classList.contains("hidden")) return true;
    if (document.querySelector(".lightbox:not(.hidden)")) return true;
    return inField() || Date.now() - lastTyped < 8000;
  }
  // SVG elements have an SVGAnimatedString className: read the class attribute, escape it, and never let a bad selector throw
  const classes = (n) => (n.getAttribute && n.getAttribute("class") || "").trim().split(/\s+/).filter(Boolean).map((c) => (window.CSS && CSS.escape ? CSS.escape(c) : c));
  const keyOf = (n) => { if (n.id) return n.id; const sel = `${n.tagName.toLowerCase()}${classes(n).map((c) => "." + c).join("")}`; let i = -1; try { i = [...document.querySelectorAll(sel)].indexOf(n); } catch (e) { /* unkeyable: no scroll restore for it */ } return `${sel}#${i}`; };
  const detailsKey = (d) => d.id || (d.querySelector("summary") ? d.querySelector("summary").textContent.trim() : "");
  function snapshot() {
    const scopes = [...document.querySelectorAll("#view-project *")].filter((n) => n.scrollTop > 0).map((n) => [keyOf(n), n.scrollTop]);
    const a = document.activeElement;
    return { x: window.scrollX, y: window.scrollY, inner: scopes, open: [...document.querySelectorAll("#view-project details[open]")].map(detailsKey), focus: a && a.id ? a.id : null, height: document.documentElement.scrollHeight };
  }
  // the page keeps its height while the contents are rebuilt, so the browser never clamps the scroll position to the top
  function hold(snap) { document.body.style.minHeight = snap.height + "px"; }
  function restore(snap) {
    for (const d of document.querySelectorAll("#view-project details")) if (snap.open.includes(detailsKey(d))) d.open = true;
    for (const [key, top] of snap.inner) { const n = [...document.querySelectorAll("#view-project *")].find((x) => keyOf(x) === key); if (n) n.scrollTop = top; }
    window.scrollTo(snap.x, snap.y);
    if (snap.focus && document.getElementById(snap.focus) && document.activeElement !== document.getElementById(snap.focus)) document.getElementById(snap.focus).focus();
    document.body.style.minHeight = "";
  }
  return { busy, snapshot, hold, restore };
})();

// ---------------------------------------------------------------------------------------------------- activity: sidebar dots and the banner
const Activity = (() => {
  let data = { projects: {}, recent: [] }, receivedAt = 0, expanded = false, timer = null, ticker = null, running = new Set(), cfg = {};
  const dismissed = new Set(); const baseTitle = document.title;
  const keyOf = (r) => r.project + "|" + r.finished_at;
  const runtimeLabel = (p) => ({ "claude-code": "Claude Code", "gemini-cli": "Gemini CLI", "antigravity-cli": "Antigravity" })[p] || p || "";
  const dur = (s) => s >= 3600 ? Math.floor(s / 3600) + "h " + Math.floor((s % 3600) / 60) + "m" : s >= 60 ? Math.floor(s / 60) + "m " + String(Math.floor(s % 60)).padStart(2, "0") + "s" : Math.floor(s) + "s";
  const live = (a) => (a.elapsed_s || 0) + (performance.now() - receivedAt) / 1000;
  const unseen = () => data.recent.filter((r) => !dismissed.has(keyOf(r)));

  function updateSidebar() {
    for (const b of document.querySelectorAll("#project-list .proj[data-pid]")) {
      const pid = b.dataset.pid, a = data.projects[pid], done = unseen().find((r) => r.project === pid && pid !== cfg.selected?.());
      b.classList.toggle("working", !!a);
      const tag = b.querySelector(".pwork");
      if (tag) {
        tag.className = "pwork" + (a ? " running" : done ? " " + done.state : ""); tag.hidden = !a && !done;
        tag.textContent = a ? "● " + (a.step.role && a.step.role !== "controller" ? a.step.role : a.job_label.toLowerCase()) + " working" : done ? (done.state === "failed" ? "✕ failed" : done.state === "waiting" ? "● needs you" : "✓ finished") : "";
        tag.title = a ? a.step.label : done ? done.step.label : "";
      }
    }
  }
  function row(a, kind) {
    const r = kitEl("div", null, "act-row " + kind);
    const head = kitEl("div", null, "act-head");
    head.append(kitEl("span", kind === "running" ? "RUNNING" : kind === "failed" ? "FAILED" : kind === "waiting" ? "NEEDS YOU" : "FINISHED", "act-badge " + kind), kitEl("b", a.name || a.project));
    const step = a.step || {};
    r.append(head, kitEl("div", step.label || a.job_label, "act-step"));
    const meta = [step.runtime ? runtimeLabel(step.runtime) : null, (kind === "running" ? dur(live(a)) : dur(a.elapsed_s) + (a.finished_at ? " · " + ago(a.finished_at) : ""))].filter(Boolean).join(" · ");
    r.append(kitEl("div", meta, "act-meta"));
    if (a.error) r.append(kitEl("div", a.error, "act-error"));
    const acts = kitEl("div", null, "act-actions");
    const go = kitEl("button", kind === "running" ? "Watch it" : "See result", "mini primary"); go.type = "button";
    go.onclick = () => { expanded = false; render(); if (cfg.goTo) cfg.goTo(a.project || a.id, step.target || { tab: "activity" }); if (kind !== "running") dismissed.add(keyOf(a)); render(); };
    acts.append(go);
    if (kind !== "running") { const x = kitEl("button", "Dismiss", "mini secondary"); x.type = "button"; x.onclick = () => { dismissed.add(keyOf(a)); render(); }; acts.append(x); }
    r.append(acts); return r;
  }
  function updateBanner() {
    const bar = document.getElementById("activity-bar"), pill = document.getElementById("activity-pill"), panel = document.getElementById("activity-panel");
    const runningList = Object.entries(data.projects).map(([pid, a]) => ({ ...a, project: pid })), fresh = unseen();
    bar.classList.toggle("hidden", !runningList.length && !fresh.length);
    if (!runningList.length && !fresh.length) { expanded = false; document.title = baseTitle; return; }
    const first = runningList[0], lastDone = fresh[0], kind = first ? "running" : lastDone.state;
    pill.className = "activity-pill " + kind;
    pill.replaceChildren(kitEl("span", null, "act-dot"));
    if (first) pill.append(kitEl("span", `${first.name} · ${first.step.label} · ${dur(live(first))}`, "act-text"), ...(runningList.length > 1 ? [kitEl("span", `+${runningList.length - 1}`, "act-more")] : []));
    else pill.append(kitEl("span", `${lastDone.name} · ${lastDone.step.label} · ${lastDone.state === "failed" ? "failed" : lastDone.state === "waiting" ? "needs you" : "finished"}`, "act-text"), ...(fresh.length > 1 ? [kitEl("span", `+${fresh.length - 1}`, "act-more")] : []));
    pill.setAttribute("aria-expanded", String(expanded)); panel.classList.toggle("hidden", !expanded);
    document.title = (first ? "● working · " : fresh.length ? "✓ done · " : "") + baseTitle;
    if (expanded) {
      panel.replaceChildren();
      if (runningList.length) { panel.append(kitEl("div", "Working now", "act-sec")); runningList.forEach((a) => panel.append(row(a, "running"))); }
      if (fresh.length) { panel.append(kitEl("div", "Finished", "act-sec")); fresh.forEach((r) => panel.append(row(r, r.state))); }
    }
  }
  function render() { updateSidebar(); updateBanner(); }
  function toggle() { expanded = !expanded; render(); }

  async function poll() {
    clearTimeout(timer);
    try {
      data = await api("/api/activity"); receivedAt = performance.now();
      const now = new Set(Object.keys(data.projects));
      for (const pid of running) if (!now.has(pid) && cfg.onFinished) cfg.onFinished(pid, data.recent.find((r) => r.project === pid) || null);
      running = now; render();
      if (cfg.onTick) cfg.onTick(now);
    } catch (e) { /* the banner is a convenience: a failed poll is retried */ }
    timer = setTimeout(poll, document.hidden ? 15000 : running.size ? 2000 : 6000);
  }
  function start(options) {
    cfg = options || {};
    document.getElementById("activity-pill").onclick = toggle;
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && expanded && document.getElementById("dlg").classList.contains("hidden")) { expanded = false; render(); } });
    document.addEventListener("mousedown", (e) => { if (expanded && !e.target.closest("#activity-bar")) { expanded = false; render(); } });
    clearInterval(ticker); ticker = setInterval(() => { if (running.size) updateBanner(); }, 1000);
    return poll();
  }
  // the user opened a project: what finished in it is no longer news
  function seen(pid) { for (const r of data.recent) if (r.project === pid) dismissed.add(keyOf(r)); render(); }
  return { start, poll, seen, render, _state: () => ({ data, expanded, dismissed }) };
})();
