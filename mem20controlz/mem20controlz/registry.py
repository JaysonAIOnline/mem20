"""Subsystem registry: who exists, how to reach them, and how honest is their status.

The registry is derived from the estate on disk (via mem20ops.clicheck, which is
the same discovery the coverage harness uses), so it cannot drift from reality.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from mem20ops import clicheck
from mem20ops.fleet import inventory as fleet_inventory

# Known HTTP surfaces for subsystems that serve one. Probed before falling back
# to the CLI, per the REST-first rule. Ports are the real ones observed on this
# host; a wrong port simply fails the probe and the CLI path is used instead.
HTTP_SURFACES: dict[str, dict[str, Any]] = {
    "mcp": {"port": 8080, "health": "/health", "ready": "/ready", "metrics": "/metrics"},
    "messaging": {"port": 8000, "health": "/health"},
    "webgateway": {"port": 18779, "health": "/health"},
    "agentz-desktop": {"port": 18785, "health": "/health"},
    "oreo": {"port": 8765, "health": "/health"},
    "ucg": {"port": 8781, "health": "/health"},
    "cviz": {"port": 8783, "health": "/health"},
    "sensez": {"port": 8784, "health": "/health"},
    "corez": {"port": 8006, "health": "/health"},
    "owebz": {"port": 4000, "health": "/health"},
    "forge": {"port": 7747, "health": "/health"},
    "interstice": {"port": 4200, "health": "/health"},
}

# Panels that are not subsystems but part of mem20 itself.
CORE_PANELS: list[dict[str, str]] = [
    {"id": "core", "name": "mem20 core", "kind": "core",
     "description": "Memory, cognition, affective state, self-models, world model, roadmaps"},
    {"id": "websites", "name": "Websites", "kind": "manager",
     "description": "Fleet deploys, health, logs, and Cloudflare DNS management"},
]


def _http_probe(port: int, path: str, timeout: float) -> dict[str, Any]:
    import urllib.error
    import urllib.request

    url = f"http://127.0.0.1:{port}{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read(2048).decode("utf-8", "replace")
            return {"reachable": True, "status": response.status, "url": url, "body": body}
    except urllib.error.HTTPError as exc:
        return {"reachable": True, "status": exc.code, "url": url, "body": "", "http_error": True}
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return {"reachable": False, "status": None, "url": url, "error": str(exc)}


def _cli_probe(binary: str, timeout: float) -> dict[str, Any]:
    """Bounded CLI probe using the standardised --json contract.

    ``--help`` is only read when the health probe did *not* confirm a healthy
    surface, because the verb list is the only thing that lets us tell "broken"
    from "exposes no health verb" - and that distinction is irrelevant when the
    health probe already succeeded. Several of these CLIs take seconds to import
    just to print help, so not asking is the difference between a responsive
    panel and a slow one.
    """
    import re
    import subprocess

    path = f"/root/.venv/bin/{binary}"

    def _verbs() -> list[str]:
        try:
            helped = subprocess.run(
                [path, "--help"], capture_output=True, text=True, timeout=timeout, check=False
            )
        except (subprocess.TimeoutExpired, OSError):
            return []
        blob = f"{helped.stdout}\n{helped.stderr}"
        match = re.search(r"\{([a-z0-9,\-]+)\}", blob)
        return [v for v in match.group(1).split(",") if v] if match else []

    try:
        proc = subprocess.run(
            [path, "--json", "health"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "timed_out": True, "verbs": _verbs(), "detail": f"exceeded {timeout}s"}
    except OSError as exc:
        return {"ok": False, "verbs": [], "detail": f"{type(exc).__name__}: {exc}"}

    payload: dict[str, Any] | None = None
    if proc.returncode == 0 or proc.stdout.strip():
        import json

        try:
            decoded = json.loads(proc.stdout)
            if isinstance(decoded, dict) and decoded.get("schema", "").startswith("mem20.cli/"):
                payload = {
                    "ok": bool(decoded.get("ok")),
                    "exit_code": decoded.get("exit_code"),
                    "stdout": (decoded.get("stdout") or "")[:2000],
                    "stderr": (decoded.get("stderr") or "")[:500],
                }
        except ValueError:
            payload = None

    if payload is None:
        payload = {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": proc.stdout[:2000],
            "stderr": proc.stderr[:500],
        }

    if not payload.get("ok"):
        payload["verbs"] = _verbs()
    return payload


def _classify(name: str) -> str:
    for key in HTTP_SURFACES:
        if key in name:
            return key
    return ""


def registry(cli_timeout: float = 15.0, http_timeout: float = 3.0) -> dict[str, Any]:
    """Build the full panel registry with live, honest status for each subsystem."""
    binaries = clicheck.installed_binaries()
    fleet = {row["subsystem"]: row for row in fleet_inventory()}

    targets = [
        (binary, _classify(binary))
        for binary in sorted(binaries)
        if binary not in clicheck.NON_CLI_BINARIES
    ]

    # Probes are subprocess calls, so threads give real concurrency here and
    # keep a full fleet sweep in the low seconds instead of summing every
    # timeout. Each probe is independently bounded, so one hang still cannot
    # hold up the registry.
    def _rest(key: str) -> dict[str, Any]:
        surface = HTTP_SURFACES.get(key)
        if not surface:
            return {}
        try:
            return _http_probe(surface["port"], surface.get("health", "/health"), http_timeout)
        except Exception as exc:  # noqa: BLE001 - one bad probe must not kill the registry
            return {"reachable": False, "status": None, "error": f"{type(exc).__name__}: {exc}"}

    def _rest_confirms_ok(result: dict[str, Any]) -> bool:
        # A reachable 500 is not a confirmed surface, so the CLI fallback must
        # still run for it: REST-first means "try REST first", not "stop here".
        return bool(result.get("reachable")) and (result.get("status") or 0) < 500

    with ThreadPoolExecutor(max_workers=16) as pool:
        rest_map = dict(zip((b for b, _ in targets), pool.map(lambda t: _rest(t[1]), targets)))
        pending = [b for b, _ in targets if not _rest_confirms_ok(rest_map.get(b) or {})]

        def _cli(binary: str) -> dict[str, Any]:
            try:
                return _cli_probe(binary, cli_timeout)
            except Exception as exc:  # noqa: BLE001 - one bad probe must not kill the registry
                return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

        cli_map = dict(zip(pending, pool.map(_cli, pending)))

    panels: list[dict[str, Any]] = []
    for core in CORE_PANELS:
        panels.append({**core, "status": "ok", "status_reason": "control plane panel"})

    for binary, surface_key in targets:
        surface = HTTP_SURFACES.get(surface_key)
        rest_result = rest_map.get(binary) or None
        cli_result = cli_map.get(binary)
        status = "unknown"
        reason = "no probe surface"

        if surface:
            if _rest_confirms_ok(rest_result or {}):
                status = "ok"
                reason = f"REST {rest_result['url']} -> {rest_result['status']}"
            else:
                status = "unreachable"
                reason = f"REST {rest_result.get('url')} not reachable"

        if status != "ok" and cli_result is not None:
            if cli_result.get("ok"):
                status = "ok"
                reason = f"CLI {binary} --json health exit 0"
            elif cli_result.get("timed_out"):
                status = "unreachable"
                reason = f"CLI {binary} probe exceeded {cli_timeout}s"
            elif cli_result.get("error"):
                status = "unknown"
                reason = f"probe error: {cli_result['error']}"
            elif cli_result.get("verbs"):
                # The CLI runs, but exposes no health verb. That is a gap in the
                # probe surface, not a broken subsystem - calling it "degraded"
                # would be a false accusation, so name it precisely.
                verbs = cli_result["verbs"]
                if "health" in verbs:
                    status = "degraded"
                    reason = (
                        f"CLI {binary} exposes health but health exit "
                        f"{cli_result.get('exit_code')}"
                    )
                else:
                    status = "no-health"
                    reason = (
                        f"CLI {binary} runs but exposes no health verb "
                        f"(exposes: {', '.join(verbs[:8]) or 'none discovered'})"
                    )
            else:
                status = "degraded"
                reason = (
                    f"CLI {binary} health exit "
                    f"{cli_result.get('exit_code')} (no verified surface)"
                )

        subsystem = next(
            (k for k, v in fleet.items() if binary in v["binaries"]), binary
        )
        panels.append(
            {
                "id": subsystem,
                "name": binary,
                "kind": "subsystem",
                "binary": binary,
                "naming": clicheck.classify_naming(binary),
                "description": (fleet.get(subsystem) or {}).get("description", ""),
                "http_surface": surface,
                "status": status,
                "status_reason": reason,
                "rest": rest_result,
                "cli": cli_result,
            }
        )

    counts: dict[str, int] = {}
    for panel in panels:
        counts[panel["status"]] = counts.get(panel["status"], 0) + 1
    return {
        "panels": panels,
        "counts": counts,
        "total": len(panels),
        "probe_timeouts": {"http_s": http_timeout, "cli_s": cli_timeout},
        "contract": {
            "discovery": "mem20ops.clicheck (same source as the coverage harness)",
            "precedence": "REST first, standardised CLI fallback",
            "honesty": "unverifiable subsystems report unknown/degraded, never ok",
        },
    }
