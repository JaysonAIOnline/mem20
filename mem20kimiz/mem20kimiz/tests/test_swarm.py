"""Hermetic tests for the mem20kimiz SwarmService mode controller."""

import unittest

from mem20kimiz.swarm import SwarmModeTrigger, SwarmService


class SwarmServiceTests(unittest.TestCase):
    def test_starts_inactive(self):
        svc = SwarmService()
        self.assertFalse(svc.is_active)
        self.assertIsNone(svc.get_trigger())

    def test_enter_and_exit(self):
        svc = SwarmService()
        svc.enter("manual")
        self.assertTrue(svc.is_active)
        self.assertEqual(svc.get_trigger(), "manual")
        svc.exit()
        self.assertFalse(svc.is_active)

    def test_idempotent_enter(self):
        svc = SwarmService()
        svc.enter("tool")
        svc.enter("task")
        self.assertEqual(svc.get_trigger(), "tool")
        svc.exit()
        svc.enter("task")
        self.assertEqual(svc.get_trigger(), "task")

    def test_all_trigger_values_accepted(self):
        for trigger in ("manual", "task", "tool"):
            svc = SwarmService()
            svc.enter(trigger)  # type: ignore[arg-type]
            self.assertEqual(svc.get_trigger(), trigger)

    def test_auto_exit_for_non_manual_triggers(self):
        for trigger in ("task", "tool"):
            svc = SwarmService()
            svc.enter(trigger)  # type: ignore[arg-type]
            svc.on_turn_ended()
            self.assertFalse(svc.is_active)

    def test_manual_survives_turn_end(self):
        svc = SwarmService()
        svc.enter("manual")
        svc.on_turn_ended()
        self.assertTrue(svc.is_active)

    def test_exit_records_reminder(self):
        svc = SwarmService()
        svc.enter("task")
        svc.exit()
        kinds = [r["kind"] for r in svc.reminders]
        self.assertIn("swarm_mode", kinds)
        self.assertIn("swarm_mode_exit", kinds)

    def test_timeline_records_entries_and_exits(self):
        svc = SwarmService()
        svc.enter("tool")
        svc.exit()
        svc.enter("manual")
        svc.exit()
        entries = [s["trigger"] for s in svc.timeline()]
        self.assertEqual(entries, ["tool", "tool", "manual", "manual"])

    def test_injection_disclosure(self):
        svc = SwarmService()
        self.assertEqual(svc.injection_disclosure()["state"], "inactive")
        svc.enter("manual")
        self.assertEqual(svc.injection_disclosure()["state"], "active")
        svc.exit()
        self.assertEqual(svc.injection_disclosure()["state"], "inactive")


if __name__ == "__main__":
    unittest.main()