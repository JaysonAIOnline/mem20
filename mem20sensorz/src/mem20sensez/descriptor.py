"""mem20sensez capability descriptors (mem30 Phase 1: sense-organs).

Five typed UCG nodes:
  cap.sense-gap.v1      — Capability Gap Mapper (RM-200)
  cap.sense-replan.v1   — Dynamic Phase Replanner (RM-199)
  cap.sense-twin.v1     — Personal Workflow Twin + Execution Digital Twin
  cap.sense-accel.v1    — Human Capability Accelerator (RM-150)
  cap.sense-enroll.v1   — Device Enrollment Autopilot (RM-151)
"""

# --- Capability Gap Mapper ---------------------------------------------
GAP_ID = "cap.sense-gap.v1"
GAP_NAME = "capability-gap-mapper"
GAP_PROVIDER = "mem30.sense.gap.mapper"
GAP_INPUTS = ["goal", "ucg_query"]
GAP_OUTPUTS = ["sense/gap/report"]


def gap_descriptor() -> dict:
    return {
        "id": GAP_ID,
        "name": GAP_NAME,
        "version": "0.1.0",
        "provider": GAP_PROVIDER,
        "inputs": GAP_INPUTS,
        "outputs": GAP_OUTPUTS,
        "requires": ["cap.rm-001-universal-capability-graph.v1"],
        "conflicts": [],
        "platforms": ["local"],
        "endpoint": "http://127.0.0.1:8784",
        "invocation": "fs-sense gap --goal '...'",
        "signed": False,
        "state": "active",
        "latency_ms": 20.0,
        "cost_units": 0.0,
        "energy_units": 0.1,
        "metadata": {
            "tag": "[REAL] mem30 Phase 1 RM-200 — real token coverage over live UCG",
            "tags": ["sense", "gap-mapper", "planning", "ucg"],
            "license": "Apache-2.0",
        },
    }


# --- Dynamic Phase Replanner --------------------------------------------
REPLAN_ID = "cap.sense-replan.v1"
REPLAN_NAME = "dynamic-phase-replanner"
REPLAN_PROVIDER = "mem30.sense.replanner"
REPLAN_INPUTS = ["goal", "phases", "gap_report"]
REPLAN_OUTPUTS = ["sense/replan/plan"]


def replan_descriptor() -> dict:
    return {
        "id": REPLAN_ID,
        "name": REPLAN_NAME,
        "version": "0.1.0",
        "provider": REPLAN_PROVIDER,
        "inputs": REPLAN_INPUTS,
        "outputs": REPLAN_OUTPUTS,
        "requires": ["cap.rm-001-universal-capability-graph.v1"],
        "conflicts": [],
        "platforms": ["local"],
        "endpoint": "http://127.0.0.1:8784",
        "invocation": "fs-sense replan --goal '...' --phases a,b,c",
        "signed": False,
        "state": "active",
        "latency_ms": 20.0,
        "cost_units": 0.0,
        "energy_units": 0.1,
        "metadata": {
            "tag": "[REAL] mem30 Phase 1 RM-199 — deterministic re-plan over UCG gaps",
            "tags": ["sense", "replanner", "planning", "braid"],
            "license": "Apache-2.0",
        },
    }


# --- Digital Twin --------------------------------------------------------
TWIN_ID = "cap.sense-twin.v1"
TWIN_NAME = "digital-twin"
TWIN_PROVIDER = "mem30.sense.digital.twin"
TWIN_INPUTS = ["self_model_rows", "memory_rows", "steps", "initial"]
TWIN_OUTPUTS = ["sense/twin/workflow", "sense/twin/exec_plan"]


def twin_descriptor() -> dict:
    return {
        "id": TWIN_ID,
        "name": TWIN_NAME,
        "version": "0.1.0",
        "provider": TWIN_PROVIDER,
        "inputs": TWIN_INPUTS,
        "outputs": TWIN_OUTPUTS,
        "requires": ["mem20.braid.ledger"],
        "conflicts": [],
        "platforms": ["local"],
        "endpoint": "http://127.0.0.1:8784",
        "invocation": "fs-sense twin | fs-sense exec --steps '[...]'",
        "signed": False,
        "state": "active",
        "latency_ms": 30.0,
        "cost_units": 0.0,
        "energy_units": 0.1,
        "metadata": {
            "tag": "[REAL] mem30 Phase 1 RM-140/141/052/053 — self-model + memory twin, langz StateGraph exec twin",
            "tags": ["sense", "twin", "self-model", "memory", "execution", "langz"],
            "license": "Apache-2.0",
        },
    }


# --- Human Capability Accelerator ---------------------------------------
ACCEL_ID = "cap.sense-accel.v1"
ACCEL_NAME = "human-capability-accelerator"
ACCEL_PROVIDER = "mem30.sense.human.accelerator"
ACCEL_INPUTS = ["human_id", "public_key", "goal", "skills", "baseline"]
ACCEL_OUTPUTS = ["sense/human/admission", "sense/human/progress"]


def accel_descriptor() -> dict:
    return {
        "id": ACCEL_ID,
        "name": ACCEL_NAME,
        "version": "0.1.0",
        "provider": ACCEL_PROVIDER,
        "inputs": ACCEL_INPUTS,
        "outputs": ACCEL_OUTPUTS,
        "requires": ["mem20.gateway.identity"],
        "conflicts": [],
        "platforms": ["local"],
        "endpoint": "http://127.0.0.1:8784",
        "invocation": "fs-sense accelerate --human '...' --goal '...'",
        "signed": False,
        "state": "active",
        "latency_ms": 30.0,
        "cost_units": 0.0,
        "energy_units": 0.1,
        "metadata": {
            "tag": "[REAL] mem30 Phase 1 RM-150 — human trust bridge + measurable growth (per-device attestation is Ed25519)",
            "tags": ["sense", "human", "trust-bridge", "growth", "ed25519"],
            "license": "Apache-2.0",
        },
    }


# --- Device Enrollment Autopilot -----------------------------------------
ENROLL_ID = "cap.sense-enroll.v1"
ENROLL_NAME = "device-enrollment-autopilot"
ENROLL_PROVIDER = "mem30.sense.device.enroller"
ENROLL_INPUTS = ["device_id", "public_key", "hostname", "platform"]
ENROLL_OUTPUTS = ["sense/device/enrollment", "sense/device/credential"]


def enroll_descriptor() -> dict:
    return {
        "id": ENROLL_ID,
        "name": ENROLL_NAME,
        "version": "0.1.0",
        "provider": ENROLL_PROVIDER,
        "inputs": ENROLL_INPUTS,
        "outputs": ENROLL_OUTPUTS,
        "requires": ["mem20.gateway.identity"],
        "conflicts": [],
        "platforms": ["local"],
        "endpoint": "http://127.0.0.1:8784",
        "invocation": "fs-sense enroll --device '...' --pubkey '...'",
        "signed": False,
        "state": "active",
        "latency_ms": 30.0,
        "cost_units": 0.0,
        "energy_units": 0.1,
        "metadata": {
            "tag": "[REAL] mem30 Phase 1 RM-151 — device trust bridge + provisioning (per-device attestation is Ed25519)",
            "tags": ["sense", "device", "trust-bridge", "enrollment", "ed25519"],
            "license": "Apache-2.0",
        },
    }


def all_descriptors() -> list[dict]:
    return [gap_descriptor(), replan_descriptor(), twin_descriptor(),
            accel_descriptor(), enroll_descriptor()]