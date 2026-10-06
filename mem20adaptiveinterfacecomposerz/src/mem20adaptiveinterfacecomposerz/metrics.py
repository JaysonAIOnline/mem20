from __future__ import annotations
from collections import defaultdict
from threading import Lock
import time

class Metrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self.counters = defaultdict(float)
        self.latencies = defaultdict(list)

    def inc(self, key: str, value: float = 1.0) -> None:
        with self._lock:
            self.counters[key] += value

    def observe(self, key: str, value: float) -> None:
        with self._lock:
            self.latencies[key].append(float(value))
            if len(self.latencies[key]) > 1000:
                self.latencies[key] = self.latencies[key][-1000:]

    def timed(self, key: str):
        metrics = self
        class T:
            def __enter__(self): self.start = time.perf_counter(); return self
            def __exit__(self, *args): metrics.observe(key, (time.perf_counter()-self.start)*1000)
        return T()

    def prometheus(self) -> str:
        lines = []
        with self._lock:
            for key, val in sorted(self.counters.items()):
                lines.append(f"freestack_interface_{key} {val}")
            for key, vals in sorted(self.latencies.items()):
                if vals:
                    lines.append(f"freestack_interface_{key}_ms_avg {sum(vals)/len(vals):.6f}")
                    lines.append(f"freestack_interface_{key}_ms_max {max(vals):.6f}")
        return "\n".join(lines) + "\n"
