from __future__ import annotations
import sqlite3, json, time, threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any

class StateStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self._lock = threading.RLock()
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS jobs(
              job_id TEXT PRIMARY KEY, app_id TEXT, version TEXT, status TEXT, mode TEXT,
              attempt INTEGER, idempotency_key TEXT UNIQUE, request_json TEXT, result_json TEXT,
              created_at REAL, updated_at REAL, cancel_requested INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS events(
              seq INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT, event_type TEXT, payload_json TEXT, created_at REAL
            );
            CREATE TABLE IF NOT EXISTS feedback(
              id INTEGER PRIMARY KEY AUTOINCREMENT, app_id TEXT, outcome REAL, correction TEXT, created_at REAL
            );
            CREATE TABLE IF NOT EXISTS microapps(
              app_id TEXT, version TEXT, bundle_path TEXT, manifest_json TEXT, updated_at REAL,
              PRIMARY KEY(app_id, version)
            );
            CREATE INDEX IF NOT EXISTS idx_events_job ON events(job_id, seq);
            ''')

    @contextmanager
    def _connect(self):
        db=sqlite3.connect(self.path,timeout=30)
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def create_job(self, row: dict[str, Any]) -> tuple[str, bool]:
        with self._lock, self._connect() as db:
            existing = db.execute("SELECT job_id FROM jobs WHERE idempotency_key=?", (row["idempotency_key"],)).fetchone()
            if existing:
                return existing[0], False
            now = time.time()
            db.execute("INSERT INTO jobs(job_id,app_id,version,status,mode,attempt,idempotency_key,request_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                       (row["job_id"],row["app_id"],row["version"],row["status"],row["mode"],row["attempt"],row["idempotency_key"],json.dumps(row.get("request",{})),now,now))
            return row["job_id"], True

    def update_job(self, job_id: str, **changes: Any) -> None:
        if not changes: return
        changes["updated_at"] = time.time()
        keys = list(changes)
        vals = [json.dumps(changes[k]) if k == "result_json" and not isinstance(changes[k], str) else changes[k] for k in keys]
        with self._lock, self._connect() as db:
            db.execute(f"UPDATE jobs SET {','.join(k+'=?' for k in keys)} WHERE job_id=?", vals+[job_id])

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            db.row_factory = sqlite3.Row
            r = db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            return dict(r) if r else None

    def list_jobs(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as db:
            db.row_factory = sqlite3.Row
            return [dict(r) for r in db.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,))]

    def event(self, job_id: str, event_type: str, payload: dict[str, Any]) -> int:
        with self._lock, self._connect() as db:
            cur = db.execute("INSERT INTO events(job_id,event_type,payload_json,created_at) VALUES(?,?,?,?)", (job_id,event_type,json.dumps(payload),time.time()))
            return int(cur.lastrowid)

    def events(self, job_id: str, after: int = 0) -> list[dict[str, Any]]:
        with self._connect() as db:
            db.row_factory = sqlite3.Row
            return [dict(r) for r in db.execute("SELECT * FROM events WHERE job_id=? AND seq>? ORDER BY seq", (job_id, after))]

    def request_cancel(self, job_id: str) -> None:
        self.update_job(job_id, cancel_requested=1)
        self.event(job_id, "cancel_requested", {})

    def cancellation_requested(self, job_id: str) -> bool:
        row = self.get_job(job_id)
        return bool(row and row["cancel_requested"])


    def register_microapp(self, app_id: str, version: str, bundle_path: str, manifest: dict[str, Any]) -> None:
        now=time.time()
        with self._lock, self._connect() as db:
            db.execute("INSERT INTO microapps(app_id,version,bundle_path,manifest_json,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(app_id,version) DO UPDATE SET bundle_path=excluded.bundle_path,manifest_json=excluded.manifest_json,updated_at=excluded.updated_at", (app_id,version,bundle_path,json.dumps(manifest),now))
        self.event("", "microapp_registered", {"app_id":app_id,"version":version,"bundle_path":bundle_path})

    def get_microapp(self, app_id: str, version: str) -> dict[str, Any] | None:
        with self._connect() as db:
            db.row_factory=sqlite3.Row
            r=db.execute("SELECT * FROM microapps WHERE app_id=? AND version=?",(app_id,version)).fetchone()
            return dict(r) if r else None

    def list_microapps(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            db.row_factory=sqlite3.Row
            return [dict(r) for r in db.execute("SELECT * FROM microapps ORDER BY app_id,version")]

    def delete_microapp(self, app_id: str, version: str) -> bool:
        with self._lock, self._connect() as db:
            cur=db.execute("DELETE FROM microapps WHERE app_id=? AND version=?",(app_id,version)); ok=cur.rowcount>0
        if ok: self.event("", "microapp_deleted", {"app_id":app_id,"version":version})
        return ok

    def add_feedback(self, app_id: str, outcome: float, correction: str = "") -> None:
        with self._connect() as db:
            db.execute("INSERT INTO feedback(app_id,outcome,correction,created_at) VALUES(?,?,?,?)", (app_id,outcome,correction,time.time()))

    def feedback_score(self, app_id: str) -> float:
        with self._connect() as db:
            r = db.execute("SELECT AVG(outcome) FROM feedback WHERE app_id=?", (app_id,)).fetchone()
            return float(r[0]) if r and r[0] is not None else 0.5

    def mode_biases(self, app_id: str) -> dict[str,float]:
        biases: dict[str,float]={}
        with self._connect() as db:
            rows=db.execute("SELECT correction FROM feedback WHERE app_id=? ORDER BY id DESC LIMIT 50",(app_id,)).fetchall()
        for (raw,) in rows:
            try:
                d=json.loads(raw) if raw else {}
                mode=d.get("prefer_mode"); weight=float(d.get("weight",0.2))
                if mode in {"local","hybrid","cloud","edge","browser"}: biases[mode]=biases.get(mode,0.0)+max(-1.0,min(1.0,weight))
            except Exception: pass
        return biases
