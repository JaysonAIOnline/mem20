from __future__ import annotations

import time
from collections import Counter
from threading import Lock


class Metrics:
    def __init__(self) -> None:
        self._counts = Counter()
        self._gauges: dict[str, float] = {}
        self._lock = Lock()
        self.started_at = time.time()

    def inc(self, key: str, amount: int = 1) -> None:
        with self._lock:
            self._counts[key] += amount

    def gauge(self, key: str, value: float) -> None:
        with self._lock:
            self._gauges[key] = float(value)

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {"uptime_seconds": time.time() - self.started_at, "counters": dict(self._counts), "gauges": dict(self._gauges)}

    def prometheus(self) -> str:
        snap = self.snapshot()
        lines = [f"mem20ucgz_uptime_seconds {snap['uptime_seconds']:.6f}"]
        for k, v in sorted(snap["counters"].items()):
            lines.append(f"mem20ucgz_{k} {v}")
        for k, v in sorted(snap["gauges"].items()):
            lines.append(f"mem20ucgz_{k} {v}")
        return "\n".join(lines) + "\n"
