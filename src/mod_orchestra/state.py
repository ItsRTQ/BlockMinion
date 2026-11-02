"""Durable, transactional Footprint state, versioned task claims and approval records."""
from __future__ import annotations
import hashlib
import json
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from .config import ensure_home, HOME

# Schema migrations (STA-001). Append only; never edit a shipped step. Each step runs in its own
# transaction and bumps PRAGMA user_version, so a DB opened by a newer craftctl is upgraded in
# place (after a backup) and a DB from a *newer* craftctl is refused rather than misread.
MIGRATIONS: list[tuple[int, str, str]] = [
    (1, "baseline: projects, events, tasks, task_edges, approvals", """
CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY, root TEXT NOT NULL UNIQUE, name TEXT NOT NULL, spec_json TEXT NOT NULL,
  spec_state TEXT NOT NULL DEFAULT 'DRAFT', status TEXT NOT NULL DEFAULT 'IDEA', created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL REFERENCES projects(id),
  created_at REAL NOT NULL, actor TEXT NOT NULL, kind TEXT NOT NULL, payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), role TEXT NOT NULL,
  title TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'BACKLOG', version INTEGER NOT NULL DEFAULT 0,
  lease_owner TEXT, lease_expiry REAL, attempt INTEGER NOT NULL DEFAULT 0, evidence_json TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS task_edges (
  predecessor TEXT NOT NULL REFERENCES tasks(id), successor TEXT NOT NULL REFERENCES tasks(id),
  PRIMARY KEY(predecessor, successor)
);
CREATE TABLE IF NOT EXISTS approvals (
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), kind TEXT NOT NULL,
  digest TEXT NOT NULL, description TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'PENDING',
  created_at REAL NOT NULL, expires_at REAL NOT NULL, used_at REAL
);
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_events_project ON events(project_id, id);
"""),
    (2, "evidence levels (R1)", """
CREATE TABLE IF NOT EXISTS evidence (
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL REFERENCES projects(id),
  level TEXT NOT NULL, actor TEXT NOT NULL, created_at REAL NOT NULL, note TEXT NOT NULL DEFAULT '',
  artifact_sha256 TEXT, manifest_sha256 TEXT, payload_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_evidence_project ON evidence(project_id, id);
"""),
    (3, "agent runs (R2 dispatch)", """
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), task_id TEXT NOT NULL,
  role TEXT NOT NULL, provider TEXT NOT NULL, state TEXT NOT NULL, created_at REAL NOT NULL,
  finished_at REAL, exit_code INTEGER, duration_s REAL, log_path TEXT, session_id TEXT,
  cost_usd REAL, turns INTEGER, handoff_json TEXT, error TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_project ON runs(project_id, created_at);
ALTER TABLE tasks ADD COLUMN last_error TEXT;
"""),
    (4, "per-task worker instructions (add-mob after generation)", """
CREATE TABLE IF NOT EXISTS task_instructions (task_id TEXT PRIMARY KEY, text TEXT NOT NULL);
"""),
    (5, "per-project settings (autopilot policy)", """
CREATE TABLE IF NOT EXISTS project_settings (project_id TEXT NOT NULL REFERENCES projects(id), key TEXT NOT NULL, value_json TEXT NOT NULL,
  PRIMARY KEY (project_id, key));
"""),
    (6, "planner tasks belong to the controller/user, never agents (host run 11, K4)", """
UPDATE tasks SET role='controller' WHERE id LIKE '%:SCAFFOLD' OR id LIKE '%:BUILD' OR id LIKE '%:CONTENT:__';
UPDATE tasks SET role='user' WHERE id LIKE '%:GAME';
UPDATE tasks SET state='READY', lease_owner=NULL, lease_expiry=NULL, version=version+1
  WHERE (id LIKE '%:SCAFFOLD' OR id LIKE '%:CONTENT:__') AND state IN ('LEASED','RUNNING','WAITING_USER','FAILED','BLOCKED');
"""),
]
SCHEMA_VERSION = MIGRATIONS[-1][0]


