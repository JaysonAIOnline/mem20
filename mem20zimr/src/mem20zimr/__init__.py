"""mem20 RM-002: Zero-Install Microapp Runtime (absorbed from FreeStack RM-002)."""
from .runtime import MicroappRuntime
from .sdk import ZeroInstallClient

__all__ = ["MicroappRuntime", "ZeroInstallClient"]
__version__ = "0.2.0"
