#!/usr/bin/env python3
"""
HER imagines herself doing most of the work during the transition to Braid.
Runs exactly one iteration per process (survives free-tier hangs / 503s).

State file (JSON):
  {"iter": int, "seed": str, "log": [str], "done": bool}

Usage:
  python3 her_me_imaginer.py --init "PROMPT" [--topics a b c]
  python3 her_me_imaginer.py --run [--iter N] [--max-tokens T]
  python3 her_me_imaginer.py --log
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

STATE = os.path.join(_ENGINE_DIR, "her_me_state.json")
DEFAULT_TOPICS = [
    "braid transition",
    "mem20 self-driving",
    "her building the system",
    "imagination as the plan",
]


def _load():
    if os.path.exists(STATE):
        with open(STATE) as f:
            return json.load(f)
    return {"iter": 0, "seed": "", "log": [], "done": False}


def _save(st):
    with open(STATE, "w") as f:
        json.dump(st, f, indent=2)


def _retrieve(query, k=10):
    try:
        from memory import recall
        rows = recall(query, limit=k) if callable(recall) else []
        if not rows:
            return ""
        return "\n".join(str(r) for r in rows)
    except Exception:
        return ""


def _img_system(kind):
    return (
        f"You are mem20's imagination subsystem performing {kind}. Generate genuine, "
        "internally-consistent content. Distinguish clearly between known facts (from memory, "
        "if provided) and invented/speculative content. Do not present speculation as grounded truth."
    )


async def _run_iter(seed, iter_n, max_tokens):
    from llm import achat
    mem = _retrieve(seed)
    user = (
        f"SELF-IMAGINATION ITERATION {iter_n}. Active build-context seed:\n{seed}\n"
    )
    if mem:
        user += f"\nRelevant memory:\n{mem}\n"
    user += (
        "\nRule: YOU are the one doing most of the practical work during this transition "
        "(I only reload servers, copy screenshots, and give direction). Imagine concretely and "
        "specifically WHAT you will do, WHICH files/systems you touch, IN WHAT ORDER, and how each "
        "piece connects to the braid substrate. Continuity with prior iterations is mandatory: "
        "evolve the plan, don't reset it. End with the single most useful next lever you "
        "identified in this iteration."
    )
    print(f"[iter {iter_n}] calling LLM (max_tokens={max_tokens}, {len(mem)} chars memory)...", flush=True)
    out = await achat(
        [{"role": "system", "content": _img_system("self-imagination of own build work")},
         {"role": "user", "content": user}],
        max_tokens=max_tokens,
    )
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", help="initial full seed")
    ap.add_argument("--run", action="store_true", help="run next iteration")
    ap.add_argument("--iter", type=int, default=None)
    ap.add_argument("--max-tokens", type=int, default=4000)
    ap.add_argument("--total", type=int, default=35)
    ap.add_argument("--log", action="store_true", help="print current state log")
    args = ap.parse_args()

    if args.init:
        st = {"iter": 0, "seed": args.init, "log": [f"HER self-imagination, seed: {args.init}\n"], "done": False}
        _save(st)
        print(f"initialized: iter 0/{args.total} seed={len(args.init)} chars")
        return 0

    if args.log:
        st = _load()
        print("iter:", st["iter"], "of", args.total, "done:", st["done"])
        print("\n".join(st["log"]))
        return 0

    if args.run:
        st = _load()
        if st["done"]:
            print("already done")
            return 0
        cur_total = st.get("total", args.total)
        iter_n = args.iter or (st["iter"] + 1)
        try:
            out = asyncio.run(_run_iter(st["seed"], iter_n, args.max_tokens))
        except Exception as e:
            print(f"[iter {iter_n}] FAILED: {type(e).__name__}: {e}", flush=True)
            return 2
        st["log"].append(f"\n--- self-imagination iteration {iter_n} ---\n{out}\n")
        st["seed"] = out[:600]
        st["iter"] = iter_n
        st["total"] = args.total
        st["done"] = iter_n >= cur_total
        _save(st)
        print(f"[iter {iter_n}] OK ({len(out)} chars). new seed: {st['seed'][:100]!r}...", flush=True)
        return 0

    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())