class StateError(RuntimeError):
    pass

class Store:
    def __init__(self, path: Path | None = None):
        if path is None:
            ensure_home()
            path = HOME / "state.sqlite"
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.path, timeout=15)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=15000")
        try:
            con.execute("BEGIN IMMEDIATE")
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def schema_version(self) -> int:
        con = sqlite3.connect(self.path, timeout=15)
        try:
            return int(con.execute("PRAGMA user_version").fetchone()[0])
        finally:
            con.close()

    def _initialize(self) -> None:
        con = sqlite3.connect(self.path, timeout=15)
        try:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA foreign_keys=ON")
            con.execute("PRAGMA busy_timeout=15000")
            current = int(con.execute("PRAGMA user_version").fetchone()[0])
            if current > SCHEMA_VERSION:
                raise StateError(f"State DB {self.path} is schema v{current}, newer than this craftctl (v{SCHEMA_VERSION}). "
                                 "Upgrade craftctl or point CRAFTCTL_HOME at a different directory.")
            pending = [m for m in MIGRATIONS if m[0] > current]
            if not pending:
                return
            if current > 0:
                self._backup(current)
            for version, title, sql in pending:
                con.execute("BEGIN IMMEDIATE")
                try:
                    for statement in (x.strip() for x in sql.split(";")):
                        if statement:
                            con.execute(statement)  # executescript would COMMIT first; keep the step atomic
                    con.execute(f"PRAGMA user_version={version}")
                    con.commit()
                except Exception:
                    con.rollback()
                    raise StateError(f"Schema migration v{version} ({title}) failed; DB left at v{current}") from None
                current = version
        finally:
            con.close()

    def _backup(self, version: int) -> Path:
        """Copy the DB before an in-place upgrade. Uses the SQLite backup API so WAL content is included."""
        target = self.path.with_name(f"{self.path.name}.bak-v{version}")
        src = sqlite3.connect(self.path, timeout=15)
        try:
            dst = sqlite3.connect(target)
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
        return target

    @staticmethod
    def event(con: sqlite3.Connection, pid: str, actor: str, kind: str, payload: dict) -> None:
        from .redact import redact_obj  # SEC-003: events are exported to footprints and agents
        con.execute("INSERT INTO events(project_id,created_at,actor,kind,payload_json) VALUES(?,?,?,?,?)",
                    (pid, time.time(), actor, kind, json.dumps(redact_obj(payload), sort_keys=True)))

    def create_project(self, pid: str, root: str, name: str, spec: dict) -> dict:
        with self.tx() as con:
            con.execute("INSERT INTO projects(id,root,name,spec_json,created_at) VALUES(?,?,?,?,?)",
                        (pid, root, name, json.dumps(spec, sort_keys=True), time.time()))
            self.event(con, pid, "system", "PROJECT_CREATED", {"root": root})
        return self.project(pid)

    def project(self, pid: str) -> dict:
        with self.tx() as con:
            row = con.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
            if row is None:
                raise StateError(f"Project not found: {pid}")
            return {**dict(row), "spec": json.loads(row["spec_json"])}

    def projects(self) -> list[dict]:
        with self.tx() as con:
            return [dict(row) for row in con.execute("SELECT id,name,root,status,spec_state,created_at FROM projects ORDER BY created_at DESC")]

    def replace_spec(self, pid: str, spec: dict, *, actor: str, reason: str) -> None:
        """USER-ONLY: rewrite the spec. Any change invalidates a previous approval (spec_state -> DRAFT)."""
        with self.tx() as con:
            row = con.execute("SELECT status FROM projects WHERE id=?", (pid,)).fetchone()
            if row is None:
                raise StateError("Unknown project")
            if row["status"] not in ("IDEA", "PLAN_READY"):
                raise StateError(f"The spec cannot change once source is generated (status {row['status']}); create a new project or add content as agent tasks")
            con.execute("UPDATE projects SET spec_json=?, spec_state='DRAFT' WHERE id=?", (json.dumps(spec, sort_keys=True), pid))
            self.event(con, pid, actor, "SPEC_CHANGED", {"reason": reason[:200]})

    def update_project(self, pid: str, *, status: str | None = None, spec_state: str | None = None) -> None:
        with self.tx() as con:
            if not con.execute("SELECT 1 FROM projects WHERE id=?", (pid,)).fetchone():
                raise StateError("Unknown project")
            if status is not None:
                con.execute("UPDATE projects SET status=? WHERE id=?", (status, pid))
                self.event(con, pid, "controller", "PROJECT_STATUS", {"status": status})
            if spec_state is not None:
                con.execute("UPDATE projects SET spec_state=? WHERE id=?", (spec_state, pid))
                self.event(con, pid, "user", "SPEC_STATUS", {"status": spec_state})

    def set_tasks(self, pid: str, tasks: list[dict], edges: list[tuple[str, str]], *, replace: bool = False) -> None:
        """Create the task graph. With replace=True (only before any source exists) the previous plan is
        dropped except runs/evidence history; a DONE SPEC task stays DONE so approval is not lost."""
        with self.tx() as con:
            existing = {r["id"]: dict(r) for r in con.execute("SELECT id,state FROM tasks WHERE project_id=?", (pid,))}
            if existing and not replace:
                raise StateError("Tasks already planned; use replan before generation")
            if existing:
                # Replace only planner-owned tasks; user/controller-added ones (ADD_*, ad-hoc add-task, REPAIR) and their edges survive.
                planner_ids = {t["id"] for t in tasks} | {i for i in existing if re.search(r":(SPEC|SCAFFOLD|BUILD|GAME)$|:(CONTENT|MODEL):", i)}
                for old in planner_ids & set(existing):
                    con.execute("DELETE FROM task_edges WHERE predecessor=? OR successor=?", (old, old))
                    con.execute("DELETE FROM tasks WHERE id=?", (old,))
            for t in tasks:
                state = "READY" if t.get("ready") else "BACKLOG"
                prev = existing.get(t["id"])
                if prev and prev["state"] == "DONE" and t["id"].endswith(":SPEC"):
                    state = "DONE"
                con.execute("INSERT INTO tasks(id,project_id,role,title,state) VALUES(?,?,?,?,?)",
                            (t["id"], pid, t["role"], t["title"], state))
            for a, b in edges:
                con.execute("INSERT INTO task_edges(predecessor,successor) VALUES(?,?)", (a, b))
            self.event(con, pid, "scrum-master", "TASK_GRAPH_REPLANNED" if existing else "TASK_GRAPH_CREATED", {"tasks": len(tasks), "edges": len(edges)})

    def tasks(self, pid: str) -> list[dict]:
        with self.tx() as con:
            return [dict(r) for r in con.execute("SELECT * FROM tasks WHERE project_id=? ORDER BY id", (pid,))]

    def refresh_ready(self, pid: str) -> None:
        with self.tx() as con:
            con.execute("""UPDATE tasks SET state='READY',version=version+1 WHERE project_id=? AND state='BACKLOG'
                AND NOT EXISTS (SELECT 1 FROM task_edges e JOIN tasks p ON p.id=e.predecessor
                                WHERE e.successor=tasks.id AND p.state!='DONE')""", (pid,))

    def claim(self, task_id: str, worker: str, *, ttl: int = 300) -> dict | None:
        if not (1 <= ttl <= 3600):
            raise StateError("Invalid lease TTL")
        with self.tx() as con:
            row = con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None or (row["state"] != "READY" and not (
                    row["state"] in ("LEASED", "RUNNING") and (row["lease_expiry"] or 0) < time.time())):
                return None
            con.execute("UPDATE tasks SET state='LEASED',lease_owner=?,lease_expiry=?,version=version+1,attempt=attempt+1 WHERE id=?",
                        (worker, time.time() + ttl, task_id))
            self.event(con, row["project_id"], worker, "TASK_LEASED", {"task": task_id})
            return dict(con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone())

    def get_setting(self, pid: str, key: str, default=None):
        with self.tx() as con:
            row = con.execute("SELECT value_json FROM project_settings WHERE project_id=? AND key=?", (pid, key)).fetchone()
        return json.loads(row["value_json"]) if row else default

    def set_setting(self, pid: str, key: str, value, *, actor: str = "user") -> None:
        """USER-ONLY (the UI and CLI are the user; MCP never calls this)."""
        with self.tx() as con:
            if con.execute("SELECT 1 FROM projects WHERE id=?", (pid,)).fetchone() is None:
                raise StateError(f"Project not found: {pid}")
            con.execute("INSERT OR REPLACE INTO project_settings(project_id, key, value_json) VALUES(?,?,?)", (pid, key, json.dumps(value)))
            self.event(con, pid, actor, "SETTING_CHANGED", {"key": key, "value": value})

    def task_instructions(self, task_id: str) -> str:
        with self.tx() as con:
            row = con.execute("SELECT text FROM task_instructions WHERE task_id=?", (task_id,)).fetchone()
        return row["text"] if row else ""

    def lease_info(self, task_id: str) -> dict | None:
        with self.tx() as con:
            row = con.execute("SELECT id,state,lease_owner,lease_expiry,version FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            return None
        remaining = max(0, int((row["lease_expiry"] or 0) - time.time())) if row["lease_owner"] else 0
        return {"task": row["id"], "state": row["state"], "holder": row["lease_owner"], "seconds_left": remaining, "version": row["version"]}

    def force_release(self, task_id: str, reason: str) -> dict:
        """USER-ONLY: break any lease on a task and return it to READY."""
        with self.tx() as con:
            row = con.execute("SELECT project_id,state,lease_owner FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                raise StateError(f"Task not found: {task_id}")
            if row["state"] not in ("LEASED", "RUNNING"):
                raise StateError(f"Task {task_id} is {row['state']}, nothing to release")
            con.execute("UPDATE tasks SET state='READY',lease_owner=NULL,lease_expiry=NULL,version=version+1 WHERE id=?", (task_id,))
            self.event(con, row["project_id"], "user", "TASK_FORCE_RELEASED", {"task": task_id, "previous_holder": row["lease_owner"], "reason": reason[:300]})
        return {"task": task_id, "state": "READY", "previous_holder": row["lease_owner"]}

    def delete_project(self, pid: str) -> dict:
        """USER-ONLY: remove every row for a project. The workspace directory is handled by the caller."""
        with self.tx() as con:
            if con.execute("SELECT 1 FROM projects WHERE id=?", (pid,)).fetchone() is None:
                raise StateError(f"Project not found: {pid}")
            counts = {}
            # every table that references the project or its tasks (schema v1-v4); children first
            counts["project_settings"] = con.execute("DELETE FROM project_settings WHERE project_id=?", (pid,)).rowcount
            counts["task_instructions"] = con.execute("DELETE FROM task_instructions WHERE task_id IN (SELECT id FROM tasks WHERE project_id=?)", (pid,)).rowcount
            counts["runs"] = con.execute("DELETE FROM runs WHERE project_id=?", (pid,)).rowcount
            for table in ("evidence", "approvals", "events"):
                counts[table] = con.execute(f"DELETE FROM {table} WHERE project_id=?", (pid,)).rowcount
            counts["task_edges"] = con.execute(
                "DELETE FROM task_edges WHERE predecessor IN (SELECT id FROM tasks WHERE project_id=?) "
                "OR successor IN (SELECT id FROM tasks WHERE project_id=?)", (pid, pid)).rowcount
            counts["tasks"] = con.execute("DELETE FROM tasks WHERE project_id=?", (pid,)).rowcount
            con.execute("DELETE FROM projects WHERE id=?", (pid,))
        return {"deleted": pid, "rows": counts}

    def release(self, task_id: str, worker: str, version: int, reason: str) -> bool:
        """Give a lease back (task returns to READY) when the worker failed before producing evidence."""
        with self.tx() as con:
            cur = con.execute("UPDATE tasks SET state='READY',lease_owner=NULL,lease_expiry=NULL,version=version+1 "
                              "WHERE id=? AND lease_owner=? AND version=? AND state IN ('LEASED','RUNNING')",
                              (task_id, worker, version))
            if cur.rowcount == 1:
                pid = con.execute("SELECT project_id FROM tasks WHERE id=?", (task_id,)).fetchone()["project_id"]
                self.event(con, pid, worker, "TASK_RELEASED", {"task": task_id, "reason": reason[:300]})
            return cur.rowcount == 1

    def set_task_state(self, task_id: str, worker: str, version: int, state: str, *, error: str | None = None) -> bool:
        """Move a leased task to a terminal/waiting state (WAITING_USER, BLOCKED, FAILED, CANCELLED)."""
        with self.tx() as con:
            row = con.execute("SELECT project_id FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                raise StateError("Unknown task")
            cur = con.execute("UPDATE tasks SET state=?,version=version+1,lease_owner=NULL,lease_expiry=NULL,last_error=? "
                              "WHERE id=? AND version=? AND lease_owner=?", (state, error, task_id, version, worker))
            if cur.rowcount:
                self.event(con, row["project_id"], worker, "TASK_STATE", {"task": task_id, "state": state, "error": error})
            return bool(cur.rowcount)

    def requeue(self, task_id: str, reason: str) -> dict:
        """USER-ONLY: return a FAILED / WAITING_USER / BLOCKED task to READY (dependencies permitting)."""
        with self.tx() as con:
            row = con.execute("SELECT project_id,state FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                raise StateError(f"Task not found: {task_id}")
            if row["state"] not in ("FAILED", "WAITING_USER", "BLOCKED", "CANCELLED"):
                raise StateError(f"Task {task_id} is {row['state']}; only FAILED/WAITING_USER/BLOCKED/CANCELLED can be requeued")
            con.execute("UPDATE tasks SET state='READY',version=version+1,lease_owner=NULL,lease_expiry=NULL,last_error=NULL,attempt=attempt+1 WHERE id=?", (task_id,))
            self.event(con, row["project_id"], "user", "TASK_REQUEUED", {"task": task_id, "from": row["state"], "reason": reason[:300]})
        return {"task": task_id, "state": "READY", "from": row["state"]}

    def add_task(self, pid: str, task_id: str, role: str, title: str, *, after: list[str] | None = None) -> dict:
        """USER-ONLY: add an ad-hoc task (e.g. 'add sapphire item') to an existing project board."""
        with self.tx() as con:
            if con.execute("SELECT 1 FROM projects WHERE id=?", (pid,)).fetchone() is None:
                raise StateError(f"Project not found: {pid}")
            if con.execute("SELECT 1 FROM tasks WHERE id=?", (task_id,)).fetchone():
                raise StateError(f"Task already exists: {task_id}")
            state = "BACKLOG" if after else "READY"
            con.execute("INSERT INTO tasks(id,project_id,role,title,state) VALUES(?,?,?,?,?)", (task_id, pid, role, title, state))
            for pred in after or []:
                if con.execute("SELECT 1 FROM tasks WHERE id=? AND project_id=?", (pred, pid)).fetchone() is None:
                    raise StateError(f"Dependency not found in project: {pred}")
                con.execute("INSERT INTO task_edges(predecessor,successor) VALUES(?,?)", (pred, task_id))
            self.event(con, pid, "user", "TASK_ADDED", {"task": task_id, "role": role, "title": title, "after": after or []})
        self.refresh_ready(pid)
        current = next(t["state"] for t in self.tasks(pid) if t["id"] == task_id)
        return {"task": task_id, "role": role, "state": current}

    def create_run(self, pid: str, task_id: str, role: str, provider: str) -> dict:
        run = {"id": secrets.token_urlsafe(9), "project_id": pid, "task_id": task_id, "role": role,
               "provider": provider, "state": "RUNNING", "created_at": time.time()}
        with self.tx() as con:
            con.execute("INSERT INTO runs(id,project_id,task_id,role,provider,state,created_at) VALUES(?,?,?,?,?,?,?)",
                        (run["id"], pid, task_id, role, provider, "RUNNING", run["created_at"]))
            self.event(con, pid, "controller", "RUN_STARTED", {"run": run["id"], "task": task_id, "role": role, "provider": provider})
        return run

    def finish_run(self, run_id: str, *, state: str, exit_code: int | None, duration_s: float | None, log_path: str | None,
                   session_id: str | None = None, cost_usd: float | None = None, turns: int | None = None,
                   handoff: dict | None = None, error: str | None = None) -> None:
        with self.tx() as con:
            pid = con.execute("SELECT project_id FROM runs WHERE id=?", (run_id,)).fetchone()["project_id"]
            con.execute("UPDATE runs SET state=?,finished_at=?,exit_code=?,duration_s=?,log_path=?,session_id=?,cost_usd=?,turns=?,handoff_json=?,error=? WHERE id=?",
                        (state, time.time(), exit_code, duration_s, log_path, session_id, cost_usd, turns,
                         json.dumps(handoff, sort_keys=True) if handoff is not None else None, error, run_id))
            self.event(con, pid, "controller", "RUN_FINISHED", {"run": run_id, "state": state, "exit_code": exit_code,
                                                                "duration_s": duration_s, "cost_usd": cost_usd, "turns": turns, "error": error})

    def runs(self, pid: str) -> list[dict]:
        with self.tx() as con:
            rows = con.execute("SELECT * FROM runs WHERE project_id=? ORDER BY created_at", (pid,)).fetchall()
        out = []
        for r in rows:
            d = dict(r); d["handoff"] = json.loads(d.pop("handoff_json") or "null"); out.append(d)
        return out

    def heartbeat(self, task_id: str, worker: str, version: int, ttl: int = 300) -> bool:
        with self.tx() as con:
            cur = con.execute("UPDATE tasks SET lease_expiry=? WHERE id=? AND lease_owner=? AND version=? AND state IN ('LEASED','RUNNING')",
                              (time.time() + ttl, task_id, worker, version))
            return cur.rowcount == 1

    def finish(self, task_id: str, worker: str, version: int, evidence: list[dict]) -> bool:
        if not evidence or any(not isinstance(e, dict) or not e.get("kind") or not e.get("value") for e in evidence):
            raise StateError("Completion requires explicit evidence entries")
        with self.tx() as con:
            row = con.execute("SELECT project_id FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                raise StateError("Unknown task")
            cur = con.execute("""UPDATE tasks SET state='DONE',version=version+1,lease_owner=NULL,lease_expiry=NULL,
               evidence_json=? WHERE id=? AND state IN ('LEASED','RUNNING','VERIFYING')
               AND version=? AND lease_owner=? AND lease_expiry>?""",
               (json.dumps(evidence), task_id, version, worker, time.time()))
            if cur.rowcount:
                self.event(con, row["project_id"], worker, "TASK_COMPLETED", {"task": task_id, "evidence": evidence})
            return bool(cur.rowcount)

    @staticmethod
    def digest(kind: str, args: dict) -> str:
        return hashlib.sha256(json.dumps({"kind": kind, "args": args}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def request_approval(self, pid: str, kind: str, args: dict, description: str, *, ttl: int = 3600) -> dict:
        if not (60 <= ttl <= 86400):
            raise StateError("Approval must expire within 1 minute to 24 hours")
        approval = secrets.token_urlsafe(18)
        with self.tx() as con:
            con.execute("INSERT INTO approvals(id,project_id,kind,digest,description,created_at,expires_at) VALUES(?,?,?,?,?,?,?)",
                        (approval, pid, kind, self.digest(kind, args), description, time.time(), time.time() + ttl))
            self.event(con, pid, "controller", "APPROVAL_REQUESTED", {"id": approval, "kind": kind, "description": description})
        return {"id": approval, "kind": kind, "description": description}

    def approvals(self, pid: str) -> list[dict]:
        with self.tx() as con:
            return [dict(x) for x in con.execute("SELECT * FROM approvals WHERE project_id=? ORDER BY created_at DESC", (pid,))]

    def decide_approval(self, approval: str, granted: bool) -> None:
        with self.tx() as con:
            row = con.execute("SELECT * FROM approvals WHERE id=?", (approval,)).fetchone()
            if not row or row["state"] != "PENDING" or row["expires_at"] <= time.time():
                raise StateError("Approval not pending or expired")
            con.execute("UPDATE approvals SET state=? WHERE id=?", ("GRANTED" if granted else "DENIED", approval))
            self.event(con, row["project_id"], "user", "APPROVAL_DECIDED", {"id": approval, "granted": granted})

    def consume_approval(self, approval: str, pid: str, kind: str, args: dict) -> bool:
        with self.tx() as con:
            cur = con.execute("""UPDATE approvals SET state='CONSUMED',used_at=? WHERE id=? AND project_id=? AND kind=?
                AND digest=? AND state='GRANTED' AND expires_at>?""",
                (time.time(), approval, pid, kind, self.digest(kind, args), time.time()))
            if cur.rowcount:
                self.event(con, pid, "controller", "APPROVAL_CONSUMED", {"id": approval, "kind": kind})
            return bool(cur.rowcount)

    def add_evidence(self, pid: str, level: str, actor: str, note: str, *, artifact_sha256: str | None,
                     manifest_sha256: str | None, payload: dict) -> dict:
        row = {"project_id": pid, "level": level, "actor": actor, "created_at": time.time(), "note": note,
               "artifact_sha256": artifact_sha256, "manifest_sha256": manifest_sha256}
        with self.tx() as con:
            cur = con.execute(
                "INSERT INTO evidence(project_id,level,actor,created_at,note,artifact_sha256,manifest_sha256,payload_json) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (pid, level, actor, row["created_at"], note, artifact_sha256, manifest_sha256, json.dumps(payload, sort_keys=True)))
            row["id"] = cur.lastrowid
            self.event(con, pid, actor, "EVIDENCE", {"level": level, "artifact_sha256": artifact_sha256})
        return row

    def evidence(self, pid: str) -> list[dict]:
        with self.tx() as con:
            rows = con.execute("SELECT id,level,actor,created_at,note,artifact_sha256,manifest_sha256,payload_json "
                               "FROM evidence WHERE project_id=? ORDER BY id", (pid,)).fetchall()
        out = []
        for r in rows:
            d = dict(r); d["payload"] = json.loads(d.pop("payload_json")); out.append(d)
        return out

    def add_event(self, pid: str, actor: str, kind: str, payload: dict) -> None:
        with self.tx() as con:
            self.event(con, pid, actor, kind, payload)

    def events(self, pid: str, limit: int = 50) -> list[dict]:
        with self.tx() as con:
            rows = con.execute("SELECT * FROM events WHERE project_id=? ORDER BY id DESC LIMIT ?", (pid, min(500, max(1, limit))))
            return [dict(r) | {"payload": json.loads(r["payload_json"])} for r in rows]
