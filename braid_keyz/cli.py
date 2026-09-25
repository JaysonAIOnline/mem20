#!/usr/bin/env python3
"""braid-keyz — CLI for the braid signer hardening tools.

Usage:  braid-keyz COMMAND ...

Commands
  bind      [--passphrase PROMPT|TEXT] [--seed FILE|HEX]   seal the signer
  unbind    [--seed FILE|HEX]                               unseal / verify
  split     [-n N] [-k K] [--seed FILE|HEX]                 threshold split
  join      [-k K]                                          rejoin from shares
  lineage   [--log PATH]                                    show rotation chain
  rotate    NEW_SIGNER_HEX [-r REASON]                      authorize new key
  selftest                                                  run all self-tests
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from braid_keyz import binding, rotation, threshold  # noqa: E402


def _signer_arg(args: argparse.Namespace) -> str:
    """Resolve --seed FILE|HEX (or --seed HEX) to a signer hex string."""
    seed = args.seed
    if seed is None:
        # default: the bridge's persistent signer.hex
        import braid_bridge

        return braid_bridge.signer_hex()
    if os.path.exists(seed):
        with open(seed, "r", encoding="utf-8") as fh:
            return fh.read().strip()
    return seed.strip()


def _maybe_passphrase(args: argparse.Namespace):
    if not getattr(args, "passphrase", None):
        return None
    if args.passphrase == "PROMPT":
        import getpass

        return getpass.getpass("Passphrase: ")
    return args.passphrase


def cmd_bind(args):
    signer = _signer_arg(args)
    passphrase = _maybe_passphrase(args)
    binding.seal_signer(signer, passphrase=passphrase)
    print(f"sealed signer (machine-bound={'yes' if passphrase is None else 'passphrase'}) -> {binding.SEALED_SIGNER_PATH}")


def cmd_unbind(args):
    signer = _signer_arg(args)
    passphrase = _maybe_passphrase(args)
    recovered = binding.unseal_signer(passphrase=passphrase)
    if recovered != signer:
        sys.exit(f"UNSEAL MISMATCH: recovered {recovered[:8]}... != source {signer[:8]}...")
    print("unseal OK: machine-bound signer recovered and matches source")


def cmd_split(args):
    signer = _signer_arg(args)
    seed = bytes.fromhex(signer)
    files = threshold.write_threshold_shares(seed, n=args.n, k=args.k)
    print(f"wrote {len(files)} shares (k={args.k} of n={args.n}):")
    for fp in files:
        print(f"  {fp}")


def cmd_join(args):
    seed = threshold.recover_from_files(k=args.k)
    print(f"rejoined {len(seed)}-byte seed from shares (k={args.k})")


def cmd_lineage(args):
    auth = rotation.authorized_signer_set(args.log)
    history = rotation.rotation_history(args.log)
    print(json.dumps(
        {
            "authorized_signers": sorted(auth),
            "rotations": history,
        },
        indent=2,
        default=str,
    ))


def cmd_rotate(args):
    import braid_bridge

    receipt = braid_bridge.commit(
        rotation.ROTATION_OP,
        args.new_signer,
        {
            "authorized_signer": args.new_signer,
            "reason": args.reason,
            "rotated_at": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat(),
        },
    )
    print("rotation committed:")
    print(json.dumps(receipt, indent=2))
    print(f"now-authorized: {sorted(rotation.authorized_signer_set())}")


def cmd_selftest(args):
    import hashlib

    seed = os.urandom(32)
    shares = threshold.split_seed(seed, n=3, k=2)
    rejoined, h1 = threshold.join_shares_verify(shares[:2], k=2)
    assert rejoined == seed, "K-of-N rejoin failed"
    try:
        threshold.join_shares(shares[:1], k=2)  # k=2 quorum, 1 share
        sys.exit("threshold FAIL: single share recovered the secret")
    except ValueError:
        pass  # correct: sub-quorum join must raise, proving no-information property
    print("threshold: 2-of-3 exact rejoin OK; 1-of-3 refused (no-info property) OK")

    go_signer = hashlib.sha256(b"test").hexdigest()
    tmp = "/tmp/opencode/braid-keyz-selftest.braid"
    if os.path.exists(tmp):
        os.remove(tmp)
    with open(tmp, "w") as fh:
        fh.write(json.dumps({
            "cid": "br0000000000000000000000000000000000000000000000000000000000000001",
            "prev": None, "op": "write:note", "target": "t",
            "payload": {}, "depth": 0, "signer": go_signer,
        }) + "\n")
    import braid_keyz.rotation as rotmod
    auth = rotmod.authorized_signer_set(tmp)
    assert go_signer in auth, "genesis signer must auto-authorize"
    assert not rotmod.is_authorized_signer("deadbeef" + "0" * 56, tmp)
    print("rotation: genesis authorized, stranger signer refused OK")

    print("braid-keyz selftest PASSED")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("bind")
    p.add_argument("--passphrase", help="passphrase to bind under, or PROMPT")
    p.add_argument("--seed", help="source signer hex or file path")
    p.set_defaults(func=cmd_bind)

    p = sub.add_parser("unbind")
    p.add_argument("--passphrase", help="passphrase to unseal with, or PROMPT")
    p.add_argument("--seed", help="source signer hex or file path to cross-check")
    p.set_defaults(func=cmd_unbind)

    p = sub.add_parser("split")
    p.add_argument("-n", type=int, default=3)
    p.add_argument("-k", type=int, default=2)
    p.add_argument("--seed", help="source signer hex or file path")
    p.set_defaults(func=cmd_split)

    p = sub.add_parser("join")
    p.add_argument("-k", type=int, default=None)
    p.set_defaults(func=cmd_join)

    p = sub.add_parser("lineage")
    p.add_argument("--log", default=rotation.DEFAULT_LOG_PATH)
    p.set_defaults(func=cmd_lineage)

    p = sub.add_parser("rotate")
    p.add_argument("new_signer")
    p.add_argument("-r", "--reason", default="")
    p.set_defaults(func=cmd_rotate)

    p = sub.add_parser("selftest")
    p.set_defaults(func=cmd_selftest)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()