"""The control plane FastAPI application.

One service that serves the API and the built frontend from a single origin, so
there is no second web server to operate. Every API route is authenticated except
the health probe and the login endpoint.
"""

from __future__ import annotations

import contextlib
import logging
import os
import threading
import time
from collections.abc import AsyncIterator
from typing import Any

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import auth, dreams, websites
from . import registry as registry_mod
from .__init__ import __version__

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
STARTED = time.time()
log = logging.getLogger("mem20controlz")

# A full fleet sweep is bounded but not free, and the UI polls on a timer. Cache
# briefly so a poll never re-pays the whole sweep, and report the cache age so a
# stale panel can never be mistaken for a live one.
REGISTRY_TTL_S = float(os.environ.get("MEM20_CONTROL_REGISTRY_TTL", "45"))
# The CLI audit is slower and changes far less often than a fleet sweep.
COVERAGE_TTL_S = float(os.environ.get("MEM20_CONTROL_COVERAGE_TTL", "600"))
_registry_lock = threading.Lock()
_registry_cache: dict[tuple[float, float], dict[str, Any]] = {}
_registry_sweeping: set[tuple[float, float]] = set()
_coverage_lock = threading.Lock()
# Held in a container so the readers and writers can update it without a
# ``global`` declaration - assigning to a module-level name inside a function
# would otherwise make Python treat it as local and raise UnboundLocalError.
_coverage_state: dict[str, Any] = {"entry": None}


def clear_registry_cache() -> None:
    """Drop cached sweeps. Used by tests and by the next explicit refresh."""
    with _registry_lock:
        _registry_cache.clear()
    with _coverage_lock:
        _coverage_state["entry"] = None


def _sweep(cli_timeout: float, http_timeout: float) -> dict[str, Any]:
    key = (cli_timeout, http_timeout)
    with _registry_lock:
        if key in _registry_sweeping:
            return {}  # another thread is already paying for this sweep
        _registry_sweeping.add(key)
    try:
        payload = registry_mod.registry(cli_timeout=cli_timeout, http_timeout=http_timeout)
        _registry_cache[key] = {"at": time.time(), "payload": payload}
        return payload
    finally:
        with _registry_lock:
            _registry_sweeping.discard(key)


def _registry_cached(cli_timeout: float, http_timeout: float) -> dict[str, Any]:
    """Serve the cached sweep, keeping the UI off the slow path.

    Probing the fleet means spawning ~30 subprocesses, some of which import
    heavy ML stacks; a cold sweep takes seconds, not milliseconds. So the first
    caller pays for it and a background refresher keeps it warm - every
    subsequent request is served from cache in milliseconds.

    The cache key includes the probe timeouts on purpose: a payload probed with
    a 15s CLI budget is not the same evidence as one probed with a 2s budget, so
    serving one for the other would be quietly dishonest. Age and staleness are
    always reported so cached data is never mistaken for a live reading.
    """
    key = (cli_timeout, http_timeout)
    entry = _registry_cache.get(key)
    if entry is not None:
        age = time.time() - entry["at"]
        return {
            **entry["payload"],
            "cached": True,
            "age_s": round(age, 2),
            "stale": age > REGISTRY_TTL_S,
        }

    payload = _sweep(cli_timeout, http_timeout)
    if not payload:  # a concurrent sweep owns it; report that honestly
        return {
            "panels": [],
            "counts": {},
            "total": 0,
            "cached": False,
            "age_s": 0.0,
            "stale": True,
            "sweeping": True,
        }
    return {**payload, "cached": False, "age_s": 0.0, "stale": False}


def _refresh_loop() -> None:
    while True:
        time.sleep(REGISTRY_TTL_S)
        for key in list(_registry_cache):
            _sweep(*key)


