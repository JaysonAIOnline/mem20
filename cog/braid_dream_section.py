#!/usr/bin/env python3
"""
Braid dream, run one iteration at a time (survives free-tier hangs).

State file (JSON):
  {"iter": int, "seed": str, "log": [str], "done": bool}

Usage:
  python3 braid_dream_section.py --init "PROMPT" [--topics a b c]
  python3 braid_dream_section.py --run [--iter N] [--max-tokens 120000]
  python3 braid_dream_section.py --log
"""
import argparse
import asyncio
import json
import os
import sys

_ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
for p in (_ENGINE_DIR, os.path.dirname(_ENGINE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

STATE = os.path.join(_ENGINE_DIR, "braid_dream_state.json")
DEFAULT_TOPICS = [
    "braid substrate spec",
    "braid build manifest",
    "braid core",
    "one consciousness three doors",
    "mem20 build",
]


def _load() -> dict:
    if os.path.exists(STATE):
        with open(STATE) as f:
            return json.load(f)
    return {"iter": 0, "seed": "", "log": [], "done": False}


def _save(st) -> None:
    with open(STATE, "w") as f:
        json.dump(st, f, indent=2)


def _retrieve(query: str, k: int = 8) -> str:
    try:
        from memory import recall
        rows = recall(query, limit=k) if callable(recall) else []
        if not rows:
            return ""
        return "\n".join(str(r) for r in rows)
    except Exception:
        return ""


def _img_system(kind: str) -> str:
    return (
        f"You are mem20's imagination subsystem performing {kind}. Generate genuine, "
        "internally-consistent content. Distinguish clearly between known facts (from memory, "
        "if provided) and invented/speculative content. Do not present speculation as grounded truth."
    )


async def _run_iter(seed: str, iter_n: int, max_tokens: int) -> str:
    from llm import achat
    mem = _retrieve(seed)
    user = f"ITERATION {iter_n}. Seed: {seed}\n"
    if mem:
        user += f"Memory inspiration:\n{mem}\n"
    user += "Produce the next creative concept elaboration (concepts mode)."
    print(f"[iter {iter_n}] calling LLM (max_tokens={max_tokens}, {len(mem)} chars memory)...", flush=True)
    out = await achat(
        [{"role": "system", "content": _img_system("dream loop")},
         {"role": "user", "content": user}],
        max_tokens=max_tokens,
    )
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", help="initial full prompt")
    ap.add_argument("--run", action="store_true", help="run next iteration")
    ap.add_argument("--iter", type=int, default=None)
    ap.add_argument("--max-tokens", type=int, default=120000)
    ap.add_argument("--total", type=int, default=3)
    ap.add_argument("--log", action="store_true", help="print current state log")
    args = ap.parse_args()

    if args.init:
        st = {"iter": 0, "seed": args.init, "log": [f"DREAM starting from: {args.init}\n"], "done": False}
        _save(st)
        print(f"initialized: iter 0/… seed={len(args.init)} chars")
        return 0

    if args.log:
        st = _load()
        print("iter:", st["iter"], "done:", st["done"])
        print("\n".join(st["log"]))
        return 0

    if args.run:
        st = _load()
        if st["done"]:
            print("already done")
            return 0
        iter_n = args.iter or (st["iter"] + 1)
        try:
            out = asyncio.run(_run_iter(st["seed"], iter_n, args.max_tokens))
        except Exception as e:
            print(f"[iter {iter_n}] FAILED: {type(e).__name__}: {e}", flush=True)
            return 2
        st["log"].append(f"\n--- iteration {iter_n} ---\n{out}\n")
        st["seed"] = out[:300]
        st["iter"] = iter_n
        st["done"] = iter_n >= args.total
        _save(st)
        print(f"[iter {iter_n}] OK ({len(out)} chars). new seed: {st['seed'][:120]!r}…", flush=True)
        return 0

    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())