"""Braid ledger tools — signed, proven, content-addressed commits + intent strand.

Every braid_* tool talks to the shared braid_bridge facade (single persistent
engine). Writes return real receipts (cid/depth/proof_hops); denials are raised
as errors, never faked.
"""
import json
import os
import sys
from typing import Any, Dict

try:
    from mcp.server import Server
    from mcp.server.lowlevel.server import ServerRequestContext
    import mcp_types as mt
except ImportError:
    print("Error: mcp package not installed. Please install with: pip install mcp")
    sys.exit(1)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


class BraidToolsMixin:
    """MCP tools exposing the braid ledger (write/read/prove/intents/status)."""

    def register_braid_tools(self):
        self.tools["braid_status"] = mt.Tool(
            name="braid_status",
            title="Braid Status",
            description="Show the braid ledger status: engine id, signer, head node, availability.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        )
        self.tools["braid_write"] = mt.Tool(
            name="braid_write",
            title="Braid Write",
            description="Commit a signed, proven node to the braid ledger (content-addressed).",
            inputSchema={
                "type": "object",
                "properties": {
                    "op": {"type": "string", "description": "Operation (e.g. write:fact, write:intent, commit:decision)"},
                    "target": {"type": "string", "description": "Target strand/resource"},
                    "payload": {"type": "object", "description": "Arbitrary JSON body"},
                    "cap": {"type": "string", "description": "Capability token (resource:action:target)", "default": "agent:write:*"},
                    "escalated_snapshot_cid": {"type": "string", "description": "Optional frozen snapshot cid for escalation", "default": ""},
                },
                "required": ["op", "target", "payload"],
            },
        )
        self.tools["braid_read"] = mt.Tool(
            name="braid_read",
            title="Braid Read",
            description="Read a node from the braid ledger by cid.",
            inputSchema={
                "type": "object",
                "properties": {
                    "cid": {"type": "string", "description": "Node cid (br...)"},
                },
                "required": ["cid"],
            },
        )
        self.tools["braid_head"] = mt.Tool(
            name="braid_head",
            title="Braid Head",
            description="Read the most recent node on the braid ledger.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        )
        self.tools["braid_prove"] = mt.Tool(
            name="braid_prove",
            title="Braid Prove",
            description="Verify a node's provenance/precommit chain on the ledger.",
            inputSchema={
                "type": "object",
                "properties": {
                    "cid": {"type": "string", "description": "Node cid to prove"},
                },
                "required": ["cid"],
            },
        )
        self.tools["braid_hash"] = mt.Tool(
            name="braid_hash",
            title="Braid Hash",
            description="Content-hash data with the braid core hash function.",
            inputSchema={
                "type": "object",
                "properties": {
                    "data": {"type": "string", "description": "Data to hash"},
                },
                "required": ["data"],
            },
        )
        self.tools["braid_intent_submit"] = mt.Tool(
            name="braid_intent_submit",
            title="Braid Intent Submit",
            description="Submit a signed intent node to the braid intent strand.",
            inputSchema={
                "type": "object",
                "properties": {
                    "desire": {"type": "string", "description": "What the intent wants"},
                    "target": {"type": "string", "description": "Target resource"},
                    "context": {"type": "object", "description": "Optional context", "default": {}},
                    "weight": {"type": "integer", "description": "Intent weight", "default": 50},
                },
                "required": ["desire", "target"],
            },
        )
        self.tools["braid_intent_view"] = mt.Tool(
            name="braid_intent_view",
            title="Braid Intent View",
            description="Project the braid intent strand: submitted/open/resolved counts.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        )
        self.tools["braid_sign"] = mt.Tool(
            name="braid_sign",
            title="Braid Signer",
            description="Show the bridge signer public key hex.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        )

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    async def _braid_status(self, args: Dict) -> str:
        try:
            from braid_bridge import status
            return json.dumps(status(), indent=2, default=str)
        except Exception as e:
            return f"Error: {e}"

    async def _braid_write(self, args: Dict) -> str:
        op = args.get("op", "")
        target = args.get("target", "")
        payload = args.get("payload", {})
        cap = args.get("cap", "agent:write:*")
        escalated = args.get("escalated_snapshot_cid", "") or None
        if not op or not target:
            return "Error: op and target are required"
        try:
            from braid_bridge import commit
            receipt = commit(op, target, payload, cap=cap, escalated=escalated)
            return json.dumps(receipt, indent=2)
        except Exception as e:
            return f"Error: {e}"

    async def _braid_read(self, args: Dict) -> str:
        cid = args.get("cid", "")
        if not cid:
            return "Error: cid is required"
        try:
            from braid_bridge import read
            node = read(cid)
            if node is None:
                return f"No node with cid {cid}"
            return json.dumps(node, indent=2, default=str)
        except Exception as e:
            return f"Error: {e}"

    async def _braid_head(self, args: Dict) -> str:
        try:
            from braid_bridge import head
            node = head()
            if node is None:
                return "(empty ledger)"
            return json.dumps(node, indent=2, default=str)
        except Exception as e:
            return f"Error: {e}"

    async def _braid_prove(self, args: Dict) -> str:
        cid = args.get("cid", "")
        if not cid:
            return "Error: cid is required"
        try:
            from braid_bridge import prove, read
            ok = prove(cid)
            node = read(cid)
            return json.dumps({
                "cid": cid,
                "proven": ok,
                "op": node["op"] if node else None,
                "depth": node["depth"] if node else None,
            }, indent=2)
        except Exception as e:
            return f"Error: {e}"

    async def _braid_hash(self, args: Dict) -> str:
        data = args.get("data", "")
        try:
            from braid_bridge import hash_data
            return json.dumps({"hash": hash_data(data)}, indent=2)
        except Exception as e:
            return f"Error: {e}"

    async def _braid_intent_submit(self, args: Dict) -> str:
        desire = args.get("desire", "")
        target = args.get("target", "")
        context = args.get("context", {}) or {}
        weight = int(args.get("weight", 50))
        if not desire or not target:
            return "Error: desire and target are required"
        try:
            from braid_bridge import intent_submit
            receipt = intent_submit(desire, target, context, weight)
            return json.dumps(receipt, indent=2)
        except Exception as e:
            return f"Error: {e}"

    async def _braid_intent_view(self, args: Dict) -> str:
        try:
            from braid_bridge import intent_view
            return json.dumps(intent_view(), indent=2, default=str)
        except Exception as e:
            return f"Error: {e}"

    async def _braid_sign(self, args: Dict) -> str:
        try:
            from braid_bridge import signer_hex
            return json.dumps({"signer": signer_hex()}, indent=2)
        except Exception as e:
            return f"Error: {e}"