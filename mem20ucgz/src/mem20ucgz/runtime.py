from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass
from threading import Event, Lock, Semaphore
from typing import Any, Callable
import time
import uuid

from .graph import CapabilityGraph
from .models import Job, JobState, Plan

Handler = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(slots=True)
class RuntimePolicy:
    max_retries: int = 2
    timeout_seconds: float = 15.0
    max_parallel: int = 8
    max_payload_bytes: int = 1_000_000


class CapabilityRuntime:
    """Resumable, idempotent execution runtime with bounded failure behavior."""

    def __init__(self, graph: CapabilityGraph, policy: RuntimePolicy | None = None) -> None:
        self.graph = graph
        self.policy = policy or RuntimePolicy()
        self.handlers: dict[str, Handler] = {}
        self._cancel: dict[str, Event] = {}
        self._lock = Lock()
        self._quota = Semaphore(self.policy.max_parallel)

    def register_handler(self, capability_id: str, handler: Handler) -> None:
        if not self.graph.get(capability_id):
            raise KeyError(f"unknown capability: {capability_id}")
        self.handlers[capability_id] = handler

    def cancel(self, job_id: str) -> bool:
        event = self._cancel.get(job_id)
        if not event:
            return False
        event.set()
        return True

    def execute(self, plan: Plan, payload: dict[str, Any], idempotency_key: str | None = None) -> Job:
        import json
        raw = json.dumps(payload, default=str).encode()
        if len(raw) > self.policy.max_payload_bytes:
            raise ValueError("payload exceeds sandbox limit")
        if plan.unresolved_outputs or plan.bottlenecks:
            raise ValueError("cannot execute an unresolved/blocked plan")

        key = idempotency_key or str(uuid.uuid4())
        existing = self.graph.store.get_job_by_key(key)
        if existing:
            return existing

        job = Job(id=str(uuid.uuid4()), idempotency_key=key, plan_id=plan.id, state=JobState.PENDING)
        self._cancel[job.id] = Event()
        self.graph.store.put_job(job)

        if not self._quota.acquire(timeout=self.policy.timeout_seconds):
            job.state = JobState.FAILED
            job.error = "runtime quota wait timed out"
            self.graph.store.put_job(job)
            return job

        try:
            context = dict(payload)
            job.state = JobState.RUNNING
            self.graph.store.put_job(job)
            for capability_id in plan.capabilities:
                if self._cancel[job.id].is_set():
                    job.state = JobState.CANCELLED
                    self.graph.store.put_job(job)
                    return job
                handler = self.handlers.get(capability_id)
                if not handler:
                    raise RuntimeError(f"no local handler registered for {capability_id}")
                attempts = 0
                while True:
                    attempts += 1
                    job.attempts += 1
                    try:
                        with ThreadPoolExecutor(max_workers=1) as pool:
                            fut = pool.submit(handler, dict(context))
                            result = fut.result(timeout=self.policy.timeout_seconds)
                        if not isinstance(result, dict):
                            raise TypeError(f"handler {capability_id} must return dict")
                        context.update(result)
                        self.graph.store.emit("job.progress", job.id, {"capability": capability_id, "attempt": attempts})
                        break
                    except FutureTimeout as e:
                        exc: Exception = TimeoutError(f"capability {capability_id} timed out")
                    except Exception as e:  # bounded and reported below
                        exc = e
                    if attempts > self.policy.max_retries:
                        raise exc
                    job.state = JobState.RETRYING
                    self.graph.store.put_job(job)
                    time.sleep(min(0.05 * (2 ** (attempts - 1)), 0.5))
                    job.state = JobState.RUNNING
            job.state = JobState.SUCCEEDED
            job.result = context
            self.graph.store.put_job(job)
            return job
        except Exception as e:
            job.state = JobState.FAILED
            job.error = f"{type(e).__name__}: {e}"
            self.graph.store.put_job(job)
            return job
        finally:
            self._quota.release()
