# mem20autouez

Native mem20 absorption of AutoUE — Unreal Engine automation over an async
WebSocket connection.

## What it is

A library-level client for talking to a running Unreal Editor via the Remote
Control JSON-over-WebSocket protocol:

- `UEConnection` — async WebSocket client (built on `websockets`) that issues
  commands and resolves them against engine responses, with a message-handler
  broadcast channel.
- `AssetManager` — asset pipeline operations: list, get info, import, export,
  delete, find referencers, bulk rename, validate.
- `BlueprintBuilder` — blueprint generation: create, add property/function/
  component, compile, generate from template.
- `LevelStreamer` — level streaming: load/unload, visibility, streaming
  distance, level bounds.
- `AutoUEConfig` / `DEFAULT_CONFIG` — YAML-backed configuration.

## Install

```bash
python -m pip install -e .
```

## CLI

```bash
mem20autouez --help
mem20autouez serve --host 0.0.0.0 --port 8004
mem20autouez connect --host 127.0.0.1 --port 30010
mem20autouez asset --list --path /Game/Assets
mem20autouez blueprint --create --parent Actor --name BP_Foo
mem20autouez level --list
mem20autouez test
```

## Library use

```python
import asyncio
from mem20autouez import UEConnection, UECommand, AssetManager

async def main():
    conn = UEConnection(host="127.0.0.1", port=30010)
    await conn.connect()
    resp = await conn.execute_console_command("version")
    print(resp.data)
    mgr = AssetManager(conn)
    assets = await mgr.list_assets("/Game/Assets")
    await conn.disconnect()

asyncio.run(main())
```

## Tests

```bash
python -m pytest mem20autouez/tests -v
```