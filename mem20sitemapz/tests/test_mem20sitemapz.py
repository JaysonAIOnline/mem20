import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mem20sitemapz import procinfo, report, search, snapshot, watch  # noqa: E402
from mem20sitemapz.index import scan  # noqa: E402
from mem20sitemapz.policy import is_skipped_dir, is_skipped_file, is_source_file, language_of  # noqa: E402


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    ops = tmp_path / "mem20ops" / "mem20ops"
    ops.mkdir(parents=True)
    (ops / "cli.py").write_text("def main():\n    return 0\n", encoding="utf-8")
    (ops / "audit.py").write_text("def audit():\n    pass\n", encoding="utf-8")
    (tmp_path / "mem20ops" / "tests").mkdir()
    (tmp_path / "mem20ops" / "tests" / "test_cli.py").write_text("def test_a():\n    pass\n", encoding="utf-8")
    (tmp_path / "mem20ops" / "README.md").write_text("# mem20ops\n\nOperational workflows.\n", encoding="utf-8")
    (tmp_path / "mem20ops" / "pyproject.toml").write_text(
        '[project]\nname = "mem20ops"\nversion = "0.1.0"\n'
        'description = "Operational workflows."\nkeywords = ["mem20", "ops"]\n'
        '[project.scripts]\nfs-ops = "mem20ops.cli:main"\n',
        encoding="utf-8",
    )
    cog = tmp_path / "cog"
    cog.mkdir()
    (cog / "engine.py").write_text("class Engine:\n    pass\n", encoding="utf-8")
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "junk.pyc").write_bytes(b"\x00\x01")
    junk = tmp_path / "node_modules"
    junk.mkdir()
    (junk / "big.js").write_text("var x=1\n", encoding="utf-8")
    return tmp_path


def test_policy_classification():
    assert is_skipped_dir("__pycache__")
    assert is_skipped_dir("node_modules")
    assert is_skipped_dir("secrets")
    assert is_skipped_dir("mem20ops.egg-info")
    assert not is_skipped_dir("mem20ops")
    assert is_skipped_file(Path("a.pyc"))
    assert is_skipped_file(Path("model.safetensors"))
    assert is_skipped_file(Path("state.db"))
    assert not is_skipped_file(Path("cli.py"))
    assert is_source_file(Path("cli.py"))
    assert is_source_file(Path("Makefile"))
    assert not is_source_file(Path("photo.png"))
    assert language_of(Path("x.py")) == "python"
    assert language_of(Path("x.ts")) == "typescript"


def test_scan_indexes_subsystems_and_skips_noise(tree: Path):
    index = scan(tree, max_depth=2)
    names = {s["name"] for s in index["subsystems"]}
    assert "mem20ops" in names
    assert "cog" in names
    assert index["totals"]["subsystems"] == 2
    entry = next(s for s in index["subsystems"] if s["name"] == "mem20ops")
    assert entry["category"] == "organ"
    assert entry["entry_points"] == {"fs-ops": "mem20ops.cli:main"}
    assert entry["test_files"] == 1
    assert entry["line_count"] > 0
    assert entry["packaged"] is True
    cog = next(s for s in index["subsystems"] if s["name"] == "cog")
    assert cog["category"] == "service"
    assert cog["packaged"] is False


def test_scan_excludes_caches_and_node_modules(tree: Path):
    index = scan(tree, max_depth=2)
    entry = next(s for s in index["subsystems"] if s["name"] == "mem20ops")
    assert "big.js" not in entry["modules"]
    assert not any("node_modules" in s["dir"] for s in index["subsystems"])


def test_search_ranks_and_filters(tree: Path):
    index = scan(tree, max_depth=2)
    hits = search.search(index, "fs-ops")
    assert hits and hits[0]["entry"]["name"] == "mem20ops"
    assert search.search(index, "nonexistentthing") == []
    multi = search.search(index, "ops")
    assert multi
    found = search.find(index, "cog")
    assert found is not None
    assert found["name"] == "cog"
    assert search.find(index, "does-not-exist") is None


def test_search_requires_all_tokens(tree: Path):
    index = scan(tree, max_depth=2)
    assert search.search(index, "ops zzzznotpresent") == []


def test_markdown_report_mentions_every_subsystem(tree: Path):
    index = scan(tree, max_depth=2)
    md = report.render_markdown(index)
    assert "mem20ops" in md
    assert "cog" in md
    assert "fs-ops" in md
    assert "sitemap search" in md
    assert report.render_terminal(index).startswith("root")


