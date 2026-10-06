"""Seed generation: associative cues, not tasks.

The previous two attempts were wrong in kind, not in detail. The first held
twelve invented sentences and handed them out round-robin. The second derived
sentences from the estate's *backlog* - this package is untested, that claim is
unverified - which is a ticket queue wearing a dream's clothes. It also
inverted the engine's purpose: a board should be fed by dreams, and this made
the dream engine a board feeder that could only point at work already visible.

What the research on dreaming actually describes is the opposite. Sleep onset
binds recent experience to *loosely associated* memory, and semantic distance
between concepts is what predicts creative quality (Lacaux et al. 2021;
Horowitz et al. 2023). Dreams are also experienced as real rather than
specified, and the dreamer has no agenda - the dreamer does not know what the
dream is for.

So a seed here is a **cue**: a theme plus a partner, phrased as something to
turn over rather than something to do. The estate supplies the *material*,
because a dream with no material is a hallucination, but the estate supplies it
as imagery and never as an agenda. The cue names a thing and a company it
never keeps; what the dreamer makes of the collision is not specified, and
deliberately is not.
"""

from __future__ import annotations

import os
import re
import tomllib
from collections.abc import Callable
from typing import Any

from . import estate

#: Every top-level entry the estate can see. ``estate_report`` only counts the
#: 157 that carry a ``pyproject.toml``; the rest are real material too.
MAX_SEED_FACTS = 600

SKIP_DIRS = frozenset(
    {".git", ".venv", "venv", "node_modules", "__pycache__", ".sitemap", "secrets", "backups"}
)


class SeedExhausted(RuntimeError):
    """Every derivable seed has already been issued."""


def _top_level_dirs(root: str) -> list[str]:
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return []
    return [
        name
        for name in names
        if name not in SKIP_DIRS
        and not name.startswith(".")
        and os.path.isdir(os.path.join(root, name))
    ]


def _domain_words(name: str) -> list[str]:
    """The words a package name is made of, once the mem20 prefix is gone.

    ``mem20adaptiveforgettingenginez`` is not a theme, it is a filename. The
    words inside it - adaptive, forgetting, engine - are themes, and they are
    what makes a distant pairing possible at all.
    """
    stripped = name.removeprefix("mem20").removesuffix("z")
    parts: list[str] = []
    for chunk in stripped.split("_"):
        parts.extend(p for p in chunk.split("-") if p)
    words: list[str] = []
    for part in parts:
        current = ""
        for char in part:
            if char.isupper() and current:
                words.append(current)
                current = char
            else:
                current += char
        if current:
            words.append(current)
    return [w.lower() for w in words if len(w) > 2]


#: Words too common to pair with anything meaningfully.
_STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "can", "for",
        "from", "has", "have", "if", "in", "into", "is", "it", "its", "may", "not",
        "of", "on", "or", "such", "that", "the", "their", "then", "there", "these",
        "they", "this", "to", "was", "were", "which", "who", "will", "with", "would",
        "you", "your", "also", "any", "all", "each", "more", "most", "other", "some",
        "than", "them", "those", "use", "used", "using", "only", "own", "same", "too",
        "very", "when", "where", "while", "without", "within", "about", "after",
        "before", "between", "during", "over", "under", "again", "once", "here",
        "both", "few", "nor", "out", "off", "above", "below", "itself",
    }
)

_WORD = re.compile(r"[a-z][a-z]{2,13}")


def _read_description(path: str) -> str:
    """The prose a package describes itself with.

    Deliberately excludes the package *name*: a filename contributes fragments
    like ``humancapabilit`` that look like words to a regex and mean nothing,
    and they then get paired with themselves.
    """
    try:
        with open(path, "rb") as handle:
            data = tomllib.load(handle)
    except Exception:  # noqa: BLE001 - a package with an unreadable manifest is not a word source
        return ""
    project = data.get("project") or {}
    return str(project.get("description") or "") + " " + " ".join(
        str(k) for k in (project.get("keywords") or [])
    )


def estate_vocabulary(
    root: str | None = None,
    min_speakers: int = 2,
    max_speakers: int = 8,
) -> list[str]:
    """The estate's own language, as words a few unrelated things share.

    A filename is not a theme. ``mem20adaptiveforgettingenginez`` yields
    *adaptive, forgetting, engine* once, and nothing else in the estate uses
    those words, so pairing on them just pairs a package with itself. Reading
    the descriptions instead gives the vocabulary mem20 actually thinks in.

    Both ends of the frequency range are filtered, and both ends matter:

    * below ``min_speakers`` a word belongs to exactly one package, so pairing
      on it just pairs that package with itself;
    * above ``max_speakers`` a word is template. The fourteen crew runtimes all
      describe themselves as a crew runtime grouping reviewed packages for joint
      integration, and left in, the most "shared" words on the estate are mem,
      runtime, crew, grouping, joint, reviewed and integration - the template
      rather than the domain. Shared by a handful of unrelated packages is
      domain language; shared by nearly all of them is a phrase they copied.
    """
    base = root or estate.ESTATE_ROOT
    counts: dict[str, int] = {}
    for name in _top_level_dirs(base):
        text = _read_description(os.path.join(base, name, "pyproject.toml"))
        if not text:
            continue
        for word in set(_WORD.findall(text.lower())):
            if word in _STOPWORDS:
                continue
            counts[word] = counts.get(word, 0) + 1

    # Prefer the strict filter. Relax only if it leaves *nothing*: an absolute
    # ceiling empties the vocabulary outright on a small estate whose packages
    # all describe themselves the same way, and an engine with no vocabulary
    # refuses to dream at all. Relaxing on "fewer than N" instead would put the
    # template straight back, which is what the ceiling exists to remove.
    ranked = [w for w, n in counts.items() if min_speakers <= n <= max_speakers]
    if not ranked:
        ceiling = max_speakers * 12
        ranked = [w for w, n in counts.items() if min_speakers <= n <= ceiling]
    ranked.sort(key=lambda w: (-counts[w], w))
    return ranked


