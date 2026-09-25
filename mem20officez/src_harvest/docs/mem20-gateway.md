# Mem20 Gateway Adapter

Claw3D can run against Mem20 by using the bundled adapter in
[`server/mem20-gateway-adapter.js`](../server/mem20-gateway-adapter.js).

This is the current production-ready Mem20 path in this repository.
It is not yet a fully native Studio-side Mem20 provider. Instead, it
uses the runtime seam in Studio while Mem20 is exposed through a
Claw3D-compatible WebSocket adapter.

## Architecture

```text
Browser UI <-> Studio runtime/client <-> Mem20 gateway adapter <-> Mem20 HTTP API
```

The frontend keeps using the Claw3D gateway protocol. The Mem20 adapter
translates that protocol into Mem20 HTTP calls and streams the results
back as gateway events.

## Quick start

### 1. Start Mem20

Start your Mem20 API server. The default expected endpoint is:

```text
http://localhost:8642
```

### 2. Configure environment

Copy `.env.example` to `.env` and set the Mem20 values:

```env
NEXT_PUBLIC_GATEWAY_URL=ws://localhost:18789

MEM20_API_URL=http://localhost:8642
MEM20_API_KEY=
MEM20_ADAPTER_PORT=18789
MEM20_MODEL=mem20
MEM20_AGENT_NAME=Mem20
```

### 3. Start Claw3D and the adapter

In separate terminals:

```bash
npm run mem20-adapter
npm run dev
```

Then open `http://localhost:3000` and connect to:

```text
ws://localhost:18789
```

In the connect screen, select `Mem20 backend`. Claw3D will persist that
selection in Studio settings and show `Mem20` as the active backend once
the adapter hello response is received.

### 4. Optional all-in-one local startup

The repo also includes:

```bash
bash scripts/clawd3d-start.sh
```

That script now resolves the repo root dynamically from the script
location instead of assuming a machine-specific checkout path.

## What this adapter supports

The adapter currently supports the Claw3D surfaces needed for normal
office use:

- Agent listing, creation, update, and deletion
- Session listing, preview, patch, reset, and history lookup
- Chat send, targeted abort, and run wait
- Config get/set/patch shims needed by the Studio UI
- Models and skills status
- Exec approvals surfaces used by the current UI
- Cron list/add/remove/patch/run
- Multi-agent orchestration tools on the Mem20 side

## Mem20 orchestration tools

The main Mem20 agent acts as an orchestrator with these tools:

| Tool | Description |
|---|---|
| `spawn_agent` | Create a specialist sub-agent |
| `delegate_task` | Send work to a specific agent |
| `list_team` | List active agents, names, and roles |
| `configure_agent` | Update agent name, role, instructions, or settings |
| `dismiss_agent` | Remove an agent from the team |
| `read_agent_context` | Read another agent's recent conversation history for coordination |

Sub-agents appear in the office as separate characters and keep their
own conversation state.

## Production-readiness notes

This adapter includes the fixes that blocked the original Mem20 PR:

- `chat.abort` now aborts only the requested `runId` or `sessionKey`
  instead of cancelling every active run
- history clears from `sessions.reset`, `agents.delete`, and
  `dismiss_agent` now persist to disk immediately
- `scripts/clawd3d-start.sh` no longer hardcodes one developer's local path

## ACP status

Mem20 has a real ACP surface and that remains the preferred long-term
integration direction.

This branch does not replace the adapter with ACP yet. The current
production-ready path uses the adapter because it works with the existing
Claw3D gateway contract today and is ready for upstream testing now.

The runtime seam added in Studio is what makes an ACP-backed Mem20
provider feasible as a follow-up without reworking the whole UI again.

## Persistence

Conversation history is stored at:

```text
~/.mem20/clawd3d-history.json
```

It is loaded on startup and updated when conversations change.

## Current limitations

- Mem20 is integrated through the adapter path today, not yet through a
  dedicated native Studio provider implementation
- Config and approvals behavior still matches the current adapter contract,
  not a fully Mem20-native settings model
- This path is intended to get Mem20 working reliably now while the
  broader runtime-provider architecture continues to mature

## When to use demo mode instead

If you only want to see the office boot without installing Mem20 or
mem20 claw plugin, use:

```bash
npm run demo-gateway
npm run dev
```

That starts a bundled mock gateway for a no-framework Claw3D demo.

## Using mem20 claw plugin instead

If you want the mem20 claw plugin path, do not run the Mem20 adapter. Start
mem20 claw plugin and point Claw3D at that gateway instead.
