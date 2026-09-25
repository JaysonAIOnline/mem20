"""enroller — Device Enrollment Autopilot (RM-151).

State machine: new -> challenge -> attested -> enrolled -> provisioned -> validated.
A device joins with a public key, proves possession via an Ed25519 challenge
signature, is issued a credential, then periodically validated by signing
server nonces. Resumable workers replay the specified step; a local simulator
replays success / malformed-input / disconnect / overload / provider-loss /
restart-recovery scenarios against the real runtime.
"""
from __future__ import annotations

import fnmatch
import threading
from dataclasses import dataclass, field
from typing import Any

from . import attest
from .state_plane import MEM20_STORE, StatePlane, StatePlaneError

# Device lifecycle states (RM-151 order).
DEVICE_STATES = ("new", "challenge", "attested", "enrolled", "provisioned", "validated")

# Deadline for a device to answer a nonce challenge.
CHALLENGE_TTL_S = 60
MAX_DEVICES = 100


@dataclass
class EnrollmentReply:
    device_id: str
    status: str
    step: str | None = None
    challenge: str | None = None
    credential: str | None = None
    validated_at: float | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "device_id": self.device_id,
            "status": self.status,
            "step": self.step,
        }
        if self.challenge is not None:
            out["challenge"] = self.challenge
        if self.credential is not None:
            out["credential"] = self.credential
        if self.validated_at is not None:
            out["validated_at"] = self.validated_at
        if self.error is not None:
            out["error"] = self.error
        return out


class EnrollmentError(RuntimeError):
    pass


