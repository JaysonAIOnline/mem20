"""mem20sensez tests — gap mapper, replanner, workflow twin, exec twin, service."""
from __future__ import annotations

import json
import sys
import os
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mem20sensez.gapper import GapMapper
from mem20sensez.ucg_client import UcgClient
from mem20sensez.replanner import PhaseReplanner
from mem20sensez.workflow_twin import WorkflowTwin
from mem20sensez.exec_twin import ExecTwin
from mem20sensez.service import SenseService
from mem20sensez.accelerator import HumanCapabilityAccelerator, HumanError
from mem20sensez.enroller import DeviceEnrollmentAutopilot, EnrollmentError
from mem20sensez import attest


CAPS = [
    {"id": "cap.sense-gap.v1", "name": "capability-gap-mapper", "provider": "p1",
     "outputs": ["sense/gap/report"], "inputs": ["goal"], "metadata": {"tags": ["sense"]},
     "state": "active"},
    {"id": "cap.cv-inference.v1", "name": "cv-inference", "provider": "p2",
     "outputs": ["cv/features"], "inputs": ["image_path"], "metadata": {"tags": ["vision"]},
     "state": "active"},
]


class _FakeService:
    def __init__(self, caps):
        self.store = _Store([dict(c) for c in caps])

    def query(self, body):
        return [c for c in self.store.all() if c["state"] == "active"]


class _Store:
    def __init__(self, caps):
        self._caps = caps

    def all_capabilities(self):
        return [dict(c) for c in self._caps]


def _as_cap(d):
    return dict(d)


class TestGapMapper(unittest.TestCase):
    def test_maps_known_goal(self):
        svc = _FakeService(CAPS)
        client = UcgClient(service=svc)
        report = GapMapper(client).map("capability gap mapper")
        self.assertEqual(len(report.matched), 1)
        self.assertEqual(report.matched[0]["id"], "cap.sense-gap.v1")
        self.assertEqual(report.coverage_ratio, 1.0)

    def test_reports_missing_tokens(self):
        svc = _FakeService(CAPS)
        client = UcgClient(service=svc)
        report = GapMapper(client).map("quantum teleportation sensor platform")
        self.assertIn("quantum", report.missing_tokens)
        self.assertEqual(report.matched, [])
        self.assertLess(report.coverage_ratio, 1.0)


class TestReplanner(unittest.TestCase):
    def test_replan_order_and_ids(self):
        svc = _FakeService(CAPS)
        client = UcgClient(service=svc)
        report = GapMapper(client).map("cv features")
        rp = PhaseReplanner(["plan", "build", "verify", "ship"])
        plan = rp.replan(report)
        self.assertEqual(len(plan.phases), 4)
        self.assertEqual(len(plan.order), 4)
        self.assertTrue(plan.plan_id)

    def test_journal_false_no_braid(self):
        svc = _FakeService(CAPS)
        report = GapMapper(UcgClient(service=svc)).map("cv features")
        plan = PhaseReplanner(["plan", "build"]).replan(report)
        self.assertEqual(plan.braid, None)


class TestWorkflowTwin(unittest.TestCase):
    def test_digest_hermetic(self):
        tw = WorkflowTwin(
            self_model_rows=[{"content": "Self-Model: big-pickle agent"}],
            memory_rows=[{"content": "phase 1 sense organs"}],
        )
        d = tw.digest()
        self.assertIn("big-pickle", d.identity)
        self.assertEqual(len(d.active_threads), 1)


class TestExecTwin(unittest.TestCase):
    def test_runs_real_graph(self):
        et = ExecTwin()
        et.build([
            {"name": "a", "action": "add 1", "value": 1, "key": "acc"},
            {"name": "b", "action": "add 2", "value": 2, "key": "acc"},
        ])
        plan = et.run({"acc": 0})
        self.assertEqual(plan.final_state.get("acc"), 3)
        self.assertEqual(len(plan.steps), 2)
        self.assertEqual(plan.steps[0].post["acc"], 1)

    def test_requires_build(self):
        et = ExecTwin()
        with self.assertRaises(ValueError):
            et.run({})


class TestSenseService(unittest.TestCase):
    def test_health(self):
        h = SenseService(ucg_service=_FakeService(CAPS)).health()
        self.assertTrue(h["ok"])
        self.assertEqual(h["ucg_capabilities"], 2)


class TestAttest(unittest.TestCase):
    def test_sign_verify_roundtrip(self):
        kp = attest.generate_keypair()
        msg = b"hello trust bridge"
        sig = attest.sign(kp["private"], msg)
        self.assertTrue(attest.verify(kp["public"], msg, sig))

    def test_verify_rejects_bad_signature(self):
        kp = attest.generate_keypair()
        sig = attest.sign(kp["private"], b"msg")
        self.assertFalse(attest.verify(kp["public"], b"other", sig))

    def test_credentials_are_fresh(self):
        self.assertNotEqual(attest.new_credential(), attest.new_credential())


def _tmp_store():
    d = tempfile.mkdtemp(prefix="sensez-test-")
    return d


