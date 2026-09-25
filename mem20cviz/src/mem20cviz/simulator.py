"""Deterministic contract simulator for cv.infer (mode="sim").

Proves the cv.infer capability contract (request -> typed result, registered in
UCG, journal-able) WITHOUT pretending to see. Output is deterministically derived
from a hash of the input payload and is ALWAYS marked simulated:true. Never used
to claim a real analysis of the image content.
"""
from __future__ import annotations

import hashlib
import json
import time
import struct
from typing import Any


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def _pseudo_random_bytes(seed: int, n: int) -> bytes:
    x = seed & 0xFFFFFFFFFFFFFFFF
    x ^= (x >> 12) & 0xFFFFFFFFFFFFFFFF
    x ^= (x << 25) & 0xFFFFFFFFFFFFFFFF
    x ^= (x >> 27) & 0xFFFFFFFFFFFFFFFF
    x = (x * 2685821657736338717) & 0xFFFFFFFFFFFFFFFF
    out = bytearray()
    for _ in range(n):
        x ^= (x >> 12) & 0xFFFFFFFFFFFFFFFF
        x ^= (x << 25) & 0xFFFFFFFFFFFFFFFF
        x ^= (x >> 27) & 0xFFFFFFFFFFFFFFFF
        x = (x * 2685821657736338717) & 0xFFFFFFFFFFFFFFFF
        out.append(x & 0xFF)
    return bytes(out)


def simulate(payload: dict[str, Any], seed_offset: int = 0) -> dict[str, Any]:
    """Deterministic simulated inference result. simulated:true always."""
    digest = hashlib.sha256(_canonical(payload)).digest()
    seed = int.from_bytes(digest[:8], "big") + seed_offset
    rng = _pseudo_random_bytes(seed, 1024)

    def u01() -> float:
        nonlocal rng
        if not rng:
            rng = _pseudo_random_bytes(seed, 1024)
        v = rng[0] / 255.0
        rng = rng[1:]
        return v

    n_objects = 1 + (seed % 3)
    objects: list[dict[str, Any]] = []
    labels = ["sim-object"]
    for i in range(n_objects):
        x = int(round(u01() * 10000)) % 500
        y = int(round(u01() * 10000)) % 500
        w = 10 + int(round(u01() * 10000)) % 200
        h = 10 + int(round(u01() * 10000)) % 200
        objects.append({
            "label": labels[0],
            "bbox": [x, y, w, h],
            "score": round(0.5 + u01() * 0.5, 4),
            "index": i,
        })
    classifications = [{"label": "sim-class", "score": round(0.5 + u01() * 0.5, 4)}]
    embed_dim = int((payload.get("options") or {}).get("embed_dim", 128))
    embedding = [round(u01(), 6) for _ in range(embed_dim)]
    return {
        "objects": objects,
        "classifications": classifications,
        "embedding": embedding,
        "metadata": {
            "simulated": True,
            "engine": "mem20cviz.simulator",
            "contract_hash": digest.hex()[:16],
            "seed": seed,
            "runtime_ms": (seed >> 8) % 10000,
        },
    }