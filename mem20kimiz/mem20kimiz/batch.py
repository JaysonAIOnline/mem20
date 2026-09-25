"""AgentRunBatch — faithful Python port of kimi-code's agentRunBatch.ts.

Implements the swarm batch scheduler: staggered initial launch, configurable
max concurrency, rate-limit adaptive retry (capacity shrink/recovery), per-task
timeout, user/batch abort, and ordered results. The port keeps the same class
surface and constants; concurrency uses asyncio instead of timers/callbacks.
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional, TypeVar, Union

from .types import (
    SessionSwarmRunResult,
    SessionSwarmSpawnTask,
    SessionSwarmTask,
    escape_xml,
)

T = TypeVar("T")

INITIAL_LAUNCH_LIMIT = 5
INITIAL_LAUNCH_INTERVAL_MS = 0.7
RATE_LIMIT_RETRY_BASE_MS = 3.0
RATE_LIMIT_RETRY_FACTOR = 2.0
RATE_LIMIT_CAPACITY_SHRINK_INTERVAL_MS = 2.0
RATE_LIMIT_CAPACITY_RECOVERY_INTERVAL_MS = 3 * 60.0
RATE_LIMIT_SUSPENDED_REASON = "Provider rate limit; subagent requeued for retry."

AGENT_SWARM_MAX_CONCURRENCY_ENV = "MEM20KIMI_SWARM_MAX_CONCURRENCY"


@dataclass
class _TaskState:
    index: int
    task: SessionSwarmTask
    agentId: Optional[str] = None
    retryAgentId: Optional[str] = None
    retryCount: int = 0
    retryReadyAt: float = 0.0
    started: bool = False


@dataclass
class AgentRunAttemptOptions:
    parentToolCallId: str = ""
    prompt: str = ""
    description: str = ""
    swarmIndex: Optional[int] = None
    runInBackground: bool = False
    signal: Optional[asyncio.Event] = None
    onReady: Optional[Callable[[], None]] = None
    suppressRateLimitFailureEvent: bool = True


@dataclass
class AgentSpawnAttemptOptions(AgentRunAttemptOptions):
    profileName: str = "subagent"
    swarmItem: Optional[str] = None
    plan: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentRunAttemptHandle:
    agentId: str
    profileName: str
    completion: "asyncio.Future[Any]"


class AgentRunBatchLauncher:
    """Injectable sub-agent operations. Each op returns an awaited handle whose
    completion future carries the sub-agent result (or raises to signal
    failure / a provider rate limit)."""

    def __init__(
        self,
        spawn: Optional[Callable[[AgentSpawnAttemptOptions], Any]] = None,
        resume: Optional[Callable[[str, AgentRunAttemptOptions], Any]] = None,
        retry: Optional[Callable[[str, AgentRunAttemptOptions], Any]] = None,
        suspended: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> None:
        self.spawn = spawn or _unsupported("spawn")
        self.resume = resume or _unsupported("resume")
        self.retry = retry or _unsupported("retry")
        self.suspended = suspended


async def _unsupported(name: str):
    raise RuntimeError(f"AgentRunBatchLauncher.{name} is not configured.")


@dataclass
class AgentRunSuspendedEvent:
    task: SessionSwarmTask
    agentId: str
    reason: str


@dataclass
class _RateLimitedOutcome:
    type: Literal["rate_limited"] = "rate_limited"
    agentId: Optional[str] = None
    error: str = ""


class _InterruptedAttempt(Exception):
    """Raised internally when an attempt is interrupted before completion.

    timed_out=True means the per-task timeout fired; otherwise the attempt was
    aborted (user cancellation or an abort signal on the task/batch).
    """

    def __init__(self, timed_out: bool, user_cancelled: bool) -> None:
        super().__init__("interrupted")
        self.timed_out = timed_out
        self.user_cancelled = user_cancelled
        self.agentId: Optional[str] = None


async def _sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


AttemptOutcome = Union[SessionSwarmRunResult, _RateLimitedOutcome]


@dataclass(eq=False)
class _ActiveAttempt:
    state: _TaskState
    controller: asyncio.Event
    cleanup: Callable[[], None] = lambda: None
    ready: bool = False
    timedOut: bool = False
    run_task: Optional[asyncio.Task] = None


def _retry_timeout(attempt: int, base: float | None = None) -> float:
    if base is None:
        base = RATE_LIMIT_RETRY_BASE_MS
    if attempt < 1:
        attempt = 1
    return base * (RATE_LIMIT_RETRY_FACTOR ** (attempt - 1))


def resolve_swarm_max_concurrency(env: Optional[dict[str, str]] = None) -> Optional[int]:
    raw = (env or {}).get(AGENT_SWARM_MAX_CONCURRENCY_ENV)
    if raw is None or str(raw).strip() == "":
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{AGENT_SWARM_MAX_CONCURRENCY_ENV} must be a positive integer, got {raw!r}")
    if value <= 0:
        raise ValueError(f"{AGENT_SWARM_MAX_CONCURRENCY_ENV} must be a positive integer, got {raw!r}")
    return value


class AgentRunBatch:
    """Run a list of swarm tasks, honoring the Kimi scheduling policy.

    The launcher is fully injectable, so the scheduler is deterministic in tests
    (no real sub-agents or network calls are required).
    """

    def __init__(
        self,
        launcher: AgentRunBatchLauncher,
        tasks: list[SessionSwarmTask],
        max_concurrency: Optional[int] = None,
    ) -> None:
        self._launcher = launcher
        self._max_concurrency = max_concurrency
        self._states: list[_TaskState] = []
        self._pending: list[_TaskState] = []
        self._results: list[Optional[SessionSwarmRunResult]] = []
        for index, task in enumerate(tasks):
            st = _TaskState(index=index, task=task)
            self._states.append(st)
            self._pending.append(st)
            self._results.append(None)

        self._noop = asyncio.Event()
        self._noop.clear()
        self._batch_signal: Optional[asyncio.Event] = None
        for task in tasks:
            if task.signal is not None:
                self._batch_signal = task.signal
                break

        self._active: set[_ActiveAttempt] = set()
        self._controller = asyncio.Event()
        self._controller.clear()
        self._normal_launch_count = 0
        self._normal_launch_future: Optional[asyncio.Task] = None
        self._rate_limit_launch_future: Optional[asyncio.Task] = None
        self._resolve: Optional[Callable[[list[SessionSwarmRunResult]], None]] = None
        self._reject: Optional[Callable[[BaseException], None]] = None
        self._finished = False
        self._started = False
        self._rate_limit_mode = False
        self._started_success_count = 0
        self._rate_limit_capacity = 1
        self._last_rate_limit_at: Optional[float] = None
        self._last_capacity_shrink_at: Optional[float] = None
        self._last_capacity_recovery_at: Optional[float] = None
        self._global_retry_interval_ms = RATE_LIMIT_RETRY_BASE_MS
        self._next_rate_limit_launch_at = 0.0

    # ---------------------------------------------------------------- public
    async def run(self) -> list[SessionSwarmRunResult]:
        if self._started:
            raise RuntimeError("AgentRunBatch.run() can only be called once.")
        self._started = True
        return await self._run_impl()

    async def _run_impl(self) -> list[SessionSwarmRunResult]:
        fut = asyncio.get_running_loop().create_future()
        outer: dict[str, Any] = {}

        def resolve(results: list[SessionSwarmRunResult]) -> None:
            if not fut.done():
                fut.set_result(results)

        def reject(err: BaseException) -> None:
            if not fut.done():
                fut.set_exception(err)

        self._resolve = resolve
        self._reject = reject

        if not self._states:
            self.finish([])
            return await fut

        self.schedule()
        try:
            result = await fut
            return result
        finally:
            self.cleanup()

    # ------------------------------------------------------------- scheduling
    def schedule(self) -> None:
        if self._finished:
            return
        if self._finish_if_complete():
            return
        if self._controller.is_set():
            return
        if self._rate_limit_mode:
            self._schedule_rate_limit_launch()
        else:
            self._schedule_normal_launch()

    def _schedule_normal_launch(self) -> None:
        while (
            self._normal_launch_count < INITIAL_LAUNCH_LIMIT
            and self._pending
            and not self._rate_limit_mode
            and not self._at_concurrency_limit()
        ):
            self._start_attempt(self._pending.pop(0))
            self._normal_launch_count += 1

        if (
            not self._pending
            or self._rate_limit_mode
            or self._normal_launch_future is not None
            or self._at_concurrency_limit()
        ):
            return

        async def _normal_launch():
            await asyncio.sleep(INITIAL_LAUNCH_INTERVAL_MS)
            self._normal_launch_future = None
            if self._finished or self._rate_limit_mode or not self._pending:
                return
            if self._at_concurrency_limit():
                return
            self._start_attempt(self._pending.pop(0))
            self._normal_launch_count += 1
            self.schedule()

        self._normal_launch_future = asyncio.create_task(_normal_launch())

    def _at_concurrency_limit(self) -> bool:
        return self._max_concurrency is not None and len(self._active) >= self._max_concurrency

    def _schedule_rate_limit_launch(self) -> None:
        self._clear_rate_limit_timer()
        if not self._pending:
            return
        now = self._now()
        self._recover_rate_limit_capacity(now)
        if len(self._active) >= self._rate_limit_capacity:
            self._schedule_rate_limit_wakeup(self._next_capacity_recovery_at(), now)
            return
        next_allowed_at = max(self._next_rate_limit_launch_at, self._next_pending_ready_at())
        next_wakeup_at = min(next_allowed_at, self._next_capacity_recovery_at())
        if next_wakeup_at > now:
            self._schedule_rate_limit_wakeup(next_wakeup_at, now)
            return
        pending_index = next(
            (i for i, s in enumerate(self._pending) if s.retryReadyAt <= now),
            -1,
        )
        if pending_index == -1:
            return
        state = self._pending.pop(pending_index)
        self._start_attempt(state)
        self._next_rate_limit_launch_at = now + self._global_retry_interval_ms
        self._schedule_next_rate_limit_wakeup(now)

    def _start_attempt(self, state: _TaskState) -> None:
        if self._finished or self._controller.is_set():
            return
        attempt = _ActiveAttempt(state=state, controller=asyncio.Event())
        attempt.cleanup = self._link_attempt_signals(attempt, state.task)
        self._active.add(attempt)
        task = asyncio.create_task(self._run_attempt(attempt))
        attempt.run_task = task

        def _outcome(inner_task: asyncio.Task) -> None:
            if inner_task.cancelled():
                exc = asyncio.CancelledError()
                self._handle_attempt_error(attempt, exc)
                return
            exc = inner_task.exception()
            if exc is not None:
                self._handle_attempt_error(attempt, exc)
            else:
                outcome = inner_task.result()
                self._handle_attempt_outcome(attempt, outcome)

        task.add_done_callback(_outcome)

    async def _run_attempt(self, attempt: _ActiveAttempt) -> AttemptOutcome:
        task = attempt.state.task
        run_options = AgentRunAttemptOptions(
            parentToolCallId=task.parentToolCallId,
            prompt=task.prompt,
            description=task.description,
            swarmIndex=task.swarmIndex,
            runInBackground=task.runInBackground,
            signal=attempt.controller,
            onReady=lambda: self._mark_attempt_ready(attempt),
        )
        try:
            if attempt.controller.is_set():
                raise _InterruptedAttempt(timed_out=False, user_cancelled=True)
            if attempt.state.retryAgentId is not None:
                handle = await self._launcher.retry(attempt.state.retryAgentId, run_options)
            elif task.kind == "resume":
                handle = await self._launcher.resume(task.resumeAgentId, run_options)
            else:
                spawn_options = AgentSpawnAttemptOptions(
                    profileName=task.profileName,
                    swarmItem=task.swarmItem,
                    plan=task.plan or {},
                    **run_options.__dict__,
                )
                handle = await self._launcher.spawn(spawn_options)
        except Exception as error:
            if isinstance(error, _InterruptedAttempt):
                return self._interrupted_attempt_outcome(attempt, error)
            return self._failed_attempt_outcome(attempt, error)

        attempt.state.agentId = handle.agentId
        completion = asyncio.ensure_future(handle.completion)
        signal_waiter = asyncio.ensure_future(attempt.controller.wait())
        timeout_waiter: Optional[asyncio.Future] = None
        if task.timeout is not None and task.timeout > 0:
            timeout_waiter = asyncio.ensure_future(_sleep(task.timeout))
        try:
            contenders = {completion, signal_waiter}
            if timeout_waiter is not None:
                contenders.add(timeout_waiter)
            done, pending = await asyncio.wait(contenders, return_when=asyncio.FIRST_COMPLETED)
            for fut in pending:
                fut.cancel()
            if completion in done:
                try:
                    result = completion.result()
                except Exception as error:
                    if self._is_rate_limit(error):
                        return _RateLimitedOutcome(
                            agentId=handle.agentId,
                            error=self._attempt_error_message(attempt, error, "failed"),
                        )
                    return self._failed_attempt_outcome(attempt, error)
                return SessionSwarmRunResult(
                    task=task,
                    agentId=handle.agentId,
                    status="completed",
                    result=result.get("result") if isinstance(result, dict) else result,
                    usage=result.get("usage") if isinstance(result, dict) else None,
                    stopReason=result.get("stopReason") if isinstance(result, dict) else None,
                )
            timed_out = timeout_waiter is not None and timeout_waiter in done
            if timed_out:
                attempt.timedOut = True
            raise _InterruptedAttempt(timed_out=timed_out, user_cancelled=not timed_out)
        finally:
            for fut in (signal_waiter, completion):
                if not fut.done():
                    fut.cancel()
            if timeout_waiter is not None and not timeout_waiter.done():
                timeout_waiter.cancel()

    def _interrupted_attempt_outcome(
        self, attempt: _ActiveAttempt, error: "_InterruptedAttempt"
    ) -> SessionSwarmRunResult:
        status: Literal["aborted", "failed"] = "failed" if error.timed_out else "aborted"
        return SessionSwarmRunResult(
            task=attempt.state.task,
            agentId=attempt.state.agentId,
            status=status,
            state="not_started" if attempt.state.agentId is None else "started",
            error=self._attempt_error_message(attempt, error, status),
        )

    def _failed_attempt_outcome(self, attempt: _ActiveAttempt, error: Exception) -> SessionSwarmRunResult:
        aborted = attempt.controller.is_set() and self._is_user_cancellation(error)
        status: Literal["aborted", "failed"] = "aborted" if aborted else "failed"
        return SessionSwarmRunResult(
            task=attempt.state.task,
            agentId=attempt.state.agentId,
            status=status,
            state="not_started" if attempt.state.agentId is None else "started",
            error=self._attempt_error_message(attempt, error, status),
        )

    def _mark_attempt_ready(self, attempt: _ActiveAttempt) -> None:
        if self._finished or attempt.ready or attempt not in self._active:
            return
        attempt.ready = True
        attempt.state.started = True
        if not self._rate_limit_mode:
            self._started_success_count += 1
        if self._rate_limit_mode:
            self._global_retry_interval_ms = RATE_LIMIT_RETRY_BASE_MS
            self._next_rate_limit_launch_at = self._now() + self._global_retry_interval_ms
            self.schedule()

    def _handle_attempt_outcome(self, attempt: _ActiveAttempt, outcome: AttemptOutcome) -> None:
        if not self._release_attempt(attempt):
            return
        if self._finished:
            return
        if isinstance(outcome, SessionSwarmRunResult):
            self._results[attempt.state.index] = outcome
        elif self._is_only_unfinished_task(attempt.state):
            self._results[attempt.state.index] = SessionSwarmRunResult(
                task=attempt.state.task,
                agentId=outcome.agentId,
                status="failed",
                state="started",
                error=outcome.error,
            )
        else:
            self._requeue_rate_limited(attempt, outcome.agentId)
        self.schedule()

    def _handle_attempt_error(self, attempt: _ActiveAttempt, error: BaseException) -> None:
        if not self._release_attempt(attempt):
            return
        if self._finished:
            return
        self._results[attempt.state.index] = SessionSwarmRunResult(
            task=attempt.state.task,
            agentId=attempt.state.agentId,
            status="failed",
            error=self._attempt_error_message(attempt, error, "failed"),
        )
        self.schedule()

    def _release_attempt(self, attempt: _ActiveAttempt) -> bool:
        if attempt not in self._active:
            return False
        self._active.discard(attempt)
        attempt.cleanup()
        return True

    def _requeue_rate_limited(self, attempt: _ActiveAttempt, agentId: Optional[str]) -> None:
        state = attempt.state
        if agentId is not None:
            state.agentId = agentId
            state.retryAgentId = agentId
        if self._launcher.suspended is not None:
            self._launcher.suspended(
                AgentRunSuspendedEvent(task=state.task, agentId=state.agentId or "", reason=RATE_LIMIT_SUSPENDED_REASON)
            )
        now = self._now()
        self._last_rate_limit_at = now
        state.retryCount += 1
        retry_delay = _retry_timeout(max(0, state.retryCount - 1))
        state.retryReadyAt = now + retry_delay
        self._pending.insert(0, state)
        self._enter_rate_limit_mode(now)

        if not attempt.ready:
            self._global_retry_interval_ms = max(self._global_retry_interval_ms * 2, retry_delay)
            self._next_rate_limit_launch_at = max(self._next_rate_limit_launch_at, now + self._global_retry_interval_ms)
        else:
            self._next_rate_limit_launch_at = max(
                self._next_rate_limit_launch_at, now + RATE_LIMIT_RETRY_BASE_MS
            )

    def _enter_rate_limit_mode(self, now: float) -> None:
        if not self._rate_limit_mode:
            self._rate_limit_mode = True
            self._clear_normal_timer()
            self._rate_limit_capacity = max(1, self._started_success_count)
            self._next_rate_limit_launch_at = max(self._next_rate_limit_launch_at, now + RATE_LIMIT_RETRY_BASE_MS)
            self._shrink_rate_limit_capacity(now, force=True)
            return
        self._shrink_rate_limit_capacity(now, force=False)

    def _shrink_rate_limit_capacity(self, now: float, force: bool) -> None:
        if (
            not force
            and self._last_capacity_shrink_at is not None
            and now - self._last_capacity_shrink_at < RATE_LIMIT_CAPACITY_SHRINK_INTERVAL_MS
        ):
            return
        self._rate_limit_capacity = max(1, self._rate_limit_capacity - 1)
        self._last_capacity_shrink_at = now

    def _recover_rate_limit_capacity(self, now: float) -> None:
        if self._next_capacity_recovery_at() > now:
            return
        self._rate_limit_capacity += 1
        self._last_capacity_recovery_at = now
        self._next_rate_limit_launch_at = min(self._next_rate_limit_launch_at, now)

    def _next_capacity_recovery_at(self) -> float:
        if not self._pending or self._last_rate_limit_at is None:
            return math.inf
        latest = max(self._last_rate_limit_at, self._last_capacity_recovery_at or 0.0)
        return latest + RATE_LIMIT_CAPACITY_RECOVERY_INTERVAL_MS

    def _schedule_rate_limit_wakeup(self, wakeup_at: float, now: float) -> None:
        if not math.isfinite(wakeup_at) or wakeup_at <= now:
            return
        async def _wakeup():
            await asyncio.sleep(wakeup_at - now)
            self._rate_limit_launch_future = None
            self.schedule()

        self._rate_limit_launch_future = asyncio.create_task(_wakeup())

    def _schedule_next_rate_limit_wakeup(self, now: float) -> None:
        if not self._pending:
            return
        next_wakeup_at = (
            self._next_capacity_recovery_at()
            if len(self._active) >= self._rate_limit_capacity
            else min(
                max(self._next_rate_limit_launch_at, self._next_pending_ready_at()),
                self._next_capacity_recovery_at(),
            )
        )
        self._schedule_rate_limit_wakeup(next_wakeup_at, now)

    def _next_pending_ready_at(self) -> float:
        return min((s.retryReadyAt for s in self._pending), default=math.inf)

    def _finish_if_complete(self) -> bool:
        if all(r is not None for r in self._results):
            self.finish(self._results)
            return True
        return False

    def _is_only_unfinished_task(self, state: _TaskState) -> bool:
        return all(r is not None for i, r in enumerate(self._results) if i != state.index)

    # ----------------------------------------------------------------- finish
    def finish_with_user_cancellation(self) -> None:
        if self._finished:
            return
        self.finish(
            [
                self._results[s.index]
                if self._results[s.index] is not None
                else SessionSwarmRunResult(
                    task=s.task,
                    agentId=s.agentId,
                    status="aborted",
                    state="started" if (s.started or s.agentId is not None) else "not_started",
                    error=(
                        "The user manually interrupted this subagent batch before this subagent "
                        "finished."
                        if (s.started or s.agentId is not None)
                        else "The user manually interrupted this subagent batch before this subagent "
                        "was started."
                    ),
                )
                for s in self._states
            ]
        )

    def finish(self, results: list[Optional[SessionSwarmRunResult]]) -> None:
        if self._finished:
            return
        self._finished = True
        self.cleanup()
        if self._resolve is not None:
            self._resolve([r for r in results if r is not None])

    def fail(self, error: BaseException) -> None:
        if self._finished:
            return
        self._finished = True
        self.cleanup()
        if self._reject is not None:
            self._reject(error)

    def cleanup(self) -> None:
        self._clear_normal_timer()
        self._clear_rate_limit_timer()
        for attempt in self._active:
            attempt.cleanup()
            if attempt.run_task is not None and not attempt.run_task.done():
                attempt.run_task.cancel()
        self._active.clear()

    # ---------------------------------------------------------------- signals
    def _link_attempt_signals(self, attempt: _ActiveAttempt, task: SessionSwarmTask) -> Callable[[], None]:
        abort_from_batch = lambda: attempt.controller.set()
        abort_from_task = lambda: task.signal.set() if task.signal is not None else None
        timeout: Optional[asyncio.Task] = None

        if task.timeout is not None and task.timeout > 0:
            async def _timeout():
                await asyncio.sleep(task.timeout)
                attempt.timedOut = True
                attempt.controller.set()

            timeout = asyncio.create_task(_timeout())

        if self._controller.is_set():
            abort_from_batch()
        elif task.signal is not None and task.signal.is_set():
            abort_from_task()
        else:
            if not self._controller.is_set():
                self._controller_set_listener(attempt, abort_from_batch)
            if task.signal is not None and not task.signal.is_set():
                task.signal.add_done_callback(lambda _: abort_from_task())

        def _cleanup():
            if timeout is not None:
                timeout.cancel()
            self._controller_set_listener(attempt, abort_from_batch, remove=True)
            if task.signal is not None:
                # listeners are best-effort; no removal needed for asyncio.Event
                pass

        return _cleanup

    def _controller_set_listener(self, attempt: _ActiveAttempt, cb: Callable[[], None], remove: bool = False) -> None:
        # Simpler: poll-free approach not needed — asyncio.Event has no cleanup hooks.
        pass

    # ------------------------------------------------------------------ utils
    def _attempt_error_message(self, attempt: _ActiveAttempt, error: BaseException, status: str) -> str:
        if attempt.timedOut and attempt.state.task.timeout is not None:
            return "Subagent timed out."
        if status == "aborted":
            return "The user manually interrupted this subagent batch."
        return str(error) if isinstance(error, Exception) else str(error)

    def _is_rate_limit(self, error: BaseException) -> bool:
        message = str(error).lower()
        return ("rate" in message and "limit" in message) or "429" in message or "throttl" in str(error).lower()

    def _is_user_cancellation(self, error: BaseException) -> bool:
        return isinstance(error, asyncio.CancelledError) or "cancelled" in str(error).lower()

    def _clear_normal_timer(self) -> None:
        if self._normal_launch_future is not None:
            self._normal_launch_future.cancel()
            self._normal_launch_future = None

    def _clear_rate_limit_timer(self) -> None:
        if self._rate_limit_launch_future is not None:
            self._rate_limit_launch_future.cancel()
            self._rate_limit_launch_future = None

    def _now(self) -> float:
        import time

        return time.monotonic()