"""mem20kimiz — native Kimi Agent Swarm substrate for mem20.

Absorbs the Kimi Agent Swarm (K2.6 / K3) primitives into a pure-standard-library
Python package with zero dependency baggage: the AgentSwarm fan-out tool, the
rate-limit-aware AgentRunBatch scheduler, the SwarmService mode controller, and
the ordered XML result contract with resume hints.

The scheduler runs sub-agents through a pluggable launcher, so it is fully
hermetic in tests (no LLM calls are made by the core).
"""

from .batch import (
    AgentRunBatch,
    AgentRunBatchLauncher,
    AgentRunAttemptHandle,
    AgentRunAttemptOptions,
    AgentSpawnAttemptOptions,
    AgentRunSuspendedEvent,
    INITIAL_LAUNCH_LIMIT,
    INITIAL_LAUNCH_INTERVAL_MS,
    RATE_LIMIT_RETRY_BASE_MS,
    RATE_LIMIT_RETRY_FACTOR,
    RATE_LIMIT_SUSPENDED_REASON,
)
from .swarm import SwarmService, SwarmModeTrigger
from .tool import AgentSwarmTool, AgentSwarmError, AgentSwarmSpec, AgentSwarmSpecs, SwarmRunResult
from .types import SessionSwarmTask, SessionSwarmSpawnTask, SessionSwarmResumeTask, SessionSwarmRunResult

__all__ = [
    "AgentRunBatch",
    "AgentRunBatchLauncher",
    "AgentRunAttemptHandle",
    "AgentRunAttemptOptions",
    "AgentSpawnAttemptOptions",
    "AgentRunSuspendedEvent",
    "INITIAL_LAUNCH_LIMIT",
    "INITIAL_LAUNCH_INTERVAL_MS",
    "RATE_LIMIT_RETRY_BASE_MS",
    "RATE_LIMIT_RETRY_FACTOR",
    "RATE_LIMIT_SUSPENDED_REASON",
    "SwarmService",
    "SwarmModeTrigger",
    "AgentSwarmTool",
    "AgentSwarmError",
    "AgentSwarmSpec",
    "AgentSwarmSpecs",
    "SwarmRunResult",
    "SessionSwarmTask",
    "SessionSwarmSpawnTask",
    "SessionSwarmResumeTask",
    "SessionSwarmRunResult",
]