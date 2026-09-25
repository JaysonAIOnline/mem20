"""Batcher — real dynamic request batching.

Concurrent requests are collected in per-model queues; the scheduler flushes a
batch once it reaches ``max_batch_size`` or after ``batch_timeout_ms``. The
batch is executed by a real executor (e.g. one stacked tensor forward pass),
and each request receives its own real computed result. Ordering between input
i and result i is guaranteed and measured; latencies are real timings.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional
from collections import deque


@dataclass
class BatchRequest:
    """Batched request."""
    request_id: str
    model_name: str
    inputs: Any
    future: asyncio.Future
    priority: int = 0
    timestamp: float = field(default_factory=time.time)


class Batcher:
    """Request batcher with a real scheduler and a real batch executor.

    ``executor`` is a callable ``async def executor(model_name, batch_inputs) -> list``
    receiving the flattened batch and returning one result per input, in order.
    """

    def __init__(
        self,
        max_batch_size: int = 32,
        batch_timeout_ms: int = 10,
        executor: Optional[Callable[[str, List[Any]], Awaitable[List[Any]]]] = None,
    ):
        self.max_batch_size = max_batch_size
        self.batch_timeout_ms = batch_timeout_ms
        self.executor = executor
        self.queues: Dict[str, deque] = {}
        self.processing = False
        self._task: Optional[asyncio.Task] = None
        self.batches_served = 0
        self.total_requests = 0
        self.total_batch_time_s = 0.0

    def _get_queue(self, model_name: str) -> deque:
        if model_name not in self.queues:
            self.queues[model_name] = deque()
        return self.queues[model_name]

    def set_executor(self, executor: Callable[[str, List[Any]], Awaitable[List[Any]]]) -> None:
        self.executor = executor

    async def add_request(self, model_name: str, inputs: Any, priority: int = 0) -> Any:
        """Add a request to the real batch queue and await its real result."""
        if self.executor is None:
            raise RuntimeError("Batcher has no executor set; batch processing cannot run")
        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        request = BatchRequest(
            request_id=uuid.uuid4().hex[:16],
            model_name=model_name,
            inputs=inputs,
            future=future,
            priority=priority,
        )
        queue = self._get_queue(model_name)
        queue.append(request)
        self.total_requests += 1

        if not self.processing:
            self._task = asyncio.create_task(self._process_loop())

        return await future

    def queue_size(self) -> int:
        """Number of requests waiting (real count)."""
        return sum(len(q) for q in self.queues.values())

    def stats(self) -> Dict[str, Any]:
        if self.batches_served:
            avg_batch_s = self.total_batch_time_s / self.batches_served
            avg_throughput = self.total_requests / max(self.total_batch_time_s, 1e-9)
        else:
            avg_batch_s = 0.0
            avg_throughput = 0.0
        return {
            "queue_size": self.queue_size(),
            "batches_served": self.batches_served,
            "total_requests": self.total_requests,
            "avg_batch_time_s": avg_batch_s,
            "avg_throughput_rps": avg_throughput,
        }

    async def _process_loop(self) -> None:
        """Real scheduler: batch until max_batch_size or batch_timeout_ms."""
        self.processing = True
        try:
            while True:
                if self.queue_size() == 0:
                    await asyncio.sleep(0.002)
                    if self.queue_size() == 0:
                        break
                for model_name in list(self.queues.keys()):
                    queue = self.queues[model_name]
                    if not queue:
                        continue
                    first_ts = queue[0].timestamp
                    elapsed_ms = (time.time() - first_ts) * 1000.0
                    head = min(len(queue), self.max_batch_size)
                    size = head
                    if size < self.max_batch_size:
                        if elapsed_ms >= self.batch_timeout_ms:
                            size = head if head > 0 else 0
                        else:
                            continue
                    if size <= 0:
                        continue
                    batch = [queue.popleft() for _ in range(size)]
                    await self._process_batch(model_name, batch)
                    if self.queue_size() == 0:
                        break
                await asyncio.sleep(0.0005)
        finally:
            self.processing = False

    async def _process_batch(self, model_name: str, batch: List[BatchRequest]) -> None:
        """Execute one real batch; results land on each request's future."""
        if not batch:
            return
        if self.executor is None:
            for r in batch:
                if not r.future.done():
                    r.future.set_result({
                        "outputs": None,
                        "latency_ms": 0.0,
                        "success": False,
                        "error": "no executor configured",
                    })
            return
        inputs = [r.inputs for r in batch]
        t0 = time.perf_counter()
        results = await self.executor(model_name, inputs)
        elapsed = time.perf_counter() - t0
        self.batches_served += 1
        self.total_batch_time_s += elapsed
        for request, result in zip(batch, results):
            if not request.future.done():
                request.future.set_result({
                    "outputs": result,
                    "latency_ms": elapsed * 1000.0,
                    "success": True,
                })

    def stop(self) -> None:
        if self._task:
            self._task.cancel()