#!/usr/bin/env python3
"""Lint assets_master.csv: required columns, P0 must be validated, paths exist if present."""
from __future__ import annotations
import csv, sys
from pathlib import Path

REQUIRED = ["asset_id", "type", "name", "path", "source", "package_section", "priority", "status", "qa_status", "notes"]
OK_STATUS = {"incoming", "validated", "integrated", "ship", "cut"}

def main(csv_path: str, root: str | None = None) -> int:
    p = Path(csv_path)
    if not p.exists():
        print(f"FAIL missing {p}")
        return 2
    rows = list(csv.DictReader(p.open(newline="", encoding="utf-8")))
    if not rows:
        print("FAIL empty manifest")
        return 2
    missing = [c for c in REQUIRED if c not in rows[0]]
    if missing:
        print(f"FAIL missing columns: {missing}")
        return 2
    errors = 0
    ids = set()
    for i, r in enumerate(rows, 2):
        aid = (r.get("asset_id") or "").strip()
        if not aid:
            print(f"L{i} FAIL empty asset_id"); errors += 1; continue
        if aid in ids:
            print(f"L{i} FAIL duplicate {aid}"); errors += 1
        ids.add(aid)
        st = (r.get("status") or "").strip().lower()
        if st not in OK_STATUS:
            print(f"L{i} FAIL {aid} bad status {st!r}"); errors += 1
        pri = (r.get("priority") or "").strip().upper()
        if pri == "P0" and st not in {"validated", "integrated", "ship"}:
            print(f"L{i} FAIL P0 {aid} status={st} (need validated+)"); errors += 1
        path = (r.get("path") or "").strip()
        if root and path:
            fp = Path(root) / path
            if not fp.exists():
                print(f"L{i} WARN {aid} path missing: {fp}")
    print(f"{'PASS' if errors == 0 else 'FAIL'} rows={len(rows)} errors={errors}")
    return 1 if errors else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "manifests/assets_master.csv",
                  sys.argv[2] if len(sys.argv) > 2 else None))
