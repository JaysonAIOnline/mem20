#!/usr/bin/env python3
"""mem20 optional HTTP bridge for the web dashboard.

This is **separate** from the MCP stdio server (`mcp/mcp_server.py`) and must
never affect it. The MCP server keeps running exactly as before on stdio + :8080.

The bridge exposes a small, safe read-oriented HTTP/JSON surface so the
`dashboard/` web app (or any HTTP client) can:

  * proxy the MCP server's operational endpoints  GET /api/health /api/ready /api/metrics
  * list the memory store contents                   GET  /api/memory
  * run a recall query                               POST /api/recall
  * overall status summary                           GET  /api/status

It is OPTIONAL and off by default. Run it with:

    pip install "fastapi" "uvicorn" "httpx"
    python bridge/server.py                 # listens on :8000

Environment:
    MEM20_BRIDGE_HOST   host the MCP health server listens on   (default 127.0.0.1)
    MEM20_BRIDGE_PORT   port the MCP health server listens on   (default 8080)
    MEM20_BRIDGE_LISTEN address:port for THIS bridge           (default 0.0.0.0:8000)
    MEM20_BRIDGE_SERVE  path to dashboard `dist/` to also serve (optional)
"""
import os
import sys
from pathlib import Path

# Make the repo root importable so `import memory` resolves to the engine shim,
# exactly like the MCP server does.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx

MEM20_HOST = os.environ.get("MEM20_BRIDGE_HOST", "127.0.0.1")
MEM20_PORT = int(os.environ.get("MEM20_BRIDGE_PORT", "8080"))
LISTEN = os.environ.get("MEM20_BRIDGE_LISTEN", "0.0.0.0:8000")

app = FastAPI(title="mem20 bridge", version="2.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_client = httpx.AsyncClient(base_url=f"http://{MEM20_HOST}:{MEM20_PORT}", timeout=5.0)


async def _proxy(path: str):
    try:
        r = await _client.get(path)
        try:
            return JSONResponse(r.json(), status_code=r.status_code)
        except Exception:
            return JSONResponse({"raw": r.text}, status_code=r.status_code)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"mem20 MCP server unreachable: {e}")


@app.get("/api/health")
async def health():
    return await _proxy("/health")


@app.get("/api/ready")
async def ready():
    return await _proxy("/ready")


@app.get("/api/metrics")
async def metrics():
    return await _proxy("/metrics")


@app.get("/api/status")
async def status():
    try:
        r = await _client.get("/health")
        mcp_health = r.json()
    except httpx.HTTPError as e:
        mcp_health = {"status": "unreachable", "error": str(e)}
    # Engine availability is probed by importing the engine shim.
    engine_ok = False
    try:
        import memory  # noqa: F401
        engine_ok = True
    except Exception:
        engine_ok = False
    return {
        "bridge": "ok",
        "mcp": mcp_health,
        "engine_available": engine_ok,
    }


@app.get("/api/memory")
async def list_memory(limit: int = Query(100, ge=1, le=1000)):
    """List recent grounded memory records (structured)."""
    try:
        import memory
        recs = memory.recall(k=limit)
        return {"count": len(recs), "records": recs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/recall")
async def recall(payload: dict):
    """Recall by topic/tags. Body: {"query": str, "tags": [str], "k": int}."""
    query = (payload or {}).get("query")
    tags = (payload or {}).get("tags") or None
    k = int((payload or {}).get("k", 5))
    try:
        import memory
        recs = memory.recall(topic=query, tags=tags, k=k)
        return {"count": len(recs), "records": recs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
async def index():
    return {
        "service": "mem20-bridge",
        "note": "Optional HTTP surface for the web dashboard. The MCP server is unaffected.",
        "endpoints": [
            "/api/health", "/api/ready", "/api/metrics",
            "/api/status", "/api/memory", "/api/recall",
        ],
    }


def main() -> None:
    import uvicorn
    host, _, port = LISTEN.partition(":")
    port = int(port or "8000")
    uvicorn.run(app, host=host or "0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
