"""mem20benchmarkz — retrieval benchmarks for the mem20 memory engine.

Measures three things, in this order of importance to mem20:

1. **Trustworthiness.** Contamination rate, stale-pointer rate, and whether
   retrieval reports its own degradation. This is the axis mem20 claims as its
   differentiator and the one competitors do not publish.
2. **Retrieval quality.** Hit rate and MRR, reported per query kind (direct,
   multi-hop, adversarial) so a single average cannot hide that keyword search
   handles direct queries and nothing else.
3. **Latency.** p50/p95/p99 per mode, measured after warm-up.

## Scope of the claim

The suite runs on `mem20-agent-kb-v1`, a corpus defined in `corpus.py`. It is
**not** LoCoMo, LongMemEval, or Zep's DMR, and its numbers are **not** comparable
to theirs. Two of those three benchmarks are private or vendor-defined, so
published figures on them cannot be reproduced from outside. Running our own
suite is the only way to have a number we can stand behind, and pretending
otherwise would be the exact failure the trust metrics are designed to catch.

## Usage

```bash
mem20benchmarkz run --out benchmarks/results   # full suite, isolated store
mem20benchmarkz drift                         # prove drift diagnostics fire
mem20benchmarkz render benchmarks/results      # re-render from latest.json
```

`run` and `drift` seed a temporary store, so neither touches live data.
"""
from .bench import (  # noqa: F401
    QueryResult,
    Report,
    render_markdown,
    run,
    save,
)
from .corpus import Corpus, Fact, Query, load  # noqa: F401

__all__ = [
    "run",
    "save",
    "render_markdown",
    "Report",
    "QueryResult",
    "Corpus",
    "Fact",
    "Query",
    "load",
]
__version__ = "0.1.0"