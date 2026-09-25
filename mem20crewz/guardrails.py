"""Guardrails — epistemic veto + quarantine + plan-execution gate.

Every Crew/Task/Flow run funnels through Guards so the cleanroom surfaces only
plans resting on grounded memory and sweeps decaying simulated content after
work. Real path: mem20 memory (epistemic_veto, quarantine_expired_simulated,
run_plan_execution_guard). Tests inject deterministic seams via _substrate.
"""

from __future__ import annotations

from typing import Optional

from ._substrate import backend as sub


class GuardrailBlocked(Exception):
    """A plan was refused by the plan-execution guard / epistemic veto."""

    def __init__(self, reason: str, detail: Optional[dict] = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail or {}


class Guards:
    """One guardrail bundle per run, free to be shared by a whole Crew."""

    def __init__(self, actor: str = "agent", enforce_plan: bool = True,
                 enforce_veto: bool = True, sweep_after: bool = True) -> None:
        self.actor = actor
        self.enforce_plan = enforce_plan
        self.enforce_veto = enforce_veto
        self.sweep_after = sweep_after
        self.events: list[dict] = []

    # ------------------------------------------------------------ plan gate
    def gate(self, fact_ids: Optional[list] = None) -> None:
        """Run the plan-execution guard. Raises GuardrailBlocked on refusal."""
        if not self.enforce_plan:
            return
        r = sub.plan_guard(list(fact_ids or []), actor=self.actor)
        self.events.append({"kind": "plan_guard", "result": r})
        blocked = bool(r.get("blocked")) if isinstance(r, dict) else False
        if blocked:
            raise GuardrailBlocked(
                r.get("reason") or r.get("message") or "plan blocked by plan-execution guard",
                r)

    # ---------------------------------------------------------- epistemic
    def check_clearance(self, fact_ids: list, allow_report_only: bool = True) -> dict:
        """Advisory epistemic veto. Returns the veto result dict."""
        if not self.enforce_veto or not fact_ids:
            return {"vetoed": False, "reason": "no fact_ids to veto-check"}
        r = sub.veto(fact_ids, actor=self.actor)
        self.events.append({"kind": "epistemic_veto", "result": r})
        return r

    def require_clearance(self, fact_ids: list) -> None:
        """Enforced clearance: raises GuardrailBlocked if the plan rests on
        unvalidated simulated beliefs."""
        if not self.enforce_veto:
            return
        r = sub.veto(fact_ids, actor=self.actor)
        self.events.append({"kind": "epistemic_veto", "result": r})
        if r.get("vetoed"):
            raise GuardrailBlocked(
                r.get("reason") or "plan rests on unvalidated simulated beliefs", r)

    # ---------------------------------------------------------- quarantine
    def sweep(self) -> dict:
        """Quarantine expired simulated content after a run."""
        if not self.sweep_after:
            return {"quarantined": []}
        r = sub.quarantine(actor=self.actor)
        self.events.append({"kind": "quarantine_sweep", "result": r})
        return r

    def summary(self) -> dict:
        return {"actor": self.actor,
                "enforce_plan": self.enforce_plan,
                "enforce_veto": self.enforce_veto,
                "sweep_after": self.sweep_after,
                "events": list(self.events)}