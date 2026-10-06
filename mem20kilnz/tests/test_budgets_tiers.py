"""Tests for detail tiers.

The point of a tier is honesty about what was built. A blockout must not be
judged against a finished-asset budget, and a blockout must not be able to
masquerade as a finished asset either. `standard` must stay byte-identical to
the roadmap budget, because that is the authoritative number.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mem20kilnz import budgets as B
from mem20kilnz import validate as V

DEMO = str(Path(__file__).resolve().parent.parent
            / "engine" / "examples" / "demo.glb")
#: The triangle count three live builds of a crate brief actually produced.
REAL_BLOCKOUT = 60


def test_standard_tier_is_the_roadmap_budget_unchanged():
    for family, band in B.TRIANGLE_BUDGETS.items():
        assert B.tier_band(family, "standard") == band, (
            f"{family}: the standard tier must not drift from the roadmap"
        )


def test_blockout_band_is_derived_not_invented():
    for family, (floor, _ceil) in B.TRIANGLE_BUDGETS.items():
        assert B.tier_band(family, "blockout") == (1, floor - 1)


def test_the_real_crate_output_passes_as_blockout_and_fails_as_standard():
    """The measured situation this tier exists for."""
    assert B.check_triangles("prop", REAL_BLOCKOUT, tier="blockout").ok is True
    standard = B.check_triangles("prop", REAL_BLOCKOUT, tier="standard")
    assert standard.ok is False
    assert "under the standard floor of 2000" in standard.reason


def test_a_blockout_cannot_masquerade_as_finished():
    """The reverse guard: blockout must have a ceiling, not just a floor."""
    verdict = B.check_triangles("prop", 5_000, tier="blockout")
    assert verdict.ok is False
    assert "exceeds the blockout ceiling" in verdict.reason


def test_a_blockout_still_requires_geometry():
    assert B.check_triangles("prop", 0, tier="blockout").ok is False


def test_hero_is_only_defined_for_hero_scale_families():
    assert B.tier_band("player", "hero") == B.TRIANGLE_BUDGETS["player"]
    assert B.tier_band("boss", "hero") == B.TRIANGLE_BUDGETS["boss"]
    assert B.tier_band("prop", "hero") is None
    verdict = B.check_triangles("prop", 3_000, tier="hero")
    assert verdict.ok is False
    assert "not defined for family 'prop'" in verdict.reason


def test_an_unknown_tier_is_refused_by_name():
    verdict = B.check_triangles("prop", 3_000, tier="ultra")
    assert verdict.ok is False
    assert "unknown detail tier 'ultra'" in verdict.reason
    assert "blockout, standard, hero" in verdict.reason


def test_unknown_family_is_still_refused_at_every_tier():
    for tier in B.DETAIL_TIERS:
        assert B.check_triangles("spaceship", 100, tier=tier).ok is False


@pytest.mark.parametrize("family,triangles,expected", [
    ("prop", 60, "blockout"),
    ("prop", 1_999, "blockout"),
    ("prop", 2_000, "standard"),
    ("prop", 6_000, "standard"),
    ("prop", 6_001, "blockout"),      # over the ceiling: not a standard pass
    ("prop", 0, "none"),
    ("player", 14_999, "blockout"),
    ("player", 18_000, "hero"),
    ("player", 9_000, "blockout"),    # under the player floor of 15,000
    # For a hero-scale family the standard and hero bands coincide, and
    # achieved_tier reports the highest tier satisfied, so this is hero.
    ("player", 15_000, "hero"),
])
def test_achieved_tier_reports_what_was_built(family, triangles, expected):
    assert B.achieved_tier(family, triangles) == expected


def test_gate_accepts_a_tier_and_defaults_to_standard():
    """Defaulting to standard is what keeps every existing caller unchanged."""
    default = V.gate(DEMO, family="prop")
    explicit = V.gate(DEMO, family="prop", tier="standard")
    assert [f.code for f in default.errors] == [f.code for f in explicit.errors]

    as_blockout = V.gate(DEMO, family="prop", tier="blockout")
    assert not any(f.code == "budget" for f in as_blockout.errors), (
        "the demo is a blockout by triangle count, so a blockout gate must accept it"
    )
    assert any(f.code == "budget" for f in default.errors), (
        "and the standard gate must still refuse it"
    )


def test_verdict_and_findings_carry_the_tier():
    verdict = B.check_triangles("prop", 60, tier="blockout")
    assert verdict.tier == "blockout"
    assert verdict.as_dict()["tier"] == "blockout"


def test_table_exposes_the_tiers():
    table = B.table()
    assert table["detail_tiers"] == list(B.DETAIL_TIERS)
    assert "hero_families" in table
    assert table["tier_bands"]["prop"]["standard"] == (2000, 6000)
