from __future__ import annotations
import os, resource, statistics, tempfile, pathlib, time
from .runtime import InterfaceComposerRuntime, RuntimeConfig
from .model import Capability, UserIntent

def _energy_joules():
    for p in ("/sys/class/powercap/intel-rapl:0/energy_uj","/sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj"):
        try:return int(open(p).read().strip())/1e6
        except Exception:pass
    return None

def benchmark(runs:int=20)->dict:
    with tempfile.TemporaryDirectory() as d:
        rt=InterfaceComposerRuntime(RuntimeConfig(db_path=str(pathlib.Path(d)/"b.sqlite")))
        rt.register_capability(Capability("search","Search","Semantic search",("search",),("search",),latency_ms=2))
        lat=[]; e0=_energy_joules(); t0=time.perf_counter()
        for i in range(runs):
            s=time.perf_counter();rt.compose(UserIntent("search knowledge"),idempotency_key=f"bench-{i}");lat.append((time.perf_counter()-s)*1000)
        elapsed=time.perf_counter()-t0;e1=_energy_joules();rt.close()
        return {"runs":runs,"latency_ms_avg":round(statistics.mean(lat),3),"latency_ms_p95":round(sorted(lat)[max(0,int(.95*len(lat))-1)],3),"throughput_per_s":round(runs/max(elapsed,1e-9),3),"memory_max_rss_kb":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,"energy_joules":round(e1-e0,6) if e0 is not None and e1 is not None else None,"network_transfer_bytes":0,"execution_cost":0.0,"mode":"local"}
