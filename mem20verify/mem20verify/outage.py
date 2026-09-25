"""Outage circuit-breaker contract check.

Exercises the real Bridge.run() loop against a transport that always fails, and
asserts the three properties the standing rule requires:
  1. three consecutive errors trip the breaker, exactly once
  2. while tripped, re-probes are spaced by the full retry interval
  3. the memory ledger receives nothing during an outage

Nothing here touches the filesystem or any real transport.
"""

from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass, field
from unittest import mock


@dataclass
class OutageResult:
    strikes: int = 0
    retry_interval_s: float = 0.0
    trip_events: int = 0
    stderr_lines: int = 0
    ledger_rows: int = 0
    re_probes: list[float] = field(default_factory=list)
    reset_after_recovery: bool = False
    polls: int = 0
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and self.trip_events == 1 and self.ledger_rows == 0

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "strikes": self.strikes,
            "retry_interval_s": self.retry_interval_s,
            "trip_events": self.trip_events,
            "stderr_lines": self.stderr_lines,
            "ledger_rows": self.ledger_rows,
            "re_probes": self.re_probes,
            "reset_after_recovery": self.reset_after_recovery,
            "polls": self.polls,
            "error": self.error,
        }


def _load_bridge():
    try:
        import mem20agentz.bridge as bridge_mod
    except ImportError as exc:
        raise RuntimeError(f"mem20agentz not importable: {exc}") from exc
    return bridge_mod


class _DeadTransport:
    """Raises on `fail_for` polls, then stops the loop and returns cleanly.

    Every run is bounded, so a check can never hang.
    """

    def __init__(self, bridge, fail_for: int):
        self.bridge = bridge
        self.fail_for = fail_for
        self.polls = 0
        self.sent: list = []

    def start(self):
        return None

    def stop(self):
        return None

    def poll(self, timeout):
        self.polls += 1
        if self.polls > self.fail_for:
            self.bridge.stop()
            return
        raise OSError("simulated outage: transport unreachable")


class _Ledger:
    def __init__(self):
        self.rows: list = []

    def session_append(self, *args):
        self.rows.append(args)


def _build(bridge_mod, fail_for: int):
    import pathlib
    import tempfile

    bridge = bridge_mod.Bridge(
        "mem20verify-probe", None, ledger=_Ledger(),
        root=pathlib.Path(tempfile.mkdtemp(prefix="mem20verify-outage-")),
        require_pairing=False,
    )
    transport = _DeadTransport(bridge, fail_for)
    bridge.transport = transport
    return bridge, transport


def check(fail_for: int = 8, re_probes: int = 5) -> OutageResult:
    result = OutageResult()
    try:
        bridge_mod = _load_bridge()
    except RuntimeError as exc:
        result.error = str(exc)
        return result

    result.strikes = bridge_mod.MAX_CONSECUTIVE_ERRORS
    result.retry_interval_s = bridge_mod.TRIP_RETRY_INTERVAL_S

    if result.strikes != 3:
        result.error = f"MAX_CONSECUTIVE_ERRORS is {result.strikes}, expected 3"
        return result
    if result.retry_interval_s <= 0:
        result.error = "TRIP_RETRY_INTERVAL_S is not positive"
        return result

    # --- property 1 and 3: bounded failure run, trip once, ledger untouched
    bridge, transport = _build(bridge_mod, fail_for=result.strikes)
    buf = io.StringIO()
    with mock.patch.object(bridge_mod, "TRIP_RETRY_INTERVAL_S", 0.0), \
            mock.patch.object(bridge_mod.time, "sleep", lambda s: None), \
            contextlib.redirect_stderr(buf):
        bridge.run(interval_s=0)
    lines = [x for x in buf.getvalue().splitlines() if x.strip()]
    result.trip_events = sum("breaker_tripped" in x for x in lines)
    result.stderr_lines = len(lines)
    result.ledger_rows = len(bridge.ledger.rows)
    result.polls = transport.polls

    # --- property 2: re-probe cadence under a real interval
    slept: list[float] = []
    bridge2, _ = _build(bridge_mod,
                                  fail_for=result.strikes + re_probes)
    with mock.patch.object(bridge_mod.time, "sleep", slept.append):
        bridge2.run(interval_s=0.5)
    result.re_probes = [s for s in slept if s >= result.retry_interval_s / 2]
    result.reset_after_recovery = (not bridge2._tripped
                                   and bridge2._consecutive_errors == 0)

    if result.trip_events != 1:
        result.error = f"expected exactly 1 trip event, saw {result.trip_events}"
    elif result.ledger_rows != 0:
        result.error = f"outage wrote {result.ledger_rows} row(s) to the ledger"
    elif not result.re_probes:
        result.error = "no re-probe wait was recorded"
    elif any(s != result.retry_interval_s for s in result.re_probes):
        result.error = f"re-probe waits were not all {result.retry_interval_s}s"
    elif not result.reset_after_recovery:
        result.error = "breaker did not reset after a successful poll"
    return result
