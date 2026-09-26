#!/usr/bin/env python3
"""Cross-check the op names the engine advertises against the ones it dispatches.

`src/core/rpc.hpp` carries an advisory op table used for capability reporting
and typo suggestions. Nothing in C++ forces it to match `apply_op`, so it drifts
silently the moment an op is added. This reads both and fails on any difference
in either direction, which is the only thing that keeps `ping`'s `ops` count
honest.

Usage:  python3 check_op_sync.py <engine-dir> [kiln-binary]
"""

import json
import os
import re
import subprocess
import sys


def dispatched_ops(ops_cpp):
    """Op names apply_op actually branches on."""
    with open(ops_cpp, encoding="utf-8") as f:
        text = f.read()
    start = text.find("OpResult apply_op(Document& doc, const nlohmann::json& op) {")
    if start < 0:
        raise SystemExit("could not find apply_op in %s" % ops_cpp)
    end = text.find("\nOpResult apply_ops(", start)
    if end < 0:
        raise SystemExit("could not find the end of apply_op")
    body = text[start:end]
    names = set()
    for m in re.finditer(r'kind == "([a-z_0-9]+)"', body):
        names.add(m.group(1))
    for m in re.finditer(r'kind == "([a-z_0-9]+)" \|\| kind == "([a-z_0-9]+)"', body):
        names.add(m.group(1))
        names.add(m.group(2))
    return names


def advertised_ops(rpc_hpp):
    with open(rpc_hpp, encoding="utf-8") as f:
        text = f.read()
    start = text.find("inline const std::vector<std::string>& op_names()")
    if start < 0:
        raise SystemExit("could not find op_names() in %s" % rpc_hpp)
    end = text.find("return kOps;", start)
    body = text[start:end]
    return set(re.findall(r'"([a-z_0-9]+)"', body))


def live_ops(binary):
    """`ping` reports ops as a count; `initialize` reports the same field as the list."""
    req = (json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}) + "\n"
           + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "initialize"}) + "\n"
           + json.dumps({"jsonrpc": "2.0", "id": 3, "method": "shutdown"}) + "\n")
    out = subprocess.run([binary, "--rpc"], input=req, capture_output=True,
                         text=True, timeout=60).stdout
    count = None
    names = set()
    reported = None
    for line in out.splitlines():
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        res = msg.get("result")
        if not isinstance(res, dict):
            continue
        if msg.get("id") == 1 and isinstance(res.get("ops"), int):
            count = res["ops"]
        if msg.get("id") == 2:
            names = set(res.get("ops", []))
            reported = res.get("ops")
    if count is None or not names:
        raise SystemExit("no usable ping/initialize response from %s" % binary)
    return names, {"ping_count": count, "initialize_list": reported}


def main():
    eng = sys.argv[1] if len(sys.argv) > 1 else "."
    binary = sys.argv[2] if len(sys.argv) > 2 else os.path.join(eng, "kiln")

    disp = dispatched_ops(os.path.join(eng, "src/ops/ops.cpp"))
    adv = advertised_ops(os.path.join(eng, "src/core/rpc.hpp"))
    live, payload = live_ops(binary)

    print("apply_op dispatches      %3d names" % len(disp))
    print("rpc.hpp advertises       %3d names" % len(adv))
    print("initialize lists         %3d names" % len(live))
    print("ping reports count       %3d" % payload["ping_count"])

    ok = True
    missing = sorted(disp - adv)
    extra = sorted(adv - disp)
    live_missing = sorted(disp - live)
    if missing:
        ok = False
        print("\nDISPATCHED BUT NOT ADVERTISED (%d):" % len(missing))
        for n in missing:
            print("   ", n)
    if extra:
        ok = False
        print("\nADVERTISED BUT NOT DISPATCHED (%d):" % len(extra))
        for n in extra:
            print("   ", n)
    if live_missing:
        ok = False
        print("\nDISPATCHED BUT NOT IN initialize (%d):" % len(live_missing))
        for n in live_missing:
            print("   ", n)
    if payload["ping_count"] != len(live):
        ok = False
        print("\nping reports ops=%d but initialize lists %d names"
              % (payload["ping_count"], len(live)))
    if set(payload["initialize_list"] or []) != live:
        ok = False
        print("\nping count and initialize list disagree")
    if not ok:
        print("\nFAIL: the advertised op surface does not match what the engine runs")
        return 1
    print("\nOK: advertised op surface matches apply_op exactly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
