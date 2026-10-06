"""FreeStack RM-003 Adaptive Interface Composer."""
from .model import Capability, UserIntent, InterfacePlan, ExecutionMode
from .runtime import InterfaceComposerRuntime, RuntimeConfig

__all__ = [
    "Capability", "UserIntent", "InterfacePlan", "ExecutionMode",
    "InterfaceComposerRuntime", "RuntimeConfig",
]
__version__ = "0.3.0"
