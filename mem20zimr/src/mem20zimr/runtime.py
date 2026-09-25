from __future__ import annotations
import json, os, shutil, subprocess, sys, tempfile, threading, time, uuid, zipfile
from pathlib import Path
from typing import Any
from .model import MicroappManifest, JobResult
from .signing import verify_manifest
from .state import StateStore
from .scheduler import ModeScheduler
from .metrics import Metrics
from .remote import RemoteAdapter

try:
    import resource
except ImportError:
    resource = None

class MicroappRuntime:
    def __init__(self, state_path: str | Path, trust: dict[str,str] | None = None, remote_endpoints: dict[str,str] | None=None, max_concurrent: int=4):
        self.store = StateStore(state_path)
        self.trust = trust or {}
        self.scheduler = ModeScheduler(); self.metrics = Metrics(); self.remote=RemoteAdapter(remote_endpoints); self._procs: dict[str,subprocess.Popen] = {}; self._lock=threading.RLock(); self._quota=threading.BoundedSemaphore(max(1,max_concurrent))

    def inspect(self, bundle: str | Path) -> MicroappManifest:
        bundle=Path(bundle)
        with zipfile.ZipFile(bundle) as z:
            manifest = MicroappManifest.from_json(z.read("manifest.json").decode())
        secret=self.trust.get(manifest.signer)
        if not secret: raise ValueError(f"untrusted signer: {manifest.signer}")
        with zipfile.ZipFile(bundle) as z: raw=json.loads(z.read("manifest.json"))
        verify_manifest(raw, secret, bundle)
        return manifest

    def register(self, bundle: str | Path) -> MicroappManifest:
        bundle=Path(bundle).resolve(); manifest=self.inspect(bundle)
        existing=self.store.get_microapp(manifest.app_id,manifest.version)
        if existing:
            old=json.loads(existing["manifest_json"] or "{}")
            if old.get("digest") != manifest.digest: raise ValueError("version conflict: same app/version has different immutable digest")
        self.store.register_microapp(manifest.app_id,manifest.version,str(bundle),manifest.to_dict())
        return manifest

    def unregister(self, app_id: str, version: str) -> bool:
        return self.store.delete_microapp(app_id,version)

    def launch_registered(self, app_id: str, version: str, payload: dict[str,Any] | None=None, **kwargs):
        row=self.store.get_microapp(app_id,version)
        if not row: raise ValueError("microapp not registered")
        return self.launch(row["bundle_path"],payload or {},**kwargs)

    def launch(self, bundle: str | Path, payload: dict[str,Any] | None = None, *, idempotency_key: str | None=None,
               preferred_mode: str | None=None, telemetry: dict | None=None, async_run: bool=False) -> str | JobResult:
        bundle=Path(bundle); manifest=self.inspect(bundle)
        existing=self.store.get_microapp(manifest.app_id,manifest.version)
        if existing:
            old=json.loads(existing["manifest_json"] or "{}")
            if old.get("digest") != manifest.digest: raise ValueError("version conflict: same app/version has different immutable digest")
        else:
            self.store.register_microapp(manifest.app_id,manifest.version,str(bundle.resolve()),manifest.to_dict())
        telemetry=dict(telemetry or {})
        telemetry.setdefault("mode_biases",self.store.mode_biases(manifest.app_id))
        if any(m in manifest.supported_modes for m in ("edge","cloud","hybrid")):
            telemetry.setdefault("network_up", bool(self.remote.endpoints) or bool(telemetry.get("network_up",False)))
        decision=self.scheduler.choose(manifest.supported_modes, telemetry, preferred_mode)
        mode=decision.chosen
        if manifest.kind == "web" and mode != "browser":
            # web bundles are portable as static browser microapps; remap local request to browser where supported
            if "browser" in manifest.supported_modes: mode="browser"
            else: raise ValueError("web microapp requires browser mode")
        job_id=str(uuid.uuid4()); key=idempotency_key or job_id
        actual, created=self.store.create_job({"job_id":job_id,"app_id":manifest.app_id,"version":manifest.version,"status":"queued","mode":mode,"attempt":0,"idempotency_key":key,"request":payload or {}})
        if not created:
            existing=self.store.get_job(actual)
            if existing and existing.get("result_json"):
                return self._result_from_row(existing)
            return actual
        self.store.event(job_id,"queued",{"mode":mode,"decision":decision.__dict__})
        if async_run:
            threading.Thread(target=self._run_job,args=(job_id,bundle,manifest,payload or {},mode,decision.__dict__),daemon=True).start(); return job_id
        return self._run_job(job_id,bundle,manifest,payload or {},mode,decision.__dict__)

    def _run_job(self, job_id: str, bundle: Path, manifest: MicroappManifest, payload: dict, mode: str, explanation: dict) -> JobResult:
        started=time.time(); self.metrics.inc("jobs_total"); last_err=""; out=""; code=None
        if mode in {"cloud","edge","hybrid"}:
            if self.remote.available(mode):
                try:
                    remote=self.remote.execute(mode,bundle,payload,manifest.limits.timeout_seconds)
                    return self._finish(job_id,manifest,mode,1,int(remote.get("exit_code",0)),remote.get("stdout",""),remote.get("stderr",""),started,{**explanation,"remote":True},remote.get("status","succeeded"))
                except Exception as e:
                    if mode != "hybrid": return self._finish(job_id,manifest,mode,1,127,"",f"remote failure: {e}",started,explanation,"failed")
                    explanation={**explanation,"fallback":"hybrid_to_local_after_remote_failure","remote_error":str(e)}; mode="local"
            elif mode == "hybrid":
                mode="local"; explanation={**explanation,"fallback":"hybrid_to_local_no_remote_adapter"}
            else:
                return self._finish(job_id,manifest,mode,1,127,"","remote adapter unavailable",started,explanation,"failed")
        if mode == "browser":
            return self._finish(job_id,manifest,mode,1,0,json.dumps({"launch_path":f"/v1/browser/{job_id}/{manifest.entrypoint}"}),"",started,explanation,"ready")
        with self._quota:
            for attempt in range(1, manifest.limits.max_retries+2):
                if self.store.cancellation_requested(job_id):
                    return self._finish(job_id,manifest,mode,attempt,None,out,"cancelled",started,explanation,"cancelled")
                self.store.update_job(job_id,status="running",attempt=attempt); self.store.event(job_id,"attempt_started",{"attempt":attempt})
                try:
                    code,out,last_err=self._exec_python(job_id,bundle,manifest,payload)
                    if code==0:
                        return self._finish(job_id,manifest,mode,attempt,code,out,last_err,started,explanation,"succeeded")
                except subprocess.TimeoutExpired:
                    code=124; last_err="timeout"
                except Exception as e:
                    code=1; last_err=f"{type(e).__name__}: {e}"
                self.store.event(job_id,"attempt_failed",{"attempt":attempt,"exit_code":code,"error":last_err})
                if attempt <= manifest.limits.max_retries: time.sleep(min(0.25*2**(attempt-1),2))
            return self._finish(job_id,manifest,mode,attempt,code,out,last_err,started,explanation,"failed")

    def browser_file(self, job_id: str, relpath: str) -> tuple[bytes,str]:
        row=self.store.get_job(job_id)
        if not row or row["status"] != "ready": raise FileNotFoundError(job_id)
        # Recover bundle from registry using app/version, keeping browser launch immutable and zero-install.
        reg=self.store.get_microapp(row["app_id"],row["version"])
        if not reg: raise FileNotFoundError("browser bundle not registered")
        rel=relpath.lstrip('/')
        if '..' in Path(rel).parts: raise ValueError("invalid path")
        import mimetypes
        with zipfile.ZipFile(reg["bundle_path"]) as z: data=z.read(rel)
        return data, mimetypes.guess_type(rel)[0] or "application/octet-stream"

    def _preexec(self, manifest: MicroappManifest):
        if resource is None: return None
        def fn():
            resource.setrlimit(resource.RLIMIT_CPU,(manifest.limits.cpu_seconds,manifest.limits.cpu_seconds))
            mem=manifest.limits.memory_mb*1024*1024
            try: resource.setrlimit(resource.RLIMIT_AS,(mem,mem))
            except Exception: pass
            resource.setrlimit(resource.RLIMIT_FSIZE,(manifest.limits.output_kb*1024,manifest.limits.output_kb*1024))
        return fn

    def _exec_python(self, job_id: str, bundle: Path, manifest: MicroappManifest, payload: dict) -> tuple[int,str,str]:
        with tempfile.TemporaryDirectory(prefix="fs-microapp-") as td:
            root=Path(td)
            with zipfile.ZipFile(bundle) as z:
                for info in z.infolist():
                    target=(root/info.filename).resolve()
                    if root.resolve() not in target.parents and target != root.resolve(): raise ValueError("zip path traversal")
                    z.extract(info,root)
            entry=(root/manifest.entrypoint).resolve()
            if root.resolve() not in entry.parents or not entry.is_file(): raise ValueError("invalid entrypoint")
            env={"PATH":os.environ.get("PATH",""),"PYTHONIOENCODING":"utf-8","FREESTACK_MICROAPP":"1"}
            p=subprocess.Popen([sys.executable,"-I",str(entry)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,cwd=root,env=env,preexec_fn=self._preexec(manifest))
            with self._lock: self._procs[job_id]=p
            try:
                stdout,stderr=p.communicate(json.dumps(payload),timeout=manifest.limits.timeout_seconds)
            except subprocess.TimeoutExpired:
                p.kill(); p.communicate(); raise
            finally:
                with self._lock: self._procs.pop(job_id,None)
            limit=manifest.limits.output_kb*1024
            return p.returncode,stdout[:limit],stderr[:limit]

    def cancel(self, job_id: str) -> None:
        self.store.request_cancel(job_id)
        with self._lock:
            p=self._procs.get(job_id)
            if p and p.poll() is None: p.terminate()

    def resume_incomplete(self, bundle_resolver) -> list[str]:
        resumed=[]
        for row in self.store.list_jobs(1000):
            if row["status"] in {"queued","running"}:
                bundle=Path(bundle_resolver(row["app_id"],row["version"]))
                manifest=self.inspect(bundle); payload=json.loads(row["request_json"] or "{}")
                threading.Thread(target=self._run_job,args=(row["job_id"],bundle,manifest,payload,row["mode"],{"reason":"restart_recovery"}),daemon=True).start(); resumed.append(row["job_id"])
        return resumed

    def _finish(self, job_id,manifest,mode,attempt,code,out,err,started,explanation,status):
        finished=time.time(); result=JobResult(job_id,manifest.app_id,status,mode,attempt,code,out,err,started,finished,explanation)
        self.store.update_job(job_id,status=status,result_json=result.__dict__); self.store.event(job_id,"finished",result.__dict__)
        self.metrics.inc(f"jobs_{status}"); self.metrics.observe(finished-started); return result

    def _result_from_row(self,row):
        d=json.loads(row["result_json"]); return JobResult(**d)
