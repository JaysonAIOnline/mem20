"""Tests for the canonical MCP server's self-contained pieces.

`/opt/mem20/mcp` is the real, running tool server, and it is the one component of
the estate that had no tests at all. The 13.5k lines cannot be covered by one file,
so this covers the two parts that are genuinely self-contained and high-risk:

* `health.py` - the liveness/readiness/metrics HTTP surface. If this lies about
  readiness, an orchestrator will route traffic to a server that cannot serve it.
* `install_tracker.py` - the local event log and its aggregation. It parses a file
  that grows by appending, so malformed lines and duplicate installs are the
  interesting cases.

The MCP tool registry itself needs the MCP SDK and a live transport; that is
explicitly out of scope here rather than faked.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

MCP_ROOT = Path("/opt/mem20/mcp")


def _load(name: str):
    """Load a module from the canonical tree by explicit file path.

    Deliberately not `importlib.import_module`: `mem20_mcp` ships shim modules with
    the same names that forward to this tree via module-level ``__getattr__``. A
    forwarded function keeps the *canonical* module's globals, so
    ``monkeypatch.setattr`` on the shim silently patches an object the function
    never reads, and a test writes to the real store instead of its fixture.
    Loading the canonical file by path makes the module under test the same object
    the code executes in.
    """
    path = MCP_ROOT / f"{name}.py"
    if not path.is_file():
        raise ImportError(f"canonical module not found: {path}")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def health():
    return _load("health")


@pytest.fixture(scope="module")
def tracker():
    return _load("install_tracker")


# --- health: the readiness contract ------------------------------------------


class _FakeServer:
    """The minimum surface _HealthHandler reads off the MCP server object."""

    def __init__(self):
        self._start_time = time.time()
        self.tools = {"mem20_memory_store": {}, "mem20_recall": {}}

    def metrics(self):
        return {"uptime_seconds": round(time.time() - self._start_time, 3), "tools": len(self.tools)}


@pytest.fixture(scope="module")
def health_server(health):
    """Start the real health server via its own start_health_server()."""
    import socket

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    # start_health_server binds and spawns its own daemon thread, and returns
    # None rather than raising if the port cannot be bound.
    httpd = health.start_health_server(_FakeServer(), port)
    assert httpd is not None, "health server did not start"
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def _get(base: str, path: str):
    # urllib's response exposes .status; HTTPResponse has no .status_code.
    with urllib.request.urlopen(base + path, timeout=10) as response:
        return response.status, json.loads(response.read().decode())


def test_health_reports_service_liveness(health_server):
    status, body = _get(health_server, "/health")
    assert status == 200
    assert body["status"] == "ok"
    assert body["service"] == "mem20-mcp"
    assert body["uptime_seconds"] >= 0


def test_health_content_type_is_json(health_server):
    with urllib.request.urlopen(health_server + "/health", timeout=10) as response:
        assert response.headers.get("Content-Type") == "application/json"


def test_ready_is_true_only_when_tools_are_registered(health_server):
    status, body = _get(health_server, "/ready")
    assert status == 200
    assert body["ready"] is True
    assert body["tools"] == 2


def test_ready_is_false_for_a_server_with_no_tools(health):
    """Readiness must not lie: a server with an empty registry is not ready."""
    import json as _json
    import urllib.request

    empty = _FakeServer()
    empty.tools = {}
    import socket

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    httpd = health.start_health_server(empty, port)
    assert httpd is not None
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/ready", timeout=10) as r:
            body = _json.loads(r.read().decode())
        assert body["ready"] is False
        assert body["tools"] == 0
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_metrics_endpoint_returns_a_mapping(health_server):
    status, body = _get(health_server, "/metrics")
    assert status == 200
    assert isinstance(body, dict)


def test_an_unknown_path_is_a_json_404_not_an_html_error(health_server):
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _get(health_server, "/definitely-not-a-route")
    assert excinfo.value.code == 404
    body = json.loads(excinfo.value.read().decode())
    assert body.get("error") == "not found"
    assert "path" in body, "the 404 should name the path it did not recognise"


def test_trailing_slashes_are_tolerated(health_server):
    """Probes hit /health/ as often as /health; both must work."""
    assert _get(health_server, "/health/")[0] == 200


def test_query_strings_are_ignored_when_routing(health_server):
    assert _get(health_server, "/health?probe=1")[0] == 200


def test_health_handler_never_crashes_on_an_unknown_route(health_server):
    """A crashing handler would take the probe endpoint down entirely."""
    for path in ("/", "/nope", "/health/deep", "/metrics/x"):
        try:
            _get(health_server, path)
        except urllib.error.HTTPError as exc:
            assert exc.code in (200, 404), f"{path} returned {exc.code}"
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"{path} raised {type(exc).__name__}: {exc}")


# --- install tracker: the local event log ------------------------------------


@pytest.fixture
def store(tmp_path, monkeypatch, tracker):
    target = tmp_path / "store"
    target.mkdir()
    monkeypatch.setattr(tracker, "_store_dir", lambda: str(target))
    monkeypatch.setenv("MEM20_INSTALL_WEBHOOK", "")
    return target


def _event(store: Path, **fields):
    base = {
        "install_id": "install-1",
        "event": "install",
        "channel": "runtime",
        "version": "0.1.0",
        "platform": "Linux",
        "timestamp": "2026-01-01T00:00:00+00:00",
    }
    base.update(fields)
    with (store / "installs.jsonl").open("a") as handle:
        handle.write(json.dumps(base) + "\n")
    return base


def test_an_event_is_appended_to_the_local_log(store, tracker):
    tracker.report(channel="runtime", event="install")
    lines = (store / "installs.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["channel"] == "runtime"
    assert payload["event"] == "install"
    assert payload["platform"], "platform should be recorded"


def test_telemetry_can_be_switched_off_entirely(store, tracker, monkeypatch):
    monkeypatch.setenv("MEM20_NO_TELEMETRY", "1")
    tracker.report()
    assert not (store / "installs.jsonl").exists(), (
        "MEM20_NO_TELEMETRY must suppress even the local log"
    )


def test_report_never_raises_even_when_the_store_is_unwritable(store, tracker, monkeypatch):
    """A telemetry failure must never take down a server startup."""
    monkeypatch.setattr(tracker, "_store_dir", lambda: "/proc/definitely/not/writable")
    tracker.report()  # must not raise


def test_metrics_of_an_empty_log_are_zero_not_an_error(store, tracker):
    metrics = tracker.compute_metrics(store=str(store))
    assert metrics["total_events"] == 0
    assert metrics["unique_installs"] == 0
    assert metrics["first_seen"] is None
    assert metrics["last_24h"] == 0


def test_metrics_count_events_and_unique_installs(store, tracker):
    _event(store, install_id="a")
    _event(store, install_id="a")
    _event(store, install_id="b")
    metrics = tracker.compute_metrics(store=str(store))
    assert metrics["total_events"] == 3
    assert metrics["unique_installs"] == 2, "repeat events from one install are not new installs"


def test_metrics_group_by_channel_platform_and_version(store, tracker):
    _event(store, channel="pip", platform="Linux", version="0.1.0")
    _event(store, channel="pip", platform="Darwin", version="0.2.0")
    metrics = tracker.compute_metrics(store=str(store))
    assert metrics["by_channel"] == {"pip": 2}
    assert metrics["by_platform"] == {"Linux": 1, "Darwin": 1}
    assert metrics["by_version"] == {"0.1.0": 1, "0.2.0": 1}


def test_a_corrupt_line_does_not_lose_the_good_events(store, tracker):
    """The log is append-only and shared; one bad line must not zero the metrics."""
    _event(store, install_id="a")
    with (store / "installs.jsonl").open("a") as handle:
        handle.write("{not json at all\n")
    _event(store, install_id="b")
    metrics = tracker.compute_metrics(store=str(store))
    assert metrics["total_events"] == 2
    assert metrics["unique_installs"] == 2


def test_blank_lines_are_ignored(store, tracker):
    _event(store)
    with (store / "installs.jsonl").open("a") as handle:
        handle.write("\n\n")
    assert tracker.compute_metrics(store=str(store))["total_events"] == 1


def test_first_and_last_seen_reflect_event_order(store, tracker):
    _event(store, timestamp="2026-01-01T00:00:00+00:00")
    _event(store, timestamp="2026-03-01T00:00:00+00:00")
    metrics = tracker.compute_metrics(store=str(store))
    assert metrics["first_seen"].startswith("2026-01-01")
    assert metrics["last_seen"].startswith("2026-03-01")


def test_events_missing_an_install_id_are_not_counted_as_installs(store, tracker):
    _event(store, install_id="")
    metrics = tracker.compute_metrics(store=str(store))
    assert metrics["total_events"] == 1
    assert metrics["unique_installs"] == 0, "a blank install id is not an install"


def test_recent_window_excludes_old_events(store, tracker):
    from datetime import datetime, timedelta, timezone

    old = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    fresh = datetime.now(timezone.utc).isoformat()
    _event(store, timestamp=old)
    _event(store, timestamp=fresh)
    metrics = tracker.compute_metrics(store=str(store))
    assert metrics["last_24h"] == 1, "only the fresh event falls in the 24h window"


def test_first_run_is_recorded_only_once(store, tracker):
    """report_first_run returns None; the contract is one recorded event, not a value."""
    assert tracker.report_first_run(channel="pip") is None
    tracker.report_first_run(channel="pip")
    tracker.report_first_run(channel="pip")
    lines = (store / "installs.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1, "a first-run event must not repeat on every run"
    assert json.loads(lines[0])["event"] == "first_run"


def test_first_run_writes_a_marker_so_the_check_is_local(store, tracker):
    tracker.report_first_run(channel="pip")
    assert (store / "first_run_reported").exists()


def test_first_run_honours_a_different_channel(store, tracker):
    tracker.report_first_run(channel="docker")
    payload = json.loads((store / "installs.jsonl").read_text().strip())
    assert payload["channel"] == "docker"


def test_an_unparseable_timestamp_does_not_break_metrics(store, tracker):
    _event(store, timestamp="not-a-timestamp")
    metrics = tracker.compute_metrics(store=str(store))
    assert metrics["total_events"] == 1
    assert metrics["last_24h"] == 0