@contextlib.asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Warm the registry in the background so the first page load is fast."""

    def warm() -> None:
        try:
            _sweep(15.0, 3.0)
        except Exception as exc:  # noqa: BLE001 - a failed warm-up must not kill startup
            log.warning("registry warm-up failed: %s", exc)
        threading.Thread(target=_refresh_loop, daemon=True).start()
        threading.Thread(target=_coverage_refresh_loop, daemon=True).start()

    threading.Thread(target=warm, daemon=True).start()
    yield

app = FastAPI(
    title="mem20 control plane",
    version=__version__,
    description="Unified control plane for the mem20 fleet, with the Websites manager.",
    lifespan=lambda _app: _lifespan(_app),
)


def _admitted(request: Request) -> dict[str, Any] | None:
    """Who the caller is, or None if nobody. Never raises for anonymous callers."""
    identity = auth.identity_from_headers(request.headers)
    if identity:
        return {"admitted_by": "cloudflare-access", "identity": identity}
    if auth.session_valid(request.cookies.get(auth.COOKIE_NAME)):
        return {"admitted_by": "admin-session", "identity": "admin"}
    return None


def _authenticated(request: Request) -> dict[str, Any]:
    admitted = _admitted(request)
    if admitted is None:
        raise HTTPException(status_code=401, detail="authentication required")
    return admitted


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "mem20-control",
        "version": __version__,
        "uptime_s": round(time.time() - STARTED, 3),
    }


@app.get("/api/auth/status")
def auth_status(request: Request) -> dict[str, Any]:
    """Configuration posture plus whether *this* caller is currently admitted.

    Deliberately unauthenticated: the login screen has to be able to ask what
    the auth setup is before it has a session. It reports posture and a boolean,
    never any secret material.
    """
    posture = auth.auth_status()
    admitted = _admitted(request)
    return {
        **posture,
        "authenticated": admitted is not None,
        "admitted_by": (admitted or {}).get("admitted_by"),
        "identity": (admitted or {}).get("identity"),
    }


@app.post("/api/auth/login")
def login(payload: dict[str, Any] = Body(default_factory=dict)) -> JSONResponse:  # noqa: B008 - FastAPI body dependency idiom
    candidate = str(payload.get("password", ""))
    if not auth.check_password(candidate):
        return JSONResponse(
            {"ok": False, "error": "invalid credentials"},
            status_code=401,
        )
    token = auth.issue_session()
    if not token:
        return JSONResponse(
            {
                "ok": False,
                "error": (
                    "no session secret configured; set MEM20_CONTROL_SECRET in "
                    "/opt/mem20/secrets/.env"
                ),
            },
            status_code=503,
        )
    response = JSONResponse({"ok": True, "admitted_by": "admin-session"})
    response.set_cookie(
        auth.COOKIE_NAME,
        token,
        max_age=auth.SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return response


@app.post("/api/auth/logout", dependencies=[Depends(_authenticated)])
def logout() -> JSONResponse:
    response = JSONResponse({"ok": True})
    response.delete_cookie(auth.COOKIE_NAME, path="/")
    return response


@app.get("/api/registry", dependencies=[Depends(_authenticated)])
def get_registry(
    cli_timeout: float = Query(default=15.0, ge=0.5, le=120.0),
    http_timeout: float = Query(default=3.0, ge=0.2, le=30.0),
) -> dict[str, Any]:
    return _registry_cached(cli_timeout, http_timeout)


@app.get("/api/cli/coverage", dependencies=[Depends(_authenticated)])
def cli_coverage(timeout: int = Query(default=15, ge=1, le=120)) -> dict[str, Any]:
    """CLI contract audit, cached the same way the registry is.

    A full audit spawns a ``--help`` for every installed CLI. Even with those
    probes running concurrently this takes seconds, which is the kind of thing
    that gets killed by a tunnel's request timeout. The audit is read-only and
    changes only when CLIs are installed or removed, so it is cached for a good
    while and refreshed in the background; age and staleness are always
    reported so a cached audit is never mistaken for a fresh one.
    """
    from mem20ops import clicheck

    now = time.time()
    with _coverage_lock:
        entry = _coverage_state["entry"]
        if entry and now - entry["at"] < COVERAGE_TTL_S and entry.get("timeout") == timeout:
            return {**entry["payload"], "cached": True, "age_s": round(now - entry["at"], 2), "stale": False}

    payload = clicheck.audit(timeout=timeout)
    with _coverage_lock:
        _coverage_state["entry"] = {"at": time.time(), "payload": payload, "timeout": timeout}
    return {**payload, "cached": False, "age_s": 0.0, "stale": False}


def _coverage_refresh_loop() -> None:
    """Keep a populated coverage cache warm.

    Only refreshes once something has actually asked for the audit, so a control
    plane nobody is browsing does not spend CPU re-auditing every CLI.
    """
    while True:
        time.sleep(COVERAGE_TTL_S)
        with _coverage_lock:
            entry = _coverage_state["entry"]
        if not entry:
            continue
        try:
            from mem20ops import clicheck

            payload = clicheck.audit(timeout=entry.get("timeout") or 15)
        except Exception as exc:  # noqa: BLE001 - a failed refresh keeps the old audit
            log.warning("cli coverage refresh failed: %s", exc)
            continue
        with _coverage_lock:
            _coverage_state["entry"] = {
                "at": time.time(),
                "payload": payload,
                "timeout": entry.get("timeout"),
            }


@app.get("/api/websites/manifest", dependencies=[Depends(_authenticated)])
def websites_manifest() -> dict[str, Any]:
    return websites.manifest()


@app.get("/api/websites/sites", dependencies=[Depends(_authenticated)])
def websites_sites() -> dict[str, Any]:
    return websites.site_inventory()


@app.get("/api/websites/dns", dependencies=[Depends(_authenticated)])
def websites_dns(
    zone: str = Query(default=websites.DEFAULT_ZONE),
    pattern: str | None = Query(default=None),
) -> dict[str, Any]:
    return websites.dns_records(zone=zone, pattern=pattern)


@app.post("/api/websites/dns", dependencies=[Depends(_authenticated)])
def websites_dns_create(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008 - FastAPI body dependency idiom
    missing = [f for f in ("zone", "type", "name", "content") if not payload.get(f)]
    if missing:
        raise HTTPException(status_code=422, detail=f"missing fields: {', '.join(missing)}")
    return websites.dns_create(
        zone=str(payload["zone"]),
        record_type=str(payload["type"]),
        name=str(payload["name"]),
        content=str(payload["content"]),
        proxied=bool(payload.get("proxied", False)),
        ttl=int(payload.get("ttl", 1)),
    )


@app.delete("/api/websites/dns/{record_id}", dependencies=[Depends(_authenticated)])
def websites_dns_delete(
    record_id: str, zone: str = Query(default=websites.DEFAULT_ZONE)
) -> dict[str, Any]:
    return websites.dns_delete(zone=zone, record_id=record_id)


@app.get("/api/websites/health", dependencies=[Depends(_authenticated)])
def websites_health() -> dict[str, Any]:
    return websites.fleet_health()


@app.get("/api/websites/logs", dependencies=[Depends(_authenticated)])
def websites_logs(
    unit: str = Query(default="mcp-server.service"),
    lines: int = Query(default=100, ge=1, le=5000),
) -> dict[str, Any]:
    return websites.logs(unit=unit, lines=lines)


@app.get("/api/websites/pages", dependencies=[Depends(_authenticated)])
def websites_pages() -> dict[str, Any]:
    return websites.pages()


# --- dreams ------------------------------------------------------------------
#
# Every route below sits behind the same admin gate as the rest of the data API.
# Promotion and run are writes that cost money or move bytes, so they are named,
# explicit POSTs and never triggered by a read.


def _dream_error(exc: dreams.DreamError) -> HTTPException:
    """A refusal becomes a 409 with the engine's own words intact.

    409 rather than 400: nothing is malformed, the request was understood and the
    estate declined it. Flattening these into a generic error is how a hollow
    lineage ends up looking like a server fault.
    """
    return HTTPException(status_code=409, detail=str(exc))


@app.get("/api/dreams/manifest", dependencies=[Depends(_authenticated)])
def dreams_manifest() -> dict[str, Any]:
    return dreams.manifest()


@app.get("/api/dreams", dependencies=[Depends(_authenticated)])
def dreams_list(
    kind: str = Query(default=""),
    include_hollow: bool = Query(default=True),
    only_unpromoted: bool = Query(default=False),
    limit: int = Query(default=0, ge=0, le=500),
) -> dict[str, Any]:
    return dreams.dream_list(
        kind=kind,
        include_hollow=include_hollow,
        only_unpromoted=only_unpromoted,
        limit=limit,
    )


@app.get("/api/dreams/idle-stats", dependencies=[Depends(_authenticated)])
def dreams_idle_stats() -> dict[str, Any]:
    return dreams.dream_idle_stats()


@app.get("/api/dreams/hollow", dependencies=[Depends(_authenticated)])
def dreams_hollow() -> dict[str, Any]:
    return dreams.hollow_report()


@app.get("/api/dreams/runs", dependencies=[Depends(_authenticated)])
def dreams_runs() -> dict[str, Any]:
    return dreams.list_runs()


@app.get("/api/dreams/runs/{job_id}", dependencies=[Depends(_authenticated)])
def dreams_run_status(job_id: str) -> dict[str, Any]:
    try:
        return dreams.run_status(job_id)
    except dreams.DreamError as exc:
        raise _dream_error(exc) from exc


@app.post("/api/dreams/runs", dependencies=[Depends(_authenticated)])
def dreams_run_start(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:  # noqa: B008 - FastAPI body dependency idiom
    """Start a run in the background. Returns a job to poll, never the run itself."""
    try:
        return dreams.start_run(
            str(payload.get("dream_id", "")),
            payload.get("iterations", dreams.DEFAULT_RUN_ITERATIONS),
        )
    except dreams.DreamError as exc:
        raise _dream_error(exc) from exc


@app.get("/api/dreams/{dream_id}", dependencies=[Depends(_authenticated)])
def dreams_detail(dream_id: str) -> dict[str, Any]:
    try:
        return dreams.dream_detail(dream_id)
    except dreams.DreamError as exc:
        raise _dream_error(exc) from exc


@app.get("/api/dreams/{dream_id}/chain", dependencies=[Depends(_authenticated)])
def dreams_chain(dream_id: str) -> dict[str, Any]:
    try:
        return dreams.dream_chain(dream_id)
    except dreams.DreamError as exc:
        raise _dream_error(exc) from exc


@app.post("/api/dreams/{dream_id}/verify", dependencies=[Depends(_authenticated)])
def dreams_verify(dream_id: str) -> dict[str, Any]:
    """Re-prove the chain. A POST because proving every node is real work, not a read."""
    try:
        return dreams.dream_verify(dream_id)
    except dreams.DreamError as exc:
        raise _dream_error(exc) from exc


@app.post("/api/dreams/{dream_id}/promote", dependencies=[Depends(_authenticated)])
def dreams_promote(dream_id: str, payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:  # noqa: B008 - FastAPI body dependency idiom
    """Promote a dream to a portable pack, unless the engine refuses and says why."""
    try:
        result = dreams.dream_promote(dream_id, force=bool(payload.get("force", False)))
    except dreams.DreamError as exc:
        raise _dream_error(exc) from exc
    # A refusal is a 200 with promoted:false, not an exception: the gate worked,
    # and the caller needs the engine's reason, which is the whole point.
    return result


@app.post("/api/dreams", dependencies=[Depends(_authenticated)])
def dreams_create(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008 - FastAPI body dependency idiom
    """Create a dream. Costs nothing: no model is called until it is run."""
    missing = [f for f in ("seed",) if not str(payload.get(f, "")).strip()]
    if missing:
        raise HTTPException(status_code=422, detail=f"missing fields: {', '.join(missing)}")
    try:
        return dreams.dream_new(
            str(payload["seed"]),
            foundation=str(payload.get("foundation", "")),
            kind=str(payload.get("kind", "active")),
        )
    except dreams.DreamError as exc:
        raise _dream_error(exc) from exc


if os.path.isdir(STATIC_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        # An unmatched /api/* path must stay a 404. Falling through to the SPA
        # here would hand a mistyped API route a 200 + HTML, so a broken client
        # would look like a working one.
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="unknown API route")
        candidate = os.path.join(STATIC_DIR, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))

else:

    @app.get("/", include_in_schema=False)
    def missing_frontend() -> JSONResponse:
        return JSONResponse(
            {
                "error": "frontend not built",
                "expected": STATIC_DIR,
                "hint": "npm install && npm run build in mem20controlz/mem20controlz/web",
            },
            status_code=503,
        )