class TestEnroller(unittest.TestCase):
    def test_full_lifecycle(self):
        store = _tmp_store()
        en = DeviceEnrollmentAutopilot(store=store)
        kp = attest.generate_keypair()
        r = en.declare("dev-1", kp["public"], hostname="h1")
        self.assertEqual(r.status, "challenge")
        self.assertTrue(r.challenge)
        r2 = en.attest("dev-1", attest.sign(kp["private"], r.challenge.encode()))
        self.assertEqual(r2.status, "attested")
        r3 = en.enroll("dev-1")
        self.assertEqual(r3.status, "enrolled")
        r4 = en.provision("dev-1")
        self.assertEqual(r4.status, "provisioned")
        self.assertTrue(r4.credential)
        nonce = attest.new_nonce()
        r5 = en.validate("dev-1", attest.sign(kp["private"], nonce.encode()), nonce=nonce)
        self.assertEqual(r5.status, "validated")
        self.assertIsNotNone(r5.validated_at)

    def test_bad_signature_rejected(self):
        store = _tmp_store()
        en = DeviceEnrollmentAutopilot(store=store)
        kp = attest.generate_keypair()
        r = en.declare("dev-2", kp["public"])
        with self.assertRaises(EnrollmentError):
            en.attest("dev-2", "deadbeef")

    def test_resume_is_idempotent(self):
        store = _tmp_store()
        en = DeviceEnrollmentAutopilot(store=store)
        kp = attest.generate_keypair()
        r1 = en.declare("dev-3", kp["public"])
        r2 = en.declare("dev-3", kp["public"])
        self.assertEqual(r1.challenge, r2.challenge)
        self.assertEqual(r2.step, "resume")

    def test_advance_resumable_worker(self):
        store = _tmp_store()
        en = DeviceEnrollmentAutopilot(store=store)
        kp = attest.generate_keypair()
        en.advance("dev-4", "declare", public_key=kp["public"])
        dev = en.get("dev-4")
        chal = dev["challenge"]
        en.advance("dev-4", "attest", signature=attest.sign(kp["private"], chal.encode()))
        self.assertEqual(en.get("dev-4")["status"], "attested")

    def test_simulator_reports_all_scenarios(self):
        store = _tmp_store()
        en = DeviceEnrollmentAutopilot(store=store)
        kp = attest.generate_keypair()
        result = en.simulator(keypair=kp, max_devices=3)
        for scenario, passed in result.items():
            self.assertTrue(passed, f"scenario {scenario} failed")


class TestAccelerator(unittest.TestCase):
    def test_full_admission_and_growth(self):
        store = _tmp_store()
        acc = HumanCapabilityAccelerator(store=store)
        kp = attest.generate_keypair()
        r = acc.declare("human-1", kp["public"], goal="become a better builder")
        self.assertEqual(r.status, "pending")
        r2 = acc.attest("human-1", attest.sign(kp["private"], r.challenge.encode()))
        self.assertEqual(r2.status, "attested")
        r3 = acc.admit("human-1")
        self.assertEqual(r3.status, "admitted")
        self.assertTrue(r3.credential)
        r4 = acc.record_growth("human-1", "coding", "delivery_speed", 2.0)
        self.assertEqual(r4.progress[0]["delta"], 2.0)
        s = acc.summary()
        self.assertEqual(s["humans_admitted"], 1)
        self.assertEqual(s["cumulative_growth_delta"], 2.0)

    def test_progress_aggregates_events(self):
        store = _tmp_store()
        acc = HumanCapabilityAccelerator(store=store)
        kp = attest.generate_keypair()
        r = acc.declare("human-2", kp["public"], goal="g")
        acc.attest("human-2", attest.sign(kp["private"], r.challenge.encode()))
        acc.admit("human-2")
        acc.record_growth("human-2", "memory", "retention", 1.0)
        acc.record_growth("human-2", "memory", "retention", 0.5)
        p = acc.progress("human-2")
        self.assertEqual(p[0]["delta"], 1.5)
        self.assertEqual(p[0]["count"], 2)

    def test_rejects_unattested_admission(self):
        store = _tmp_store()
        acc = HumanCapabilityAccelerator(store=store)
        kp = attest.generate_keypair()
        acc.declare("human-3", kp["public"], goal="g")
        with self.assertRaises(HumanError):
            acc.admit("human-3")

    def test_simulator_reports_all_scenarios(self):
        store = _tmp_store()
        acc = HumanCapabilityAccelerator(store=store)
        kp = attest.generate_keypair()
        result = acc.simulator(keypair=kp, max_humans=3)
        for scenario, passed in result.items():
            self.assertTrue(passed, f"scenario {scenario} failed")


class TestServiceBridge(unittest.TestCase):
    def test_accelerate_summary(self):
        svc = SenseService(ucg_service=_FakeService(CAPS))
        out = svc.accelerate("summary", "human-x")
        self.assertIn("humans_total", out)

    def test_enroll_list(self):
        svc = SenseService(ucg_service=_FakeService(CAPS))
        out = svc.enroll("list", "device-x")
        self.assertIn("devices", out)


if __name__ == "__main__":
    unittest.main()