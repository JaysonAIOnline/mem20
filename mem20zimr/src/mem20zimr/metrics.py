from __future__ import annotations
import threading, time
from collections import Counter

class Metrics:
    def __init__(self):
        self._lock = threading.Lock(); self.c = Counter(); self.latencies=[]
    def inc(self, key: str, n: int = 1):
        with self._lock: self.c[key]+=n
    def observe(self, seconds: float):
        with self._lock:
            self.latencies.append(seconds); self.latencies=self.latencies[-1000:]
    def prometheus(self) -> str:
        with self._lock:
            lines=[f"freestack_microapp_{k} {v}" for k,v in sorted(self.c.items())]
            if self.latencies:
                lines += [f"freestack_microapp_latency_seconds_sum {sum(self.latencies)}", f"freestack_microapp_latency_seconds_count {len(self.latencies)}"]
            return "\n".join(lines)+"\n"
