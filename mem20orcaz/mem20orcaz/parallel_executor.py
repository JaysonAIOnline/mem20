"""Parallel branch execution for mem20orcaz.

Pure-stdlib port of OrKa's ParallelExecutor: runs a set of agents concurrently
(gated by the ConcurrencyManager) and records results into the shared context,
so fork branches can genuinely run in parallel without any model dependency.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from .concurrency import ConcurrencyManager
from .response_builder import ResponseBuilder


class ParallelExecutor:
    """Executes a list of agents concurrently with bounded concurrency."""

    def __init__(self, max_concurrency: int = 10, fork_group_manager: Any = None,
                 memory_logger: Any = None, concurrency_manager: Any = None) -> None:
        self.max_concurrency = int(max_concurrency)
        self.concurrency_manager = concurrency_manager or ConcurrencyManager(
            max_concurrency=self.max_concurrency)
        self.fork_group_manager = fork_group_manager
        self.memory_logger = memory_logger

    async def execute_parallel(self, agents: List[str], context: Dict[str, Any],
                               agent_runner: Any, fork_group_id: Optional[str] = None,
                               timeout_seconds: Optional[float] = None) -> Dict[str, Any]:
        agents = [str(a) for a in (agents or []) if a]
        results: Dict[str, Any] = {}
        errors: Dict[str, Any] = {}

        async def _one(agent_id: str) -> None:
            try:
                resp = await self.concurrency_manager.run_with_timeout(
                    asyncio.wait_for(
                        agent_runner.run(agent_id, {**context, "agent_id": agent_id}),
                        timeout=timeout_seconds or 120,
                    ),
                    timeout=timeout_seconds or 120,
                )
                if isinstance(resp, dict):
                    resp.setdefault("agent_id", agent_id)
                results[agent_id] = resp
            except Exception as error:
                errors[agent_id] = ResponseBuilder.create_error_response(
                    error, agent_id=str(agent_id), trace_id=context.get("trace_id"))

        if agents:
            await asyncio.gather(*(_one(a) for a in agents))

        # fold results back into the shared previous-outputs map
        context_manager = context.get("_context_manager")
        if context_manager is not None:
            for agent_id, resp in results.items():
                context_manager.update_previous_outputs(agent_id, resp)

        if self.fork_group_manager is not None and fork_group_id:
            for agent_id in agents:
                self.fork_group_manager.mark_agent_done(fork_group_id, agent_id)

        return {"results": results, "errors": errors,
                "completed_count": len(results), "failed_count": len(errors),
                "fork_group_id": fork_group_id}

    async def execute(self, agents: List[str], context: Dict[str, Any],
                      agent_runner: Any) -> Dict[str, Any]:
        return await self.execute_parallel(agents, context, agent_runner)

    def shutdown(self) -> None:
        self.concurrency_manager.shutdown()