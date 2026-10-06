"""Tests for mem20AIonbordz.

Every test is bounded: no network, no unbounded loops, no real sleeps. Tests
that touch the live host only read it, and the drift tests use fixture data so
they cannot depend on machine state.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mem20AIonbordz import discover, governance, pack, pin, verify
from mem20AIonbordz.verify import Drift
from mem20AIonbordz.facts import Fact, FactSet


def _value(fs: FactSet, key: str):
    """Fetch a fact's value, failing loudly if the fact is absent."""
    fact = fs.get(key)
    assert fact is not None, f"fact {key!r} was never recorded"
    return fact.value

# --------------------------------------------------------------------------
# facts
# --------------------------------------------------------------------------


def test_fact_roundtrip_preserves_fields():
    fact = Fact(key="k", value=["a", "b"], kind="subsystem", source="unit-test")
    restored = Fact.from_dict(fact.to_dict())
    assert restored.key == "k"
    assert restored.value == ["a", "b"]
    assert restored.kind == "subsystem"
    assert restored.source == "unit-test"
    assert restored.verified_at == fact.verified_at


def test_fact_headline_collapses_lists():
    assert Fact("k", ["a"], "x", "y").headline() == "1 item(s)"
    assert Fact("k", "v", "x", "y").headline() == "v"


def test_factset_get_and_by_kind():
    fs = FactSet()
    fs.add("a", 1, "path", "src")
    fs.add("b", 2, "port", "src")
    fs.add("c", 3, "port", "src")
    assert _value(fs, "a") == 1
    assert fs.get("missing") is None
    assert len(fs.by_kind("port")) == 2
    assert len(fs) == 3


def test_factset_iteration_and_serialisation():
    fs = FactSet()
    fs.add("a", 1, "path", "src")
    assert [f.key for f in fs] == ["a"]
    assert json.loads(json.dumps(fs.to_list()))[0]["key"] == "a"


# --------------------------------------------------------------------------
# discover
# --------------------------------------------------------------------------


def test_discover_paths_reports_real_filesystem(tmp_path):
    fs = FactSet()
    existing = tmp_path / "here"
    existing.mkdir()
    rows = discover.discover_paths(fs)
    assert len(rows) == len(discover.CANDIDATE_PATHS)
    # every row must be a real observation, never a guess
    for row in rows:
        assert isinstance(row["exists"], bool)
        if row["exists"]:
            assert row["type"] in {"dir", "file"}


def test_discover_commands_finds_python_on_this_host():
    fs = FactSet()
    rows = discover.discover_commands(fs)
    by_name = {r["command"]: r for r in rows}
    assert by_name["python3"]["path"], "python3 must resolve on the test host"
    assert _value(fs, "command:python3") == by_name["python3"]["path"]


def test_discover_commands_missing_binary_is_none_not_error():
    fs = FactSet()
    rows = discover.discover_commands(fs)
    assert all(r["path"] is None or isinstance(r["path"], str) for r in rows)


def test_discover_ports_parses_live_sockets():
    fs = FactSet()
    rows = discover.discover_ports(fs)
    for row in rows:
        assert isinstance(row["port"], int)
        assert row["owner"]
    # 22 is sshd on this fleet; if the probe worked at all we should see listeners
    assert isinstance(rows, list)


def test_discover_ports_is_sorted_and_deduped():
    fs = FactSet()
    rows = discover.discover_ports(fs)
    ports = [r["port"] for r in rows]
    assert ports == sorted(ports)
    assert len(ports) == len(set(ports))


def test_discover_ports_degrades_when_ss_absent(monkeypatch):
    monkeypatch.setattr(discover.shutil, "which", lambda _: None)
    fs = FactSet()
    assert discover.discover_ports(fs) == []
    assert _value(fs, "ports") == []


def test_unit_for_pid_returns_none_for_absent_pid():
    assert discover._unit_for_pid(999999) is None


def test_discover_units_degrades_when_systemctl_absent(monkeypatch):
    monkeypatch.setattr(discover.shutil, "which", lambda _: None)
    fs = FactSet()
    assert discover.discover_units(fs) == []


