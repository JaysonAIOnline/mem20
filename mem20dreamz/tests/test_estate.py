"""Tests for estate awareness, and the prompt/format contract it depends on.

The second half matters more than the first: adding a placeholder to a template
that the engine does not supply raises KeyError at the first real dream, not at
import time. These tests fail loudly instead.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from mem20dreamz import estate
from mem20dreamz import verdicts as v

# --- estate reads the estate, not the story ----------------------------------


def _fake_estate(tmp_path: Path) -> Path:
    root = tmp_path / "estate"
    (root / "mem20alpha").mkdir(parents=True)
    (root / "mem20alpha" / "pyproject.toml").write_text("[project]\nname='mem20alpha'\n")
    (root / "mem20beta").mkdir(parents=True)
    (root / "mem20beta" / "pyproject.toml").write_text("[project]\nname='mem20beta'\n")
    (root / "notapackage").mkdir(parents=True)  # a directory, not a subsystem
    (root / "loosefile.txt").write_text("x")
    return root


def _log(tmp_path: Path, nodes: list[dict]) -> Path:
    path = tmp_path / "braid.log"
    path.write_text("\n".join(json.dumps(n) for n in nodes) + "\n")
    return path


def test_only_real_packages_count_as_installed(tmp_path):
    root = _fake_estate(tmp_path)
    names = [s["name"] for s in estate.installed_subsystems(str(root))]
    assert sorted(names) == ["mem20alpha", "mem20beta"], "a bare directory is not a subsystem"


def test_capability_claims_take_the_latest_write(tmp_path):
    path = _log(
        tmp_path,
        [
            {
                "op": "write:capability",
                "payload": {"payload": {"id": "cap.x.v1", "name": "old"}},
                "depth": 1,
                "cid": "br1",
            },
            {
                "op": "write:capability",
                "payload": {"payload": {"id": "cap.x.v1", "name": "new"}},
                "depth": 2,
                "cid": "br2",
            },
            {"op": "write:fact", "payload": {}, "depth": 3, "cid": "br3"},
        ],
    )
    claims = estate.capability_claims(str(path))
    assert list(claims) == ["cap.x.v1"]
    assert claims["cap.x.v1"]["name"] == "new", "the later claim must win"
    assert claims["cap.x.v1"]["cid"] == "br2"


def test_claims_with_no_name_match_are_unverified_not_absent(tmp_path):
    """Overstating the gap would feed the dreamer a falsehood."""
    root = _fake_estate(tmp_path)
    path = _log(
        tmp_path,
        [
            {"op": "write:capability", "payload": {"payload": {"id": "cap.alpha.v1"}}, "cid": "b1"},
            {"op": "write:capability", "payload": {"payload": {"id": "cap.quantum-beacon.v9"}}, "cid": "b2"},
            {"op": "write:capability", "payload": {"payload": {"id": "a"}}, "cid": "b3"},
        ],
    )
    report = estate.estate_report(str(root), str(path))
    assert report["installed_count"] == 2
    assert report["claimed_count"] == 3
    # cap.alpha.v1 matches the installed mem20alpha by stem, so it is NOT unverified.
    assert [c["id"] for c in report["unverified_claims"]] == ["cap.quantum-beacon.v9"]
    assert [c["id"] for c in report["junk_claims"]] == ["a"], "one-letter ids are probe noise"
    assert "unverified" in report["match_basis"]


def test_stem_join_links_a_claim_to_its_package(tmp_path):
    """cap.alpha.v1 and mem20alpha are the same thing spelled differently."""
    root = _fake_estate(tmp_path)
    path = _log(tmp_path, [{"op": "write:capability", "payload": {"payload": {"id": "cap.alpha.v1"}}, "cid": "b1"}])
    report = estate.estate_report(str(root), str(path))
    assert report["unverified_claims"] == [], "a matched claim must not be reported as a gap"


def test_corrupt_log_lines_do_not_abort_the_scan(tmp_path):
    path = tmp_path / "braid.log"
    path.write_text(
        "{not json\n"
        + json.dumps({"op": "write:capability", "payload": {"payload": {"id": "cap.k.v1"}}, "cid": "b1"})
        + "\n\n"
    )
    claims = estate.capability_claims(str(path))
    assert list(claims) == ["cap.k.v1"], "one bad line must not lose the good ones"


def test_missing_log_is_not_a_crash(tmp_path):
    assert estate.capability_claims(str(tmp_path / "nope.log")) == {}
    assert estate.tool_counts() is not None


# --- the feed tells the panel the truth --------------------------------------


def test_feed_names_installed_and_hedges_the_join(tmp_path):
    root = _fake_estate(tmp_path)
    path = _log(tmp_path, [{"op": "write:capability", "payload": {"payload": {"id": "cap.ghost.v1"}}, "cid": "b1"}])
    feed = estate.estate_feed(str(root), str(path))
    assert "mem20alpha" in feed and "mem20beta" in feed
    assert "do not reinvent" in feed
    assert "unverified" in feed.lower()
    assert "may exist under another name" in feed, "the weak join must be stated, not hidden"


def test_feed_never_blocks_nonexistent_proposals(tmp_path):
    """The whole point: it must not stop the dreamer inventing."""
    root = _fake_estate(tmp_path)
    feed = estate.estate_feed(str(root), str(_log(tmp_path, [])))
    assert "genuinely does not exist yet" in feed
    assert "do not assume a claim means it was built" in feed


def test_unreadable_estate_says_so_rather_than_guessing(tmp_path):
    feed = estate.estate_feed(str(tmp_path / "does-not-exist"), str(tmp_path / "no.log"))
    assert "could not be read" in feed
    assert "Assume nothing" in feed


def test_feed_stays_inside_a_context_budget(tmp_path):
    root = tmp_path / "big"
    for index in range(200):
        pkg = root / f"mem20pkg{index:03d}"
        pkg.mkdir(parents=True)
        (pkg / "pyproject.toml").write_text("[project]\n")
    feed = estate.estate_feed(str(root), str(_log(tmp_path, [])))
    assert len(feed) < 6000, f"feed is {len(feed)} chars; it crowds out the actual brief"


# --- the prompt/format contract ----------------------------------------------


def _kwargs():
    """Exactly what engine.run_iteration supplies to a template."""
    return {"seed": "s", "artifact": "a", "digest": "d", "estate": "e"}


@pytest.mark.parametrize(
    "name,template,extra",
    [
        ("FIDELITY_PROMPT", v.FIDELITY_PROMPT, {}),
        ("OMISSION_PROMPT", v.OMISSION_PROMPT, {}),
        ("SKEPTIC_PROMPT", v.SKEPTIC_PROMPT, {}),
        ("INVENTOR_PROMPT", v.INVENTOR_PROMPT, {"critiques": "c"}),
        ("FORECAST_PROMPT", v.FORECAST_PROMPT, {"axis": "ax"}),
        ("PAIRWISE_PROMPT", v.PAIRWISE_PROMPT, {"a": "A", "b": "B"}),
    ],
)
def test_every_template_formats_with_the_kwargs_the_engine_passes(name, template, extra):
    """A placeholder with no matching kwarg is a KeyError on the first real dream."""
    try:
        out = template.format(**{**_kwargs(), **extra})
    except KeyError as exc:  # pragma: no cover - the failure this test exists for
        pytest.fail(f"{name} has a placeholder the engine never supplies: {exc}")
    except IndexError as exc:
        pytest.fail(f"{name} has a positional placeholder the engine never supplies: {exc}")
    assert isinstance(out, str) and out.strip()


def test_inventor_prompt_actually_shows_the_estate():
    out = v.INVENTOR_PROMPT.format(artifact="A", critiques="C", estate="ESTATE-MARKER")
    assert "ESTATE-MARKER" in out
    assert "do not propose it again" in out, "awareness must change the instruction, not just add text"


def test_no_template_still_contains_an_unsupplied_placeholder():
    """Catches a new placeholder added to any template, not just the inventor's."""
    supplied = set(_kwargs()) | {"critiques", "axis", "a", "b"}
    for name in dir(v):
        value = getattr(v, name)
        if not (isinstance(value, str) and name.endswith("_PROMPT")):
            continue
        text = textwrap.dedent(value)
        for chunk in text.replace("{{", "\x00").replace("}}", "\x01").split("\x00"):
            body = chunk.split("\x01")[0]
            for _, field, _, _ in __import__("string").Formatter().parse(body):
                if field and field not in supplied:
                    pytest.fail(f"{name} uses unsupplied placeholder {{{field}}}")


def test_estate_context_block_is_the_feed(tmp_path, monkeypatch):
    monkeypatch.setattr(estate, "ESTATE_ROOT", str(_fake_estate(tmp_path)))
    monkeypatch.setattr(estate, "BRAID_LOG", str(_log(tmp_path, [])))
    assert "mem20alpha" in estate.context_block()
