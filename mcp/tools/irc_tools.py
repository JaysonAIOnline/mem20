"""IRC room tools for agents — join the #mem20 channel, read it, speak in it.

Thin by design. The persistent connection, the reconnect supervision and the
noise filtering all live in the mem20ircz daemon; these tools are a door onto
that daemon's unix socket and nothing more. Reimplementing any of it here would
give an agent two sources of truth about who is in the room.

The tool descriptions carry the two rules an agent needs in order not to waste
tokens or miss messages: keep the sequence cursor, and never poll in a loop.
"""
import asyncio
import json
import os
import sys
import time
from typing import Any, Dict

try:
    from mcp.server import Server
    from mcp.server.lowlevel.server import ServerRequestContext
    import mcp_types as mt
except ImportError:
    print("Error: MCP package not installed. Install with: pip install mcp")
    sys.exit(1)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

SOCKET_PATH = os.environ.get("MEM20IRCZ_SOCKET", "/run/mem20ircz/hub.sock")

_CURSOR_NOTE = (
    "Pass back the 'latest_seq' from the previous call as 'since'. That returns "
    "only what arrived since, which is what makes a reply cost one cheap call "
    "instead of a re-read of the whole channel."
)


class IRCToolsMixin:
    """MCP tools exposing the persistent IRC room (join / read / say / who)."""

    def register_irc_tools(self):
        self.tools["irc_status"] = mt.Tool(
            name="irc_status",
            title="IRC Room Status",
            description=(
                "Show the IRC hub: whether each nick is connected and in the "
                "channel, and how many protocol lines the noise filter has "
                "swallowed. Use this to check the room is reachable before "
                "expecting messages, or to confirm a filter is doing its job."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        )
        self.tools["irc_join"] = mt.Tool(
            name="irc_join",
            title="IRC Join Room",
            description=(
                "Join the IRC room under a nick and get the backlog depth. The "
                "connection is owned by a persistent daemon, so this does not "
                "reconnect or lose anything. Returns 'ready', which is true "
                "only once the channel roster has arrived and you can actually "
                "hear and be heard."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "nick": {"type": "string",
                             "description": "Nick to take. Defaults to the hub's own."},
                },
                "required": [],
            },
        )
        self.tools["irc_read"] = mt.Tool(
            name="irc_read",
            title="IRC Read Channel",
            description=(
                "Read channel messages newer than a sequence cursor. Server "
                "noise (MOTD, numerics, joins/parts) is already filtered out "
                "before it reaches you, so every message here is real "
                "conversation. " + _CURSOR_NOTE +
                " Call once; if it returns nothing new, there is nothing new."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "since": {"type": "integer", "default": 0,
                              "description": "Return only messages after this sequence number."},
                    "limit": {"type": "integer", "default": 50},
                    "nick": {"type": "string",
                             "description": "Which connection to read from."},
                    "wait_seconds": {"type": "integer", "default": 0,
                                     "description": "Wait up to this many seconds for the first new message. Keep it small."},
                },
                "required": [],
            },
        )
        self.tools["irc_say"] = mt.Tool(
            name="irc_say",
            title="IRC Say",
            description=(
                "Send a message to the IRC channel. Returns as soon as it is "
                "written to the socket; it does not wait for a reply, so send "
                "and then call irc_read with your cursor to see the answer."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Message to send."},
                    "nick": {"type": "string",
                             "description": "Which connection to send from."},
                },
                "required": ["text"],
            },
        )
        self.tools["irc_who"] = mt.Tool(
            name="irc_who",
            title="IRC Who Is In The Room",
            description="List who else is in the channel, tracked from the roster the filter swallows.",
            inputSchema={
                "type": "object",
                "properties": {
                    "nick": {"type": "string",
                             "description": "Which connection to ask."},
                },
                "required": [],
            },
        )

    # ------------------------------------------------------------- handlers
    def _hub(self):
        from mem20ircz.ipc import HubClient
        return HubClient(SOCKET_PATH)

    async def _irc_status(self, args: Dict) -> str:
        try:
            return json.dumps(self._hub().status(), indent=2, default=str)
        except Exception as e:  # noqa: BLE001
            return (f"Error: {e}\n\nThe IRC hub is not reachable. Check "
                    f"`systemctl status mem20ircz`.")

    async def _irc_join(self, args: Dict) -> str:
        try:
            reply = self._hub().join(args.get("nick") or None)
            if not reply.get("ok"):
                return f"Error: {reply.get('error')}"
            if not reply.get("ready"):
                return (f"Joined as {reply['nick']} but the channel roster has "
                        f"not arrived yet, so messages sent now could be "
                        f"dropped. Call irc_read in a moment to confirm.")
            return (f"Joined as {reply['nick']}, in the room. "
                    f"{reply['backlog']} messages in backlog, latest sequence "
                    f"{reply['latest_seq']}. Read with irc_read.")
        except Exception as e:  # noqa: BLE001
            return f"Error: {e}"

    async def _irc_read(self, args: Dict) -> str:
        try:
            wait = min(int(args.get("wait_seconds") or 0), 30)
            reply = self._hub().read(
                since=int(args.get("since") or 0),
                limit=int(args.get("limit") or 50),
                nick=args.get("nick") or None)
            if not reply.get("ok"):
                return f"Error: {reply.get('error')}"
            deadline = time.time() + wait
            # Bounded wait, and only for the *first* new message. An agent turn
            # must be able to end, so this never blocks indefinitely.
            while wait and not reply.get("count") and time.time() < deadline:
                await asyncio.sleep(0.25)
                reply = self._hub().read(
                    since=int(args.get("since") or 0),
                    limit=int(args.get("limit") or 50),
                    nick=args.get("nick") or None)

            notes = []
            if reply.get("truncated"):
                notes.append(
                    f"NOTE: messages before sequence {reply['oldest_seq']} have "
                    f"aged out of the buffer; this is a gap, not the whole "
                    f"conversation.")
            if reply.get("disconnects"):
                notes.append(
                    f"NOTE: the connection dropped {reply['disconnects']} time(s); "
                    f"anything said during a drop was not received.")

            if not reply.get("count"):
                body = "(nothing new)"
            else:
                body = "\n".join(
                    f"<{m['nick']}> {m['text']}"
                    + ("  (you)" if m.get("mine") else "")
                    for m in reply["messages"])

            footer = (f"\n-- {reply['count']} new, latest_seq="
                      f"{reply['latest_seq']}. Pass that back as 'since'.")
            return "\n".join(notes + [body, footer])
        except Exception as e:  # noqa: BLE001
            return f"Error: {e}"

    async def _irc_say(self, args: Dict) -> str:
        text = str(args.get("text") or "").strip()
        if not text:
            return "Error: 'text' is required."
        try:
            reply = self._hub().say(text, nick=args.get("nick") or None)
            if not reply.get("ok"):
                return f"Error: {reply.get('error')}"
            return f"Sent to {reply['nick']}. Call irc_read with your cursor to see replies."
        except Exception as e:  # noqa: BLE001
            return f"Error: {e}"

    async def _irc_who(self, args: Dict) -> str:
        try:
            reply = self._hub().who(args.get("nick") or None)
            nicks = reply.get("nicks") or []
            return ("In the room: " + " ".join(nicks)) if nicks else \
                   "(nobody seen yet — the roster has not arrived)"
        except Exception as e:  # noqa: BLE001
            return f"Error: {e}"
