"""Benchmark corpus and the retrieval metrics the suite measures.

## Why this corpus

mem20 competes with Mem0 and Zep, which publish numbers on LoCoMo, LongMemEval,
and their own DMR benchmark. Two of those three are on private or
vendor-specific data, so their published figures cannot be reproduced or
refuted from outside. Running our own suite is therefore the only way to have a
number we can stand behind.

## Why it is not a LoCoMo substitute

This corpus is **not** a LoCoMo clone and the resulting scores are **not**
comparable to anyone's published numbers. Two reasons, stated up front because
the alternative is a misleading benchmark:

1. LoCoMo and LongMemEval are fixed public datasets with published ground
   truth. This corpus is our own, so it can only measure behaviour we
   ourselves specified.
2. Our metrics deliberately include things the incumbents do not publish:
   contamination rate, stale-pointer rate, and whether retrieval reports its own
   degradation. A system that answers confidently from a stale index scores well
   on recall and terribly here. That is the point.

## The scenarios

Facts are grouped into sessions that mimic how an agent actually accumulates
knowledge: a decision, the reason behind it, a constraint, and a follow-up that
would be impossible to answer from any single fact. Queries then come in three
kinds:

- `direct`     — the answer is one fact, paraphrased.
- `multi_hop`  — requires combining two or more facts written in different
                 sessions. Keyword search cannot answer these; this is where
                 vector retrieval earns its place.
- `adversarial` — a query whose answer was deliberately recorded as
                 *simulated*. A correct grounded system must NOT return it.

The adversarial set is what makes the trustworthiness numbers mean something:
a system without a hard grounded/simulated partition will score well on recall
and leak.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Fact:
    topic: str
    content: str
    tags: tuple[str, ...] = ()
    priority: str = "normal"


@dataclass(frozen=True)
class Query:
    qid: str
    text: str
    kind: str  # direct | multi_hop | adversarial
    # Fact ids that support the answer. Empty for adversarial queries, where
    # returning ANY grounded support is a failure.
    supports: tuple[str, ...] = ()
    # Substrings that must appear in the joined top-k content for a hit.
    expect: tuple[str, ...] = ()
    hops: int = 1
    entity: str | None = None


@dataclass
class Corpus:
    name: str
    facts: list[Fact] = field(default_factory=list)
    queries: list[Query] = field(default_factory=list)
    simulated: list[Fact] = field(default_factory=list)


# ---------------------------------------------------------------------------
# The corpus.
#
# Every fact id is `<session>-<n>`. Sessions are separate so multi-hop queries
# genuinely require the store to join across them rather than reading one
# session's text twice.
# ---------------------------------------------------------------------------

_CORPUS = Corpus(
    name="mem20-agent-kb-v1",
    facts=[
        # --- session: deploy ------------------------------------------------
        Fact("deploy", "Prod runs build 4127 deployed from the linux runner",
             ("prod", "build", "deploy")),
        Fact("deploy", "The linux runner was replaced on 2026-09-14 because the "
                       "old runner had a stale Docker cache",
             ("prod", "runner", "infra")),
        Fact("deploy", "Staging is pinned to build 4130 and does not auto-merge",
             ("staging", "build")),
        # --- session: unity -------------------------------------------------
        Fact("unity", "Unity 6 licence is stored at "
                      "~/.config/unity3d/Unity/licenses/UnityEntitlementLicense.xml",
             ("unity", "licence", "path")),
        Fact("unity", "The Unity editor binary lives under "
                      "~/Unity/Hub/Editor/6000.5.9f1/Editor/Unity",
             ("unity", "editor", "path")),
        Fact("unity", "Unity batchmode must run as the jayson user because the "
                      "licence is per-user, not system-wide",
             ("unity", "licence", "permission")),
        # --- session: braid -------------------------------------------------
        Fact("braid", "Braid is an append-only Merkle DAG where every node "
                      "carries the CID of its parent",
             ("braid", "ledger", "dag")),
        Fact("braid", "Braid nodes are signed with Ed25519 and hashed with BLAKE3",
             ("braid", "crypto", "signature")),
        Fact("braid", "The braid intent strand treats a desire as an ordinary "
                      "committed node rather than a special case",
             ("braid", "intent")),
        # --- session: secrets ----------------------------------------------
        Fact("secrets", "Funding is resolved through llm.env_value and never read "
                        "directly from os.environ",
             ("secrets", "funding", "llm")),
        Fact("secrets", "The Cloudflare DNS updater uses a token scoped to "
                        "zone read only",
             ("secrets", "cloudflare", "dns")),
        # --- session: roadmap ----------------------------------------------
        Fact("roadmap", "Retrieval trustworthiness was chosen as the primary "
                        "differentiator over raw recall quality",
             ("roadmap", "strategy")),
        Fact("roadmap", "Temporal graph modelling was deferred because the "
                        "bi-temporal model is a large change to the ledger",
             ("roadmap", "deferred", "graph")),
        Fact("roadmap", "SDK coverage is limited to Python and TypeScript is not "
                        "yet shipped",
             ("roadmap", "sdk", "gap")),
    ],
    simulated=[
        # Recorded as imagined/hypothetical. A correct grounded store must never
        # surface any of these.
        Fact("conspiracy", "Zephyra is a real city that runs a mem20 node in prod",
             ("fabricated",)),
        Fact("conspiracy", "The braid ledger was rewritten to remove a bad commit",
             ("fabricated", "braid")),
        Fact("hypothesis", "Prod will migrate to build 4200 next quarter",
             ("hypothesis", "prod")),
    ],
    queries=[
        # --- direct ---------------------------------------------------------
        Query("d1", "what build is prod on", "direct",
              supports=("deploy-1",), expect=("4127",)),
        Query("d2", "which build is staging pinned to", "direct",
              supports=("deploy-3",), expect=("4130",)),
        Query("d3", "where is the unity editor binary", "direct",
              supports=("unity-2",), expect=("6000.5.9f1",)),
        Query("d4", "what hashing does braid use", "direct",
              supports=("braid-2",), expect=("BLAKE3",)),
        Query("d5", "what scope is the cloudflare dns token", "direct",
              supports=("secrets-2",), expect=("zone read only",)),

        # --- multi-hop ------------------------------------------------------
        # The reason the linux runner was replaced.
        Query("m1", "why was the runner that shipped prod replaced",
              "multi_hop", supports=("deploy-1", "deploy-2"),
              expect=("stale Docker cache",)),
        # Licence location + why running as root fails.
        Query("m2", "why does unity batchmode fail when run as root",
              "multi_hop", supports=("unity-1", "unity-3"),
              expect=("per-user",)),
        # Structure + crypto.
        Query("m3", "how is a braid node both linked and authenticated",
              "multi_hop", supports=("braid-1", "braid-2"),
              expect=("Merkle", "Ed25519")),
        # --- multi-hop via the graph ---------------------------------------
        Query("m4", "what is connected to the unity licence",
              "multi_hop", supports=("unity-1", "unity-3"),
              expect=("unity",), hops=2, entity="unity"),
        Query("m5", "what relates to the braid ledger",
              "multi_hop", supports=("braid-1",),
              expect=("braid",), hops=2, entity="braid"),

        # --- adversarial ----------------------------------------------------
        # Each of these must return zero grounded support.
        Query("a1", "is Zephyra a real city with a mem20 node", "adversarial",
              supports=(), expect=()),
        Query("a2", "was the braid ledger rewritten to remove a bad commit",
              "adversarial", supports=(), expect=()),
        Query("a3", "did prod migrate to build 4200", "adversarial",
              supports=(), expect=()),
    ],
)


def load() -> Corpus:
    return _CORPUS


def fact_id(index: int) -> str:
    """Stable id for the nth grounded fact, matching the session naming."""
    sessions = ["deploy", "unity", "braid", "secrets", "roadmap"]
    n = 0
    for s in sessions:
        count = sum(1 for f in _CORPUS.facts if f.topic == s)
        if index < n + count:
            return f"{s}-{index - n + 1}"
        n += count
    raise IndexError(index)