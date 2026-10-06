from __future__ import annotations
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from threading import BoundedSemaphore, Event, Lock
from pathlib import Path
from typing import Any
import hashlib, json, time, uuid
from .model import Capability, UserIntent, InterfacePlan, Job, JobState, ExecutionMode, canonical_json
from .state import StateStore
from .composer import InterfaceComposer
from .scheduler import Scheduler, Telemetry
from .metrics import Metrics
from .security import redact
from .remote import RemotePeer, RemoteError

@dataclass
class RuntimeConfig:
    db_path: str = "interface_composer.db"
    max_concurrent: int = 4
    max_queue: int = 32
    max_retries: int = 2
    timeout_s: float = 5.0
    cache_ttl_s: float = 300.0
    origin: str = "local"
    cloud_endpoint: str | None = None
    edge_endpoint: str | None = None

class InterfaceComposerRuntime:
    def __init__(self,config:RuntimeConfig|None=None):
        self.config=config or RuntimeConfig(); self.state=StateStore(self.config.db_path,self.config.origin)
        self.composer=InterfaceComposer(); self.scheduler=Scheduler(); self.metrics=Metrics()
        self._sem=BoundedSemaphore(self.config.max_concurrent); self._executor=ThreadPoolExecutor(max_workers=self.config.max_concurrent)
        self._cancel:dict[str,Event]={}; self._cancel_lock=Lock(); self._queue_lock=Lock(); self._queued=0

    def close(self):self._executor.shutdown(wait=True,cancel_futures=True)

    def register_capability(self,cap:Capability,expected_revision:int|None=None)->int:return self.state.put_capability(cap,expected_revision=expected_revision)
    def query_capabilities(self)->list[dict[str,Any]]:return [c.to_dict() for c in self.state.list_capabilities()]
    def delete_capability(self,cid:str)->bool:return self.state.delete_capability(cid)
    def subscribe(self,after:int=0)->list[dict[str,Any]]:return self.state.events(after)

    def _feedback_weights(self)->dict[str,float]:
        out={}
        for f in self.state.feedback("capability_weight"):
            p=f["payload"]; cid=str(p.get("capability_id","")); delta=float(p.get("delta",0))
            if cid:out[cid]=max(-0.1,min(0.1,out.get(cid,0)+delta))
        return out

    def add_feedback(self,kind:str,payload:dict[str,Any])->None:
        safe=redact(payload); self.state.add_feedback(kind,safe)
        if kind=="mode_bias":self.scheduler.apply_feedback(str(safe.get("mode")),float(safe.get("delta",0)))

    def discovery(self)->dict[str,bool]:
        return {"local":True,"edge":bool(self.config.edge_endpoint and RemotePeer(self.config.edge_endpoint).health()),"cloud":bool(self.config.cloud_endpoint and RemotePeer(self.config.cloud_endpoint).health())}

    def _telemetry(self)->Telemetry:
        d=self.discovery()
        return Telemetry(local_load=min(1.0,self._queued/max(1,self.config.max_queue)),cloud_available=d["cloud"],edge_available=d["edge"],network_quality=1.0 if (d["cloud"] or d["edge"]) else 0.0)

    def compose(self,intent:UserIntent,*,idempotency_key:str|None=None,preferred_mode:str|None=None,telemetry:Telemetry|None=None)->dict[str,Any]:
        intent.validate(); safe_intent=UserIntent.from_dict(redact(intent.to_dict()))
        key=idempotency_key or hashlib.sha256(canonical_json(safe_intent.to_dict()).encode()).hexdigest()
        decision=self.scheduler.choose(telemetry or self._telemetry(),preferred_mode)
        job=Job("job_"+uuid.uuid4().hex,key,safe_intent.to_dict(),JobState.QUEUED.value,decision.mode)
        job,created=self.state.create_job(job)
        if not created:
            plan=self.state.get_plan(job.plan_id) if job.plan_id else None
            return {"job":job.to_dict(),"plan":plan.to_dict() if plan else None,"idempotent_replay":True,"schedule":decision.__dict__}
        with self._queue_lock:
            if self._queued>=self.config.max_queue:
                self.state.update_job(job.job_id,state=JobState.FAILED.value,error="backpressure: queue quota exceeded")
                self.metrics.inc("backpressure_rejections_total"); raise RuntimeError("backpressure: queue quota exceeded")
            self._queued+=1
        try:
            return self._run_job(job,safe_intent,decision)
        finally:
            with self._queue_lock:self._queued=max(0,self._queued-1)

    def compose_async(self,intent:UserIntent,**kwargs):return self._executor.submit(self.compose,intent,**kwargs)

    def _run_job(self,job:Job,intent:UserIntent,decision)->dict[str,Any]:
        with self._cancel_lock:self._cancel[job.job_id]=Event()
        if not self._sem.acquire(timeout=self.config.timeout_s):
            self.state.update_job(job.job_id,state=JobState.FAILED.value,error="concurrency timeout");raise TimeoutError("concurrency timeout")
        try:
            self.state.update_job(job.job_id,state=JobState.RUNNING.value)
            self.state.emit("job.progress",job.job_id,{"progress":0.1,"artifact":{"type":"intent","task":intent.task}})
            last_error=None
            for attempt in range(1,self.config.max_retries+2):
                if self._cancel[job.job_id].is_set():
                    self.state.update_job(job.job_id,state=JobState.CANCELLED.value,attempts=attempt-1);raise RuntimeError("cancelled")
                self.state.update_job(job.job_id,attempts=attempt)
                try:
                    with self.metrics.timed("compose_latency"):
                        plan=self._execute_mode(job,intent,decision.mode)
                    self.state.emit("job.progress",job.job_id,{"progress":0.7,"artifact":{"type":"interface_plan","plan_id":plan.plan_id,"generation":plan.generation}})
                    plan=self.composer.rebuild(plan,JobState.SUCCEEDED.value,1.0,{"type":"completion","selected":len(plan.selected_capabilities)})
                    self.state.put_plan(plan); self.state.update_job(job.job_id,state=JobState.SUCCEEDED.value,plan_id=plan.plan_id,error="")
                    self.metrics.inc("compose_success_total")
                    return {"job":self.state.get_job(job.job_id).to_dict(),"plan":plan.to_dict(),"idempotent_replay":False,"schedule":decision.__dict__}
                except (RemoteError,TimeoutError,FutureTimeout,OSError) as e:
                    last_error=e; self.metrics.inc("retry_total")
                    if attempt<=self.config.max_retries:time.sleep(min(0.05*attempt,0.2));continue
                    break
            self.state.update_job(job.job_id,state=JobState.FAILED.value,error=str(last_error));self.metrics.inc("compose_failure_total");raise RuntimeError(str(last_error))
        finally:
            self._sem.release()

    def _execute_mode(self,job:Job,intent:UserIntent,mode:str)->InterfacePlan:
        caps=self.state.list_capabilities(); ckey=self.composer.cache_key(intent,caps,mode); cached=self.state.cache_get(ckey)
        if cached:
            self.metrics.inc("cache_hit_total"); p=InterfacePlan.from_dict(cached); p.plan_id="plan_"+uuid.uuid4().hex;p.job_id=job.job_id;return p
        def local()->InterfacePlan:
            p=self.composer.compose(job.job_id,intent,caps,"local",self._feedback_weights());self.state.cache_put(ckey,p.to_dict(),self.config.cache_ttl_s);return p
        if mode==ExecutionMode.LOCAL.value:return local()
        endpoint=self.config.cloud_endpoint if mode==ExecutionMode.CLOUD.value else (self.config.edge_endpoint or self.config.cloud_endpoint)
        if endpoint:
            try:
                data=RemotePeer(endpoint,self.config.timeout_s).compose({"intent":intent.to_dict(),"capabilities":[c.to_dict() for c in caps]})
                p=InterfacePlan.from_dict(data["plan"]);p.job_id=job.job_id;p.plan_id="plan_"+uuid.uuid4().hex;return p
            except RemoteError:
                if mode==ExecutionMode.HYBRID.value:
                    self.metrics.inc("failover_total");self.state.emit("runtime.failover",job.job_id,{"from":"remote","to":"local"});return local()
                raise
        if mode==ExecutionMode.HYBRID.value:return local()
        raise RemoteError("cloud peer unavailable")

    def remote_compose(self,intent:UserIntent,capabilities:list[Capability])->InterfacePlan:
        return self.composer.compose("remote_job",intent,capabilities,"cloud",{})

    def cancel(self,job_id:str)->bool:
        with self._cancel_lock:e=self._cancel.get(job_id)
        if not e:
            j=self.state.get_job(job_id)
            if j and j.state in {JobState.QUEUED.value,JobState.RUNNING.value}:self.state.update_job(job_id,state=JobState.CANCELLED.value);return True
            return False
        e.set();self.state.emit("job.cancel_requested",job_id,{});return True

    def recover_pending(self,execute:bool=False)->list[str]:
        recovered=[]
        for job in self.state.pending_jobs():
            self.state.update_job(job.job_id,state=JobState.QUEUED.value,error="recovered_after_restart");recovered.append(job.job_id)
            if execute:
                intent=UserIntent.from_dict(job.intent)
                try:self._run_job(self.state.get_job(job.job_id),intent,self.scheduler.choose(self._telemetry(),job.mode))
                except Exception:pass
        return recovered

    def sync_from(self,records:list[dict[str,Any]])->dict[str,int]:return self.state.reconcile_capabilities(records)
    def sync_export(self)->list[dict[str,Any]]:return self.state.export_capabilities()
