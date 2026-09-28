"""Tests for the promotion pack.

The pack's job is to carry a dream somewhere else without deceiving whoever
reads it. So the tests care most about the two honesty guarantees: skills are
never presented as verified, and a damaged chain is never promoted.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from mem20dreamz import promote
from mem20dreamz.lineage import Lineage


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr("mem20dreamz.lineage.STORE", str(tmp_path / "dreams"))
    yield


def _iteration(n: int = 1, artifact: str = "a real built thing", accepted: bool = True):
    from mem20dreamz.lineage import Iteration

    return Iteration(
        n=n,
        artifact=artifact,
        fidelity={"score": 90.0},
        omission={"score": 40.0, "summary": "added the pricing table"},
        forecast={},
        critiques=[],
        inventions_added=["pricing table"],
        dreamer_evolved=True,
        accepted=accepted,
    )


def _lineage(dream_id: str = "dream-test-promo", **kw) -> Lineage:
    lineage = Lineage(
        dream_id=dream_id,
        seed=kw.get("seed", "a storefront that explains itself"),
        kind=kw.get("kind", "active"),
        foundation=kw.get("foundation", "Make it trustworthy in one glance"),
        artifact=kw.get("artifact", "first draft"),
    )
    return lineage


# --- the four parts are all present ------------------------------------------


def test_pack_has_all_four_parts():
    lineage = _lineage()
    lineage.record(_iteration(artifact="the designed storefront"))
    lineage.dreamer.add_technique("watch for: a broken claim nobody implemented")
    pack = promote.build_pack(lineage)
    for part in ("maps", "skills", "information", "design"):
        assert part in pack, f"pack is missing {part}"
    assert pack["maps"]["dream"]["dream_id"] == "dream-test-promo"
    assert pack["maps"]["estate"]["installed_packages"] >= 0
    assert pack["skills"], "a learned technique must reach the skills section"
    assert pack["design"]["final_artifact"] == "the designed storefront"
    assert pack["design"]["best_iteration"] == 1
    assert pack["information"]["accepted_iterations"] == 1


def test_uniterated_lineage_reports_no_design_rather_than_the_seed():
    """The seed is the brief, not a design. Reporting it as one would be a lie."""
    design = promote.build_design(_lineage())
    assert design["final_artifact"] == ""
    assert design["best_iteration"] is None
    assert "no accepted iteration" in design["selected_because"]


def test_skills_are_labelled_unverified_observations():
    lineage = _lineage()
    lineage.dreamer.add_technique("watch for: silent capability drift")
    skill = promote.build_skills(lineage)[0]
    assert skill["kind"] == "learned_observation"
    assert skill["verified"] is False
    assert "not from a passing test" in skill["why_unverified"]


def test_observation_prefix_becomes_a_checkable_statement():
    lineage = _lineage()
    lineage.dreamer.add_technique("watch for: a claim with no implementation")
    statement = promote.build_skills(lineage)[0]["statement"]
    assert statement.startswith("Check that"), statement
    assert "watch for" not in statement.lower()
    assert lineage.dreamer.techniques[0].startswith("watch for:"), "raw text is preserved"


def test_technique_is_never_invented_into_a_procedure():
    """A question-shaped observation must not become a confident instruction."""
    lineage = _lineage()
    lineage.dreamer.add_technique("watch for: does the claim even exist?")
    skill = promote.build_skills(lineage)[0]
    assert skill["statement"].startswith("Confirm:"), skill["statement"]


def test_fidelity_range_ignores_missing_values():
    lineage = _lineage()
    lineage.score_history.extend(
        [
            {"n": 1, "fidelity": 90.0, "omission": 1, "accepted": True},
            {"n": 2, "fidelity": None, "omission": 1, "accepted": False},
            {"n": 3, "fidelity": 70.0, "omission": 1, "accepted": True},
        ]
    )
    info = promote.build_information(lineage)
    assert info["fidelity"]["min"] == 70.0
    assert info["fidelity"]["max"] == 90.0
    assert info["accepted_iterations"] == 2
    assert info["rejected_iterations"] == 1
    assert "not measurements" in info["confidence_note"]


def test_empty_lineage_produces_an_empty_pack_not_a_crash():
    pack = promote.build_pack(_lineage())
    assert pack["skills"] == []
    assert pack["information"]["inventions"] == []
    assert pack["design"]["final_artifact"] == ""
    assert "none learned yet" in promote.render_markdown(pack)


# --- the honesty header ------------------------------------------------------


def test_markdown_leads_with_what_the_pack_is_not():
    lineage = _lineage()
    lineage.dreamer.add_technique("watch for: overclaiming")
    text = promote.render_markdown(promote.build_pack(lineage))
    assert "learned observations" in text
    assert "not tested procedures" in text
    assert "learned observations" in text.split("## Skills")[0], "the warning must come first"


def test_markdown_says_scores_are_not_measurements():
    text = promote.render_markdown(promote.build_pack(_lineage()))
    assert "panel judgements" in text


# --- the integrity gate ------------------------------------------------------


def test_promotion_is_refused_when_the_chain_is_damaged(tmp_path, monkeypatch):
    lineage = _lineage()
    lineage.braid_cids = ["brgood", "brbad"]
    lineage.save()
    monkeypatch.setattr(
        promote, "check_provenance", lambda ln: {"healthy": False, "broken": [{"cid": "brbad"}]}
    )
    out = tmp_path / "pack"
    result = promote.promote("dream-test-promo", str(out))
    assert result["promoted"] is False
    assert "refusing" in result["reason"]
    assert not out.exists(), "a refused promotion must not leave a pack behind"


def test_promotion_proceeds_when_the_chain_verifies(tmp_path, monkeypatch):
    lineage = _lineage()
    lineage.dreamer.add_technique("watch for: a real gap")
    lineage.braid_cids = ["brgood"]
    lineage.save()
    monkeypatch.setattr(promote, "check_provenance", lambda ln: {"healthy": True, "checked": 1})
    monkeypatch.setattr(
        promote, "commit_promotion", lambda ln, pk: {"committed": True, "cid": "brpromo"}
    )
    out = tmp_path / "pack"
    result = promote.promote("dream-test-promo", str(out))
    assert result["promoted"] is True
    assert result["skills"] == 1
    assert result["braid"]["cid"] == "brpromo"
    assert sorted(result["files"]) == ["dream-test-promo.json", "dream-test-promo.md"]


def test_lineage_with_no_nodes_is_not_blocked(tmp_path, monkeypatch):
    """Nothing to verify is not the same as a damaged chain."""
    lineage = _lineage()
    lineage.save()
    monkeypatch.setattr(promote, "commit_promotion", lambda ln, pk: {"committed": False})
    result = promote.promote("dream-test-promo", str(tmp_path / "pack"))
    assert result["promoted"] is True
    assert result["provenance"]["checked"] == 0


def test_unknown_dream_is_an_error_not_an_empty_pack(tmp_path):
    with pytest.raises(FileNotFoundError):
        promote.promote("dream-does-not-exist", str(tmp_path / "pack"))


# --- writing the pack --------------------------------------------------------


def test_pack_write_is_atomic_and_leaves_no_temp_files(tmp_path):
    target = promote.write_pack(promote.build_pack(_lineage()), str(tmp_path / "pack"))
    assert not list(Path(target).glob("*.tmp"))
    assert len(list(Path(target).iterdir())) == 2


def test_pack_never_silently_overwrites(tmp_path):
    target = tmp_path / "pack" / "dream-test-promo"
    target.mkdir(parents=True)
    (target / "someone-elses-work.md").write_text("keep me")
    with pytest.raises(FileExistsError):
        promote.write_pack(promote.build_pack(_lineage()), str(tmp_path / "pack"))
    assert (target / "someone-elses-work.md").read_text() == "keep me"
    promote.write_pack(promote.build_pack(_lineage()), str(tmp_path / "pack"), force=True)


def test_many_dreams_share_one_promotions_store(tmp_path):
    """One output directory must not lock out every other dream."""
    store = tmp_path / "promotions"
    first = _lineage("dream-one")
    second = _lineage("dream-two")
    a = promote.write_pack(promote.build_pack(first), str(store))
    b = promote.write_pack(promote.build_pack(second), str(store))
    assert a != b
    assert sorted(os.listdir(store)) == ["dream-one", "dream-two"]
    assert sorted(os.listdir(a)) == ["dream-one.json", "dream-one.md"]


def test_pack_json_round_trips(tmp_path):
    target = promote.write_pack(promote.build_pack(_lineage()), str(tmp_path / "pack"))
    data = json.loads((Path(target) / "dream-test-promo.json").read_text())
    assert data["dream_id"] == "dream-test-promo"
    assert data["pack_version"] == promote.PACK_VERSION
    assert data["honesty"]["skills_are_verified"] is False


def test_catalogue_reports_provenance_per_dream():
    lineage = _lineage()
    lineage.dreamer.add_technique("watch for: something")
    lineage.braid_cids = []
    lineage.save()
    rows = promote.catalogue()
    assert any(r["dream_id"] == "dream-test-promo" for r in rows)
    row = next(r for r in rows if r["dream_id"] == "dream-test-promo")
    assert row["skills"] == 1
    assert row["provenance"] is True


# --- rollback: a failed promotion must not leave reality half-changed ----------
#
# The defect these cover: `write_pack` created the target directory, then wrote
# the JSON, then the markdown. Each individual write was atomic, but the *pair*
# was not. A crash between them, or a failure on the second file, left the target
# directory non-empty - and the "never silently overwrite" guard only asks whether
# the directory has anything in it. So a half-written pack locked out every
# future retry, with no way for an operator to tell it apart from a real pack.

import builtins


def test_a_render_failure_writes_nothing_at_all(tmp_path, monkeypatch):
    """Fail before touching the filesystem, not halfway through it."""
    pack = promote.build_pack(_lineage())

    def _boom(_pack):
        raise RuntimeError("renderer exploded")

    monkeypatch.setattr(promote, "render_markdown", _boom)
    out = tmp_path / "pack"

    with pytest.raises(RuntimeError):
        promote.write_pack(pack, str(out))

    assert not out.exists(), "a failed render must leave no promotions directory"
    assert not (out / "dream-test-promo").exists(), "and no dream directory"


def test_a_crash_while_staging_leaves_no_half_written_pack(tmp_path, monkeypatch):
    """The headline case: writing the pack fails. Nothing half-written survives."""
    real_stage = promote._stage_files

    def _stage(staging, files):
        # Write the first file for real, then die on the second - the exact shape
        # of a disk-full or a revoked permission partway through a pack.
        real_stage(staging, files[:1])
        raise OSError("no space left on device")

    monkeypatch.setattr(promote, "_stage_files", _stage)
    out = tmp_path / "pack"

    with pytest.raises(OSError):
        promote.write_pack(promote.build_pack(_lineage()), str(out))
    monkeypatch.setattr(promote, "_stage_files", real_stage)

    target = out / "dream-test-promo"
    assert not target.exists(), f"a failed pack left {sorted(os.listdir(out)) if out.exists() else []}"
    assert not [p for p in out.glob(".staging*")], "the staging directory must be swept"
    assert not [p for p in out.glob("*.bak-*")], "nothing was replaced, so no backup may exist"


def test_a_retry_after_a_failed_promotion_succeeds_without_force(tmp_path, monkeypatch):
    """The operator experience the old code made impossible."""
    out = tmp_path / "pack"
    real_stage = promote._stage_files

    def _stage(staging, files):
        real_stage(staging, files[:1])
        raise OSError("no space left on device")

    monkeypatch.setattr(promote, "_stage_files", _stage)
    with pytest.raises(OSError):
        promote.write_pack(promote.build_pack(_lineage()), str(out))
    monkeypatch.setattr(promote, "_stage_files", real_stage)

    # No --force: a failed attempt must not have locked out the retry.
    target = promote.write_pack(promote.build_pack(_lineage()), str(out))
    assert sorted(os.listdir(target)) == ["dream-test-promo.json", "dream-test-promo.md"]


def test_leftover_temp_files_are_recognised_as_debris_not_as_a_pack(tmp_path):
    """A directory holding only a .tmp is an interrupted write, not somebody's work."""
    target = tmp_path / "pack" / "dream-test-promo"
    target.mkdir(parents=True)
    (target / "dream-test-promo.json.tmp").write_text('{"half')

    written = promote.write_pack(promote.build_pack(_lineage()), str(tmp_path / "pack"))
    assert sorted(os.listdir(written)) == ["dream-test-promo.json", "dream-test-promo.md"]
    assert not list(Path(written).glob("*.tmp")), "the debris must be swept, not joined"


