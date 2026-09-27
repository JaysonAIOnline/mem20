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
from . import catalogue as _catalogue
from . import describe as _describe
from . import engine as _engine
from . import ingest as _ingest
from . import pipeline as _pipeline
from . import secrets as _secrets
from . import validate as _validate
from .errors import EngineMissing, KilnError
from .rpc import Kiln

_DETAIL_TIERS = _budgets.DETAIL_TIERS


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


def _note_missing_credential() -> None:
    if not _secrets.engine_env().get("KILN_API_KEY"):
        print(
            "note: no LLM credential found in "
            f"{_secrets.SECRETS_PATH}; the engine will use its built-in "
            "English and DSL agent, which handles simple shapes. Set "
            "KILNZ_API_KEY (or OPENAI_API_KEY) in the secrets file for briefs "
            "that need a language model.",
            file=sys.stderr,
        )


def cmd_build(args) -> int:
    """One brief to an asset, a preview, a manifest, and a gate verdict."""
    _note_missing_credential()
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    name = args.name or "asset"
    with Kiln(env=_secrets.engine_env()) as k:
        result = _pipeline.build(
            _pipeline.BuildRequest(
                brief=args.prompt,
                out_dir=outdir,
                name=name,
                family=args.family,
                preview=not args.no_preview,
                samples=args.samples,
                gate=not args.no_gate,
                require_prefix=args.require_prefix,
                lod=args.lod,
                tier=args.tier,
            ),
            kiln=k,
        )
    _emit({"built": 1, "out": str(outdir), "entries": [result.as_dict()]})
    if result.error:
        return 1
    return 0 if result.ok else 2


def cmd_verify(args) -> int:
    """Re-check a manifest against the artifacts it claims."""
    report = _pipeline.verify(args.manifest)
    _emit(report)
    return 0 if report["ok"] else 1


def cmd_batch(args) -> int:
    """Many briefs in one engine session, each with its own manifest."""
    try:
        payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read {args.file}: {exc}", file=sys.stderr)
        return 1
    if isinstance(payload, dict):
        payload = payload.get("prompts", [])
    if not isinstance(payload, list):
        print('batch file must be a JSON list of strings, or {"prompts": [...]}',
              file=sys.stderr)
        return 1

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    items: list[tuple[str, str]] = []
    for i, item in enumerate(payload):
        if isinstance(item, str):
            items.append((item, f"asset_{i:03d}"))
        elif isinstance(item, dict) and item.get("brief"):
            items.append((str(item["brief"]), str(item.get("name") or f"asset_{i:03d}")))
    if not items:
        print("no usable briefs in the batch file", file=sys.stderr)
        return 1

    _note_missing_credential()
    results: list[dict] = []
    refused = 0
    errored = 0
    with Kiln(env=_secrets.engine_env()) as k:
        for brief, name in items:
            entry = _pipeline.build(
                _pipeline.BuildRequest(
                    brief=brief,
                    out_dir=outdir,
                    name=name,
                    family=args.family,
                    preview=not args.no_preview,
                    samples=args.samples,
                    gate=not args.no_gate,
                    require_prefix=args.require_prefix,
                    lod=args.lod,
                    tier=args.tier,
                ),
                kiln=k,
            ).as_dict()
            if entry["error"]:
                errored += 1
            elif not entry["ok"]:
                refused += 1
            results.append(entry)

    _emit({
        "count": len(results),
        "errored": errored,
        "refused_by_gate": refused,
        "out": str(outdir),
        "results": results,
    })
    if errored:
        return 1
    return 0 if refused == 0 else 2


def cmd_probe(args) -> int:
    """Measure an external file without modifying it."""
    report = _ingest.probe(args.file, family=args.family, lod=args.lod, tier=args.tier)
    _emit(report.as_dict())
    return 0 if report.ok else 1