def _cue_shapes() -> tuple[tuple[str, Callable[[str, str, str], str]], ...]:
    """Grammars for a cue. The grammar is not the content; the words are."""

    def _a(w1: str, w2: str, host: str) -> str:
        return f"{w1} and {w2}, which have never had anything to do with each other"

    def _b(w1: str, w2: str, host: str) -> str:
        return f"what {host} would become if it took {w1} seriously, having never considered {w2}"

    def _c(w1: str, w2: str, host: str) -> str:
        return f"the shape of {w1} arriving in a place built entirely out of {w2}"

    def _d(w1: str, w2: str, host: str) -> str:
        return f"a thing that is neither {w1} nor {w2} and does not know either of them exist"

    def _e(w1: str, w2: str, host: str) -> str:
        return f"{w1} without memory, meeting {w2} without a name"

    def _f(w1: str, w2: str, host: str) -> str:
        return f"the thing you could build at 3am out of {w1} and {w2} and never tell anyone about"

    def _g(w1: str, w2: str, host: str) -> str:
        return f"the wrong shape for {w1} and {w2} at once, and no name for the result"

    def _h(w1: str, w2: str, host: str) -> str:
        return f"{w1} as a feeling rather than a feature, next to {w2} as a law rather than a file"

    def _i(w1: str, w2: str, host: str) -> str:
        return f"a language for {w1} that {w2} would not recognise as the same subject"

    def _j(w1: str, w2: str, host: str) -> str:
        return f"what is left of {w1} once {w2} has taken everything it was for"

    def _k(w1: str, w2: str, host: str) -> str:
        return f"the instrument you would build to hear {w1} and {w2} at the same time"

    def _l(w1: str, w2: str, host: str) -> str:
        return f"somewhere {w1} stops being a metaphor and {w2} stops being a feature"

    def _m(w1: str, w2: str, host: str) -> str:
        return f"the second-order effect of {w1} on {w2}, which nobody has needed yet"

    return (
        ("collision", _a),
        ("serious", _b),
        ("arrival", _c),
        ("neither", _d),
        ("nameless", _e),
        ("3am", _f),
        ("wrong_shape", _g),
        ("feeling_law", _h),
        ("language", _i),
        ("remnant", _j),
        ("instrument", _k),
        ("crossing", _l),
        ("second_order", _m),
    )


def _distance(a: str, b: str) -> int:
    """Character-level distance, a cheap stand-in for semantic distance.

    Used only to *order* pairings so the most distant ones are reached first.
    The dream engine measures real divergence on the artifact; this only decides
    which words get put in front of the panel.
    """
    return len(set(a) ^ set(b)) + abs(len(a) - len(b)) // 2


def candidates(root: str | None = None) -> list[tuple[str, str]]:
    """(fingerprint, cue) for every cue derivable from the estate's vocabulary.

    Pairings are walked widest-first. A cue that pairs two words sharing letters
    is a paraphrase of a subsystem that already exists; the whole point is to
    put words next to each other that have no reason to be near.
    """
    hosts = _top_level_dirs(root or estate.ESTATE_ROOT)[:MAX_SEED_FACTS]
    vocab = estate_vocabulary(root)
    shapes = _cue_shapes()
    if not vocab:
        return []

    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    rendered: set[str] = set()
    host = hosts[0] if hosts else "this machine"

    for i, w1 in enumerate(vocab):
        for w2 in vocab[i + 1 :]:
            if w1 == w2:
                continue
            far = _distance(w1, w2)
            if far < 4:
                continue
            shape_name, render = shapes[(i + far) % len(shapes)]
            who = hosts[(i + far) % len(hosts)] if hosts else host
            cue = render(w1, w2, who)
            fingerprint = f"{shape_name}:{w1}:{w2}"
            # Dedupe on the rendered sentence, not only the fingerprint: two
            # shapes can ignore one of their words and render identically, and
            # a seed that repeats verbatim is the exact defect this replaces.
            if fingerprint in seen or cue in rendered:
                continue
            seen.add(fingerprint)
            rendered.add(cue)
            out.append((f"{far:03d}:{fingerprint}", cue))
    out.sort(key=lambda item: item[0], reverse=True)
    return out


def next_seed(
    state: dict[str, Any],
    root: str | None = None,
) -> str:
    """Draw a cue that has never been issued before.

    ``state`` is the caller's idle state; the issued ledger is written back into
    it so a restart cannot reissue a cue the engine has already dreamed.
    """
    issued = set(state.get("seeds_issued") or [])
    fingerprints = set(state.get("seed_fingerprints") or [])
    pool = candidates(root)
    if not pool:
        raise SeedExhausted("the estate exposed no vocabulary to pair from")

    for fingerprint, cue in pool:
        if fingerprint in fingerprints or cue in issued:
            continue
        state["seed_fingerprints"] = sorted(fingerprints | {fingerprint})
        state["seeds_issued"] = sorted(issued | {cue})
        state["seed_index"] = int(state.get("seed_index", 0)) + 1
        return cue

    raise SeedExhausted(
        f"every one of the {len(pool)} derivable cues has already been issued; "
        f"widen the vocabulary or the shapes rather than repeating one"
    )


def cue_pool_size(root: str | None = None) -> int:
    return len(candidates(root))