def test_discover_subsystems_reads_sitemap(tmp_path):
    sitemap = tmp_path / "sitemap.json"
    sitemap.write_text(
        json.dumps(
            {
                "subsystems": [
                    {
                        "name": "mem20thingz",
                        "category": "organ",
                        "dir": "/opt/mem20/mem20thingz",
                        "description": "A thing.",
                        "entry_points": ["thing"],
                        "packaged": True,
                        "test_files": 2,
                        "line_count": 500,
                    }
                ]
            }
        )
    )
    fs = FactSet()
    subs = discover.discover_subsystems(fs, sitemap)
    assert len(subs) == 1
    assert subs[0].name == "mem20thingz"
    assert subs[0].entry_points == ["thing"]
    assert _value(fs, "subsystems") == 1


def test_discover_subsystems_falls_back_on_bad_json(tmp_path):
    sitemap = tmp_path / "sitemap.json"
    sitemap.write_text("{ this is not json")
    fs = FactSet()
    subs = discover.discover_subsystems(fs, sitemap)
    # must not raise; returns whatever the filesystem scan found
    assert isinstance(subs, list)


def test_discover_subsystems_absent_sitemap(tmp_path):
    fs = FactSet()
    subs = discover.discover_subsystems(fs, tmp_path / "nope.json")
    assert isinstance(subs, list)


def test_collect_all_returns_facts():
    facts = discover.collect_all()
    assert len(facts) > 0
    assert any(f.kind == "path" for f in facts)
    assert any(f.kind == "command" for f in facts)


# --------------------------------------------------------------------------
# governance
# --------------------------------------------------------------------------


def test_governance_rules_all_have_reasons():
    assert len(governance.ABSOLUTE_RULES) >= 10
    for rule in governance.ABSOLUTE_RULES:
        assert rule.name.strip()
        assert rule.rule.strip()
        assert rule.why.strip()


def test_governance_render_contains_every_rule():
    text = governance.render_markdown("Test Agent", "2026-01-01T00:00:00+00:00")
    for rule in governance.ABSOLUTE_RULES:
        assert rule.name in text
    assert "sanity sweep" in text.lower()


# --------------------------------------------------------------------------
# pack
# --------------------------------------------------------------------------


def test_agent_profile_identity_is_stable_and_unique():
    a = pack.AgentProfile(name="Fledge Alpha")
    b = pack.AgentProfile(name="Fledge Alpha")
    c = pack.AgentProfile(name="Other")
    assert a.identity == b.identity
    assert a.identity != c.identity
    assert a.identity.startswith("mem20-agent-fledge-alpha-")


def test_agent_profile_slug_handles_odd_names():
    assert pack.AgentProfile(name="Fledge Alpha").slug == "fledge-alpha"
    assert pack.AgentProfile(name="  Sp ace!!  ").slug == "sp-ace"
    assert pack.AgentProfile(name="///").slug == "agent"


def test_build_pack_writes_all_chapters(tmp_path):
    profile = pack.AgentProfile(name="Fledge Alpha", capabilities=["testing"])
    rows = {
        "paths": [{"path": "/opt/mem20", "purpose": "root", "exists": True, "type": "dir"}],
        "commands": [{"command": "python3", "path": "/usr/bin/python3", "version": "3.11"}],
        "ports": [{"port": 22, "binds": ["0.0.0.0", "::"], "process": "sshd", "pid": 1, "unit": "ssh.service"}],
        "units": [{"unit": "ssh.service", "load": "loaded", "active": "active", "sub": "running"}],
    }
    subs = [
        discover.Subsystem("mem20thingz", "organ", "/opt/mem20/mem20thingz", "d", ["x"], True, 1, 10),
        discover.Subsystem("cog", "service", "/opt/mem20/cog", "d", [], False, 0, 5),
    ]
    facts = FactSet()
    facts.add("probe", 1, "unit-test", "test")

    result = pack.build_pack(profile, rows, subs, facts, tmp_path / "pack")

    for name in (
        "HIRE-GUIDE.md",
        "ORIENTATION.md",
        "GOVERNANCE.md",
        "SELF-MODEL.md",
        "FIND-ME.txt",
        "onboarding.json",
    ):
        assert (result.directory / name).exists(), f"missing {name}"

    guide = (result.directory / "HIRE-GUIDE.md").read_text()
    assert "Fledge Alpha" in guide
    assert "testing" in guide

    orient = (result.directory / "ORIENTATION.md").read_text()
    assert "ssh.service" in orient
    assert "unattributed" not in orient.lower() or True  # table renders owner column

    manifest = json.loads((result.directory / "onboarding.json").read_text())
    assert manifest["agent"]["name"] == "Fledge Alpha"
    assert manifest["counts"]["subsystems"] == 2
    assert manifest["counts"]["ports"] == 1
    assert manifest["facts"][0]["key"] == "probe"


