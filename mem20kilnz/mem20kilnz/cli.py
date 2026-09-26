"""mem20kilnz CLI — the agent-facing entry point.

Every subcommand either does real work and prints real numbers, or says plainly
that it cannot and why. There is no simulated output and no silent degradation:
`doctor` reports a missing engine as missing, and a neural generation command
that this host cannot run is not offered as though it could.

    mem20kilnz doctor              describe the local kernel and secrets
    mem20kilnz build-engine        compile the C++ kernel, report warnings
    mem20kilnz ops                 list every op the engine advertises
    mem20kilnz validate FILE       structural + budget gate on a glTF/GLB
    mem20kilnz budgets             the budget and naming table
    mem20kilnz build "a red cube"  run one prompt, export a GLB and a preview
    mem20kilnz batch FILE          run a JSON list of prompts
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import budgets as _budgets
from . import engine as _engine
from . import secrets as _secrets
from . import validate as _validate
from .errors import EngineMissing, KilnError, OpFailed
from .rpc import Kiln


def _emit(obj) -> None:
    print(json.dumps(obj, indent=2, sort_keys=True))


def cmd_doctor(args) -> int:
    info = _engine.engine_info()
    info["secrets"] = _secrets.status()
    info["package_op_count_hint"] = "run `mem20kilnz ops` against a live engine"
    _emit(info)
    if args.build:
        res = _engine.build(jobs=args.jobs, clean=args.clean)
        _emit({"build": {"ok": res.ok, "returncode": res.returncode, "warnings": res.warnings,
                         "errors": res.errors, "compiler": res.compiler, "binary": res.binary,
                         "summary": res.summary()}})
        if not res.ok:
            if args.verbose:
                print(res.log, file=sys.stderr)
            return 1
    if not info.get("binary_exists") and not args.build:
        return 1
    return 0


def cmd_build_engine(args) -> int:
    res = _engine.build(jobs=args.jobs, clean=args.clean)
    _emit({"ok": res.ok, "returncode": res.returncode, "warnings": res.warnings,
           "errors": res.errors, "compiler": res.compiler, "binary": res.binary,
           "summary": res.summary()})
    if not res.ok and args.verbose:
        print(res.log, file=sys.stderr)
    return 0 if res.ok else 1


def cmd_ops(args) -> int:
    with Kiln() as k:
        payload = k.initialize()
        names = payload.get("ops", [])
        if args.json:
            _emit({"count": len(names), "ops": names, "methods": payload.get("methods", []),
                   "protocol": payload.get("protocol", "")})
        else:
            print(f"{len(names)} ops (protocol {payload.get('protocol')})")
            for n in names:
                print("  " + n)
    return 0


def cmd_validate(args) -> int:
    """Structural validation only.

    Budget and naming findings belong to `gate`; conflating them makes a
    structurally perfect file report FAIL, which hides real corruption.
    """
    report = _validate.validate(args.file)
    if args.gate:
        report.findings.extend(
            _validate.check_budgets(report, family=args.family,
                                    require_prefix=args.require_prefix, lod=args.lod)
        )
    verdict = report.gate_ok if args.gate else report.ok
    if args.json:
        _emit(report.as_dict())
    else:
        print(f"{report.path}: {'PASS' if verdict else 'FAIL'}")
        print(f"  version {report.version or '?'}  generator {report.generator or '?'}")
        print(f"  bytes {report.actual_bytes} (declared {report.declared_bytes or 'n/a'})")
        print(f"  nodes {report.nodes}  meshes {len(report.meshes)}  "
              f"triangles {report.total_triangles}")
        for m in report.meshes:
            print(f"    {m.name}: {m.triangles} tris, {m.vertices} verts, "
                  f"normals={'y' if m.has_normals else 'n'}, uvs={'y' if m.has_uvs else 'n'}")
        for f in report.findings:
            print(f"  {f.severity.upper()}: [{f.code}] {f.message}"
                  + (f"  ({f.where})" if f.where else ""))
    return 0 if (report.gate_ok if args.gate else report.ok) else 1


def cmd_gate(args) -> int:
    """Structural validation plus the JAIRF budget and naming gate."""
    report = _validate.gate(args.file, family=args.family,
                            require_prefix=args.require_prefix, lod=args.lod)
    if args.json:
        _emit(report.as_dict())
    else:
        print(f"{report.path}: {'PASS' if report.gate_ok else 'FAIL'}")
        print(f"  triangles {report.total_triangles}  meshes {len(report.meshes)}  "
              f"errors {len(report.errors)}  warnings {len(report.warnings)}")
        for f in report.findings:
            print(f"  {f.severity.upper()}: [{f.code}] {f.message}"
                  + (f"  ({f.where})" if f.where else ""))
    return 0 if report.gate_ok else 1


def cmd_budgets(args) -> int:
    _emit(_budgets.table())
    return 0


def _build_one(k: Kiln, prompt: str, out_glb: Path, out_png: Path | None,
               samples: int, family: str | None, gate_on: bool) -> dict:
    out_glb.parent.mkdir(parents=True, exist_ok=True)
    if out_png is not None:
        out_png.parent.mkdir(parents=True, exist_ok=True)
    k.reset()
    result = k.command(prompt)
    k.export(str(out_glb))
    if out_png is not None:
        k.render(str(out_png), samples=samples)
    entry: dict = {
        "prompt": prompt,
        "glb": str(out_glb),
        "glb_bytes": out_glb.stat().st_size if out_glb.is_file() else 0,
        "engine_message": result.get("message", ""),
    }
    if out_png is not None and out_png.is_file():
        entry["png"] = str(out_png)
        entry["png_bytes"] = out_png.stat().st_size
    if gate_on and out_glb.is_file():
        report = _validate.gate(out_glb, family=family)
        entry["gate"] = {"ok": report.ok, "triangles": report.total_triangles,
                         "errors": len(report.errors), "warnings": len(report.warnings),
                         "findings": [f.as_dict() for f in report.findings]}
    return entry


def cmd_build(args) -> int:
    env = _secrets.engine_env()
    if not env.get("KILN_API_KEY"):
        print(
            "note: no LLM credential found in "
            f"{_secrets.SECRETS_PATH}; the engine will use its built-in "
            "English and DSL agent, which handles simple shapes. Set "
            "KILNZ_API_KEY (or OPENAI_API_KEY) in the secrets file for prompts "
            "that need a language model.",
            file=sys.stderr,
        )
    outdir = Path(args.out)
    stems = [args.name] if args.name else ["asset"]
    entries = []
    failed = False
    with Kiln(env=env) as k:
        for stem in stems:
            glb = outdir / f"{stem}.glb"
            png = outdir / f"{stem}.png" if args.preview else None
            try:
                entries.append(
                    _build_one(k, args.prompt, glb, png, args.samples,
                               args.family, not args.no_gate)
                )
            except OpFailed as exc:
                failed = True
                entries.append({"prompt": args.prompt, "ok": False, "error": exc.message,
                                "code": exc.code})
    _emit({"built": len(entries), "out": str(outdir), "entries": entries})
    if failed:
        return 1
    for e in entries:
        if e.get("gate") and not e["gate"]["ok"]:
            return 2
    return 0


def cmd_batch(args) -> int:
    try:
        prompts = json.loads(Path(args.file).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read {args.file}: {exc}", file=sys.stderr)
        return 1
    if isinstance(prompts, dict):
        prompts = prompts.get("prompts", [])
    if not isinstance(prompts, list):
        print("batch file must be a JSON list of strings, or {\"prompts\": [...]}", file=sys.stderr)
        return 1
    env = _secrets.engine_env()
    outdir = Path(args.out)
    results = []
    failures = 0
    with Kiln(env=env) as k:
        for i, item in enumerate(prompts):
            prompt = item if isinstance(item, str) else str(item.get("prompt", ""))
            stem = (item.get("name") if isinstance(item, dict) else None) or f"asset_{i:03d}"
            glb = outdir / f"{stem}.glb"
            png = outdir / f"{stem}.png" if args.preview else None
            try:
                entry = _build_one(k, prompt, glb, png, args.samples,
                                   args.family, not args.no_gate)
                entry["ok"] = True
            except OpFailed as exc:
                entry = {"prompt": prompt, "ok": False, "error": exc.message, "code": exc.code}
                failures += 1
            results.append(entry)
    _emit({"count": len(results), "failures": failures, "out": str(outdir), "results": results})
    return 0 if failures == 0 else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mem20kilnz", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("doctor", help="describe the local kernel and secrets")
    p.add_argument("--build", action="store_true", help="also compile the engine")
    p.add_argument("--clean", action="store_true")
    p.add_argument("--jobs", type=int, default=None)
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("build-engine", help="compile the C++ kernel")
    p.add_argument("--clean", action="store_true")
    p.add_argument("--jobs", type=int, default=None)
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(func=cmd_build_engine)

    p = sub.add_parser("ops", help="list every op the engine advertises")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_ops)

    p = sub.add_parser("validate", help="structural validation of a glTF/GLB")
    p.add_argument("file")
    p.add_argument("--gate", action="store_true",
                   help="also apply budget and naming findings (same as `gate`)")
    p.add_argument("--family", default=None, help="asset family for the poly budget")
    p.add_argument("--require-prefix", action="store_true", help="fail on a naming-prefix miss")
    p.add_argument("--lod", type=int, default=0)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("gate", help="validate and apply JAIRF budget/naming gate")
    p.add_argument("file")
    p.add_argument("--family", default=None, help="asset family for the poly budget")
    p.add_argument("--require-prefix", action="store_true", help="fail on a naming-prefix miss")
    p.add_argument("--lod", type=int, default=0)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_gate)

    p = sub.add_parser("budgets", help="print the budget and naming table")
    p.set_defaults(func=cmd_budgets)

    p = sub.add_parser("build", help="run one prompt and export a GLB (and a preview)")
    p.add_argument("prompt")
    p.add_argument("--out", default="kilnz-out")
    p.add_argument("--name", default=None)
    p.add_argument("--preview", action="store_true", help="also render a PNG")
    p.add_argument("--samples", type=int, default=2)
    p.add_argument("--family", default=None)
    p.add_argument("--no-gate", action="store_true", help="skip the validation gate")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("batch", help="run a JSON list of prompts")
    p.add_argument("file")
    p.add_argument("--out", default="kilnz-out")
    p.add_argument("--preview", action="store_true")
    p.add_argument("--samples", type=int, default=2)
    p.add_argument("--family", default=None)
    p.add_argument("--no-gate", action="store_true")
    p.set_defaults(func=cmd_batch)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except EngineMissing as exc:
        print(exc.message, file=sys.stderr)
        return 3
    except KilnError as exc:
        print(f"kiln: {exc}", file=sys.stderr)
        return 1
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
