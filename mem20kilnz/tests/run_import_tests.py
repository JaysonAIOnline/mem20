#!/usr/bin/env python3
"""Run the kiln importer over every fixture and check it against expected.json.

Reads kiln's own op output rather than trusting the exit code, because a
successful exit with zero geometry is exactly the failure mode that matters.

Usage:  python3 run_import_tests.py <kiln-binary> <fixture-dir>
"""

import json
import os
import re
import subprocess
import sys

BIN = "kiln"


def run_import(binary, path, timeout=60):
    proc = subprocess.run(
        [binary, "--headless", "import %s replace" % path],
        capture_output=True, text=True, timeout=timeout)
    return proc.returncode, proc.stdout, proc.stderr


def parse(out):
    m = re.search(r"imported .*?: (\d+) meshes, (\d+) faces, (\d+) verts, (\d+) materials", out)
    if not m:
        return None
    d = {"meshes": int(m.group(1)), "faces": int(m.group(2)),
         "vertices": int(m.group(3)), "materials": int(m.group(4))}
    sk = re.search(r"(\d+) skins/(\d+) bones", out)
    if sk:
        d["skins"] = int(sk.group(1))
        d["bones"] = int(sk.group(2))
    dm = re.search(r"dropped: ([^\)]+)\)", out)
    if dm:
        d["dropped"] = sorted(dm.group(1).split())
    return d


ALIAS = {"embedded_gltf": "embedded", "external_gltf": "external"}


def fixture_path(fdir, name):
    stem = ALIAS.get(name, name)
    for ext in (".glb", ".gltf"):
        p = os.path.join(fdir, stem + ext)
        if os.path.exists(p):
            return p
    return None


def ensure_fixtures(fdir):
    """Generate the fixture set if it is not already on disk.

    The importer suite used to require a hand-created fixtures/ directory, so a
    clean checkout failed with FileNotFoundError instead of testing anything.
    """
    marker = os.path.join(fdir, "expected.json")
    if os.path.exists(marker):
        return fdir
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import make_fixtures

    os.makedirs(fdir, exist_ok=True)
    argv = sys.argv
    sys.argv = ["make_fixtures.py", fdir]
    try:
        make_fixtures.main()
    finally:
        sys.argv = argv
    if not os.path.exists(marker):
        raise SystemExit(f"fixture generation produced no {marker}")
    return fdir


def main():
    binary = sys.argv[1] if len(sys.argv) > 1 else BIN
    fdir = sys.argv[2] if len(sys.argv) > 2 else "fixtures"
    ensure_fixtures(fdir)
    expected = json.load(open(os.path.join(fdir, "expected.json")))

    npass = nfail = 0
    failures = []
    for name in sorted(expected):
        exp = expected[name]
        path = fixture_path(fdir, name)
        if path is None:
            failures.append((name, "fixture file missing"))
            nfail += 1
            continue
        try:
            rc, out, errout = run_import(binary, path)
        except subprocess.TimeoutExpired:
            failures.append((name, "TIMEOUT"))
            nfail += 1
            continue
        crashed = rc < 0 or "Assertion" in errout or "terminate called" in errout
        if crashed:
            failures.append((name, "CRASH rc=%d %s" % (rc, errout.strip()[:70])))
            nfail += 1
            continue
        if exp.get("must_fail"):
            if "ok  import" in out:
                failures.append((name, "should have been rejected but imported"))
                nfail += 1
            else:
                line = [x.strip() for x in out.splitlines() if x.strip()][:2]
                print("PASS  %-18s rejected cleanly: %s" % (name, " ".join(line)[:60]))
                npass += 1
            continue
        got = parse(out)
        if got is None:
            failures.append((name, "no import verdict: %s" % out.strip()[:70]))
            nfail += 1
            continue
        bad = []
        for k in ("meshes", "faces", "vertices", "materials", "skins", "bones"):
            if k in exp and got.get(k) != exp[k]:
                bad.append("%s want %s got %s" % (k, exp[k], got.get(k)))
        if bad:
            failures.append((name, "; ".join(bad)))
            nfail += 1
            continue
        extra = ""
        if got.get("dropped"):
            extra = " dropped=%s" % ",".join(got["dropped"])
        skin = ""
        if got.get("skins"):
            skin = " skins=%d bones=%d" % (got["skins"], got["bones"])
        print("PASS  %-18s meshes=%d faces=%d verts=%d materials=%d%s%s"
              % (name, got["meshes"], got["faces"], got["vertices"],
                 got["materials"], skin, extra))
        npass += 1

    print("\n%d passed, %d failed" % (npass, nfail))
    for n, why in failures:
        print("FAIL  %-18s %s" % (n, why))
    return 1 if nfail else 0


if __name__ == "__main__":
    raise SystemExit(main())
