"""UE Connection primitives — native absorption of AutoUE UEConnection."""

from __future__ import annotations

import asyncio
import json
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import websockets
from websockets.asyncio.client import ClientConnection

from .config import DEFAULT_CONFIG


@dataclass
class UECommand:
    """Command to send to UE."""
    command_type: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])


@dataclass
class UEResponse:
    """Response from UE."""
    request_id: str
    success: bool
    data: Any = None
    error: Optional[str] = None


class UEConnection:
    """Unreal Engine WebSocket connection — absorption of AutoUE UEConnection."""

    def __init__(self, host: str = None, port: int = None):
        self.host = host or DEFAULT_CONFIG.ue_host
        self.port = port or DEFAULT_CONFIG.ue_port
        self.websocket: Optional[ClientConnection] = None
        self.pending_requests: Dict[str, asyncio.Future] = {}
        self.message_handlers: Dict[str, Callable] = {}
        self._running = False

    async def connect(self) -> bool:
        """Connect to UE via WebSocket."""
        try:
            uri = f"ws://{self.host}:{self.port}"
            self.websocket = await websockets.connect(uri)
            self._running = True
            asyncio.create_task(self._receive_loop())
            return True
        except Exception as e:
            return False

    async def disconnect(self):
        """Disconnect from UE."""
        self._running = False
        if self.websocket:
            await self.websocket.close()
            self.websocket = None

    async def send_command(self, command: UECommand) -> UEResponse:
        """Send command and wait for response."""
        if not self.websocket:
            return UEResponse(request_id=command.request_id, success=False, error="Not connected")

        future = asyncio.get_running_loop().create_future()
        self.pending_requests[command.request_id] = future

        try:
            await self.websocket.send(json.dumps({
                "type": command.command_type,
                "request_id": command.request_id,
                "parameters": command.parameters,
            }))
        except Exception as e:
            self.pending_requests.pop(command.request_id, None)
            return UEResponse(request_id=command.request_id, success=False, error=str(e))

        try:
            response_data = await asyncio.wait_for(future, timeout=30.0)
            return UEResponse(
                request_id=command.request_id,
                success=response_data.get("success", False),
                data=response_data.get("data"),
                error=response_data.get("error"),
            )
        except asyncio.TimeoutError:
            self.pending_requests.pop(command.request_id, None)
            return UEResponse(request_id=command.request_id, success=False, error="Timeout")

    async def _receive_loop(self):
        """Receive messages from UE."""
        try:
            async for message in self.websocket:
                data = json.loads(message)
                request_id = data.get("request_id")
                if request_id in self.pending_requests:
                    future = self.pending_requests.pop(request_id)
                    if not future.done():
                        future.set_result(data)
                else:
                    # Broadcast message
                    msg_type = data.get("type")
                    if msg_type in self.message_handlers:
                        await self.message_handlers[msg_type](data)
        except Exception:
            self._running = False

    def register_handler(self, msg_type: str, handler: Callable):
        """Register message handler."""
        self.message_handlers[msg_type] = handler

    # High-level commands
    async def get_actor_info(self, actor_path: str) -> UEResponse:
        return await self.send_command(UECommand("get_actor_info", {"actor_path": actor_path}))

    async def set_actor_transform(self, actor_path: str, location: List[float] = None,
                                  rotation: List[float] = None, scale: List[float] = None) -> UEResponse:
        params = {"actor_path": actor_path}
        if location: params["location"] = location
        if rotation: params["rotation"] = rotation
        if scale: params["scale"] = scale
        return await self.send_command(UECommand("set_actor_transform", params))

    async def spawn_actor(self, class_path: str, location: List[float] = None,
                          rotation: List[float] = None, name: str = None) -> UEResponse:
        params = {"class_path": class_path}
        if location: params["location"] = location
        if rotation: params["rotation"] = rotation
        if name: params["name"] = name
        return await self.send_command(UECommand("spawn_actor", params))

    async def destroy_actor(self, actor_path: str) -> UEResponse:
        return await self.send_command(UECommand("destroy_actor", {"actor_path": actor_path}))

    async def get_level_actors(self, level_path: str = None) -> UEResponse:
        return await self.send_command(UECommand("get_level_actors", {"level_path": level_path}))

    async def execute_console_command(self, command: str) -> UEResponse:
        return await self.send_command(UECommand("execute_console_command", {"command": command}))