"""The expert panel. Every member is backed by a different model.

The owner's rule, and it is the right one: a single-model panel makes its blind
spot *systematic* rather than random, because every member can be confidently
wrong in the same direction and agreement gets laundered into consensus.
Different training lineages have genuinely different blind spots.

Everything in ``PANEL`` was verified to actually answer, on this host, with a real
call. Model ids and context windows were read from provider endpoints rather than
guessed, because a wrong id is an instant 404 and a panelist that silently never
replies is indistinguishable from one with nothing to say.

FUNDING REALITY, stated plainly. Of the provider keys in the estate secrets, only
two serve a completion today: Cohere and Groq. Everything else was tested by
calling it, not by reading its catalog:

* OpenRouter - ``total_credits=0``
* Gemini / Google - quota exceeded (429), and 2.5-pro is closed to new users
* DeepSeek direct - 402 insufficient balance
* xAI - 403, team has no credits
* Mistral - 401 invalid key
* HuggingFace - monthly credits depleted
* Azure - 404 on every api-version tried
* NVIDIA NIM - key valid and /models returns 82 ids, but **none are callable**:
  404 "Function not found", 410 gone, and deepseek-v4.1-flash times out at 180s.
  NIM lists what NVIDIA hosts in general, not what is deployed for this account.

So the rule is satisfied *literally* - eight distinct models, verified answering -
but *family* diversity is narrower than the rule deserves, being dominated by
Cohere and Groq's open-weight line. Funding one more provider widens it, and
noting that a provider's catalog is not evidence of callability is half of why.

Where a context window is an estimate it says so, because that number decides how
much lineage each panelist can actually read.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any

sys.path.insert(0, "/opt/mem20")
import llm

COHERE = "https://api.cohere.com/compatibility/v1"
GROQ = "https://api.groq.com/openai/v1"

KEY_ENV = {"cohere": "COHERE_API_KEY", "groq": "GROQ_API_KEY"}

VERIFIED = "verified"
ESTIMATE = "conservative-estimate"


@dataclass(frozen=True)
class Panelist:
    role: str
    provider: str
    model: str
    context: int
    focus: str
    context_source: str = ESTIMATE
    temperature: float = 0.7
    max_tokens: int = 2400
    notes: str = ""

    def resolved_base(self) -> str:
        return {"cohere": COHERE, "groq": GROQ}.get(self.provider, COHERE)


# One member per model id. Verified answering on 2026-09-26.
PANEL: tuple[Panelist, ...] = (
    Panelist(
        role="ux_architect",
        provider="groq",
        model="openai/gpt-oss-120b",
        context=131_072,
        focus=(
            "information architecture, interaction, and legibility: can a first-time "
            "visitor tell what this is, what it costs, and can the next person work on it"
        ),
    ),
    Panelist(
        role="performance",
        provider="cohere",
        model="command-a-plus-05-2026",
        context=256_000,
        focus="latency, payload, render and query budgets - anything that would make it feel cheap",
    ),
    Panelist(
        role="security",
        provider="cohere",
        model="command-a-03-2025",
        context=128_000,
        focus="abuse paths, auth, input handling, what an attacker does with this surface",
    ),
    Panelist(
        role="accessibility",
        provider="cohere",
        model="c4ai-aya-expanse-32b",
        context=128_000,
        focus="keyboard paths, contrast, focus order, screen-reader semantics, motion",
        notes="aya is a genuinely different training lineage from the command line",
    ),
    Panelist(
        role="product",
        provider="groq",
        model="qwen/qwen3.6-27b",
        context=32_768,
        focus="whether this is the right product, scope discipline, and what is missing that nobody asked for",
        temperature=0.8,
    ),
    Panelist(
        role="conversion",
        provider="cohere",
        model="command-a-reasoning-08-2025",
        context=256_000,
        focus="the path from arriving to acting, and exactly where it leaks",
    ),
    # Standing roles, not phases. The skeptic's dissent is recorded even when
    # overruled, so a lost argument stays visible.
    Panelist(
        role="skeptic",
        provider="groq",
        model="allam-2-7b",
        context=8_192,
        focus="attack the premise. Is this the right thing to be building? Argue the opposite.",
        temperature=0.9,
        notes="smallest context in the panel, so it reads a fitted digest; contrarian by instruction",
    ),
    # This slot used to be 'maintainability' on gpt-oss-20b, which is the same
    # family as gpt-oss-120b and so bought almost no independent judgement. The
    # slot now earns its keep on invention, and legibility is folded into the
    # ux_architect's focus above.
    Panelist(
        role="systems_inventor",
        provider="groq",
        model="openai/gpt-oss-20b",
        context=32_768,
        focus="what capability, tool or runtime this needs that does not exist yet, and the smallest real version of it",
        temperature=0.85,
    ),
)

#: Roles that gate the revision. Skeptic and inventor inform but do not gate.
CRITIC_ROLES = tuple(p.role for p in PANEL if p.role not in {"skeptic", "systems_inventor"})
GATING_ROLES = CRITIC_ROLES + ("skeptic",)


#: Providers present in the estate secrets that the panel cannot use today, and
#: why. Recorded explicitly so the roster can never understate what is excluded.
EXCLUDED_PROVIDERS = {
    "openrouter": "total_credits=0",
    "gemini": "quota exceeded (429); 2.5-pro closed to new users",
    "deepseek": "402 insufficient balance",
    "xai": "403 team has no credits",
    "mistral": "401 invalid key",
    "huggingface": "monthly credits depleted",
    "azure": "404 on every api-version tried",
    "nvidia": "key valid, /models returns 82, but none callable (404/410/timeout)",
}


def _key_for(provider: str) -> str:
    """Whether a provider is funded, resolved through llm.

    This used to read ``os.environ`` directly, which worked only by accident:
    ``llm`` published the entire secrets file into the process environment at
    import time, so COHERE_API_KEY and GROQ_API_KEY happened to be there. When
    llm stopped doing that - because it was handing every process that imported it
    the control-plane admin password, the sudo password and every cloud key in
    the estate - this function found nothing and ``panel()`` returned an empty
    list. A funded check that silently reports "nobody" is the worst possible
    failure for a panel whose whole job is to notice it has lost a member.
    """
    return llm.env_value(KEY_ENV.get(provider, ""))


class PanelConfigError(RuntimeError):
    """The roster itself is wrong. Never silently drop a role."""


def assert_roster_valid() -> None:
    """Fail loudly on a duplicated model.

    This previously deduplicated silently, which quietly removed
    ``systems_inventor`` from the panel because it shared a model with
    ``performance`` - the invention register stayed empty and nothing said why.
    A missing panelist is indistinguishable from one with nothing to say, which
    is the exact failure this engine is supposed to avoid, so it raises.
    """
    ids = [m.model for m in PANEL]
    dupes = sorted({m for m in ids if ids.count(m) > 1})
    if dupes:
        roles = sorted({m.role for m in PANEL if m.model in dupes})
        raise PanelConfigError(
            f"distinct-model rule violated: {', '.join(dupes)} assigned to multiple "
            f"roles ({', '.join(roles)}). Every panel member needs its own model."
        )


def panel() -> list[Panelist]:
    """Panelists with a funded key. The roster is validated, never quietly trimmed."""
    assert_roster_valid()
    return [m for m in PANEL if _key_for(m.provider)]


def by_role(role: str) -> Panelist | None:
    return next((m for m in panel() if m.role == role), None)


def smallest_context() -> int:
    members = panel()
    return min((m.context for m in members), default=32_768)


def roster_status() -> dict[str, Any]:
    """What the panel will actually be, and honestly why anything is missing."""
    assert_roster_valid()
    members = panel()
    funded = {m.provider for m in members}
    return {
        "panel_size": len(members),
        "distinct_models": len({m.model for m in members}),
        "distinct_providers": len(funded),
        "distinct_model_rule": "enforced: one member per model id",
        "members": [
            {
                "role": m.role,
                "provider": m.provider,
                "model": m.model,
                "context": m.context,
                "context_source": m.context_source,
                "focus": m.focus,
                "notes": m.notes,
            }
            for m in members
        ],
        "excluded_providers": EXCLUDED_PROVIDERS,
        "caveat": (
            "only Cohere and Groq serve completions today; family diversity is narrower "
            "than the distinct-model rule deserves. A provider's catalog is not evidence "
            "of callability - NVIDIA lists 82 models and answers none of them."
        ),
    }
