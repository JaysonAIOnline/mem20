# syntax=docker/dockerfile:1
# mem20 MCP server image.
# The canonical runtime (`python mcp/mcp_server.py`) is preserved unchanged:
# it starts an MCP stdio JSON-RPC server plus an HTTP health server on :8080.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MEM20_HEALTH_PORT=8080 \
    MEM20_STORE_PATH=/data

WORKDIR /app

# System deps needed to build some Python wheels (faiss/numpy).
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install runtime deps first (cached layer).
COPY requirements.txt requirements-optional.txt ./
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

ENV PATH="/opt/venv/bin:$PATH"

# Copy the repo (includes the mcp/ directory run as a script).
COPY . .

RUN mkdir -p /data

EXPOSE 8080

# Optional HTTP bridge for the web dashboard (separate from the MCP server).
# Disabled by default; enable by running the bridge instead of/alongside mem20-mcp.
# CMD ["python", "bridge/server.py"]

# Canonical entrypoint (constraint #1: must keep working unchanged).
CMD ["python", "mcp/mcp_server.py"]