def cmd_ingest(args) -> int:
    """Import external meshes and record where each one came from."""
    records = _ingest.convert(args.files, args.out, family=args.family,
                              gate=not args.no_gate, lod=args.lod, tier=args.tier)
    converted = sum(1 for r in records if r["converted"])
    _emit({
        "count": len(records),
        "converted": converted,
        "failed": len(records) - converted,
        "out": str(args.out),
        "records": records,
    })
    if converted != len(records):
        return 1
    return 0 if all(r.get("gate_ok") is not False for r in records) else 2


def cmd_describe(args) -> int:
    """Plain-English description of a model, for an agent that cannot see."""
    result = _describe.describe(args.file)
    if args.json:
        _emit(result.as_dict())
    else:
        print(result.text())
        for item in result.not_computable:
            print(f"  not computable: {item}")
    return 0 if result.ok else 1


def cmd_catalogue(args) -> int:
    """Index built assets from their manifests."""
    cat = _catalogue.Catalogue(args.root)
    _emit({
        "summary": cat.summary(),
        "entries": [e.as_dict() for e in cat.entries],
        "untracked_glb": cat.untracked,
        "unreadable_manifests": cat.unreadable,
    })
    return 0


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

    def _add_build_args(target: argparse.ArgumentParser) -> None:
        target.add_argument("--out", default="kilnz-out",
                            help="output directory (default: kilnz-out)")
        target.add_argument("--no-preview", action="store_true",
                            help="skip the PNG preview render")
        target.add_argument("--samples", type=int, default=2,
                            help="preview samples, 1..16 (default: 2)")
        target.add_argument("--family", default=None,
                            help="asset family for the poly budget")
        target.add_argument("--no-gate", action="store_true",
                            help="skip the budget and naming gate")
        target.add_argument("--require-prefix", action="store_true",
                            help="treat a missing roadmap prefix as an error")
        target.add_argument("--lod", type=int, default=0,
                            help="LOD tier for the poly budget (default: 0)")
        target.add_argument("--tier", default="standard", choices=_DETAIL_TIERS,
                            help="detail bar to judge against: "
                                 + ", ".join(_DETAIL_TIERS) + " (default: standard)")

    p = sub.add_parser("build",
                       help="one brief to a GLB, a preview, and a manifest")
    p.add_argument("prompt", help="the written brief")
    p.add_argument("--name", default=None, help="asset name (default: asset)")
    _add_build_args(p)
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("batch",
                       help="many briefs in one engine session, each with a manifest")
    p.add_argument("file", help='JSON list of strings, or [{"brief": ..., "name": ...}]')
    _add_build_args(p)
    p.set_defaults(func=cmd_batch)

    p = sub.add_parser("verify",
                       help="re-check a manifest against the artifacts it claims")
    p.add_argument("manifest")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("probe", help="measure an external mesh without modifying it")
    p.add_argument("file")
    p.add_argument("--family", default=None, help="asset family for the poly budget")
    p.add_argument("--lod", type=int, default=0)
    p.add_argument("--tier", default="standard", choices=_DETAIL_TIERS)
    p.set_defaults(func=cmd_probe)

    p = sub.add_parser("ingest", help="import external meshes with provenance")
    p.add_argument("files", nargs="+")
    p.add_argument("--out", default="kilnz-ingest")
    p.add_argument("--family", default=None)
    p.add_argument("--no-gate", action="store_true")
    p.add_argument("--lod", type=int, default=0)
    p.add_argument("--tier", default="standard", choices=_DETAIL_TIERS)
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("describe",
                       help="describe a model in plain English, without seeing it")
    p.add_argument("file")
    p.add_argument("--json", action="store_true", help="emit the measurements as JSON")
    p.set_defaults(func=cmd_describe)

    p = sub.add_parser("catalogue", help="index built assets from their manifests")
    p.add_argument("root", nargs="?", default="kilnz-out")
    p.set_defaults(func=cmd_catalogue)

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
