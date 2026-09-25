"""cv.infer orchestration service: route mode -> engine or contract simulator.

mode="real" runs the real classical-CV engine on the actual image.
mode="sim" runs the deterministic contract simulator (simulated:true).
An optional heavy-model provider hook exists for future real NN inference; when
not configured it is honestly reported as unavailable — never faked.
"""
from __future__ import annotations

import time
from typing import Any

from . import braid_hook
from .descriptor import CAPABILITY_ID, CAPABILITY_NAME, CAPABILITY_VERSION
from .engine import CvEngineError, compute_features, load_image


class InferenceError(RuntimeError):
    pass


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


def run_inference(payload: dict[str, Any], journal: bool = True) -> dict[str, Any]:
    """Run one cv.infer request. Returns the typed result dict.

    Raises InferenceError on contract violation; braid journal failure is
    surfaced if journal=True and the ledger is reachable but refuses.
    """
    if not isinstance(payload, dict):
        raise InferenceError("payload must be a JSON object")
    mode = payload.get("mode", "real")
    if mode not in ("real", "sim"):
        raise InferenceError(f"mode must be real or sim, got {mode!r}")
    image_path = payload.get("image_path")
    frame_blob = payload.get("frame_blob_b64")
    options = payload.get("options") or {}

    if mode == "sim":
        from .simulator import simulate
        result = simulate(payload)
        result["metadata"]["capability"] = CAPABILITY_ID
        result["metadata"]["engine_version"] = CAPABILITY_VERSION
        if journal:
            result["metadata"]["_braid"] = braid_hook.journal_inference(result, payload)
        return result

    # real mode
    if not image_path and not frame_blob:
        raise InferenceError("real mode requires image_path or frame_blob_b64")
    start = time.monotonic()
    try:
        feats = compute_features(image_path or None, frame_blob or None,
                                 embed_dim=int(options.get("embed_dim", 128)))
    except CvEngineError as e:
        raise InferenceError(str(e)) from e
    d = feats.to_dict()
    result = {
        "objects": [],
        "classifications": [],
        "embedding": d["embedding"],
        "features": {k: v for k, v in d.items() if k != "embedding"},
        "metadata": {
            "simulated": False,
            "engine": "mem20cviz.classical",
            "capability": CAPABILITY_ID,
            "engine_version": CAPABILITY_VERSION,
            "runtime_ms": _elapsed_ms(start),
            "width": d["width"],
            "height": d["height"],
        },
    }
    if journal:
        result["metadata"]["_braid"] = braid_hook.journal_inference(result, payload)
    return result