def test_snapshot_writes_source_only_zip(tree: Path, tmp_path: Path):
    secrets = tree / "secrets"
    secrets.mkdir()
    (secrets / ".env").write_text("TOKEN=abc\n", encoding="utf-8")
    (tree / "state.db").write_bytes(b"\x00" * 32)
    out = tmp_path / "out.zip"
    result = snapshot.create_snapshot(tree, out)
    assert result.files > 0
    assert result.skipped_secrets >= 1
    assert out.is_file()
    with __import__("zipfile").ZipFile(out) as zf:
        names = zf.namelist()
    assert not any(n.startswith("secrets/") for n in names)
    assert not any(n.endswith(".db") for n in names)
    assert not any("node_modules" in n for n in names)
    assert "mem20ops/mem20ops/cli.py" in names


def test_snapshot_verify_flags_secret_paths(tree: Path, tmp_path: Path):
    out = tmp_path / "bad.zip"
    import zipfile

    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("secrets/.env", "TOKEN=abc")
    check = snapshot.verify_zip(out)
    assert check["ok"] is False
    assert check["secret_paths"]


def test_snapshot_dry_run_writes_nothing(tree: Path, tmp_path: Path):
    out = tmp_path / "dry.zip"
    result = snapshot.create_snapshot(tree, out, dry_run=True)
    assert result.files > 0
    assert not out.exists()


def test_verify_missing_file(tmp_path: Path):
    check = snapshot.verify_zip(tmp_path / "nope.zip")
    assert check["ok"] is False


def _fake_table(spec: dict[int, tuple[int, str, int, float]]) -> dict[int, procinfo.ProcInfo]:
    table = {}
    for pid, (ppid, comm, tty, cpu) in spec.items():
        table[pid] = procinfo.ProcInfo(
            pid=pid,
            comm=comm,
            state="S",
            ppid=ppid,
            tty_nr=tty,
            utime=int(cpu * 100),
            stime=0,
            starttime=0.0,
        )
    return table


def test_descendants_resolves_transitively():
    table = _fake_table({1: (0, "init", 0, 1.0), 2: (1, "a", 0, 1.0), 3: (2, "b", 0, 1.0)})
    assert procinfo.descendants(2, table) == [3]
    assert procinfo.descendants(1, table) == [2, 3]


def test_subtree_cpu_includes_children():
    table = _fake_table({1: (0, "a", 0, 1.0), 2: (1, "b", 0, 2.5)})
    assert procinfo.subtree_cpu_seconds(1, table) == pytest.approx(3.5)
    assert procinfo.subtree_cpu_seconds(99, table) is None


def test_descendants_terminates_on_cyclic_ppid():
    table = _fake_table({1: (2, "a", 0, 0.0), 2: (1, "b", 0, 0.0)})
    assert procinfo.descendants(1, table) == [2]
    assert procinfo.descendants(2, table) == [1]


def _make_db(path: Path, rows: list[tuple[str, int]]) -> None:
    conn = sqlite3.connect(path)
    conn.execute("create table part (id text primary key, message_id text, session_id text, time_created integer, time_updated integer, data text)")
    for i, (sid, offset) in enumerate(rows):
        conn.execute(
            "insert into part values (?,?,?,?,?,?)",
            (f"p{i}", f"m{i}", sid, 0, offset, json.dumps({"state": {"status": "running"}})),
        )
    conn.commit()
    conn.close()


def test_in_flight_excludes_self_sessions(tmp_path: Path):
    import time as _t

    db = tmp_path / "db.sqlite"
    now_ms = int(_t.time() * 1000)
    _make_db(db, [("sess_self", now_ms), ("sess_other", now_ms)])
    hits = watch.in_flight_sessions(db, ["sess_self"], window=60)
    assert hits == ["sess_other"]


def test_in_flight_ignores_stale_rows(tmp_path: Path):
    db = tmp_path / "db.sqlite"
    _make_db(db, [("sess_old", 1000)])
    assert watch.in_flight_sessions(db, [], window=5) == []


