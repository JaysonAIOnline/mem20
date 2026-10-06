"""Guard that Sarge will not emit a card whose dependencies are unmet.

The real defect this prevents, seen on the live board on 2026-10-03: a
twenty-step roadmap with an explicit dependency spine was flattened into twenty
independent Backlog cards. Every step became pickable at once, so eleven steps
that depend on a pinned API contract were advertised as available work while
that contract did not exist anywhere on disk.

A dependency is satisfied only when the phase it names is itself marked
completed. Anything else -- unmet, unresolvable, self-referential -- is
treated as NOT satisfied. Failing closed is the whole point: an unresolvable
reference must never be read as permission to proceed.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mem20kanbanz.sarge import (  # noqa: E402
    Outcome,
    Phase,
    read_phases,
    load_roadmap,
    run_once,
    watermark,
)


class RecordingDoor:
    """Captures the cards Sarge would create, without a door."""

    def __init__(self) -> None:
        self.cards: list[str] = []

    def add_card(self, board, title, content="", assignee="", tags=(),
                 column="", metadata=None):
        self.cards.append(title)
        return type("C", (), {"id": f"card-{len(self.cards)}"})()


def write_roadmap(directory: Path, name: str, phases: list) -> Path:
    path = directory / f"{name}.json"
    path.write_text(json.dumps({"name": name, "description": "dep test",
                                "phases": phases}, indent=2), encoding="utf-8")
    return path


def phases_of(path: Path):
    data = load_roadmap(path)
    assert data is not None
    return list(read_phases(path, data))


class TestDependsOnIsParsed(unittest.TestCase):
    def test_integer_dependency_is_read(self):
        with tempfile.TemporaryDirectory() as td:
            p = write_roadmap(Path(td), "r", [
                {"name": "Step 0: one", "status": "planned", "notes": ""},
                {"name": "Step 1: two", "status": "planned", "notes": "",
                 "depends_on": [0]},
            ])
            got = phases_of(p)
            self.assertEqual(got[0].depends_on, ())
            self.assertEqual(got[1].depends_on, (0,))

    def test_string_dependency_is_read(self):
        with tempfile.TemporaryDirectory() as td:
            p = write_roadmap(Path(td), "r", [
                {"name": "Step 0: one", "status": "planned", "notes": ""},
                {"name": "Step 1: two", "status": "planned", "notes": "",
                 "depends_on": ["0"]},
            ])
            self.assertEqual(phases_of(p)[1].depends_on, (0,))

    def test_absent_field_means_no_dependencies(self):
        with tempfile.TemporaryDirectory() as td:
            p = write_roadmap(Path(td), "r", [
                {"name": "Step 0: one", "status": "planned", "notes": ""},
            ])
            self.assertEqual(phases_of(p)[0].depends_on, ())

    def test_malformed_dependencies_are_ignored_not_fatal(self):
        """A bad reference must not stop the roadmap being read."""
        with tempfile.TemporaryDirectory() as td:
            p = write_roadmap(Path(td), "r", [
                {"name": "Step 0: one", "status": "planned", "notes": "",
                 "depends_on": "not-a-list"},
            ])
            self.assertEqual(phases_of(p)[0].depends_on, ())


class TestDependencyGating(unittest.TestCase):
    def _run(self, phases):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        d = Path(td.name)
        # Watermark first, then write. The watermark exists to hide roadmaps
        # that predate Sarge, so a roadmap written before this line is correctly
        # invisible and testing dependency gating that way proves nothing.
        state = d / "sarge.json"
        mark = watermark(state)
        write_roadmap(d, "r", phases)
        door = RecordingDoor()
        outcome = run_once(door, board="Fleet HQ", roadmaps_dir=d,
                           since=mark, dry_run=False)
        return door, outcome

    def test_unmet_dependency_blocks_the_card(self):
        """The defect: a dependent step must not be advertised as pickable."""
        door, outcome = self._run([
            {"name": "Step 0: ground", "status": "planned", "notes": ""},
            {"name": "Step 1: build on it", "status": "planned", "notes": "",
             "depends_on": [0]},
        ])
        self.assertIn("Step 0: ground", door.cards)
        self.assertNotIn("Step 1: build on it", door.cards)
        self.assertEqual(outcome.blocked_dependency, 1)

    def test_completed_dependency_unblocks_the_card(self):
        door, outcome = self._run([
            {"name": "Step 0: ground", "status": "completed", "notes": ""},
            {"name": "Step 1: build on it", "status": "planned", "notes": "",
             "depends_on": [0]},
        ])
        self.assertNotIn("Step 0: ground", door.cards)  # completed: no card
        self.assertIn("Step 1: build on it", door.cards)
        self.assertEqual(outcome.blocked_dependency, 0)

    def test_chain_only_the_ready_head_is_created(self):
        """0 -> 1 -> 2 with nothing done: only step 0 is pickable."""
        door, outcome = self._run([
            {"name": "Step 0: a", "status": "planned", "notes": ""},
            {"name": "Step 1: b", "status": "planned", "notes": "",
             "depends_on": [0]},
            {"name": "Step 2: c", "status": "planned", "notes": "",
             "depends_on": [1]},
        ])
        self.assertEqual(door.cards, ["Step 0: a"])
        self.assertEqual(outcome.blocked_dependency, 2)

    def test_chain_completing_the_head_unblocks_only_the_next(self):
        door, _ = self._run([
            {"name": "Step 0: a", "status": "completed", "notes": ""},
            {"name": "Step 1: b", "status": "planned", "notes": "",
             "depends_on": [0]},
            {"name": "Step 2: c", "status": "planned", "notes": "",
             "depends_on": [1]},
        ])
        self.assertEqual(door.cards, ["Step 1: b"])

    def test_unresolvable_dependency_fails_closed(self):
        """An unknown reference must never be read as permission to proceed."""
        door, outcome = self._run([
            {"name": "Step 9: orphan", "status": "planned", "notes": "",
             "depends_on": [42]},
        ])
        self.assertEqual(door.cards, [])
        self.assertEqual(outcome.blocked_dependency, 1)

    def test_self_dependency_does_not_hang_or_create(self):
        """Bounded: a self-referential phase is blocked, never looped on."""
        door, outcome = self._run([
            {"name": "Step 0: selfish", "status": "planned", "notes": "",
             "depends_on": [0]},
        ])
        self.assertEqual(door.cards, [])
        self.assertEqual(outcome.blocked_dependency, 1)

    def test_dependency_satisfied_regardless_of_its_own_card(self):
        """A dependency marked completed is done even with no card of its own."""
        door, _ = self._run([
            {"name": "Step 0: a", "status": "completed", "notes": ""},
            {"name": "Step 1: b", "status": "planned", "notes": "",
             "depends_on": [0]},
        ])
        self.assertEqual(door.cards, ["Step 1: b"])

    def test_roadmap_without_dependencies_is_unchanged(self):
        """No depends_on anywhere means every phase behaves as before."""
        door, outcome = self._run([
            {"name": "Step 0: a", "status": "planned", "notes": ""},
            {"name": "Step 1: b", "status": "planned", "notes": ""},
        ])
        self.assertEqual(door.cards, ["Step 0: a", "Step 1: b"])
        self.assertEqual(outcome.blocked_dependency, 0)


class TestOutcomeReporting(unittest.TestCase):
    def test_summary_counts_blocked_dependencies(self):
        text = Outcome(blocked_dependency=3).summary
        self.assertIn("3", text)
        self.assertIn("blocked", text.lower())


if __name__ == "__main__":
    unittest.main()