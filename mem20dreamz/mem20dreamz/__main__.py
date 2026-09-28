"""``python -m mem20dreamz`` — run and inspect dreams."""

from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, "/opt/mem20")
from llm import LLMError

from . import audit as audit_mod
from . import engine, ledger
from . import idle as idle_mod
from . import panel as panel_mod
from . import promote as promote_mod
from .lineage import Lineage, list_lineages


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="mem20-dream", description="dream engine: iteration that improves, never condenses"
    )
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("panel", help="show the panel roster and who is excluded")

    p_run = sub.add_parser("run", help="run iterations for a dream")
    p_run.add_argument("--dream-id", required=True)
    p_run.add_argument("--iterations", type=int, default=1)
    p_run.add_argument("--max-tokens", type=int, default=6000)

    p_new = sub.add_parser("new", help="create a dream from a seed")
    p_new.add_argument("--seed", required=True)
    p_new.add_argument("--foundation", default="", help="the premise it grows biased toward")
    p_new.add_argument("--kind", default="active")

    p_show = sub.add_parser("show", help="show a lineage")
    p_show.add_argument("--dream-id", required=True)

    p_chain = sub.add_parser("chain", help="show a lineage's braid chain")
    p_chain.add_argument("--dream-id", required=True)

    p_verify = sub.add_parser("verify", help="re-prove every node in a lineage's chain")
    p_verify.add_argument("--dream-id", required=True)

    p_rewind = sub.add_parser("rewind", help="read a committed iteration back from braid")
    p_rewind.add_argument("--cid", required=True)
    p_rewind.add_argument("--chars", type=int, default=1200)

    sub.add_parser("ledger", help="braid ledger status")
    sub.add_parser("list", help="list lineages")
    sub.add_parser("idle", help="one idle dream turn (yields to any active run)")
    sub.add_parser("idle-stats", help="what idle dreaming has produced, browsable later")
    p_promote = sub.add_parser("promote", help="export a portable roadmap pack")
    p_promote.add_argument("--dream-id", required=True)
    p_promote.add_argument("--out", default="/opt/mem20/store/promotions")
    p_promote.add_argument("--force", action="store_true")
    sub.add_parser("promotable", help="which lineages could be promoted, and why not")
    p_hollow = sub.add_parser("audit-hollow", help="find dream iterations that were failed calls")
    p_hollow.add_argument(
        "--commit", action="store_true", help="also record the correction in braid"
    )
    args = parser.parse_args(args)

    if args.cmd == "panel":
        print(json.dumps(panel_mod.roster_status(), indent=2))
        return 0

    if args.cmd == "ledger":
        print(json.dumps(ledger.head(), indent=2))
        return 0

    if args.cmd == "chain":
        lineage = Lineage.load(args.dream_id)
        if lineage is None:
            print(f"no such dream: {args.dream_id}", file=sys.stderr)
            return 1
        print(
            json.dumps(
                {
                    "dream_id": lineage.dream_id,
                    "iterations": lineage.iteration_count,
                    "braid_committed": len(lineage.braid_cids),
                    "uncommitted": lineage.uncommitted,
                    "chain": [
                        {"iteration": i + 1, "cid": cid} for i, cid in enumerate(lineage.braid_cids)
                    ],
                },
                indent=2,
            )
        )
        return 0

    if args.cmd == "verify":
        lineage = Lineage.load(args.dream_id)
        if lineage is None:
            print(f"no such dream: {args.dream_id}", file=sys.stderr)
            return 1
        report = ledger.verify_chain(lineage.braid_cids)
        print(json.dumps(report, indent=2))
        return 0 if report.get("healthy") else 1

    if args.cmd == "rewind":
        node = ledger.read_iteration(args.cid)
        if node is None:
            print(f"could not read {args.cid} from braid", file=sys.stderr)
            return 1
        payload = node.get("payload") or {}
        print(
            json.dumps(
                {
                    "cid": node.get("cid"),
                    "depth": node.get("depth"),
                    "is_proven": node.get("is_proven"),
                    "op": node.get("op"),
                    "target": node.get("target"),
                    "iteration": payload.get("iteration"),
                    "artifact_chars": payload.get("artifact_chars"),
                    "fidelity": (payload.get("fidelity") or {}).get("score"),
                    "omission": (payload.get("omission") or {}).get("score"),
                    "artifact_preview": (payload.get("artifact") or "")[: args.chars],
                },
                indent=2,
            )
        )
        return 0

    if args.cmd == "list":
        rows = list_lineages()
        print(json.dumps(rows, indent=2) if rows else "no dreams yet")
        return 0

    if args.cmd == "new":
        lineage = engine.new_dream(args.seed, kind=args.kind, foundation=args.foundation)
        print(json.dumps({"dream_id": lineage.dream_id, "state": lineage.state_path}, indent=2))
        return 0

    if args.cmd == "show":
        lineage = Lineage.load(args.dream_id)
        if lineage is None:
            print(f"no such dream: {args.dream_id}", file=sys.stderr)
            return 1
        payload = lineage.as_dict()
        payload["artifact_preview"] = payload["artifact"][:2000]
        payload.pop("artifact", None)
        print(json.dumps(payload, indent=2)[:6000])
        return 0

    if args.cmd == "run":
        lineage = Lineage.load(args.dream_id)
        if lineage is None:
            print(f"no such dream: {args.dream_id}", file=sys.stderr)
            return 1
        # An explicit run is the work somebody is waiting on, so it takes the
        # lock: idle dreaming yields its turn entirely for the whole run. The
        # claim is exclusive, so a second run is refused rather than allowed to
        # overwrite the first one's claim and dream alongside it.
        claim = idle_mod.claim_active(lineage.dream_id)
        if not claim.get("claimed"):
            held = claim.get("held_by") or {}
            print(
                f"refusing to start: {claim.get('reason', 'the run lock is held')}",
                file=sys.stderr,
            )
            if held.get("dream_id"):
                print(
                    f"the lock belongs to {held['dream_id']} (held {held.get('age_s')}s)",
                    file=sys.stderr,
                )
            # 3, deliberately distinct from 2 (paused) and 0 (finished): this run
            # did not start at all, and a caller can tell that from a pause.
            return 3
        try:
            for _ in range(args.iterations):
                if lineage.done:
                    break
                n = lineage.iteration_count + 1
                try:
                    iteration = engine.run_iteration(lineage, n)
                except LLMError as exc:
                    # Retry already happened inside. Checkpoint and pause, and say
                    # exactly where it stopped so a pause is never a lost run.
                    lineage.paused = True
                    lineage.pause_reason = str(exc)[:400]
                    lineage.save()
                    print(f"[iter {n}] PAUSED: {exc}", file=sys.stderr)
                    print(
                        f"resume with: mem20-dream run --dream-id {lineage.dream_id}",
                        file=sys.stderr,
                    )
                    return 2
                lineage.record(iteration)
                receipt = ledger.commit_iteration(lineage, iteration)
                if receipt.get("committed"):
                    lineage.braid_cids.append(receipt["cid"])
                    commit_note = f"braid={receipt['cid'][:18]} ack={receipt.get('proven_at_commit')}"
                else:
                    # Recorded as NOT committed, with the reason. A lineage that
                    # looks content-addressed when it is not is worse than one that
                    # admits it.
                    lineage.uncommitted.append(
                        {"n": iteration.n, "reason": receipt.get("reason", "")}
                    )
                    commit_note = f"UNCOMMITTED: {receipt.get('reason', '')[:60]}"
                lineage.save()
                print(
                    f"[iter {iteration.n}] fidelity={iteration.fidelity.get('score')} "
                    f"omission={iteration.omission.get('score')} "
                    f"accepted={iteration.accepted} inventions={len(iteration.inventions_added)} "
                    f"{commit_note}"
                )
            return 0
        finally:
            # Released even on a pause or a crash, so one failed run cannot wedge
            # idle dreaming for ever - and released by token, so this run can only
            # ever free a lock it actually holds.
            idle_mod.release_active(claim.get("token"))

    if args.cmd == "idle":
        result = idle_mod.idle_turn()
        print(json.dumps(result, indent=2))
        # A skip is the fairness rule working, not a failure, so the timer does
        # not treat it as an error and retry.
        return 0

    if args.cmd == "idle-stats":
        print(json.dumps(idle_mod.inventory(), indent=2))
        return 0

    if args.cmd == "promote":
        try:
            result = promote_mod.promote(args.dream_id, args.out, force=args.force)
        except (FileNotFoundError, FileExistsError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("promoted") else 1

    if args.cmd == "promotable":
        print(json.dumps(promote_mod.catalogue(), indent=2))
        return 0

    if args.cmd == "audit-hollow":
        result = audit_mod.quarantine(commit=args.commit)
        printable = {k: v for k, v in result.items() if k != "entries"}
        printable["entries_sample"] = [
            {
                "dream_id": e["dream_id"],
                "iterations": [i["n"] for i in e["hollow_iterations"]],
                "reason": e["hollow_iterations"][0]["reason"][:110],
            }
            for e in result["entries"][:5]
        ]
        print(json.dumps(printable, indent=2, default=str))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