def test_a_complete_existing_pack_is_still_refused_without_force(tmp_path):
    """The overwrite guard must survive the debris exception."""
    promote.write_pack(promote.build_pack(_lineage()), str(tmp_path / "pack"))
    with pytest.raises(FileExistsError):
        promote.write_pack(promote.build_pack(_lineage()), str(tmp_path / "pack"))


def test_force_replaces_a_real_pack_and_leaves_no_backup_behind(tmp_path):
    target = promote.write_pack(promote.build_pack(_lineage()), str(tmp_path / "pack"))
    promote.write_pack(promote.build_pack(_lineage()), str(tmp_path / "pack"), force=True)
    assert sorted(os.listdir(target)) == ["dream-test-promo.json", "dream-test-promo.md"]
    store = tmp_path / "pack"
    assert sorted(os.listdir(store)) == ["dream-test-promo"], "no .bak left lying about"


def test_a_failure_during_force_restores_the_previous_pack(tmp_path, monkeypatch):
    """Rollback, properly: the old pack must survive a failed replacement."""
    target = promote.write_pack(promote.build_pack(_lineage()), str(tmp_path / "pack"))
    original = (Path(target) / "dream-test-promo.md").read_text()
    real_replace = os.replace
    install_target = str(Path(target))
    state = {"failed": False}

    def _replace(src, dst, *args, **kwargs):
        # Fail the install rename once, then behave. The set-aside rename of the
        # old pack has already happened by then, which is the recoverable moment,
        # and the rollback rename that follows must be allowed to succeed.
        if str(dst) == install_target and not state["failed"]:
            state["failed"] = True
            raise OSError("no space left on device")
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(promote.os, "replace", _replace)
    with pytest.raises(OSError):
        promote.write_pack(promote.build_pack(_lineage()), str(tmp_path / "pack"), force=True)
    monkeypatch.setattr(promote.os, "replace", real_replace)

    assert Path(target).exists(), "the previous pack must be restored, not left missing"
    assert (Path(target) / "dream-test-promo.md").read_text() == original
    assert sorted(os.listdir(target)) == ["dream-test-promo.json", "dream-test-promo.md"]
    assert sorted(os.listdir(tmp_path / "pack")) == ["dream-test-promo"], "the backup was consumed"


