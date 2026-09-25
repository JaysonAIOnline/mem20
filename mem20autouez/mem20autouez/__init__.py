"""mem20autouez — native AutoUE absorption.

Public surface: async WebSocket connection to Unreal Engine, asset pipeline,
blueprint generation, and level streaming primitives.
"""

from .config import AutoUEConfig, DEFAULT_CONFIG
from .connection import UECommand, UEResponse, UEConnection
from .asset_manager import AssetInfo, AssetManager
from .blueprint_builder import (
    BlueprintBuilder,
    BlueprintComponent,
    BlueprintFunction,
    BlueprintProperty,
)
from .level_streamer import LevelStreamer, LevelStreamingConfig, StreamingLevel

__title__ = "mem20autouez"
__version__ = "0.1.0"

__all__ = [
    "AutoUEConfig",
    "DEFAULT_CONFIG",
    "UECommand",
    "UEResponse",
    "UEConnection",
    "AssetInfo",
    "AssetManager",
    "BlueprintBuilder",
    "BlueprintComponent",
    "BlueprintFunction",
    "BlueprintProperty",
    "LevelStreamer",
    "LevelStreamingConfig",
    "StreamingLevel",
    "__title__",
    "__version__",
]