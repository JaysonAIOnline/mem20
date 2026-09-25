"""Level Streamer — native absorption of AutoUE level streaming."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .connection import UECommand


@dataclass
class StreamingLevel:
    """Streaming level info."""
    package_name: str
    level_name: str
    is_loaded: bool = False
    is_visible: bool = False
    should_block_on_load: bool = True
    location: tuple = (0.0, 0.0, 0.0)
    rotation: tuple = (0.0, 0.0, 0.0)
    scale: tuple = (1.0, 1.0, 1.0)


@dataclass
class LevelStreamingConfig:
    """Level streaming configuration."""
    streaming_levels: List[StreamingLevel] = field(default_factory=list)
    default_level: str = "/Game/Levels/MainLevel"
    streaming_distance: float = 50000.0
    unload_distance: float = 60000.0


def _level_from_dict(data: Dict[str, Any]) -> StreamingLevel:
    """Build a StreamingLevel from an engine response payload."""
    return StreamingLevel(
        package_name=data.get("package_name", ""),
        level_name=data.get("level_name", data.get("package_name", "")),
        is_loaded=data.get("is_loaded", False),
        is_visible=data.get("is_visible", False),
        should_block_on_load=data.get("should_block_on_load", True),
        location=tuple(data.get("location") or (0.0, 0.0, 0.0)),
        rotation=tuple(data.get("rotation") or (0.0, 0.0, 0.0)),
        scale=tuple(data.get("scale") or (1.0, 1.0, 1.0)),
    )


def _level_to_dict(level: StreamingLevel) -> Dict[str, Any]:
    """Serialize a StreamingLevel for the engine."""
    return {
        "package_name": level.package_name,
        "level_name": level.level_name,
        "is_loaded": level.is_loaded,
        "is_visible": level.is_visible,
        "should_block_on_load": level.should_block_on_load,
        "location": list(level.location),
        "rotation": list(level.rotation),
        "scale": list(level.scale),
    }


class LevelStreamer:
    """Level streaming — absorption of AutoUE level streaming.

    Every operation issues a real command over the WebSocket connection and
    interprets the engine's response. `loaded_levels` mirrors engine state and
    is only mutated based on engine responses, never fabricated.
    """

    def __init__(self, connection: Any):
        self.connection = connection
        self.config = LevelStreamingConfig()
        self.loaded_levels: Dict[str, StreamingLevel] = {}

    async def load_level(
        self,
        level_name: str,
        make_visible: bool = True,
        should_block: bool = False,
    ) -> bool:
        """Load a streaming level."""
        resp = await self.connection.send_command(UECommand("load_level", {
            "level_name": level_name,
            "make_visible": make_visible,
            "should_block": should_block,
        }))
        if not resp.success:
            return False
        if isinstance(resp.data, dict):
            level = _level_from_dict(resp.data)
            self.loaded_levels[level.level_name or level_name] = level
        else:
            self.loaded_levels[level_name] = StreamingLevel(
                package_name=level_name,
                level_name=level_name,
                is_loaded=True,
                is_visible=make_visible,
                should_block_on_load=should_block,
            )
        return True

    async def unload_level(
        self,
        level_name: str,
    ) -> bool:
        """Unload a streaming level."""
        resp = await self.connection.send_command(UECommand("unload_level", {"level_name": level_name}))
        if not resp.success:
            return False
        self.loaded_levels.pop(level_name, None)
        return True

    async def set_level_visibility(
        self,
        level_name: str,
        visible: bool,
    ) -> bool:
        """Set level visibility."""
        resp = await self.connection.send_command(UECommand("set_level_visibility", {
            "level_name": level_name,
            "visible": visible,
        }))
        if not resp.success:
            return False
        if level_name in self.loaded_levels:
            self.loaded_levels[level_name].is_visible = visible
        return True

    async def get_streaming_levels(self) -> List[StreamingLevel]:
        """Get all streaming levels from the engine."""
        resp = await self.connection.send_command(UECommand("get_streaming_levels", {}))
        if resp.success:
            levels = [_level_from_dict(item) for item in (resp.data or [])]
            self.loaded_levels = {level.level_name: level for level in levels}
            return levels
        return list(self.loaded_levels.values())

    async def set_streaming_distance(self, distance: float) -> bool:
        """Set streaming distance."""
        self.config.streaming_distance = distance
        resp = await self.connection.send_command(UECommand("set_streaming_distance", {"distance": distance}))
        return resp.success

    async def get_level_bounds(self, level_name: str) -> Optional[Tuple[tuple, tuple]]:
        """Get level bounds (min, max) from the engine."""
        resp = await self.connection.send_command(UECommand("get_level_bounds", {"level_name": level_name}))
        if not resp.success:
            return None
        data = resp.data or {}
        minimum = tuple(data.get("min") or (0.0, 0.0, 0.0))
        maximum = tuple(data.get("max") or (0.0, 0.0, 0.0))
        return (minimum, maximum)

    async def is_level_loaded(self, level_name: str) -> bool:
        return level_name in self.loaded_levels