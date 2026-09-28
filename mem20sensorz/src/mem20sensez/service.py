"""sense service — orchestrate Phase 1 sense-organs operations.

gap / replan / twin / exec run against the real UCG, self-model memory store,
and mem20langz StateGraph. Every operation can journal to braid.
"""
from __future__ import annotations

import json
from typing import Any

from .descriptor import TWIN_ID
from .gapper import GapMapper
from .replanner import PhaseReplanner
from .ucg_client import UcgClient
from .workflow_twin import WorkflowTwin


class SenseError(RuntimeError):
    pass


class SenseService:
    def __init__(self, ucg_service: Any = None) -> None:
        self.client = UcgClient(service=ucg_service) if ucg_service is not None else UcgClient()
        self.gapper = GapMapper(self.client)
        self.replanner = PhaseReplanner(["plan", "build", "verify", "ship"])
        self.workflow_twin = WorkflowTwin()
        self.accelerator = self._new_accelerator()
        self.enroller = self._new_enroller()

    @staticmethod
    def _new_accelerator():
        from .accelerator import HumanCapabilityAccelerator
        return HumanCapabilityAccelerator()

    @staticmethod
    def _new_enroller():
        from .enroller import DeviceEnrollmentAutopilot
        return DeviceEnrollmentAutopilot()

    def gap(self, goal: str) -> dict[str, Any]:
        if not goal or not str(goal).strip():
            raise SenseError("goal must be a non-empty string")
        report = self.gapper.map(str(goal))
        return report.to_dict()

    def replan(self, goal: str, phases: list[str] | None = None,
               journal: bool = False) -> dict[str, Any]:
        if not goal or not str(goal).strip():
            raise SenseError("goal must be a non-empty string")
        report = self.gapper.map(str(goal))
        rp = PhaseReplanner(phases or self.replanner.phases)
        plan = rp.replan(report, journal=journal)
        return plan.to_dict()

    def twin(self) -> dict[str, Any]:
        return self.workflow_twin.digest().to_dict()

    def exec(self, steps: list[dict[str, Any]] | None = None,
             initial: dict[str, Any] | None = None,
             journal: bool = False) -> dict[str, Any]:
        if not steps:
            steps = [
                {"name": "gather", "action": "load context", "value": 1, "key": "ctx"},
                {"name": "execute", "action": "run real work", "value": 2, "key": "done"},
            ]
        from .exec_twin import ExecTwin
        et = ExecTwin()
        et.build(steps)
        plan = et.run(initial or {"ctx": 0, "done": 0}, journal=journal)
        return plan.to_dict()

    # --- RM-150 human trust bridge -------------------------------------
    def accelerate(self, action: str, human: str, public_key: str | None = None,
                   goal: str | None = None, signature: str | None = None,
                   metric: str | None = None, delta: float | None = None,
                   **extra: Any) -> dict[str, Any]:
        from .accelerator import HumanError
        acc = self.accelerator
        try:
            if action == "declare":
                return acc.declare(human, public_key or "", goal or "",
                                   name=extra.get("name")).to_dict()
            if action == "attest":
                return acc.attest(human, signature or "").to_dict()
            if action == "admit":
                return acc.admit(human).to_dict()
            if action == "growth":
                return acc.record_growth(human, metric or "", metric or "", delta or 0.0).to_dict()
            if action == "progress":
                return {"human_id": human, "progress": acc.progress(human)}
            if action == "summary":
                return acc.summary()
            if action == "revoke":
                return {"revoked": acc.revoke(human)}
            if action == "simulate":
                return acc.simulator(human, max_humans=extra.get("max_devices", 3))
            raise HumanError(f"unknown accelerator action {action!r}")
        except HumanError as e:
            return {"error": str(e)}

    # --- RM-151 device trust bridge ------------------------------------
    def enroll(self, action: str, device: str, public_key: str | None = None,
               signature: str | None = None, nonce: str | None = None,
               **extra: Any) -> dict[str, Any]:
        from .enroller import EnrollmentError
        en = self.enroller
        try:
            if action == "declare":
                return en.declare(device, public_key or "",
                                  hostname=extra.get("hostname"),
                                  platform=extra.get("platform")).to_dict()
            if action == "attest":
                return en.attest(device, signature or "").to_dict()
            if action == "enroll":
                return en.enroll(device).to_dict()
            if action == "provision":
                return en.provision(device).to_dict()
            if action == "validate":
                return en.validate(device, signature or "", nonce=nonce).to_dict()
            if action == "revoke":
                return {"revoked": en.revoke(device)}
            if action == "list":
                return {"devices": en.list()}
            if action == "simulate":
                return en.simulator(device, max_devices=extra.get("max_devices", 3))
            raise EnrollmentError(f"unknown enrollment action {action!r}")
        except EnrollmentError as e:
            return {"error": str(e)}

    def health(self) -> dict[str, Any]:
        from .braid_hook import braid_ok

        try:
            n = len(self.client.all(active_only=True))
        except Exception:
            n = -1
        return {
            "ok": True,
            "capability": TWIN_ID,
            "service": "mem20sensez",
            "ucg_capabilities": n,
            "braid": braid_ok(),
        }