def test_a_failed_rollback_names_the_surviving_pack(tmp_path, monkeypatch):
    """If the rollback cannot run, the pack must not disappear quietly."""
    target = promote.write_pack(promote.build_pack(_lineage()), str(tmp_path / "pack"))
    real_replace = os.replace
    install_target = str(Path(target))

    def _replace(src, dst, *args, **kwargs):
        # Everything targeting the final path fails - the install rename and then
        # the restore rename. The set-aside rename (which targets the .bak name)
        # succeeds, so a stranded copy really does exist to be lost.
        if str(dst) == install_target:
            raise OSError("read-only filesystem")
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(promote.os, "replace", _replace)
    with pytest.raises(RuntimeError) as excinfo:
        promote.write_pack(promote.build_pack(_lineage()), str(tmp_path / "pack"), force=True)
    monkeypatch.setattr(promote.os, "replace", real_replace)

    message = str(excinfo.value)
    assert "could not be restored" in message
    stranded = [n for n in os.listdir(tmp_path / "pack") if ".bak-" in n]
    assert stranded, "the previous pack must still exist somewhere"
    assert stranded[0] in message, f"the operator must be told where it is: {message}"


def test_a_directory_holding_unrelated_files_is_never_treated_as_debris(tmp_path):
    """Guessing wrong here destroys somebody's work, so the rule stays narrow."""
    target = tmp_path / "pack" / "dream-test-promo"
    target.mkdir(parents=True)
    (target / "someone-elses-work.md").write_text("keep me")

    with pytest.raises(FileExistsError):
        promote.write_pack(promote.build_pack(_lineage()), str(tmp_path / "pack"))
    assert (target / "someone-elses-work.md").read_text() == "keep me"


