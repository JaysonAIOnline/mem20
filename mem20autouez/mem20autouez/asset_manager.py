"""Asset Manager — native absorption of AutoUE asset pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .config import DEFAULT_CONFIG
from .connection import UECommand


@dataclass
class AssetInfo:
    """Asset metadata."""
    path: str
    asset_type: str
    size_bytes: int = 0
    dependencies: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "AssetInfo":
        """Build AssetInfo from an engine response payload."""
        return AssetInfo(
            path=data.get("path"),
            asset_type=data.get("asset_type", "Unknown"),
            size_bytes=data.get("size_bytes", 0),
            dependencies=list(data.get("dependencies") or []),
            tags=list(data.get("tags") or []),
            metadata=dict(data.get("metadata") or {}),
        )


class AssetManager:
    """Asset management — absorption of AutoUE AssetManager.

    Every operation issues a real command over the WebSocket connection and
    interprets the engine's response. The cache is only populated from engine
    responses, never fabricated.
    """

    def __init__(self, connection: Any, asset_root: str = None):
        self.connection = connection
        self.asset_root = asset_root or DEFAULT_CONFIG.asset_root
        self.asset_cache: Dict[str, AssetInfo] = {}

    async def list_assets(self, path: str = None, asset_type: str = None) -> List[AssetInfo]:
        """List assets in path."""
        params: Dict[str, Any] = {}
        if path:
            params["path"] = path
        if asset_type:
            params["asset_type"] = asset_type
        resp = await self.connection.send_command(UECommand("list_assets", params))
        if not resp.success:
            return []
        assets = [AssetInfo.from_dict(item) for item in (resp.data or [])]
        for info in assets:
            if info.path:
                self.asset_cache[info.path] = info
        return assets

    async def get_asset_info(self, asset_path: str) -> Optional[AssetInfo]:
        """Get asset info."""
        if asset_path in self.asset_cache:
            return self.asset_cache[asset_path]
        resp = await self.connection.send_command(UECommand("get_asset_info", {"asset_path": asset_path}))
        if not resp.success or not resp.data:
            return None
        info = AssetInfo.from_dict(resp.data)
        self.asset_cache[asset_path] = info
        return info

    async def import_asset(self, source_path: str, destination_path: str,
                           asset_type: str = "Auto") -> bool:
        """Import asset from file system."""
        resp = await self.connection.send_command(UECommand("import_asset", {
            "source_path": source_path,
            "destination_path": destination_path,
            "asset_type": asset_type,
        }))
        return resp.success

    async def export_asset(self, asset_path: str, destination_path: str) -> bool:
        """Export asset to file system."""
        resp = await self.connection.send_command(UECommand("export_asset", {
            "asset_path": asset_path,
            "destination_path": destination_path,
        }))
        return resp.success

    async def delete_asset(self, asset_path: str) -> bool:
        """Delete asset."""
        resp = await self.connection.send_command(UECommand("delete_asset", {"asset_path": asset_path}))
        if resp.success:
            self.asset_cache.pop(asset_path, None)
        return resp.success

    async def find_referencers(self, asset_path: str) -> List[str]:
        """Find assets referencing this asset."""
        resp = await self.connection.send_command(UECommand("find_referencers", {"asset_path": asset_path}))
        if not resp.success:
            return []
        return list(resp.data or [])

    async def bulk_rename(self, old_pattern: str, new_pattern: str) -> int:
        """Bulk rename assets."""
        resp = await self.connection.send_command(UECommand("bulk_rename", {
            "old_pattern": old_pattern,
            "new_pattern": new_pattern,
        }))
        if not resp.success:
            return 0
        try:
            return int(resp.data or 0)
        except (TypeError, ValueError):
            return 0

    async def validate_assets(self, paths: List[str]) -> Dict[str, List[str]]:
        """Validate assets."""
        resp = await self.connection.send_command(UECommand("validate_assets", {"paths": paths}))
        if not resp.success:
            return {"valid": [], "invalid": []}
        data = resp.data or {}
        return {
            "valid": list(data.get("valid") or []),
            "invalid": list(data.get("invalid") or []),
        }