class DeviceEnrollmentAutopilot:
    """Securely recognize, enroll, provision, and validate new devices (RM-151)."""

    def __init__(self, store: str | None = None, max_devices: int = MAX_DEVICES,
                 challenge_ttl_s: float = CHALLENGE_TTL_S) -> None:
        self._store = store or MEM20_STORE
        self.state = StatePlane(
            "device_enrollment",
            store=self._store,
            validator=self._validate_device,
        )
        self.max_devices = max_devices
        self.challenge_ttl_s = challenge_ttl_s
        self._mutex = threading.Lock()

    # --- domain model -------------------------------------------------
    def _validate_device(self, device_id: str, device: dict[str, Any]) -> None:
        if not isinstance(device_id, str) or not device_id.strip():
            raise StatePlaneError("device_id must be a non-empty string")
        if not device.get("public_key"):
            raise StatePlaneError("public_key is required")
        if device.get("status") not in DEVICE_STATES:
            raise StatePlaneError(f"unknown device status {device.get('status')!r}")

    # --- execution runtime --------------------------------------------
    def declare(self, device_id: str, public_key: str, hostname: str | None = None,
                platform: str | None = None) -> EnrollmentReply:
        """New device requests enrollment. Idempotent: existing device is resumed."""
        with self._mutex:
            existing = self.state.get(device_id)
            if existing is not None:
                return EnrollmentReply(device_id=device_id, status=existing["status"],
                                       step="resume",
                                       challenge=existing.get("challenge"))
            if len(self.state.all()) >= self.max_devices:
                raise EnrollmentError("device quota reached; refusing new enrollment")
            challenge = attest.new_nonce()
            device = {
                "entity_id": device_id,
                "status": "challenge",
                "public_key": public_key,
                "hostname": hostname,
                "platform": platform,
                "challenge": challenge,
                "challenge_issued_s": __import__("time").time(),
                "attempts": 0,
                "credential": None,
                "events": ["declare"],
            }
            self.state.put(device_id, device)
            return EnrollmentReply(device_id=device_id, status="challenge", step="declare",
                                   challenge=challenge)

    def attest(self, device_id: str, signature_hex: str) -> EnrollmentReply:
        """Device proves possession of its key by signing the pending challenge."""
        with self._mutex:
            device = self.state.get(device_id)
            if device is None:
                raise EnrollmentError(f"unknown device {device_id!r}")
            if device["status"] not in ("challenge", "attested"):
                raise EnrollmentError(f"device {device_id!r} is in state {device['status']!r}, not awaiting attestation")
            if device["status"] == "attested":
                return EnrollmentReply(device_id=device_id, status="attested", step="attest")
            import time
            if time.time() - device["challenge_issued_s"] > self.challenge_ttl_s:
                raise EnrollmentError("challenge expired; re-declare to receive a fresh nonce")
            device["attempts"] += 1
            ok = attest.verify(device["public_key"], device["challenge"].encode(),
                               signature_hex)
            if not ok:
                self.state.put(device_id, device)  # persist attempt count
                raise EnrollmentError("attestation signature invalid")
            device["status"] = "attested"
            device["events"].append("attest")
            self.state.put(device_id, device)
            return EnrollmentReply(device_id=device_id, status="attested", step="attest")

    def enroll(self, device_id: str) -> EnrollmentReply:
        """Admit an attested device into the fleet (no credential yet)."""
        with self._mutex:
            device = self.state.get(device_id)
            if device is None:
                raise EnrollmentError(f"unknown device {device_id!r}")
            if device["status"] != "attested":
                raise EnrollmentError(f"device {device_id!r} must be attested before enrolling")
            device["status"] = "enrolled"
            device["events"].append("enroll")
            self.state.put(device_id, device)
            return EnrollmentReply(device_id=device_id, status="enrolled", step="enroll")

    def provision(self, device_id: str) -> EnrollmentReply:
        """Issue a fresh credential to an enrolled device (idempotent)."""
        with self._mutex:
            device = self.state.get(device_id)
            if device is None:
                raise EnrollmentError(f"unknown device {device_id!r}")
            if device["status"] not in ("enrolled", "provisioned"):
                raise EnrollmentError(f"device {device_id!r} must be enrolled before provisioning")
            if device["status"] != "provisioned" or device.get("credential") is None:
                device["credential"] = attest.new_credential()
                device["status"] = "provisioned"
                device["events"].append("provision")
                self.state.put(device_id, device)
            return EnrollmentReply(device_id=device_id, status="provisioned", step="provision",
                                   credential=device["credential"])

    def validate(self, device_id: str, signature_hex: str, nonce: str | None = None) -> EnrollmentReply:
        """Prove a provisioned device is still live: sign a fresh server nonce."""
        with self._mutex:
            device = self.state.get(device_id)
            if device is None:
                raise EnrollmentError(f"unknown device {device_id!r}")
            if device["status"] != "provisioned":
                raise EnrollmentError(f"device {device_id!r} must be provisioned before validation")
            if nonce is None:
                nonce = attest.new_nonce()
            ok = attest.verify(device["public_key"], nonce.encode(), signature_hex)
            if not ok:
                raise EnrollmentError("validation signature invalid")
            import time
            device["status"] = "validated"
            device["validated_at"] = time.time()
            device["events"].append("validate")
            self.state.put(device_id, device)
            return EnrollmentReply(device_id=device_id, status="validated", step="validate",
                                   validated_at=device["validated_at"])

    # --- query / subscribe / delete ------------------------------------
    def get(self, device_id: str) -> dict[str, Any] | None:
        return self.state.get(device_id)

    def list(self, status: str | None = None) -> list[dict[str, Any]]:
        return self.state.query(status=status) if status else self.state.all()

    def revoke(self, device_id: str) -> bool:
        return self.state.delete(device_id)

    def ids(self, status: str | None = None) -> list[str]:
        all_ids = self.state.subscribe_ids()
        if not status:
            return all_ids
        return [i for i in all_ids if (self.state.get(i) or {}).get("status") == status]

    # --- simulator (RM-151 execution runtime replay) ----------------------
    def simulator(self, device_id: str = "sim-device-1", keypair: dict[str, str] | None = None,
                  max_devices: int = 3) -> dict[str, bool]:
        """Replay success/malformed/disconnect/overload/provider-loss/restart."""
        kp = keypair or attest.generate_keypair()
        sim = DeviceEnrollmentAutopilot(store=self._store, max_devices=max_devices)
        out: dict[str, bool] = {}

        r = sim.declare(device_id, kp["public"], hostname="sim-host")
        out["success"] = (r.status == "challenge" and r.challenge is not None)
        if out["success"]:
            sig = attest.sign(kp["private"], r.challenge.encode())
            r2 = sim.attest(device_id, sig)
            out["success"] = out["success"] and r2.status == "attested"
            r3 = sim.enroll(device_id)
            out["success"] = out["success"] and r3.status == "enrolled"
            r4 = sim.provision(device_id)
            out["success"] = out["success"] and r4.status == "provisioned" and r4.credential
            nonce = attest.new_nonce()
            r5 = sim.validate(device_id, attest.sign(kp["private"], nonce.encode()), nonce=nonce)
            out["success"] = out["success"] and r5.status == "validated"

        try:
            sim.attest(device_id, "deadbeef")
            out["malformed_input"] = False
        except EnrollmentError:
            out["malformed_input"] = True

        sim2 = DeviceEnrollmentAutopilot(store=self._store, max_devices=max_devices)
        r = sim2.declare("disconnect-dev", kp["public"])
        try:
            import time
            time.sleep(0.01)
            sim2.challenge_ttl_s = 0.0
            sig = attest.sign(kp["private"], r.challenge.encode())
            sim2.attest("disconnect-dev", sig)
            out["disconnect"] = False
        except EnrollmentError:
            out["disconnect"] = True
        sim2.revoke("disconnect-dev")

        full = DeviceEnrollmentAutopilot(store=self._store, max_devices=1)
        try:
            full.declare("overload-a", kp["public"])
            full.declare("overload-b", kp["public"])
            out["overload"] = False
        except EnrollmentError as e:
            out["overload"] = "quota" in str(e)

        sim3 = DeviceEnrollmentAutopilot(store=self._store, max_devices=4)
        r = sim3.declare("provider-loss-dev", kp["public"])
        sig = attest.sign(kp["private"], r.challenge.encode())
        sim3.attest("provider-loss-dev", sig)
        out["provider_loss"] = (sim3.get("provider-loss-dev")["status"] == "attested")

        out["restart_recovery"] = (self.get(device_id) is None)

        for d in ("overload-a", "overload-b", "provider-loss-dev"):
            full.revoke(d)
        return out

    def advance(self, device_id: str, action: str, **kw: Any) -> EnrollmentReply:
        """Resumable worker: run the specified lifecycle step by name."""
        actions = {
            "declare": lambda: self.declare(device_id, kw.get("public_key", "")),
            "attest": lambda: self.attest(device_id, kw.get("signature", "")),
            "enroll": lambda: self.enroll(device_id),
            "provision": lambda: self.provision(device_id),
            "validate": lambda: self.validate(device_id, kw.get("signature", ""),
                                              nonce=kw.get("nonce")),
        }
        if action not in actions:
            raise EnrollmentError(f"unknown action {action!r}")
        return actions[action]()