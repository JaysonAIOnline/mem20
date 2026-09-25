"""cv.infer capability descriptor (imagined -> registered real)."""
from __future__ import annotations

CAPABILITY_ID = "cap.cv-inference.v1"
CAPABILITY_NAME = "cv-inference"
CAPABILITY_VERSION = "0.1.0"
CAPABILITY_PROVIDER = "mem30.cv.inference"

INPUT_TYPES = ["image_path", "frame_blob_b64", "mode", "options"]
OUTPUT_TYPES = ["cv/features", "cv/objects", "cv/classifications", "cv/embedding"]


def descriptor() -> dict:
    """Return the typed UCG descriptor for the cv.infer capability node."""
    return {
        "id": CAPABILITY_ID,
        "name": CAPABILITY_NAME,
        "version": CAPABILITY_VERSION,
        "provider": CAPABILITY_PROVIDER,
        "inputs": INPUT_TYPES,
        "outputs": OUTPUT_TYPES,
        "requires": ["mem20.braid.ledger"],
        "conflicts": [],
        "platforms": ["local"],
        "endpoint": "http://127.0.0.1:8783",
        "invocation": "fs-cv infer --image ... | --frame-blob <b64> [--mode real|sim]",
        "signed": False,
        "state": "active",
        "latency_ms": 6.0,
        "cost_units": 0.0,
        "energy_units": 0.1,
        "metadata": {
            "tag": "[SPEC] imagined by mem20 2026-09-20, built real as mem20cviz",
            "tags": ["vision", "inference", "local", "deterministic", "classical"],
            "real_engine": "numpy/PIL classical CV feature extraction",
            "sim_contract": "mode=sim returns simulated:true, hash-derived",
            "heavy_provider": "optional; only real when configured",
            "license": "Apache-2.0",
        },
    }