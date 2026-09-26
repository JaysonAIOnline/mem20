"""Poly, texture and naming budgets for asset families.

The numbers come from the mem20 roadmap `jairf-tech-budgets`, which is the
single source for JAIRF budgets and naming. They are transcribed here, not
invented, and the roadmap reference is recorded so a drift is traceable.

LOD0 is the authored budget. LOD1-3 are the reduced budgets the engine's `lod`
op is expected to hit; they are stated as fractions of LOD0 rather than as
absolute numbers so they track a changed LOD0 automatically.
"""
from __future__ import annotations

from dataclasses import dataclass

ROADMAP_SOURCE = "jairf-tech-budgets"

#: Asset family -> (LOD0 min, LOD0 max) triangles.
TRIANGLE_BUDGETS: dict[str, tuple[int, int]] = {
    "player": (15_000, 25_000),
    "boss": (20_000, 35_000),
    "enemy": (8_000, 15_000),
    "weapon": (3_000, 8_000),
    "prop": (2_000, 6_000),
    "tree": (3_000, 8_000),
    "builder_piece": (500, 3_000),
}

#: Fraction of the LOD0 ceiling each reduced level must stay under.
LOD_FRACTIONS: dict[int, float] = {1: 0.60, 2: 0.30, 3: 0.15}

#: Texture edge in pixels by role.
TEXTURE_BUDGETS: dict[str, int] = {
    "hero": 2048,
    "normal": 1024,
    "modular": 1024,
    "small": 512,
}

#: Naming prefixes required by the roadmap, mapped to what they denote.
NAME_PREFIXES: dict[str, str] = {
    "SM_": "static mesh",
    "SK_": "skeletal mesh",
    "M_": "mesh",
    "T_": "texture",
    "PF_": "prefab",
    "A_": "animation",
    "SFX_": "sound effect",
    "MUS_": "music",
    "AMB_": "ambience",
    "UI_": "user interface",
    "SO_": "scriptable object data",
}

#: Families that must not be prefixed, because the prefix would be meaningless.
UNPREFIXED = {"material", "scene", "camera", "light"}


@dataclass(frozen=True)
class BudgetVerdict:
    family: str
    triangles: int
    lod0_min: int
    lod0_max: int
    ok: bool
    reason: str

    def as_dict(self) -> dict:
        return {
            "family": self.family,
            "triangles": self.triangles,
            "lod0_min": self.lod0_min,
            "lod0_max": self.lod0_max,
            "ok": self.ok,
            "reason": self.reason,
        }


def families() -> list[str]:
    return sorted(TRIANGLE_BUDGETS)


def lod_ceiling(family: str, lod: int = 0) -> int | None:
    """Triangle ceiling for a family at a given LOD, or None if the family is unknown."""
    band = TRIANGLE_BUDGETS.get(family)
    if band is None:
        return None
    frac = LOD_FRACTIONS.get(lod)
    if frac is None:
        return band[1] if lod == 0 else None
    return int(band[1] * frac)


def check_triangles(family: str, triangles: int, lod: int = 0) -> BudgetVerdict:
    band = TRIANGLE_BUDGETS.get(family)
    if band is None:
        return BudgetVerdict(
            family, triangles, 0, 0, False,
            f"unknown asset family '{family}'; known: {', '.join(families())}",
        )
    lo, hi = band
    if lod == 0:
        if triangles < lo:
            return BudgetVerdict(
                family, triangles, lo, hi, False,
                f"{triangles} is under the LOD0 floor of {lo} for {family}",
            )
        if triangles > hi:
            return BudgetVerdict(
                family, triangles, lo, hi, False,
                f"{triangles} exceeds the LOD0 ceiling of {hi} for {family}",
            )
        return BudgetVerdict(family, triangles, lo, hi, True, f"within LOD0 {lo}-{hi}")
    ceiling = lod_ceiling(family, lod)
    if ceiling is None:
        return BudgetVerdict(family, triangles, lo, hi, False, f"LOD{lod} is not a defined level")
    if triangles > ceiling:
        return BudgetVerdict(
            family, triangles, lo, hi, False,
            f"{triangles} exceeds the LOD{lod} ceiling of {ceiling} for {family}",
        )
    return BudgetVerdict(family, triangles, lo, hi, True, f"within LOD{lod} ceiling {ceiling}")


def infer_family(name: str) -> str:
    """Best-effort family from a name, used to pre-select a budget.

    Deliberately conservative: an unrecognised name yields `prop`, the smallest
    common family, so an unclassified asset is judged against a tight budget
    rather than a generous one.
    """
    low = name.lower()
    for key in ("player", "hero", "character", "boss", "enemy", "weapon", "sword",
                "tree", "prop", "crate", "barrel", "builder", "piece"):
        if key in low:
            if key in ("piece",):
                return "builder_piece"
            if key in ("hero", "character"):
                return "player"
            if key in ("crate", "barrel", "prop"):
                return "prop"
            return key
    return "prop"


def check_name(name: str) -> tuple[bool, str]:
    """Check a name against the roadmap's prefix table."""
    if name.lower() in UNPREFIXED:
        return True, f"'{name}' is in the unprefixed set"
    for prefix in NAME_PREFIXES:
        if name.startswith(prefix):
            return True, f"'{name}' carries the {prefix} prefix ({NAME_PREFIXES[prefix]})"
    if not name:
        return False, "name is empty"
    return False, (
        f"'{name}' has no roadmap prefix; expected one of "
        f"{', '.join(sorted(NAME_PREFIXES))}"
    )


def check_texture(role: str, edge_pixels: int) -> tuple[bool, str]:
    cap = TEXTURE_BUDGETS.get(role)
    if cap is None:
        return False, f"unknown texture role '{role}'; known: {', '.join(sorted(TEXTURE_BUDGETS))}"
    if edge_pixels > cap:
        return False, f"{edge_pixels}px exceeds the {role} budget of {cap}px"
    return True, f"{edge_pixels}px within the {role} budget of {cap}px"


def table() -> dict:
    return {
        "roadmap_source": ROADMAP_SOURCE,
        "triangle_budgets": {k: {"min": v[0], "max": v[1]} for k, v in TRIANGLE_BUDGETS.items()},
        "lod_fractions": {str(k): v for k, v in LOD_FRACTIONS.items()},
        "texture_budgets": TEXTURE_BUDGETS,
        "name_prefixes": NAME_PREFIXES,
        "unprefixed": sorted(UNPREFIXED),
    }
