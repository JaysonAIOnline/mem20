from __future__ import annotations
from contextlib import contextmanager
import sqlite3, json, time
from pathlib import Path
from typing import Any, Iterable
from .model import Capability, InterfacePlan, Job, canonical_json

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS capabilities(
  capability_id TEXT PRIMARY KEY, payload TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
  origin TEXT NOT NULL DEFAULT 'local', updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs(
  job_id TEXT PRIMARY KEY, idempotency_key TEXT UNIQUE NOT NULL, intent TEXT NOT NULL, state TEXT NOT NULL,
  mode TEXT NOT NULL, attempts INTEGER NOT NULL, error TEXT, plan_id TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS plans(
  plan_id TEXT PRIMARY KEY, job_id TEXT NOT NULL, payload TEXT NOT NULL, generation INTEGER NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS events(
  seq INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL, entity_id TEXT NOT NULL, payload TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS feedback(
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, payload TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS cache(
  cache_key TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at REAL NOT NULL, expires_at REAL NOT NULL
);
"""

class StateStore:
    def __init__(self, path: str | Path, origin: str = "local"):
        self.path = str(path); self.origin = origin
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db: db.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15, check_same_thread=False)
        db.row_factory = sqlite3.Row
        try:
            yield db; db.commit()
        except Exception:
            db.rollback(); raise
        finally: db.close()

    def emit(self, event_type: str, entity_id: str, payload: dict[str, Any]) -> int:
        with self.connect() as db:
            cur = db.execute("INSERT INTO events(event_type,entity_id,payload,created_at) VALUES(?,?,?,?)",
                             (event_type, entity_id, canonical_json(payload), time.time()))
            return int(cur.lastrowid)

    def events(self, after: int = 0, limit: int = 200) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM events WHERE seq>? ORDER BY seq LIMIT ?", (after, min(limit, 1000))).fetchall()
        return [{"seq":r["seq"],"type":r["event_type"],"entity_id":r["entity_id"],"payload":json.loads(r["payload"]),"created_at":r["created_at"]} for r in rows]

    # Capability CRUD + optimistic versioning.
    def put_capability(self, cap: Capability, *, expected_revision: int | None = None, origin: str | None = None) -> int:
        cap.validate(); now=time.time(); origin=origin or self.origin; payload=canonical_json(cap.to_dict())
        with self.connect() as db:
            old=db.execute("SELECT revision FROM capabilities WHERE capability_id=?", (cap.capability_id,)).fetchone()
            if old:
                rev=int(old["revision"])
                if expected_revision is not None and rev != expected_revision: raise RuntimeError("revision conflict")
                rev += 1
                db.execute("UPDATE capabilities SET payload=?,revision=?,origin=?,updated_at=? WHERE capability_id=?",(payload,rev,origin,now,cap.capability_id))
            else:
                if expected_revision not in (None,0): raise RuntimeError("revision conflict")
                rev=1
                db.execute("INSERT INTO capabilities VALUES(?,?,?,?,?)",(cap.capability_id,payload,rev,origin,now))
        self.emit("capability.upserted",cap.capability_id,{"revision":rev,"origin":origin}); return rev

    def get_capability(self, capability_id: str) -> dict[str, Any] | None:
        with self.connect() as db: r=db.execute("SELECT * FROM capabilities WHERE capability_id=?",(capability_id,)).fetchone()
        if not r:return None
        return {"capability":Capability.from_dict(json.loads(r["payload"])),"revision":r["revision"],"origin":r["origin"],"updated_at":r["updated_at"]}

    def list_capabilities(self) -> list[Capability]:
        with self.connect() as db: rows=db.execute("SELECT payload FROM capabilities ORDER BY capability_id").fetchall()
        return [Capability.from_dict(json.loads(r["payload"])) for r in rows]

    def delete_capability(self, capability_id: str) -> bool:
        with self.connect() as db: changed=db.execute("DELETE FROM capabilities WHERE capability_id=?",(capability_id,)).rowcount>0
        if changed:self.emit("capability.deleted",capability_id,{})
        return changed

    def export_capabilities(self) -> list[dict[str, Any]]:
        with self.connect() as db: rows=db.execute("SELECT * FROM capabilities ORDER BY capability_id").fetchall()
        return [{"capability":json.loads(r["payload"]),"revision":r["revision"],"origin":r["origin"],"updated_at":r["updated_at"]} for r in rows]

    def reconcile_capabilities(self, records: Iterable[dict[str, Any]]) -> dict[str,int]:
        applied=conflicts=ignored=0
        for rec in records:
            cap=Capability.from_dict(rec["capability"]); incoming_rev=int(rec["revision"]); incoming_origin=str(rec.get("origin","remote")); incoming_ts=float(rec.get("updated_at",0))
            with self.connect() as db:
                old=db.execute("SELECT * FROM capabilities WHERE capability_id=?",(cap.capability_id,)).fetchone(); take=False
                if not old: take=True
                else:
                    old_rev=int(old["revision"]); old_ts=float(old["updated_at"]); old_origin=str(old["origin"])
                    if incoming_rev>old_rev: take=True
                    elif incoming_rev==old_rev and json.loads(old["payload"]) != cap.to_dict():
                        conflicts += 1; take=(incoming_ts,incoming_origin)>(old_ts,old_origin)
                if take:
                    db.execute("INSERT INTO capabilities(capability_id,payload,revision,origin,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(capability_id) DO UPDATE SET payload=excluded.payload,revision=excluded.revision,origin=excluded.origin,updated_at=excluded.updated_at",
                               (cap.capability_id,canonical_json(cap.to_dict()),incoming_rev,incoming_origin,incoming_ts or time.time())); applied+=1
                else: ignored+=1
        self.emit("sync.reconciled","capabilities",{"applied":applied,"conflicts":conflicts,"ignored":ignored})
        return {"applied":applied,"conflicts":conflicts,"ignored":ignored}

    # Jobs are idempotent through a unique idempotency_key.
    def create_job(self, job: Job) -> tuple[Job,bool]:
        with self.connect() as db:
            existing=db.execute("SELECT * FROM jobs WHERE idempotency_key=?",(job.idempotency_key,)).fetchone()
            if existing:return self._row_job(existing),False
            db.execute("INSERT INTO jobs(job_id,idempotency_key,intent,state,mode,attempts,error,plan_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                       (job.job_id,job.idempotency_key,canonical_json(job.intent),job.state,job.mode,job.attempts,job.error,job.plan_id,job.created_at,job.updated_at))
        self.emit("job.created",job.job_id,{"state":job.state,"mode":job.mode}); return job,True

    def _row_job(self,r) -> Job:
        return Job(job_id=r["job_id"],idempotency_key=r["idempotency_key"],intent=json.loads(r["intent"]),state=r["state"],mode=r["mode"],attempts=r["attempts"],error=r["error"],plan_id=r["plan_id"],created_at=r["created_at"],updated_at=r["updated_at"])

    def get_job(self, job_id: str) -> Job | None:
        with self.connect() as db:r=db.execute("SELECT * FROM jobs WHERE job_id=?",(job_id,)).fetchone()
        return self._row_job(r) if r else None

    def list_jobs(self, limit:int=100) -> list[Job]:
        with self.connect() as db: rows=db.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?",(min(limit,1000),)).fetchall()
        return [self._row_job(r) for r in rows]

    def update_job(self, job_id:str, *, state:str|None=None, attempts:int|None=None, error:str|None=None, plan_id:str|None=None) -> Job:
        job=self.get_job(job_id)
        if not job: raise KeyError(job_id)
        state=state if state is not None else job.state; attempts=attempts if attempts is not None else job.attempts
        error=error if error is not None else job.error; plan_id=plan_id if plan_id is not None else job.plan_id; now=time.time()
        with self.connect() as db:
            db.execute("UPDATE jobs SET state=?,attempts=?,error=?,plan_id=?,updated_at=? WHERE job_id=?",(state,attempts,error,plan_id,now,job_id))
        self.emit("job.updated",job_id,{"state":state,"attempts":attempts,"plan_id":plan_id,"error":error})
        return self.get_job(job_id)  # type: ignore[return-value]

    def pending_jobs(self) -> list[Job]:
        with self.connect() as db: rows=db.execute("SELECT * FROM jobs WHERE state IN ('queued','running') ORDER BY created_at").fetchall()
        return [self._row_job(r) for r in rows]

    # Plan snapshots/event history.
    def put_plan(self, plan: InterfacePlan) -> None:
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO plans(plan_id,job_id,payload,generation,created_at) VALUES(?,?,?,?,?)",(plan.plan_id,plan.job_id,canonical_json(plan.to_dict()),plan.generation,plan.created_at))
        self.emit("plan.snapshot",plan.plan_id,{"job_id":plan.job_id,"generation":plan.generation,"job_state":plan.job_state})

    def get_plan(self, plan_id:str) -> InterfacePlan | None:
        with self.connect() as db:r=db.execute("SELECT payload FROM plans WHERE plan_id=?",(plan_id,)).fetchone()
        return InterfacePlan.from_dict(json.loads(r["payload"])) if r else None

    def add_feedback(self, kind:str, payload:dict[str,Any]) -> None:
        with self.connect() as db:db.execute("INSERT INTO feedback(kind,payload,created_at) VALUES(?,?,?)",(kind,canonical_json(payload),time.time()))
        self.emit("feedback.received",kind,payload)

    def feedback(self, kind:str|None=None) -> list[dict[str,Any]]:
        with self.connect() as db:
            rows=db.execute("SELECT kind,payload,created_at FROM feedback"+(" WHERE kind=?" if kind else "")+(" ORDER BY id"),((kind,) if kind else ())).fetchall()
        return [{"kind":r["kind"],"payload":json.loads(r["payload"]),"created_at":r["created_at"]} for r in rows]

    def cache_get(self,key:str) -> dict[str,Any] | None:
        now=time.time()
        with self.connect() as db:r=db.execute("SELECT payload,expires_at FROM cache WHERE cache_key=?",(key,)).fetchone()
        if not r:return None
        if r["expires_at"]<now:
            with self.connect() as db:db.execute("DELETE FROM cache WHERE cache_key=?",(key,))
            return None
        return json.loads(r["payload"])

    def cache_put(self,key:str,payload:dict[str,Any],ttl_s:float=300) -> None:
        now=time.time()
        with self.connect() as db:db.execute("INSERT OR REPLACE INTO cache VALUES(?,?,?,?)",(key,canonical_json(payload),now,now+ttl_s))
