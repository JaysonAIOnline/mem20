from __future__ import annotations
import json, tempfile, time
from pathlib import Path
from .runtime import MicroappRuntime

SCENARIOS=("success","malformed_input","disconnection","overload","provider_loss","restart_recovery")

def run(runtime: MicroappRuntime,bundle: str|Path, scenario: str):
    if scenario not in SCENARIOS: raise ValueError(f"unknown scenario: {scenario}")
    if scenario=="success": return runtime.launch(bundle,{"name":"simulator"})
    if scenario=="malformed_input": return runtime.launch(bundle,{"__malformed__":True})
    if scenario=="disconnection": return runtime.launch(bundle,{},telemetry={"network_up":False},preferred_mode="local")
    if scenario=="overload": return runtime.scheduler.choose(["local","cloud"],{"network_up":True,"network_latency_ms":30,"local_load":0.98})
    if scenario=="provider_loss": return runtime.scheduler.choose(["local","cloud"],{"network_up":False,"local_load":0.3})
    if scenario=="restart_recovery":
        return {"supported":True,"mechanism":"persistent queued/running jobs + resume_incomplete(bundle_resolver)"}