def test_a_half_written_pack_is_debris_but_an_unrelated_one_is_not(tmp_path):
    """The two cases the old guard conflated, side by side."""
    debris = tmp_path / "debris" / "dream-test-promo"
    debris.mkdir(parents=True)
    (debris / "dream-test-promo.json").write_text("{}")  # crashed before the .md
    assert promote._existing_pack_is_incomplete(str(debris), ["dream-test-promo.json", "dream-test-promo.md"])

    foreign = tmp_path / "foreign" / "dream-test-promo"
    foreign.mkdir(parents=True)
    (foreign / "notes.md").write_text("mine")
    assert not promote._existing_pack_is_incomplete(str(foreign), ["dream-test-promo.json", "dream-test-promo.md"])


def test_a_pack_stranded_by_a_crash_is_restored_on_the_next_attempt(tmp_path):
    """The window between the two renames must not orphan the only real copy."""
    target = promote.write_pack(promote.build_pack(_lineage()), str(tmp_path / "pack"))

    # Exactly what a process killed between set-aside and install leaves behind.
    os.replace(target, str(target) + ".bak-1700000000")
    assert not Path(target).exists()

    promote.write_pack(promote.build_pack(_lineage()), str(tmp_path / "pack"), force=True)
    assert Path(target).exists(), "the stranded pack must be healed, not ignored"
    assert sorted(os.listdir(tmp_path / "pack")) == ["dream-test-promo"], "no .bak may linger"


