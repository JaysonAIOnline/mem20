"""Gateway daemon — manages bridges and delivery (sub-phase 2.5).

The daemon loads every bridge named in config `gateway.bridges`, gives each a
per-chat agent factory (continuous per-chat sessions), and logs all traffic to
the mem20 ledger. `serve()` blocks; `status()`/`pair()`/`unpair()` are usable
while running (the pair state is on-disk so any process can read it).
"""

from __future__ import annotations

import threading
import time
from typing import Optional

from .bridge import Bridge, AuthError
from .config import config_dir, load_config


def build_agent_factory(backend=None, profile="mem20", model=None,
                        incarnation: str = "gateway",
                        session_prefix: str = "chat:"):
    """Return callable(chat_id) -> AgentCore with a stable per-chat session.

    Session ids are derived from the chat id so a second message to the same
    chat continues the same transcript (resume via history weaving). The
    `session_prefix` scopes transcript namespaces (bridge chats use "chat:",
    the web gateway uses "web:", peer agents use "acp:").
    """

    def factory(chat_id: str) -> object:
        from .agentz import AgentCore
        core = AgentCore(backend=backend, profile=profile, model=model,
                         approvals="auto", toolsets=("skills",),
                         history=_history(backend, session_prefix, chat_id))
        return core

    return factory


def _history(backend, session_prefix: str, chat_id: str,
             k: int = 20) -> list[dict]:
    if backend is None:
        return []
    try:
        msgs = backend.session_messages("gateway", session_prefix + chat_id,
                                        k=k)
    except Exception:  # noqa: BLE001
        msgs = []
    out = []
    for m in msgs:
        content = m.get("content", "")
        direction, _, rest = content.partition(":")
        if direction not in ("in", "out") or not rest:
            continue
        # ledger format from Bridge._log: "<dir>:<session_id> <text>"
        text = rest.partition(" ")[2] or rest
        role = "user" if direction == "in" else "assistant"
        out.append({"role": role, "content": text})
        if len(out) >= k:
            break
    return out[-k:]


class Gateway:
    def __init__(self, backend=None, root: Optional[pathlib.Path] = None,
                 agent_factory=None) -> None:
        self.backend = backend
        self.root = root or config_dir() / "gateway"
        self.agent_factory = agent_factory or build_agent_factory(backend)
        self.bridges: dict[str, Bridge] = {}
        self.transport_errors: dict[str, str] = {}
        self._threads: list[threading.Thread] = []
        self._running = False

    # ------------------------------------------------------------ config
    def configured_bridges(self) -> list[str]:
        cfg = load_config()
        return list(cfg.get("gateway", {}).get("bridges") or
                    ["telegram"])

    def load(self, names: Optional[list[str]] = None) -> None:
        missing = []
        for name in names or self.configured_bridges():
            try:
                transport = _make_transport(name)
            except AuthError as exc:
                self.transport_errors[str(name)] = str(exc)
                missing.append(name)
                continue
            if transport is None:
                import sys
                print(f"[gateway] bridge '{name}' unknown; skipping",
                      file=sys.stderr)
                self.transport_errors[str(name)] = "unknown transport"
                continue
            self.bridges[name] = Bridge(name=name, transport=transport,
                                        agent_factory=self.agent_factory,
                                        ledger=self.backend,
                                        root=self.root,
                                        require_pairing=name != "loopback")

    def require_ready(self) -> None:
        if not self.bridges:
            reason = "; ".join(f"{k}: {v}" for k, v in
                               self.transport_errors.items()) or "none"
            raise AuthError(
                f"gateway has no runnable bridge ({reason or 'unset'})")

    def find_bridge(self, name: str) -> Bridge:
        if name not in self.bridges:
            raise KeyError(f"bridge '{name}' not loaded")
        return self.bridges[name]

    # ------------------------------------------------------------ lifecycle
    def serve(self, names: Optional[list[str]] = None) -> None:
        self.load(names)
        self.require_ready()
        self._running = True
        for name, bridge in self.bridges.items():
            t = threading.Thread(target=self._run_bridge,
                                 args=(name, bridge), daemon=True)
            t.start()
            self._threads.append(t)
        try:
            while self._running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()

    def _run_bridge(self, name: str, bridge: Bridge) -> None:
        print(f"[gateway] {name} bridge starting")
        try:
            bridge.run()
        except Exception as exc:  # noqa: BLE001
            import sys
            print(f"[gateway] {name} bridge died: {exc}", file=sys.stderr)

    def stop(self) -> None:
        self._running = False
        for bridge in self.bridges.values():
            bridge.stop()

    def status(self) -> dict:
        bridges = []
        for name in self.configured_bridges():
            bridge = self.bridges.get(name)
            if bridge is None:
                bridges.append({
                    "name": name,
                    "state": "unconfigured",
                    "reason": self.transport_errors.get(name, ""),
                })
                continue
            bridges.append({
                "name": name,
                "state": "ready",
                "paired": len(bridge.pairs()),
                "transport": type(bridge.transport).__name__,
            })
        return {
            "running": self._running,
            "bridges": bridges,
            "configured": self.configured_bridges(),
        }

    def client(self, name: str) -> Optional[Bridge]:
        return self.bridges.get(name)


def _make_transport(name: str):
    if name == "telegram":
        from .bridges.telegram import TelegramTransport
        return TelegramTransport()
    if name == "loopback":
        from .bridges.loopback import LoopbackTransport
        return LoopbackTransport()
    return None