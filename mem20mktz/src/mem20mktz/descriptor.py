"""mem20mktz capability descriptors (RM-010/RM-012/RM-015/RM-061/RM-070/RM-087).

Mirrors mem20sensez/descriptor.py shape exactly: typed capability descriptors
versioned `cap.mkt-*.v1`, each declaring `requires` on the Universal
Capability Graph (cap.rm-001-universal-capability-graph.v1), and the UCG
hosts them at its `/query` endpoint (POST, empty text -> all). The market
service signs + journals every descriptor commitment to the braid ledger so
proposed capabilities are provable, not just claimed.
"""
from __future__ import annotations

from typing import Any

# --- Model Genome Lab (RM-061) -------------------------------------------
GENOME_ID = "cap.mkt-genome.v1"
GENOME_NAME = "model-genome-lab"
GENOME_PROVIDER = "mem30.mkt.genome.lab"
GENOME_INPUTS = ["model_id", "capabilities", "costs", "visibility"]
GENOME_OUTPUTS = ["mkt/genome/status", "mkt/genome/best-match"]


def genome_descriptor() -> dict[str, Any]:
    return {
        "id": GENOME_ID,
        "name": GENOME_NAME,
        "version": "0.1.0",
        "provider": GENOME_PROVIDER,
        "inputs": GENOME_INPUTS,
        "outputs": GENOME_OUTPUTS,
        "requires": ["cap.rm-001-universal-capability-graph.v1"],
        "conflicts": [],
        "platforms": ["local"],
        "endpoint": "http://127.0.0.1:8785",
        "invocation": "fs-mkt genome --model '...' --capabilities '...'",
        "signed": False,
        "state": "active",
        "latency_ms": 15.0,
        "cost_units": 0.0,
        "energy_units": 0.1,
        "metadata": {
            "tag": "[REAL] mem30 Phase 2 RM-061 — Model Genome Lab: genome.generated, attest.new_nonce fix",
            "tags": ["mkt", "genome", "model-lab", "rm-061"],
            "license": "Apache-2.0",
        },
    }


# --- Capability Marketplace (RM-010) -------------------------------------
CAPABILITY_ID = "cap.mkt-capability.v1"
CAPABILITY_NAME = "capability-marketplace"
CAPABILITY_PROVIDER = "mem30.mkt.capability.market"
CAPABILITY_INPUTS = ["goal", "requires", "owns", "visibility"]
CAPABILITY_OUTPUTS = ["mkt/capability/listing", "mkt/capability/trade"]


def capability_descriptor() -> dict[str, Any]:
    return {
        "id": CAPABILITY_ID,
        "name": CAPABILITY_NAME,
        "version": "0.1.0",
        "provider": CAPABILITY_PROVIDER,
        "inputs": CAPABILITY_INPUTS,
        "outputs": CAPABILITY_OUTPUTS,
        "requires": ["cap.rm-001-universal-capability-graph.v1"],
        "conflicts": [],
        "platforms": ["local"],
        "endpoint": "http://127.0.0.1:8785",
        "invocation": "fs-mkt capability --goal '...' --visibility '...'",
        "signed": False,
        "state": "active",
        "latency_ms": 12.0,
        "cost_units": 0.0,
        "energy_units": 0.1,
        "metadata": {
            "tag": "[REAL] mem30 Phase 2 RM-010 — Capability Marketplace on the UCG (RM-010)",
            "tags": ["mkt", "capability", "marketplace", "rm-010"],
            "license": "Apache-2.0",
        },
    }


# --- Inference Marketplace (RM-070) --------------------------------------
INFERENCE_ID = "cap.mkt-inference.v1"
INFERENCE_NAME = "inference-marketplace"
INFERENCE_PROVIDER = "mem30.mkt.inference.market"
INFERENCE_INPUTS = ["model_id", "task", "budget", "latency_tolerance"]
INFERENCE_OUTPUTS = ["mkt/inference/listing", "mkt/inference/match"]


def inference_descriptor() -> dict[str, Any]:
    return {
        "id": INFERENCE_ID,
        "name": INFERENCE_NAME,
        "version": "0.1.0",
        "provider": INFERENCE_PROVIDER,
        "inputs": INFERENCE_INPUTS,
        "outputs": INFERENCE_OUTPUTS,
        "requires": [
            "cap.rm-001-universal-capability-graph.v1",
            "cap.mkt-genome.v1",
        ],
        "conflicts": [],
        "platforms": ["local"],
        "endpoint": "http://127.0.0.1:8785",
        "invocation": "fs-mkt inference --model '...' --task '...' --budget '...'",
        "signed": False,
        "state": "active",
        "latency_ms": 14.0,
        "cost_units": 0.0,
        "energy_units": 0.1,
        "metadata": {
            "tag": "[REAL] mem30 Phase 2 RM-070 — Adaptive Inference Marketplace (RM-070)",
            "tags": ["mkt", "inference", "marketplace", "rm-070"],
            "license": "Apache-2.0",
        },
    }


