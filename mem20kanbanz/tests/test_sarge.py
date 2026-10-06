"""Tests for Sarge, the kanban decomposer.

Hermetic in the same sense as the rest of this suite: a real HTTP server stands
in for the door on an ephemeral loopback port, roadmaps are written into a
temporary directory, and the watermark lives in a temporary state file. No test
here can reach the live door, the real ``/opt/mem20/roadmaps`` or the production
kanban.

The properties worth protecting, in order of how much damage it would do if they
broke:

* **Idempotency.** A second pass must create nothing. Without ``jobid`` this
  tool fills the board with duplicates within minutes.
* **Both phase-name shapes.** 51 of the 318 real phases store ``name`` as a
  nested object. A decomposer that assumes a string silently skips them.
* **Atomic write-back.** Roadmaps are hand-edited source; a truncated one loses
  someone's thinking.
* **Refusal over invention.** A phase with no usable title gets no card.
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mem20kanbanz.door import Door, DoorError  # noqa: E402
from mem20kanbanz.sarge import (  # noqa: E402
    JOB_FIELD,
    MIN_INTERVAL,
    Phase,
    SargeError,
    card_content,
    card_metadata,
    decompose_phase,
    load_roadmap,
    phase_title,
    run_once,
    scan,
    serve,
    stamp_jobid,
    watermark,
    wants_card,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_mem20kanbanz import DoorServer  # noqa: E402


def write_roadmap(directory: Path, name: str, phases: list,
                  description: str = "A test roadmap") -> Path:
    """Write a roadmap file. ``phases`` are raw dicts, shapes included."""
    path = directory / f"{name}.json"
    path.write_text(json.dumps({"name": name, "description": description,
                                "phases": phases}, indent=2),
                    encoding="utf-8")
    return path


def string_phase(title: str, status: str = "planned", **extra) -> dict:
    return {"name": title, "status": status, "notes": "", **extra}


def nested_phase(title: str, status: str = "planned", **extra) -> dict:
    """The malformed shape the real roadmaps actually contain."""
    return {"name": {"name": title, "status": status},
            "status": status, "notes": "", **extra}


class TestPhaseTitle(unittest.TestCase):
    def test_plain_string_name(self):
        self.assertEqual(phase_title({"name": "Do the thing"}), "Do the thing")

    def test_nested_object_name_is_recovered(self):
        raw = {"name": {"name": "Phase 1: Audit", "status": "in_progress"},
               "status": "planned"}
        self.assertEqual(phase_title(raw), "Phase 1: Audit")

    def test_nested_without_inner_name_is_refused(self):
        self.assertEqual(phase_title({"name": {"status": "planned"}}), "")

    def test_missing_name_is_refused_not_invented(self):
        self.assertEqual(phase_title({"status": "planned"}), "")
        self.assertEqual(phase_title({}), "")

    def test_whitespace_is_trimmed(self):
        self.assertEqual(phase_title({"name": "  spaced  "}), "spaced")


class TestLoadRoadmap(unittest.TestCase):
    def test_malformed_json_is_skipped_not_raised(self):
        with TemporaryDirectory() as td:
            bad = Path(td) / "broken.json"
            bad.write_text("{not json at all", encoding="utf-8")
            self.assertIsNone(load_roadmap(bad))

    def test_json_without_phases_is_not_a_roadmap(self):
        with TemporaryDirectory() as td:
            path = Path(td) / "other.json"
            path.write_text(json.dumps({"name": "x", "notes": "hi"}),
                            encoding="utf-8")
            self.assertIsNone(load_roadmap(path))

    def test_malformed_file_is_left_byte_identical(self):
        """Detection must never rewrite what it inspected."""
        with TemporaryDirectory() as td:
            path = Path(td) / "broken.json"
            original = "{not json at all"
            path.write_text(original, encoding="utf-8")
            load_roadmap(path)
            self.assertEqual(path.read_text(encoding="utf-8"), original)


class TestWantsCard(unittest.TestCase):
    @staticmethod
    def phase(jobid=None, status="planned") -> Phase:
        return Phase(roadmap="r", roadmap_description="", path=Path("/x.json"),
                     index=0, title="t", status=status, notes="", jobid=jobid)

    def test_planned_phase_wants_a_card(self):
        self.assertTrue(wants_card(self.phase()))

    def test_phase_with_a_jobid_is_skipped(self):
        self.assertFalse(wants_card(self.phase(jobid="abc")))

    def test_completed_phase_is_skipped(self):
        self.assertFalse(wants_card(self.phase(status="completed")))

    def test_blocked_phase_is_skipped(self):
        self.assertFalse(wants_card(self.phase(status="blocked")))

    def test_status_is_case_insensitive(self):
        self.assertFalse(wants_card(self.phase(status="Completed")))


class TestScan(unittest.TestCase):
    def test_yields_both_phase_shapes(self):
        with TemporaryDirectory() as td:
            d = Path(td)
            write_roadmap(d, "mixed", [string_phase("plain one"),
                                       nested_phase("nested one")])
            titles = sorted(p.title for p in scan(d))
            self.assertEqual(titles, ["nested one", "plain one"])

    def test_phase_without_a_title_is_dropped(self):
        with TemporaryDirectory() as td:
            d = Path(td)
            write_roadmap(d, "gap", [{"name": {"status": "planned"}},
                                      string_phase("real one")])
            self.assertEqual([p.title for p in scan(d)], ["real one"])

    def test_missing_directory_yields_nothing(self):
        self.assertEqual(list(scan(Path("/nonexistent/roadmaps"))), [])


class TestWatermark(unittest.TestCase):
    def test_first_call_records_it(self):
        with TemporaryDirectory() as td:
            state = Path(td) / "sarge.json"
            first = watermark(state)
            self.assertIsInstance(first, float)
            self.assertEqual(watermark(state), first)

    def test_create_false_does_not_stamp(self):
        with TemporaryDirectory() as td:
            state = Path(td) / "sarge.json"
            self.assertIsNone(watermark(state, create=False))
            self.assertFalse(state.exists())

    def test_roadmap_older_than_the_watermark_is_invisible(self):
        """The behaviour Jayson asked for: only roadmaps made after Sarge."""
        with TemporaryDirectory() as td:
            d = Path(td)
            state = d / "sarge.json"
            old = write_roadmap(d, "old", [string_phase("ancient work")])
            os.utime(old, (1000, 1000))
            mark = watermark(state)
            assert mark is not None
            self.assertEqual(list(scan(d, since=mark)), [])
            new = write_roadmap(d, "new", [string_phase("fresh work")])
            os.utime(new, (mark + 10, mark + 10))
            self.assertEqual([p.title for p in scan(d, since=mark)],
                             ["fresh work"])

    def test_a_roadmap_sarge_touched_stays_in_scope(self):
        """Write-back updates mtime, so an already-decomposed roadmap must not
        fall out of scope and be re-read as if it were new."""
        with TemporaryDirectory() as td:
            d = Path(td)
            state = d / "sarge.json"
            path = write_roadmap(d, "r", [string_phase("work")])
            mark = watermark(state)
            assert mark is not None
            os.utime(path, (mark - 100, mark - 100))
            self.assertEqual(list(scan(d, since=mark)), [])
            stamp_jobid(path, 0, "job-1")  # rewrites the file, bumping mtime
            phases = list(scan(d, since=mark))
            self.assertEqual(len(phases), 1)
            self.assertEqual(phases[0].jobid, "job-1")


class TestStampJobid(unittest.TestCase):
    def test_writes_the_id_onto_the_right_phase(self):
        with TemporaryDirectory() as td:
            path = write_roadmap(Path(td), "r", [string_phase("one"),
                                                  string_phase("two")])
            self.assertTrue(stamp_jobid(path, 1, "job-xyz"))
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn(JOB_FIELD, data["phases"][0])
            self.assertEqual(data["phases"][1][JOB_FIELD], "job-xyz")

    def test_stamping_twice_reports_no_change(self):
        with TemporaryDirectory() as td:
            path = write_roadmap(Path(td), "r", [string_phase("one")])
            self.assertTrue(stamp_jobid(path, 0, "job-xyz"))
            self.assertFalse(stamp_jobid(path, 0, "job-xyz"))

    def test_out_of_range_index_changes_nothing(self):
        with TemporaryDirectory() as td:
            path = write_roadmap(Path(td), "r", [string_phase("one")])
            before = path.read_text(encoding="utf-8")
            self.assertFalse(stamp_jobid(path, 9, "job-xyz"))
            self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_write_is_atomic_no_temp_files_left(self):
        with TemporaryDirectory() as td:
            path = write_roadmap(Path(td), "r", [string_phase("one")])
            stamp_jobid(path, 0, "job-xyz")
            leftovers = [p.name for p in Path(td).iterdir() if p.suffix == ".tmp"]
            self.assertEqual(leftovers, [])
            json.loads(path.read_text(encoding="utf-8"))  # still valid


class TestCardContent(unittest.TestCase):
    @staticmethod
    def phase(roadmap_description="Do alpha well.", notes="careful") -> Phase:
        return Phase(roadmap="alpha", roadmap_description=roadmap_description,
                     path=Path("/opt/mem20/roadmaps/alpha.json"), index=2,
                     title="Wire the gate", status="planned", notes=notes)

    def test_content_carries_the_real_provenance(self):
        body = card_content(self.phase())
        for expected in ("alpha", "Do alpha well.", "Wire the gate",
                         "careful", "alpha.json", "alpha#2"):
            self.assertIn(expected, body)

    def test_content_is_never_empty(self):
        """A title-only card is the exact failure this system just removed."""
        self.assertTrue(card_content(self.phase(roadmap_description="",
                                                notes="")).strip())

    def test_metadata_names_the_source_roadmap_and_phase(self):
        meta = card_metadata(self.phase())
        self.assertEqual(meta["source"], "sarge")
        self.assertEqual(meta["roadmap"], "alpha")
        self.assertEqual(meta["phase_index"], 2)


class TestDecomposeAgainstARealDoor(unittest.TestCase):
    """Real HTTP, real client, real wire contract."""

    def setUp(self):
        self._td = TemporaryDirectory()
        self.dir = Path(self._td.name)
        self.state = self.dir / "sarge.json"
        self._server = DoorServer().__enter__()
        self.door = Door(self._server.url)
        self.door.create_board("Fleet HQ", "test board")
        # Stamp first, then write roadmaps. The watermark exists to hide
        # roadmaps that predate Sarge, so a roadmap written before this line is
        # correctly invisible and testing it that way proves nothing about
        # decomposition.
        self.mark = watermark(self.state)
        assert self.mark is not None

    def tearDown(self):
        self._server.__exit__(None, None, None)
        self._td.cleanup()

    def _phases(self):
        return list(scan(self.dir, since=watermark(self.state, create=False)))

    def test_creates_a_card_and_stamps_the_id(self):
        path = write_roadmap(self.dir, "alpha", [string_phase("first task")])
        outcome = run_once(self.door, "Fleet HQ", self.dir,
                           since=self.mark)
        self.assertEqual(len(outcome.created), 1)
        self.assertEqual(outcome.stamped, 1)
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["phases"][0][JOB_FIELD], outcome.created[0][0])
        board = self.door.board("Fleet HQ")
        self.assertEqual(len(board.cards), 1)
        self.assertEqual(board.cards[0].title, "first task")

    def test_card_content_reaches_the_door_not_just_the_title(self):
        write_roadmap(self.dir, "alpha", [string_phase("first task")],
                      description="the real roadmap description")
        run_once(self.door, "Fleet HQ", self.dir, since=self.mark)
        # board() omits content by design (a board listing should not ship every
        # body); card() is the full record, which is what a worker must be sent.
        card_id = self.door.board("Fleet HQ").cards[0].id
        self.assertIn("the real roadmap description",
                      self.door.card(card_id).content)

    def test_second_pass_creates_nothing(self):
        write_roadmap(self.dir, "alpha", [string_phase("first task"),
                                          string_phase("second task")])
        first = run_once(self.door, "Fleet HQ", self.dir, since=self.mark)
        self.assertEqual(len(first.created), 2)
        second = run_once(self.door, "Fleet HQ", self.dir, since=self.mark)
        self.assertEqual(second.created, [])
        self.assertEqual(second.skipped_existing, 2)
        self.assertEqual(len(self.door.board("Fleet HQ").cards), 2)

    def test_ten_passes_create_ten_cards_not_a_hundred(self):
        write_roadmap(self.dir, "alpha", [string_phase("only task")])
        mark = watermark(self.state)
        for _ in range(10):
            run_once(self.door, "Fleet HQ", self.dir, since=self.mark)
        self.assertEqual(len(self.door.board("Fleet HQ").cards), 1)

    def test_completed_phase_never_becomes_a_card(self):
        write_roadmap(self.dir, "alpha", [string_phase("old work",
                                                      status="completed")])
        outcome = run_once(self.door, "Fleet HQ", self.dir,
                           since=self.mark)
        self.assertEqual(outcome.created, [])
        self.assertEqual(outcome.skipped_status, 1)

    def test_nested_name_phase_still_becomes_a_card(self):
        write_roadmap(self.dir, "alpha", [nested_phase("nested but real")])
        outcome = run_once(self.door, "Fleet HQ", self.dir,
                           since=self.mark)
        self.assertEqual([t for _, t in outcome.created], ["nested but real"])

    def test_untitled_phase_gets_no_card(self):
        write_roadmap(self.dir, "alpha", [{"name": {"status": "planned"}}])
        outcome = run_once(self.door, "Fleet HQ", self.dir,
                           since=self.mark)
        self.assertEqual(outcome.created, [])
        self.assertEqual(self.door.board("Fleet HQ").cards, ())

    def test_one_bad_roadmap_does_not_stop_the_others(self):
        (self.dir / "broken.json").write_text("{oh no", encoding="utf-8")
        write_roadmap(self.dir, "good", [string_phase("still works")])
        outcome = run_once(self.door, "Fleet HQ", self.dir,
                           since=self.mark)
        self.assertEqual(len(outcome.created), 1)

    def test_door_failure_is_reported_not_raised(self):
        write_roadmap(self.dir, "alpha", [string_phase("doomed")])
        self._server.state.fail_next = "/api/tasks"
        outcome = run_once(self.door, "Fleet HQ", self.dir,
                           since=self.mark)
        self.assertEqual(outcome.created, [])
        self.assertEqual(len(outcome.failed), 1)
        self.assertIn("alpha#0", outcome.failed[0][0])

    def test_dry_run_creates_nothing_and_stamps_nothing(self):
        path = write_roadmap(self.dir, "alpha", [string_phase("first task")])
        before = path.read_text(encoding="utf-8")
        outcome = run_once(self.door, "Fleet HQ", self.dir,
                           since=watermark(self.state), dry_run=True)
        self.assertEqual(len(outcome.created), 1)
        self.assertEqual(outcome.stamped, 0)
        self.assertEqual(self.door.board("Fleet HQ").cards, ())
        self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_unreachable_door_is_reported_not_fatal(self):
        write_roadmap(self.dir, "alpha", [string_phase("anything")])
        dead = Door("http://127.0.0.1:1")
        outcome = run_once(dead, "Fleet HQ", self.dir,
                           since=self.mark)
        self.assertEqual(outcome.created, [])
        self.assertEqual(len(outcome.failed), 1)


class TestDecomposePhase(unittest.TestCase):
    def test_refuses_when_the_door_refuses(self):
        class Refusing:
            def add_card(self, *a, **k):
                raise DoorError("no")
        with TemporaryDirectory() as td:
            phase = Phase(roadmap="r", roadmap_description="", path=Path("x"),
                          index=0, title="t", status="planned", notes="")
            with self.assertRaises(SargeError):
                decompose_phase(Refusing(), phase, "Fleet HQ")


class TestServe(unittest.TestCase):
    def test_runs_is_bounded(self):
        """No unbounded loop in a test: ``runs`` is how the loop is stopped."""
        class Idle:
            def add_card(self, *a, **k):
                raise AssertionError("should not be called")
        with TemporaryDirectory() as td:
            import io
            done = serve(Idle(), runs=3, interval=MIN_INTERVAL,
                         roadmaps_dir=Path(td), stream=io.StringIO())
            self.assertEqual(done, 0)

    def test_interval_is_clamped_to_the_minimum(self):
        class Idle:
            def add_card(self, *a, **k):
                raise AssertionError("should not be called")
        import io
        with TemporaryDirectory() as td:
            # 0 would otherwise spin as fast as the machine allows.
            serve(Idle(), runs=1, interval=0, roadmaps_dir=Path(td),
                  stream=io.StringIO())


if __name__ == "__main__":
    unittest.main()