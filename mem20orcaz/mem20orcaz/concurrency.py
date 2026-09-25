"""Concurrency management primitives for mem20orcaz.

Pure-stdlib port of OrKa's concurrency utils: semaphore-bounded concurrency,
per-operation timeouts, a decorator for easy application, task tracking and
graceful shutdown. Environment defaults match OrKa
(``ORKA_MAX_CONCURRENT_REQUESTS`` fallback 10, ``ORKA_TIMEOUT_SECONDS`` fallback
300, per-agent fallback 120).
"""

from __future__ import annotations

import asyncio
import logging
import time
import os
from functools import wraps
from typing import Any, Awaitable, Callable, Optional, TypeVar, cast

logger = logging.getLogger(__name__)

T = TypeVar("T")


def default_max_concurrency() -> int:
    """Resolve the default concurrency limit from ORKA_MAX_CONCURRENT_REQUESTS (fallback 10)."""
    try:
        value = int(os.getenv("ORKA_MAX_CONCURRENT_REQUESTS", "10"))
        return value if value > 0 else 10
    except (TypeError, ValueError):
        logger.warning("Invalid ORKA_MAX_CONCURRENT_REQUESTS; using default 10")
        return 10


def default_timeout_seconds() -> float:
    """Resolve the default operation timeout from ORKA_TIMEOUT_SECONDS (fallback 300s)."""
    try:
        value = float(os.getenv("ORKA_TIMEOUT_SECONDS", "300"))
        return value if value > 0 else 300.0
    except (TypeError, ValueError):
        logger.warning("Invalid ORKA_TIMEOUT_SECONDS; using default 300")
        return 300.0


def default_agent_timeout_seconds() -> float:
    """Resolve the per-agent execution timeout (fallback 120s)."""
    try:
        value = float(os.getenv("ORKA_AGENT_TIMEOUT_SECONDS", "120"))
        return value if value > 0 else 120.0
    except (TypeError, ValueError):
        logger.warning("Invalid ORKA_AGENT_TIMEOUT_SECONDS; using default 120")
        return 120.0


class TimeoutError_(asyncio.TimeoutError):
    """Abstraction over asyncio.TimeoutError (removed as builtin in 3.11)."""


class ConcurrencyManager:
    """Controls task concurrency and timeouts."""

    def __init__(self, max_concurrency: Optional[int] = None) -> None:
        self.max_concurrency = max_concurrency if max_concurrency else default_max_concurrency()
        self._semaphore = asyncio.Semaphore(self.max_concurrency)
        self._tasks: set[asyncio.Task] = set()
        self._closed = False

    async def run_with_timeout(self, coro: Awaitable[T], timeout: Optional[float] = None,
                               **_: Any) -> T:
        """Run ``coro`` under the concurrency semaphore and an optional timeout."""
        timeout = timeout if timeout is not None else default_timeout_seconds()

        async def _run() -> T:
            async with self._semaphore:
                if self._closed:
                    raise RuntimeError("ConcurrencyManager is shut down")
                return await coro

        task: asyncio.Task[T] = asyncio.ensure_future(_run())
        self._tasks.add(task)
        try:
            try:
                return await asyncio.wait_for(task, timeout=timeout)
            except asyncio.TimeoutError:
                task.cancel()
                raise TimeoutError_(
                    f"operation timed out after {timeout:.1f}s"
                ) from None
        finally:
            self._tasks.discard(task)

    def with_concurrency(self, timeout: Optional[float] = None) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
        """Decorator applying concurrency control + timeout to an async function."""
        sem = self._semaphore

        def decorator(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
            @wraps(fn)
            async def wrapper(*args: Any, **kwargs: Any) -> T:
                effective_timeout = timeout if timeout is not None else default_timeout_seconds()

                async def _run() -> T:
                    async with sem:
                        if self._closed:
                            raise RuntimeError("ConcurrencyManager is shut down")
                        return await fn(*args, **kwargs)

                task = asyncio.ensure_future(_run())
                self._tasks.add(task)
                try:
                    try:
                        return await asyncio.wait_for(task, timeout=effective_timeout)
                    except asyncio.TimeoutError:
                        task.cancel()
                        raise TimeoutError_(
                            f"{getattr(fn, '__name__', 'function')} timed out after {effective_timeout:.1f}s"
                        ) from None
                finally:
                    self._tasks.discard(task)

            return wrapper

        return decorator

    async def shutdown(self, timeout: Optional[float] = None) -> None:
        """Cancel pending tasks and block until they settle."""
        self._closed = True
        pending = [t for t in self._tasks if not t.done()]
        if not pending:
            return
        for t in pending:
            t.cancel()
        gathered = asyncio.gather(*pending, return_exceptions=True)
        try:
            await asyncio.wait_for(gathered, timeout=timeout or 10.0)
        except asyncio.TimeoutError:
            logger.warning("ConcurrencyManager.shutdown timed out; leaving %d tasks", len(pending))
        self._tasks = set()

    @property
    def remaining_slots(self) -> int:
        return self._semaphore._value  # type: ignore[attr-defined]


class Timer:
    """Lightweight wall-clock timer for metrics."""

    def __init__(self) -> None:
        self._start = time.monotonic()

    def elapsed(self) -> float:
        return time.monotonic() - self._start

    def reset(self) -> None:
        self._start = time.monotonic()