"""
A2A Tools Mixin for mem20 MCP Server

Provides agent-to-agent communication tools so bots can:
- Discover peer agents
- Send tasks to peers
- List active peers
- Recall conversation history
- Orchestrate fan-out tasks

These are Hermes-level features, separate from mem20's thought processes.
"""
import mcp_types as mt


import os
import sys
import json
import time
import asyncio
import aiohttp
from pathlib import Path
from typing import Any, Dict, List, Optional



class A2AToolsMixin:
    """Agent-to-Agent communication tools for mem20."""

    def register_a2a_tools(self):
        """Register all A2A tools."""
        self.tools["a2a_list"] = mt.Tool(
            name="a2a_list",
            title="A2A List Peers",
            description="List all configured A2A peer agents and their status",
            input_schema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        )
        self.tools["a2a_call"] = mt.Tool(
            name="a2a_call",
            title="A2A Call Agent",
            description="Send a natural-language task to a remote A2A agent",
            input_schema={
                "type": "object",
                "properties": {
                    "agent": {"type": "string", "description": "Name of the peer agent to call"},
                    "message": {"type": "string", "description": "Task or message to send"},
                    "context_id": {"type": "string", "description": "Optional conversation context ID", "default": ""},
                    "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 120},
                },
                "required": ["agent", "message"],
            },
        )
        self.tools["a2a_discover"] = mt.Tool(
            name="a2a_discover",
            title="A2A Discover Agent",
            description="Fetch and summarize a peer agent's Agent Card (capabilities, status)",
            input_schema={
                "type": "object",
                "properties": {
                    "agent": {"type": "string", "description": "Name of the peer agent"},
                },
                "required": ["agent"],
            },
        )
        self.tools["a2a_history"] = mt.Tool(
            name="a2a_history",
            title="A2A Conversation History",
            description="Recall a persisted A2A conversation transcript by context ID",
            input_schema={
                "type": "object",
                "properties": {
                    "context_id": {"type": "string", "description": "Conversation context ID"},
                    "limit": {"type": "integer", "description": "Max messages to return", "default": 20},
                },
                "required": ["context_id"],
            },
        )
        self.tools["a2a_orchestrate"] = mt.Tool(
            name="a2a_orchestrate",
            title="A2A Orchestrate",
            description="Fan-out a task to multiple peer agents by capability",
            input_schema={
                "type": "object",
                "properties": {
                    "capability": {"type": "string", "description": "Capability to filter peers by"},
                    "message": {"type": "string", "description": "Task to send"},
                    "mode": {"type": "string", "enum": ["parallel", "sequential"], "description": "Execution mode", "default": "parallel"},
                },
                "required": ["capability", "message"],
            },
        )

    def _get_a2a_config(self) -> tuple:
        """Load A2A configuration from the active profile's config.yaml."""
        import yaml
        profile = os.environ.get("HERMES_PROFILE", "mem20-bot")
        config_path = os.path.expanduser(f"~/.hermes/profiles/{profile}/config.yaml")
        if not os.path.exists(config_path):
            config_path = os.path.expanduser("~/.hermes/config.yaml")
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}
        return config.get("a2a", {}), config.get("a2a_agents", {})

    def _get_peer_url(self, agent_name: str) -> Optional[str]:
        """Get the URL for a named peer agent."""
        _, agents = self._get_a2a_config()
        if agent_name in agents:
            return agents[agent_name].get("url")
        return None

    async def _a2a_list(self, args: Dict) -> str:
        """List all configured A2A peers."""
        a2a_config, agents = self._get_a2a_config()
        if not agents:
            return "No A2A peers configured."
        
        output = f"**A2A Peers ({len(agents)} configured)**\n\n"
        for name, info in agents.items():
            url = info.get("url", "unknown")
            caps = info.get("capabilities", [])
            output += f"- **{name}** — {url}"
            if caps:
                output += f"  [{', '.join(caps)}]"
            output += "\n"
        return output

    async def _a2a_call(self, args: Dict) -> str:
        """Send a task to a remote A2A agent via JSON-RPC message/send."""
        agent = args.get("agent", "")
        message = args.get("message", "")
        context_id = args.get("context_id", "")
        timeout = args.get("timeout", 120)

        url = self._get_peer_url(agent)
        if not url:
            return f"Error: Unknown agent '{agent}'. Use a2a_list to see configured peers."

        # Build JSON-RPC 2.0 request
        payload = {
            "jsonrpc": "2.0",
            "id": f"mem2a-{int(time.time())}",
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"kind": "text", "text": message}],
                    "messageId": f"msg-{int(time.time())}",
                }
            }
        }
        if context_id:
            payload["params"]["contextId"] = context_id

