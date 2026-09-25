"""mem20langz — native mem20 graph substrate absorption.

Stateful, multi-actor application graphs: StateGraph + Pregel runtime,
checkpointing (InMemorySaver), streaming (values/updates), interrupts
(human-in-the-loop), and Send-based dynamic fan-out. Zero mem20 chain substrate/mem20 graph substrate
dependency.
"""

from ._runtime import Pregel
from .checkpointer import BaseCheckpointSaver, InMemorySaver
from .graph import StateGraph
from .types import (
    Command,
    END,
    GraphRecursionError,
    InvalidUpdateError,
    LangzError,
    Send,
    START,
    interrupt,
)
from .state import Message, add_messages

__all__ = [
    "Command",
    "END",
    "GraphRecursionError",
    "InvalidUpdateError",
    "InMemorySaver",
    "BaseCheckpointSaver",
    "LangzError",
    "Message",
    "Pregel",
    "Send",
    "START",
    "StateGraph",
    "add_messages",
    "interrupt",
]

__version__ = "0.1.0"