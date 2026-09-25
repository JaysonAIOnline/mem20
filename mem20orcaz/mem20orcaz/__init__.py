"""mem20orcaz -- pure-stdlib orchestration absorbed from OrKa (marcosomma/orka-reasoning).

Phase 19 of the mem20 absorption roadmap. Faithful, dependency-free port: the
WorkflowGraph (node/edge descriptors + topological queue), the AgentRegistry
(factory + deterministic agent/node types, lazy DI), the StateManager
(context + memory + trace), the Scaler (fork groups + parallel executor +
concurrency manager) and the Orchestrator (QueueProcessor run loop).
"""

from __future__ import annotations

from .contracts import (Context, Output, ResourceConfig, Trace, MemoryEntry,
                        OrkaResponse, new_trace_id, now_iso, set_current_trace_id)
from .ordering import topological_queue, ordered_initial_queue
from .concurrency import ConcurrencyManager, TimeoutError_
from .graph_api import (NodeDescriptor, EdgeDescriptor, GraphState, GraphAPI,
                        CONTROL_FLOW_TYPES, DEFAULT_BUDGETS)
from .loader import ConfigError, YAMLLoader, yaml_safe_load
from .response_builder import ResponseBuilder
from .fork_group_manager import ForkGroupManager, SimpleForkGroupManager, ForkGroupError
from .memory import (InMemoryMemoryLogger, create_memory_logger,
                     MemoryLoggerError)
from .prompt_rendering import (SimplifiedPromptRenderer, render_template,
                               TemplateSafeObject, extract_template_variables)
from .registry import ResourceRegistry, init_registry
from .agents import (BaseAgent, EchoAgent, CounterAgent, ConstantAgent,
                     LLMAgent, BinaryClassifierAgent, RouterAgent,
                     MemoryAgent, ValidationStructuringAgent, AGENT_CLASSES)
from .nodes import (BaseNode, ForkNode, JoinNode, RouterNode, LoopNode,
                    LoopValidatorNode, FailingNode, FailoverNode,
                    MemoryReaderNode, MemoryWriterNode, RAGNode,
                    GraphScoutAgent, NODE_CLASSES)
from .execution import (ContextManager, ResponseNormalizer, ResponseExtractor,
                        TraceBuilder, MemoryRouter, AgentRunner,
                        ResponseProcessor, QueueProcessor, MetricsCollector)
from .parallel_executor import ParallelExecutor
from .agent_factory import AgentFactory, AgentFactoryError, default_factory
from .orchestrator import OrchestratorBase, Orchestrator

__version__ = "0.9.17+mem20"

__all__ = [
    # contracts
    "Context", "Output", "ResourceConfig", "Trace", "MemoryEntry", "OrkaResponse",
    "new_trace_id", "now_iso", "set_current_trace_id",
    # ordering
    "topological_queue", "ordered_initial_queue",
    # concurrency
    "ConcurrencyManager", "TimeoutError_",
    # graph
    "NodeDescriptor", "EdgeDescriptor", "GraphState", "GraphAPI",
    "CONTROL_FLOW_TYPES", "DEFAULT_BUDGETS",
    # loader
    "ConfigError", "YAMLLoader", "yaml_safe_load",
    # response
    "ResponseBuilder",
    # fork groups
    "ForkGroupManager", "SimpleForkGroupManager", "ForkGroupError",
    # memory
    "InMemoryMemoryLogger", "create_memory_logger", "MemoryLoggerError",
    # prompt rendering
    "SimplifiedPromptRenderer", "render_template", "TemplateSafeObject",
    "extract_template_variables",
    # di
    "ResourceRegistry", "init_registry",
    # agents / nodes
    "BaseAgent", "EchoAgent", "CounterAgent", "ConstantAgent", "LLMAgent",
    "BinaryClassifierAgent", "RouterAgent", "MemoryAgent",
    "ValidationStructuringAgent", "AGENT_CLASSES",
    "BaseNode", "ForkNode", "JoinNode", "RouterNode", "LoopNode",
    "LoopValidatorNode", "FailingNode", "FailoverNode", "MemoryReaderNode",
    "MemoryWriterNode", "RAGNode", "GraphScoutAgent", "NODE_CLASSES",
    # execution
    "ContextManager", "ResponseNormalizer", "ResponseExtractor", "TraceBuilder",
    "MemoryRouter", "AgentRunner", "ResponseProcessor", "QueueProcessor",
    "MetricsCollector",
    # parallel
    "ParallelExecutor",
    # factory
    "AgentFactory", "AgentFactoryError", "default_factory",
    # orchestrator
    "OrchestratorBase", "Orchestrator",
    "__version__",
]