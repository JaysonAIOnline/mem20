"""Hermetic tests for the mem20kimiz AgentRunBatch scheduler."""

import asyncio
import unittest
from dataclasses import dataclass, field

from mem20kimiz.batch import (
    AgentRunAttemptHandle,
    AgentRunBatch,
    AgentRunBatchLauncher,
    AgentRunSuspendedEvent,
    INITIAL_LAUNCH_INTERVAL_MS,
    RATE_LIMIT_RETRY_BASE_MS,
)
from mem20kimiz.types import SessionSwarmSpawnTask, SessionSwarmResumeTask

class RateLimitError(Exception):
    pass


class CancelError(Exception):
    pass


@dataclass
class _FakeBackend:
    delay: float = 0.01
    fail_at: list[str] = field(default_factory=list)
    rate_limit_at: list[str] = field(default_factory=list)
    spawns: list[str] = field(default_factory=list)
    resumes: list[str] = field(default_factory=list)
    retries: list[str] = field(default_factory=list)
    suspended: list[AgentRunSuspendedEvent] = field(default_factory=list)
    _counter: int = 0

    def incr(self) -> str:
        self._counter += 1
        return f"agent-{self._counter}"

    def _complete(self, agent_id: str) -> asyncio.Future:
        loop = asyncio.get_running_loop()
        fut = loop.create_future()

        async def work() -> None:
            if agent_id in self.rate_limit_at:
                self.rate_limit_at.remove(agent_id)
                if not fut.cancelled():
                    fut.set_exception(RateLimitError("Provider rate limit reached"))
            elif agent_id in self.fail_at:
                self.fail_at.remove(agent_id)
                if not fut.cancelled():
                    fut.set_exception(RuntimeError("worker crashed"))
            else:
                await asyncio.sleep(self.delay)
                if not fut.cancelled():
                    fut.set_result({"result": f"output:{agent_id}", "stopReason": None})

        worker = asyncio.create_task(work())
        fut.add_done_callback(lambda f, wt=worker: wt.cancel())
        return fut

    async def spawn(self, opts):
        aid = self.incr()
        profile = opts.profileName
        self.spawns.append(aid)
        if opts.onReady is not None:
            opts.onReady()
        return AgentRunAttemptHandle(agentId=aid, profileName=profile, completion=self._complete(aid))

    async def resume(self, agent_id: str, opts):
        self.resumes.append(agent_id)
        return AgentRunAttemptHandle(agentId=agent_id, profileName="subagent", completion=self._complete(agent_id))

    async def retry(self, agent_id: str, opts):
        self.retries.append(agent_id)
        return AgentRunAttemptHandle(agentId=agent_id, profileName="subagent", completion=self._complete(agent_id))

    def on_suspended(self, event: AgentRunSuspendedEvent) -> None:
        self.suspended.append(event)


def _spawn(prompt: str, timeout=None, signal=None) -> SessionSwarmSpawnTask:
    return SessionSwarmSpawnTask(kind="spawn", prompt=prompt, timeout=timeout, signal=signal)


def _resume(agent_id: str) -> SessionSwarmResumeTask:
    return SessionSwarmResumeTask(kind="resume", resumeAgentId=agent_id)


def _run(batch: AgentRunBatch) -> any:
    return asyncio.get_event_loop().run_until_complete(batch.run())


class BatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self) -> None:
        self.loop.close()
        asyncio.set_event_loop(None)

    def _batch(self, backend: _FakeBackend, tasks, max_concurrency=None):
        launcher = AgentRunBatchLauncher(
            spawn=backend.spawn,
            resume=backend.resume,
            retry=backend.retry,
            suspended=backend.on_suspended,
        )
        return AgentRunBatch(launcher, tasks, max_concurrency=max_concurrency)

    def test_all_completed_ordered(self):
        backend = _FakeBackend()
        batch = self._batch(backend, [_spawn("a"), _spawn("b"), _spawn("c")], max_concurrency=1)
        results = self.loop.run_until_complete(batch.run())
        self.assertEqual([r.status for r in results], ["completed", "completed", "completed"])
        self.assertEqual(backend.spawns, ["agent-1", "agent-2", "agent-3"])
        self.assertTrue(backend.spawns[0] in results[0].result)

    def test_empty_batch_finishes_empty(self):
        backend = _FakeBackend()
        results = self.loop.run_until_complete(self._batch(backend, []).run())
        self.assertEqual(results, [])

    def test_resume_uses_resume_path(self):
        backend = _FakeBackend()
        batch = self._batch(backend, [_resume("agent-9")])
        results = self.loop.run_until_complete(batch.run())
        self.assertEqual(backend.resumes, ["agent-9"])
        self.assertEqual(results[0].status, "completed")

    def test_failure_is_failed(self):
        backend = _FakeBackend(fail_at=["agent-1"])
        batch = self._batch(backend, [_spawn("a"), _spawn("b")], max_concurrency=1)
        results = self.loop.run_until_complete(batch.run())
        statuses = sorted(r.status for r in results)
        self.assertEqual(statuses, ["completed", "failed"])

    def test_rate_limit_then_retry_succeeds(self):
        backend = _FakeBackend(rate_limit_at=["agent-1"])
        batch = self._batch(backend, [_spawn("a"), _spawn("b")])
        results = self.loop.run_until_complete(batch.run())
        self.assertEqual([r.status for r in results], ["completed", "completed"])
        self.assertEqual(backend.retries, ["agent-1"])
        self.assertEqual(len(backend.suspended), 1)
        self.assertEqual(backend.suspended[0].agentId, "agent-1")
        self.assertIn("rate limit", backend.suspended[0].reason.lower())

    def test_single_task_rate_limit_fails_if_only_unfinished(self):
        backend = _FakeBackend(rate_limit_at=["agent-1"])
        batch = self._batch(backend, [_spawn("a")])
        results = self.loop.run_until_complete(batch.run())
        self.assertEqual(results[0].status, "failed")
        self.assertIn("rate limit", results[0].error)

    def test_timeout_marks_timed_out_failed(self):
        backend = _FakeBackend(delay=2.0)
        batch = self._batch(backend, [_spawn("slow", timeout=0.01)])
        results = self.loop.run_until_complete(batch.run())
        self.assertEqual(results[0].status, "failed")
        self.assertIn("timed out", results[0].error)

    def test_batch_run_once_only(self):
        backend = _FakeBackend()
        batch = self._batch(backend, [_spawn("a")])
        self.loop.run_until_complete(batch.run())
        with self.assertRaises(RuntimeError):
            self.loop.run_until_complete(batch.run())

    def test_finish_with_user_cancellation(self):
        backend = _FakeBackend(delay=10.0)
        batch = self._batch(backend, [_spawn("slow1"), _spawn("slow2")])

        async def scenario():
            runner = asyncio.create_task(batch.run())
            await asyncio.sleep(0.05)
            batch.finish_with_user_cancellation()
            return await runner

        results = self.loop.run_until_complete(scenario())
        self.assertTrue(all(r.status == "aborted" for r in results))


class RetryTimingTests(unittest.TestCase):
    def test_retry_timeout_growth(self):
        from mem20kimiz.batch import _retry_timeout

        base = 3.0
        self.assertAlmostEqual(_retry_timeout(0, base), 3.0)
        self.assertAlmostEqual(_retry_timeout(1, base), 3.0)
        self.assertAlmostEqual(_retry_timeout(2, base), 6.0)
        self.assertAlmostEqual(_retry_timeout(3, base), 12.0)

    def test_resolve_max_concurrency_env(self):
        from mem20kimiz.batch import resolve_swarm_max_concurrency

        self.assertEqual(resolve_swarm_max_concurrency({"MEM20KIMI_SWARM_MAX_CONCURRENCY": "4"}), 4)
        self.assertIsNone(resolve_swarm_max_concurrency({}))
        self.assertIsNone(resolve_swarm_max_concurrency({"MEM20KIMI_SWARM_MAX_CONCURRENCY": ""}))
        with self.assertRaises(ValueError):
            resolve_swarm_max_concurrency({"MEM20KIMI_SWARM_MAX_CONCURRENCY": "0"})
        with self.assertRaises(ValueError):
            resolve_swarm_max_concurrency({"MEM20KIMI_SWARM_MAX_CONCURRENCY": "x"})


if __name__ == "__main__":
    unittest.main()