# --- Resource Exchange (RM-012) ------------------------------------------
RESOURCE_ID = "cap.mkt-resource.v1"
RESOURCE_NAME = "resource-exchange-market"
RESOURCE_PROVIDER = "mem30.mkt.resource.exchange"
RESOURCE_INPUTS = ["resource", "quantity", "unit_cost", "buyer"]
RESOURCE_OUTPUTS = ["mkt/resource/trade", "mkt/resource/quote"]


def resource_descriptor() -> dict[str, Any]:
    return {
        "id": RESOURCE_ID,
        "name": RESOURCE_NAME,
        "version": "0.1.0",
        "provider": RESOURCE_PROVIDER,
        "inputs": RESOURCE_INPUTS,
        "outputs": RESOURCE_OUTPUTS,
        "requires": ["cap.rm-001-universal-capability-graph.v1"],
        "conflicts": [],
        "platforms": ["local"],
        "endpoint": "http://127.0.0.1:8785",
        "invocation": "fs-mkt resource --resource '...' --quantity N --buyer '...'",
        "signed": False,
        "state": "active",
        "latency_ms": 10.0,
        "cost_units": 0.0,
        "energy_units": 0.1,
        "metadata": {
            "tag": "[REAL] mem30 Phase 2 RM-012 — Resource Exchange Market (RM-012)",
            "tags": ["mkt", "resource", "exchange", "rm-012"],
            "license": "Apache-2.0",
        },
    }


# --- Adaptive Pricing Brain (RM-015) -------------------------------------
PRICING_ID = "cap.mkt-pricing.v1"
PRICING_NAME = "adaptive-pricing-brain"
PRICING_PROVIDER = "mem30.mkt.pricing.brain"
PRICING_INPUTS = ["bundle", "margin", "policy", "reference_price"]
PRICING_OUTPUTS = ["mkt/pricing/quote", "mkt/pricing/decision"]


def pricing_descriptor() -> dict[str, Any]:
    return {
        "id": PRICING_ID,
        "name": PRICING_NAME,
        "version": "0.1.0",
        "provider": PRICING_PROVIDER,
        "inputs": PRICING_INPUTS,
        "outputs": PRICING_OUTPUTS,
        "requires": ["cap.rm-001-universal-capability-graph.v1"],
        "conflicts": [],
        "platforms": ["local"],
        "endpoint": "http://127.0.0.1:8785",
        "invocation": "fs-mkt pricing --bundle '...' --margin 0.2 --policy fair",
        "signed": False,
        "state": "active",
        "latency_ms": 8.0,
        "cost_units": 0.0,
        "energy_units": 0.0,
        "metadata": {
            "tag": "[REAL] mem30 Phase 2 RM-015 — Adaptive Pricing Brain (RM-015)",
            "tags": ["mkt", "pricing", "adaptive", "rm-015"],
            "license": "Apache-2.0",
        },
    }


# --- Service Bundling (RM-087) -------------------------------------------
BUNDLE_ID = "cap.mkt-bundle.v1"
BUNDLE_NAME = "service-bundling-engine"
BUNDLE_PROVIDER = "mem30.mkt.bundle.engine"
BUNDLE_INPUTS = ["name", "model_ids", "cap_ids", "margin"]
BUNDLE_OUTPUTS = ["mkt/bundle/composed", "mkt/bundle/ar-training-offer"]


def bundle_descriptor() -> dict[str, Any]:
    return {
        "id": BUNDLE_ID,
        "name": BUNDLE_NAME,
        "version": "0.1.0",
        "provider": BUNDLE_PROVIDER,
        "inputs": BUNDLE_INPUTS,
        "outputs": BUNDLE_OUTPUTS,
        "requires": [
            "cap.rm-001-universal-capability-graph.v1",
            "cap.mkt-genome.v1",
            "cap.mkt-pricing.v1",
        ],
        "conflicts": [],
        "platforms": ["local"],
        "endpoint": "http://127.0.0.1:8785",
        "invocation": "fs-mkt bundle --name 'AR-training' --models '...' --caps '...' --margin 0.2",
        "signed": False,
        "state": "active",
        "latency_ms": 20.0,
        "cost_units": 0.0,
        "energy_units": 0.1,
        "metadata": {
            "tag": "[REAL] mem30 Phase 2 RM-087 — Service Bundling Engine (RM-087)",
            "tags": ["mkt", "bundle", "service", "rm-087"],
            "license": "Apache-2.0",
        },
    }


_ORDERS = (
    genome_descriptor,
    capability_descriptor,
    inference_descriptor,
    resource_descriptor,
    pricing_descriptor,
    bundle_descriptor,
)


def all_descriptors() -> list[dict[str, Any]]:
    return [fn() for fn in _ORDERS]


def known_ids() -> list[str]:
    return [d["id"] for d in all_descriptors()]

MKTZ_DESCRIPTORS: list[dict[str, Any]] = [
    genome_descriptor(),
    capability_descriptor(),
    inference_descriptor(),
    resource_descriptor(),
    pricing_descriptor(),
    bundle_descriptor(),
]