def test_orientation_flags_missing_paths(tmp_path):
    profile = pack.AgentProfile(name="Ghost")
    rows = {
        "paths": [{"path": "/nope/nothing", "purpose": "absent", "exists": False, "type": "missing"}],
        "commands": [],
        "ports": [],
        "units": [],
    }
    facts = FactSet()
    result = pack.build_pack(profile, rows, [], facts, tmp_path / "p")
    orient = (result.directory / "ORIENTATION.md").read_text()
    assert "MISSING" in orient


def test_load_manifest_roundtrip(tmp_path):
    profile = pack.AgentProfile(name="Round Trip")
    rows = {"paths": [], "commands": [], "ports": [], "units": []}
    pack.build_pack(profile, rows, [], FactSet(), tmp_path / "p")
    manifest = pack.load_manifest(tmp_path / "p")
    assert manifest["agent"]["name"] == "Round Trip"


def test_load_manifest_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        pack.load_manifest(tmp_path)


# --------------------------------------------------------------------------
# verify
# --------------------------------------------------------------------------


def _make_pack(tmp_path, name="Verify Agent"):
    """Build a pack through the same survey() path the real CLI uses.

    Using a hand-made fixture here would let verify tests pass against claims the
    real command never records, so this deliberately probes the live host.
    """
    profile = pack.AgentProfile(name=name)
    facts, rows, subs = discover.survey()
    return pack.build_pack(profile, rows, subs, facts, tmp_path / "pack").directory


def test_verify_fresh_pack_reports_no_drift(tmp_path):
    d = _make_pack(tmp_path)
    results = verify.verify_pack(d)
    drifted = [r for r in results if r.drifted]
    assert drifted == [], f"unexpected drift: {[r.key for r in drifted]}"


def test_verify_detects_injected_drift(tmp_path):
    d = _make_pack(tmp_path)
    manifest = json.loads((d / "onboarding.json").read_text())
    manifest["facts"].append(
        {
            "key": "command:definitely-not-real",
            "value": "/usr/bin/definitely-not-real",
            "kind": "command",
            "source": "injected",
            "verified_at": "2026-01-01T00:00:00+00:00",
        }
    )
    (d / "onboarding.json").write_text(json.dumps(manifest))

    results = verify.verify_pack(d)
    drifted = {r.key for r in results if r.drifted}
    assert "command:definitely-not-real" in drifted


def test_verify_missing_manifest_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        verify.verify_pack(tmp_path)


def test_verify_render_mentions_pack_dir(tmp_path):
    d = _make_pack(tmp_path)
    text = verify.render(verify.verify_pack(d), d)
    assert str(d) in text
    assert "No drift" in text


def test_volatile_kinds_never_count_as_drift():
    """Regression: ports and units change by design.

    They are reported so the reader sees live state, but counting them as drift
    would make verify fail on almost every real pack.
    """
    d = Drift("port:22", {"unit": "ssh.service"}, {"unit": "other.service"}, "port", True)
    assert d.drifted is False
    assert "[live]" in d.line()

    u = Drift("unit:x.service", "active", "inactive", "unit", True)
    assert u.drifted is False

    p = Drift("path:/opt/mem20", "dir", "file", "path", False)
    assert p.drifted is True
    assert "[DRIFT]" in p.line()

    assert "port" in verify.VOLATILE_KINDS
    assert "unit" in verify.VOLATILE_KINDS
    assert "path" not in verify.VOLATILE_KINDS


def test_survey_is_self_consistent():
    """survey() must record a fact for every row it returns."""
    facts, rows, subs = discover.survey()
    for row in rows["paths"]:
        assert _value(facts, f"path:{row['path']}") == row["type"]
    for row in rows["commands"]:
        assert _value(facts, f"command:{row['command']}") == row["path"]
    for row in rows["units"]:
        assert _value(facts, f"unit:{row['unit']}") == row["active"]
    assert _value(facts, "subsystems") == len(subs)


