from __future__ import annotations
import os, time
from pathlib import Path
from .runtime import MicroappRuntime

def _energy_uj():
    for p in Path('/sys/class/powercap').glob('intel-rapl*/energy_uj'):
        try: return int(p.read_text())
        except Exception: pass
    return None

def benchmark(runtime: MicroappRuntime,bundle: str|Path,runs: int=5) -> dict:
    lat=[]; e0=_energy_uj(); t0=time.perf_counter()
    for i in range(max(1,runs)):
        a=time.perf_counter(); r=runtime.launch(bundle,{'benchmark':i},idempotency_key=f'bench-{time.time_ns()}-{i}',preferred_mode='local'); lat.append(time.perf_counter()-a)
        if r.status!='succeeded': raise RuntimeError(r.stderr)
    total=time.perf_counter()-t0; e1=_energy_uj()
    try:
        import resource; rss_kb=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except Exception: rss_kb=None
    return {'runs':runs,'latency_ms_avg':round(sum(lat)/len(lat)*1000,3),'latency_ms_p95':round(sorted(lat)[max(0,int(len(lat)*.95)-1)]*1000,3),'throughput_per_sec':round(runs/total,3),'memory_max_rss_kb':rss_kb,'energy_joules':None if e0 is None or e1 is None else round((e1-e0)/1_000_000,6),'network_transfer_bytes':0,'execution_cost':0.0,'mode':'local'}
