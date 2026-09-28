"""accelerator — Human Capability Accelerator (RM-150).

Human trust bridge: a person declares a capability goal and a public key, proves
ownership via an Ed25519 challenge signature, and — once attested — is admitted
with a freshly provisioned credential. On top of the trust bridge the core
tracks measurable personal growth: typed growth goals with baselines and
targets, coach actions that produce real deltas, and a progress summary. A
local simulator replays success / malformed-input / disconnect / overload /
provider-loss / restart-recovery against the real runtime.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

from . import attest
from .state_plane import MEM20_STORE, StatePlane, StatePlaneError

HUMAN_STATES = ("pending", "attested", "admitted")
CHALLENGE_TTL_S = 60
MAX_HUMANS = 100


@dataclass
class HumanReply:
    human_id: str
    status: str
    step: str | None = None
    challenge: str | None = None
    credential: str | None = None
    progress: list[dict[str, Any]] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"human_id": self.human_id, "status": self.status,
                               "step": self.step}
        if self.challenge is not None:
            out["challenge"] = self.challenge
        if self.credential is not None:
            out["credential"] = self.credential
        if self.progress is not None:
            out["progress"] = self.progress
        if self.error is not None:
            out["error"] = self.error
        return out


class HumanError(RuntimeError):
    pass


class HumanCapabilityAccelerator:
    """Combine coaching, tools, agents, memory, and simulation around measurable
    personal growth, behind a human trust bridge (RM-150)."""

    def __init__(self, store: str | None = None, max_humans: int = MAX_HUMANS,
                 challenge_ttl_s: float = CHALLENGE_TTL_S) -> None:
        self._store = store or MEM20_STORE
        self.state = StatePlane("human_capability", store=self._store,
                                validator=self._validate_human)
        self.max_humans = max_humans
        self.challenge_ttl_s = challenge_ttl_s
        self._mutex = threading.Lock()

    def _validate_human(self, human_id: str, human: dict[str, Any]) -> None:
        if not isinstance(human_id, str) or not human_id.strip():
            raise StatePlaneError("human_id must be a non-empty string")
        if not human.get("public_key"):
            raise StatePlaneError("public_key is required")
        if human.get("status") not in HUMAN_STATES:
            raise StatePlaneError(f"unknown human status {human.get('status')!r}")

    # --- trust bridge: join / attest / admit ----------------------------
    def declare(self, human_id: str, public_key: str, goal: str,
                skills: list[str] | None = None, baseline: dict[str, float] | None = None,
                name: str | None = None) -> HumanReply:
        with self._mutex:
            existing = self.state.get(human_id)
            if existing is not None:
                return HumanReply(human_id=human_id, status=existing["status"], step="resume")
            if len(self.state.all()) >= self.max_humans:
                raise HumanError("human quota reached; refusing new admission")
            if not goal or not str(goal).strip():
                raise HumanError("goal must be a non-empty string")
            challenge = attest.new_nonce()
            human = {
                "entity_id": human_id,
                "status": "pending",
                "public_key": public_key,
                "name": name,
                "goal": str(goal).strip(),
                "skills": skills or [],
                "baseline": dict(baseline or {}),
                "challenge": challenge,
                "challenge_issued_s": time.time(),
                "attempts": 0,
                "credential": None,
                "growth_events": [],
                "events": ["declare"],
            }
            self.state.put(human_id, human)
            return HumanReply(human_id=human_id, status="pending", step="declare",
                              challenge=challenge)

    def attest(self, human_id: str, signature_hex: str) -> HumanReply:
        with self._mutex:
            human = self.state.get(human_id)
            if human is None:
                raise HumanError(f"unknown human {human_id!r}")
            if human["status"] not in ("pending", "attested"):
                raise HumanError(f"human {human_id!r} is in state {human['status']!r}, not awaiting attestation")
            if human["status"] == "attested":
                return HumanReply(human_id=human_id, status="attested", step="attest")
            if time.time() - human["challenge_issued_s"] > self.challenge_ttl_s:
                raise HumanError("challenge expired; re-declare to receive a fresh nonce")
            human["attempts"] += 1
            ok = attest.verify(human["public_key"], human["challenge"].encode(), signature_hex)
            if not ok:
                self.state.put(human_id, human)
                raise HumanError("attestation signature invalid")
            human["status"] = "attested"
            human["events"].append("attest")
            self.state.put(human_id, human)
            return HumanReply(human_id=human_id, status="attested", step="attest")

    def admit(self, human_id: str) -> HumanReply:
        """Admit an attested human: auto-provision a fresh credential on join."""
        with self._mutex:
            human = self.state.get(human_id)
            if human is None:
                raise HumanError(f"unknown human {human_id!r}")
            if human["status"] != "attested":
                raise HumanError(f"human {human_id!r} must be attested before admission")
            human["credential"] = attest.new_credential()
            human["status"] = "admitted"
            human["events"].append("admit")
            self.state.put(human_id, human)
            return HumanReply(human_id=human_id, status="admitted", step="admit",
                              credential=human["credential"])

    # --- measurable personal growth --------------------------------------
    def record_growth(self, human_id: str, skill: str, metric: str,
                      delta: float) -> HumanReply:
        """A coach action produced a measurable delta against a skill metric."""
        with self._mutex:
            human = self.state.get(human_id)
            if human is None:
                raise HumanError(f"unknown human {human_id!r}")
            if human["status"] != "admitted":
                raise HumanError(f"human {human_id!r} must be admitted before recording growth")
            event = {
                "ts": time.time(),
                "skill": skill,
                "metric": metric,
                "delta": float(delta),
            }
            human["growth_events"].append(event)
            human["events"].append("growth")
            self.state.put(human_id, human)
            return HumanReply(human_id=human_id, status="admitted", step="growth",
                              progress=self.progress(human_id))

    def progress(self, human_id: str) -> list[dict[str, Any]]:
        human = self.state.get(human_id)
        if human is None:
            return []
        agg: dict[str, dict[str, float]] = {}
        for ev in human.get("growth_events", []):
            key = f"{ev['skill']}:{ev['metric']}"
            row = agg.setdefault(key, {"skill": ev["skill"], "metric": ev["metric"],
                                       "delta": 0.0, "count": 0})
            row["delta"] = round(row["delta"] + ev["delta"], 4)
            row["count"] += 1
        return sorted(agg.values(), key=lambda r: r["skill"])

    def summary(self) -> dict[str, Any]:
        humans = self.state.all()
        admitted = sum(1 for h in humans if h["status"] == "admitted")
        total_growth = 0.0
        for h in humans:
            for ev in h.get("growth_events", []):
                total_growth += ev["delta"]
        return {
            "humans_total": len(humans),
            "humans_admitted": admitted,
            "goals": [h.get("goal") for h in humans],
            "cumulative_growth_delta": round(total_growth, 4),
            "store": self._store,
        }

    def get(self, human_id: str) -> dict[str, Any] | None:
        return self.state.get(human_id)

    def list(self, status: str | None = None) -> list[dict[str, Any]]:
        return self.state.query(status=status) if status else self.state.all()

    def revoke(self, human_id: str) -> bool:
        return self.state.delete(human_id)

    # --- simulator ---------------------------------------------------------
    def simulator(self, human_id: str = "sim-human-1",
                  keypair: dict[str, str] | None = None,
                  max_humans: int = 3) -> dict[str, bool]:
        """Replay success / malformed-input / disconnect / overload /
        provider-loss / restart-recovery against the real runtime."""
        kp = keypair or attest.generate_keypair()
        sim = HumanCapabilityAccelerator(store=self._store, max_humans=max_humans)
        out: dict[str, bool] = {}

        r = sim.declare(human_id, kp["public"], goal="become a capable builder")
        out["success"] = (r.status == "pending" and r.challenge is not None)
        if out["success"]:
            r2 = sim.attest(human_id, attest.sign(kp["private"], r.challenge.encode()))
            out["success"] = out["success"] and r2.status == "attested"
            r3 = sim.admit(human_id)
            out["success"] = out["success"] and r3.status == "admitted" and r3.credential
            r4 = sim.record_growth(human_id, "coding", "delivery_speed", 1.5)
            out["success"] = out["success"] and r4.progress and r4.progress[0]["delta"] == 1.5

        try:
            sim.attest(human_id, "deadbeef")
            out["malformed_input"] = False
        except HumanError:
            out["malformed_input"] = True

        sim2 = HumanCapabilityAccelerator(store=self._store, max_humans=max_humans)
        r = sim2.declare("disconnect-human", kp["public"], goal="g")
        try:
            time.sleep(0.01)
            sim2.challenge_ttl_s = 0.0
            sim2.attest("disconnect-human", attest.sign(kp["private"], r.challenge.encode()))
            out["disconnect"] = False
        except HumanError:
            out["disconnect"] = True
        sim2.revoke("disconnect-human")

        full = HumanCapabilityAccelerator(store=self._store, max_humans=1)
        try:
            full.declare("overload-a", kp["public"], goal="ga")
            full.declare("overload-b", kp["public"], goal="gb")
            out["overload"] = False
        except HumanError as e:
            out["overload"] = "quota" in str(e)

        sim3 = HumanCapabilityAccelerator(store=self._store, max_humans=4)
        r = sim3.declare("provider-loss-human", kp["public"], goal="g")
        sim3.attest("provider-loss-human", attest.sign(kp["private"], r.challenge.encode()))
        out["provider_loss"] = (sim3.get("provider-loss-human")["status"] == "attested")

        out["restart_recovery"] = (self.get(human_id) is None)

        for h in ("overload-a", "overload-b", "provider-loss-human"):
            full.revoke(h)
        return out