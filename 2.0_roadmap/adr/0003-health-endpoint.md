# ADR-0003: Operational Health Endpoint

- **Status:** Accepted
- **Date:** 2026-08-28
- **Deciders:** mem20 engineering

## Context
The static review recommended a `/health`, `/ready`, `/metrics` endpoint for
production readiness. The MCP server transports over stdio JSON-RPC, so a naive
HTTP listener could block or crash the transport.

## Decision
Add `mcp/health.py` exposing `/health`, `/ready`, `/metrics` via the
standard-library `http.server.ThreadingHTTPServer` running in a **daemon thread**,
so it can never block the stdio loop. Bind failures are **non-fatal** (the MCP
server keeps running). Port is configurable via `MEM20_HEALTH_PORT` (default
8080); `MEM20_HEALTH_DISABLE=1` turns it off.

`server.py` tracks `request_count`/`request_errors` and per-tool
`tool_calls`/`tool_errors`, plus an `event_taxonomy`
(`tool.call`, `tool.success`, `tool.error`). `metrics()` returns these and
`memory_system_available`. `logging` is configured in `run()`.

## Consequences
- Liveness/readiness probes and basic observability are available with zero new
  dependencies (stdlib only).
- Safe under stdio deployment; no production restart risk from the endpoint.
- Trade-off: metrics are in-memory (lost on restart). Step 16's instrumentation
  plan recommends a durable sink (push to a metrics backend) for 2.0.
