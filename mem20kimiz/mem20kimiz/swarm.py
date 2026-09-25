"""SwarmService — port of kimi-code's swarm feature: mode trigger, enter/exit.

Swarm mode is a coordinator state (manual | task | tool) that gates fan-out.
Enter/exit are recorded on the caller's state; auto-exit fires after the turn
ends for task/tool triggers. Context injection (reminders) is represented by a
minimal hook so the scheduler does not leak into agent contexts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

SwarmModeTrigger = Literal["manual", "task", "tool"]

SWARM_KEY = "swarm"


@dataclass
class SwarmStateSnapshot:
    trigger: Optional[SwarmModeTrigger] = None
    entered_at: float = 0.0
    exited_at: Optional[float] = None


@dataclass
class SwarmService:
    """Coordinates the swarm-mode lifecycle for a single caller agent."""

    state: dict[str, Any] = field(default_factory=dict)
    reminders: list[dict[str, Any]] = field(default_factory=list)
    _timeline: list[SwarmStateSnapshot] = field(default_factory=list)

    @property
    def is_active(self) -> bool:
        return self.state.get(SWARM_KEY) is not None

    def enter(self, trigger: SwarmModeTrigger) -> None:
        if self.state.get(SWARM_KEY) is not None:
            return
        self.state[SWARM_KEY] = trigger
        snap = SwarmStateSnapshot(trigger=trigger, entered_at=_now())
        self._timeline.append(snap)
        self.reminders.append({"kind": "swarm_mode", "state": "active"})

    def exit(self) -> None:
        trigger = self.state.get(SWARM_KEY)
        if trigger is None:
            return
        self.state[SWARM_KEY] = None
        snap = SwarmStateSnapshot(trigger=trigger, exited_at=_now())
        self._timeline.append(snap)
        self.reminders.append({"kind": "swarm_mode_exit", "state": "inactive"})

    def on_turn_ended(self) -> None:
        """Mirror kimi's auto-exit: task/tool triggers end with the turn."""
        trigger = self.state.get(SWARM_KEY)
        if trigger in ("task", "tool"):
            self.exit()

    def get_trigger(self) -> Optional[SwarmModeTrigger]:
        return self.state.get(SWARM_KEY)

    def injection_disclosure(self) -> dict[str, Any]:
        trigger = self.get_trigger()
        active = trigger is not None and trigger != "tool"
        return {"kind": "swarm_mode", "state": "active" if active else "inactive"}

    def timeline(self) -> list[dict[str, Any]]:
        return [
            {
                "trigger": s.trigger,
                "entered_at": s.entered_at,
                "exited_at": s.exited_at,
            }
            for s in self._timeline
        ]


def _now() -> float:
    import time

    return time.monotonic()