def test_in_flight_missing_db_is_not_fatal(tmp_path: Path):
    assert watch.in_flight_sessions(tmp_path / "nope.db", [], window=5) == []


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def test_monitor_requires_sustained_silence(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(procinfo, "process_table", lambda: _fake_table({42: (1, "opencode", 0, 10.0)}))
    monkeypatch.setattr(procinfo, "subtree_cpu_seconds", lambda pid, table=None: 10.0)
    monkeypatch.setattr(procinfo, "pgrp_of", lambda pid: pid)
    monkeypatch.setattr(procinfo, "foreground_pgrp", lambda tty: None)
    clock = FakeClock()
    monitor = watch.Monitor(
        [42],
        self_sessions=[],
        window=20,
        streak_required=3,
        max_wait=10_000,
        db=tmp_path / "none.db",
        clock=clock.time,
        sleeper=clock.sleep,
    )
    assert monitor.tick() is False
    assert monitor.state.samples[42].baseline is True
    assert monitor.state.samples[42].quiet_streak == 0
    for _ in range(2):
        assert monitor.tick() is False
    assert monitor.tick() is True
    assert monitor.state.samples[42].quiet_streak == 3
    assert monitor.summary()["quiescent"] is True


def test_monitor_resets_streak_when_cpu_moves(monkeypatch, tmp_path: Path):
    cpu = {"value": 10.0}
    monkeypatch.setattr(procinfo, "process_table", lambda: _fake_table({42: (1, "opencode", 0, 0.0)}))
    monkeypatch.setattr(procinfo, "subtree_cpu_seconds", lambda pid, table=None: cpu["value"])
    monkeypatch.setattr(procinfo, "pgrp_of", lambda pid: pid)
    monkeypatch.setattr(procinfo, "foreground_pgrp", lambda tty: None)
    clock = FakeClock()
    monitor = watch.Monitor(
        [42],
        window=20,
        streak_required=3,
        max_wait=10_000,
        db=tmp_path / "none.db",
        clock=clock.time,
        sleeper=clock.sleep,
    )
    for _ in range(2):
        monitor.tick()
    cpu["value"] = 12.0
    assert monitor.tick() is False
    assert monitor.state.samples[42].quiet_streak == 0
    assert any("subtree" in r for r in monitor.state.samples[42].reasons)


def test_monitor_treats_exited_process_as_quiet(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(procinfo, "process_table", lambda: {})
    monkeypatch.setattr(procinfo, "pgrp_of", lambda pid: pid)
    monkeypatch.setattr(procinfo, "foreground_pgrp", lambda tty: None)
    clock = FakeClock()
    monitor = watch.Monitor(
        [777],
        window=20,
        streak_required=1,
        max_wait=10_000,
        db=tmp_path / "none.db",
        clock=clock.time,
        sleeper=clock.sleep,
    )
    assert monitor.tick() is True
    assert monitor.state.samples[777].reasons == ["process-exited"]


def test_monitor_gives_up_at_max_wait(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(procinfo, "process_table", lambda: _fake_table({42: (1, "opencode", 0, 5.0)}))
    monkeypatch.setattr(procinfo, "subtree_cpu_seconds", lambda pid, table=None: 5.0)
    monkeypatch.setattr(procinfo, "pgrp_of", lambda pid: pid)
    monkeypatch.setattr(procinfo, "foreground_pgrp", lambda tty: None)
    clock = FakeClock()
    monitor = watch.Monitor(
        [42],
        window=20,
        streak_required=99,
        max_wait=60,
        db=tmp_path / "none.db",
        clock=clock.time,
        sleeper=clock.sleep,
    )
    assert monitor.run() is False
    assert monitor.state.reason.startswith("max-wait-exceeded")
    assert clock.slept, "must not busy-spin"


def test_monitor_blocked_by_other_in_flight_session(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(procinfo, "process_table", lambda: _fake_table({42: (1, "opencode", 0, 1.0)}))
    monkeypatch.setattr(procinfo, "subtree_cpu_seconds", lambda pid, table=None: 1.0)
    monkeypatch.setattr(procinfo, "pgrp_of", lambda pid: pid)
    monkeypatch.setattr(procinfo, "foreground_pgrp", lambda tty: None)
    monkeypatch.setattr(watch, "in_flight_sessions", lambda *a, **k: ["someone_else"])
    clock = FakeClock()
    monitor = watch.Monitor(
        [42],
        window=20,
        streak_required=1,
        max_wait=10_000,
        db=tmp_path / "none.db",
        clock=clock.time,
        sleeper=clock.sleep,
    )
    assert monitor.tick() is False
    assert monitor.tick() is False
    assert "other-session-in-flight" in monitor.state.samples[42].reasons
    assert monitor.state.samples[42].quiet_streak == 1


def test_format_status_is_readable(tmp_path: Path):
    clock = FakeClock()
    state = watch.PollState(started_at=clock.now, window=20, streak_required=3, max_wait=100)
    state.samples[42] = watch.Sample(pid=42, quiescent=False, reasons=["cpu+1.0s"])
    text = watch.format_status(state)
    assert "42:BUSY" in text
    assert "cpu+1.0s" in text
    assert "streak=0/3" in text
    assert json.loads(state.to_json())["window"] == 20
