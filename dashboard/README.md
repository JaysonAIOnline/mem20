# mem20 dashboard

A small [Vite](https://vitejs.dev) + React web dashboard for **mem20**. It shows
live server status and the contents of the memory store.

## What it shows

- **Status cards** polling the MCP server's operational endpoints via the optional
  bridge: `/health`, `/ready`, `/metrics`.
- **Memory store** listing (recent grounded records).
- **Recall** box to query the store.

## How it connects

The dashboard talks to the **optional HTTP bridge** (`bridge/server.py`), not the
MCP stdio server directly. The bridge proxies `/health`, `/ready`, `/metrics` and
adds `/api/memory` and `/api/recall`.

Default API base: `http://localhost:8000` (override with `VITE_API_BASE`).

## Develop

```bash
# terminal 1: run the mem20 MCP server (provides /health on :8080)
python mcp/mcp_server.py

# terminal 2: run the optional bridge (provides /api/* on :8000)
pip install fastapi uvicorn httpx
python bridge/server.py

# terminal 3: run the dashboard with hot reload
npm install
npm run dev          # http://localhost:5173
```

In dev, `/api` is proxied to `http://localhost:8000` (see `vite.config.js`).

## Build & serve the static site

```bash
npm install
npm run build       # outputs dashboard/dist/

# Serve the built files (any static server works):
npx serve dashboard/dist
# or let the bridge serve them by setting MEM20_BRIDGE_SERVE=dashboard/dist
```

`npm run build` is the only required step for packaging; the resulting `dist/`
is plain static assets.
