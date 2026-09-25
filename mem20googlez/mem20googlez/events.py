from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .util import datetime_from_iso, utcnow


@dataclass
class Part:
    text: str = ""
    function_call: dict | None = None
    function_response: dict | None = None

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "function_call": self.function_call,
            "function_response": self.function_response,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Part:
        return cls(
            text=str(data.get("text", "")),
            function_call=data.get("function_call"),
            function_response=data.get("function_response"),
        )


@dataclass
class Content:
    role: str
    parts: list[Part] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"role": self.role, "parts": [part.to_dict() for part in self.parts]}

    @classmethod
    def from_dict(cls, data: dict) -> Content:
        return cls(
            role=str(data.get("role", "")),
            parts=[Part.from_dict(part) for part in data.get("parts", [])],
        )


@dataclass
class EventActions:
    transfer_to_agent: str | None = None
    escalate: bool = False
    request_user_input: bool = False
    skip_summarization: bool = False
    state_delta: dict = field(default_factory=dict)
    artifact_delta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "transfer_to_agent": self.transfer_to_agent,
            "escalate": self.escalate,
            "request_user_input": self.request_user_input,
            "skip_summarization": self.skip_summarization,
            "state_delta": self.state_delta,
            "artifact_delta": self.artifact_delta,
        }

    @classmethod
    def from_dict(cls, data: dict) -> EventActions:
        return cls(
            transfer_to_agent=data.get("transfer_to_agent"),
            escalate=bool(data.get("escalate", False)),
            request_user_input=bool(data.get("request_user_input", False)),
            skip_summarization=bool(data.get("skip_summarization", False)),
            state_delta=dict(data.get("state_delta") or {}),
            artifact_delta=dict(data.get("artifact_delta") or {}),
        )


@dataclass
class Event:
    id: str
    invocation_id: str
    author: str
    branch: str = "root"
    timestamp: datetime = field(default_factory=utcnow)
    content: Content | None = None
    actions: EventActions | None = None
    partial: bool = False
    turn_complete: bool = False
    interrupted: bool = False
    error_code: str = ""
    error_message: str = ""

    @classmethod
    def from_model(
        cls,
        invocation_id: str,
        author: str,
        content: str,
        branch: str = "root",
        turn_complete: bool = False,
    ) -> Event:
        return cls(
            id=f"evt_{uuid.uuid4().hex}",
            invocation_id=invocation_id,
            author=author,
            branch=branch,
            content=Content(role=author, parts=[Part(text=content)]),
            turn_complete=turn_complete,
        )

    @classmethod
    def from_tool_call(
        cls,
        invocation_id: str,
        author: str,
        function_name: str,
        arguments: dict,
        branch: str = "root",
        call_id: str | None = None,
    ) -> Event:
        return cls(
            id=f"evt_{uuid.uuid4().hex}",
            invocation_id=invocation_id,
            author=author,
            branch=branch,
            content=Content(
                role=author,
                parts=[
                    Part(
                        function_call={
                            "id": call_id or function_name,
                            "name": function_name,
                            "arguments": dict(arguments or {}),
                        }
                    )
                ],
            ),
        )

    @classmethod
    def from_tool_response(
        cls,
        invocation_id: str,
        author: str,
        function_name: str,
        response: Any,
        branch: str = "root",
        call_id: str | None = None,
    ) -> Event:
        return cls(
            id=f"evt_{uuid.uuid4().hex}",
            invocation_id=invocation_id,
            author=author,
            branch=branch,
            content=Content(
                role="tool",
                parts=[
                    Part(
                        function_response={
                            "id": call_id or function_name,
                            "name": function_name,
                            "response": response,
                        }
                    )
                ],
            ),
        )

    @classmethod
    def from_function_response(
        cls,
        invocation_id: str,
        author: str,
        function_name: str,
        response: Any,
        branch: str = "root",
    ) -> Event:
        return cls.from_tool_response(invocation_id, author, function_name, response, branch)

    def text(self) -> str:
        if not self.content:
            return ""
        for part in self.content.parts:
            if part.text:
                return part.text
        return ""

    def is_tool_call(self) -> bool:
        return bool(self.content and any(part.function_call is not None for part in self.content.parts))

    def tool_call(self) -> dict | None:
        if not self.content:
            return None
        for part in self.content.parts:
            if part.function_call is not None:
                return part.function_call
        return None

    def is_tool_response(self) -> bool:
        return bool(
            self.content and any(part.function_response is not None for part in self.content.parts)
        )

    def tool_response(self) -> dict | None:
        if not self.content:
            return None
        for part in self.content.parts:
            if part.function_response is not None:
                return part.function_response
        return None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "invocation_id": self.invocation_id,
            "author": self.author,
            "branch": self.branch,
            "timestamp": self.timestamp.isoformat(),
            "content": self.content.to_dict() if self.content else None,
            "actions": self.actions.to_dict() if self.actions else None,
            "partial": self.partial,
            "turn_complete": self.turn_complete,
            "interrupted": self.interrupted,
            "error_code": self.error_code,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Event:
        timestamp = data.get("timestamp")
        return cls(
            id=str(data.get("id", "")),
            invocation_id=str(data.get("invocation_id", "")),
            author=str(data.get("author", "")),
            branch=str(data.get("branch", "root")),
            timestamp=datetime_from_iso(timestamp) if timestamp else utcnow(),
            content=Content.from_dict(data["content"]) if data.get("content") else None,
            actions=EventActions.from_dict(data["actions"]) if data.get("actions") else None,
            partial=bool(data.get("partial", False)),
            turn_complete=bool(data.get("turn_complete", False)),
            interrupted=bool(data.get("interrupted", False)),
            error_code=str(data.get("error_code", "")),
            error_message=str(data.get("error_message", "")),
        )