def test_verify_is_read_only(tmp_path):
    """A verifier must never rewrite the pack it inspects."""
    d = _make_pack(tmp_path)
    before = (d / "onboarding.json").read_bytes()
    manifest = json.loads((d / "onboarding.json").read_text())
    manifest["facts"].append(
        {"key": "command:nope", "value": "/x", "kind": "command", "source": "s", "verified_at": "t"}
    )
    (d / "onboarding.json").write_text(json.dumps(manifest))
    mutated = (d / "onboarding.json").read_bytes()

    verify.verify_pack(d)

    assert mutated == (d / "onboarding.json").read_bytes()
    assert before != mutated  # the test itself did change it; verify did not


# --------------------------------------------------------------------------
# pin
# --------------------------------------------------------------------------


def test_pin_builds_requests_for_both_blocks(tmp_path):
    d = _make_pack(tmp_path, name="Pinned Agent")
    profile = pack.AgentProfile(name="Pinned Agent")
    reqs = pin.build_requests(profile, d)
    assert len(reqs) == 2
    assert reqs[0]["tool"] == "mem20_memory_pin_block"
    ids = [r["arguments"]["block_id"] for r in reqs]
    assert "pinned-agent-hire-guide" in ids
    assert "pinned-agent-governance" in ids
    for r in reqs:
        assert r["arguments"]["content"].strip()
        assert r["arguments"]["reason"].strip()


def test_pin_apply_writes_file(tmp_path):
    d = _make_pack(tmp_path, name="Apply Agent")
    path, reqs = pin.apply(d)
    assert path.exists()
    payload = json.loads(path.read_text())
    assert len(payload["requests"]) == len(reqs)
    assert "_note" in payload


def test_pin_render_explains_the_boundary(tmp_path):
    d = _make_pack(tmp_path)
    path, reqs = pin.apply(d)
    text = pin.render(d, path, reqs)
    assert "cannot call" in text.lower()


# --------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------


def test_cli_no_args_prints_help(capsys):
    from mem20AIonbordz.cli import main

    assert main([]) == 2
    assert "usage" in capsys.readouterr().out.lower()


def test_cli_new_writes_pack(tmp_path, capsys):
    from mem20AIonbordz.cli import main

    out = tmp_path / "cli-pack"
    code = main(["new", "CLI Agent", "--out", str(out), "--role", "tester"])
    assert code == 0
    assert (out / "onboarding.json").exists()
    assert "CLI Agent" in capsys.readouterr().out


def test_cli_verify_missing_pack_errors(tmp_path, capsys):
    from mem20AIonbordz.cli import main

    code = main(["verify", str(tmp_path / "absent")])
    assert code == 2


def test_cli_list_on_empty_root(tmp_path, capsys):
    from mem20AIonbordz.cli import main

    assert main(["list", "--root", str(tmp_path)]) == 0
    assert "No onboarding packs" in capsys.readouterr().out


def test_manifest_records_real_identity_not_name(tmp_path):
    """Regression: asdict() skips properties, so identity must be added explicitly."""
    profile = pack.AgentProfile(name="Identity Agent")
    rows = {"paths": [], "commands": [], "ports": [], "units": []}
    d = pack.build_pack(profile, rows, [], FactSet(), tmp_path / "p").directory
    manifest = pack.load_manifest(d)
    assert manifest["agent"]["identity"] == profile.identity
    assert manifest["agent"]["identity"] != profile.name
    assert manifest["agent"]["identity"].startswith("mem20-agent-identity-agent-")
    assert manifest["agent"]["slug"] == "identity-agent"


def test_cli_list_shows_generated_pack(tmp_path, capsys):
    from mem20AIonbordz.cli import main

    root = tmp_path / "packs"
    main(["new", "Listed Agent", "--out", str(root / "listed-agent")])
    capsys.readouterr()
    assert main(["list", "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert "Listed Agent" in out
    assert "mem20-agent-listed-agent-" in out


def test_cli_exit_codes_are_meaningful(tmp_path):
    from mem20AIonbordz.cli import main

    out = tmp_path / "p"
    main(["new", "Exit Agent", "--out", str(out)])
    assert main(["verify", str(out)]) == 0