def test_recovery_reports_when_there_was_nothing_to_recover(tmp_path):
    assert promote.recover_stranded_backup(str(tmp_path / "nope"), "dream-x") is None


def test_recovery_never_overwrites_a_pack_that_is_already_in_place(tmp_path):
    """A completed pack wins; the backup is left alone rather than assumed worthless."""
    store = tmp_path / "pack"
    target = promote.write_pack(promote.build_pack(_lineage()), str(store))
    stranded = store / "dream-test-promo.bak-1700000000"
    stranded.mkdir()
    (stranded / "dream-test-promo.md").write_text("the older one")

    assert promote.recover_stranded_backup(str(store), "dream-test-promo") is None
    assert Path(target).exists(), "the pack in place must not be touched"
    assert stranded.exists(), "an unreferenced backup must not be deleted on a guess"


def test_promote_reports_a_pack_it_recovered(tmp_path, monkeypatch):
    lineage = _lineage()
    lineage.save()
    monkeypatch.setattr(promote, "check_provenance", lambda ln: {"healthy": True, "checked": 0})
    monkeypatch.setattr(promote, "commit_promotion", lambda ln, pk: {"committed": True})

    store = tmp_path / "pack"
    os.makedirs(store / "dream-test-promo.bak-1700000000", exist_ok=True)
    (store / "dream-test-promo.bak-1700000000" / "dream-test-promo.md").write_text("the old one")

    result = promote.promote("dream-test-promo", str(store))
    assert result["promoted"] is True
    assert result["recovered_stranded_pack"], "a recovered pack must be reported, not done quietly"


def test_a_braid_commit_failure_is_reported_rather_than_hidden(tmp_path, monkeypatch):
    """The pack on disk is real output; the missing ledger record must be said."""
    lineage = _lineage()
    lineage.save()
    monkeypatch.setattr(promote, "check_provenance", lambda ln: {"healthy": True, "checked": 0})
    monkeypatch.setattr(
        promote,
        "commit_promotion",
        lambda ln, pk: {"committed": False, "reason": "braid reports unavailable"},
    )
    result = promote.promote("dream-test-promo", str(tmp_path / "pack"))
    assert result["promoted"] is True, "the pack was written, so it was promoted"
    assert result["braid"]["committed"] is False
    assert "unavailable" in result["braid"]["reason"]


def test_a_write_that_never_happens_leaves_no_directory(tmp_path, monkeypatch):
    """Even a total filesystem failure must leave the store as it was."""
    out = tmp_path / "pack"
    monkeypatch.setattr(
        builtins, "open", lambda *a, **k: (_ for _ in ()).throw(OSError("read-only filesystem"))
    )
    with pytest.raises(OSError):
        promote.write_pack(promote.build_pack(_lineage()), str(out))
    assert not out.exists() or not any(out.iterdir())
