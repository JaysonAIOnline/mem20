# opencode-gui — 20-step AI-executable roadmap

**Goal:** a modern graphical client for interacting with opencode, built on opencode's own
server and SDK rather than as a new agent runtime.

**Status:** approved to build. Nothing here is built yet.

---

## Ground truth this roadmap is built on

Measured on this box on 2026-10-03, not assumed:

| Fact | Value |
|---|---|
| opencode binary | 1.18.34 at `/root/.opencode/bin/opencode` |
| SDK | `@opencode-ai/sdk` 1.18.18 at `/root/.opencode/node_modules/@opencode-ai/sdk` |
| Server surfaces already shipped | `opencode serve` (headless), `opencode web` (built-in web UI), `opencode attach <url>`, `opencode acp` (Agent Client Protocol) |
| HTTP surface | ~170 endpoints across 36 client groups |
| SDK entry points | `.`, `./client`, `./server`, `./v2`, `./v2/client`, `./v2/server`, `./v2/types` |
| Event transport | server-sent events (`/event`, `/api/event`, `/session/{id}/event`, `/global/event`) |
| Notable groups | `session`, `part`, `permission`, `question`, `pty`, `vcs`, `provider`, `mcp`, `skill`, `agent`, `lsp`, `formatter`, `worktree`, `sync`, `tui`, `model`, `find`, `file`, `fs`, `command`, `config`, `project`, `workspace` |

**Consequence for the design:** opencode already has a server, a transport and a thin web
UI. This roadmap builds a *client*, not a runtime. Anything that re-implements session
management, provider auth or event streaming is out of scope by construction.

**API groups worth knowing by heart before starting:**
`/session`, `/session/{id}/message`, `/session/{id}/prompt_async`, `/session/{id}/abort`,
`/session/{id}/fork`, `/session/{id}/children`, `/session/{id}/diff`, `/session/{id}/todo`,
`/session/{id}/permissions/{id}`, `/permission/{requestID}/reply`, `/question/{requestID}/reply`,
`/pty`, `/pty/{id}/connect-token`, `/vcs/status`, `/vcs/diff`, `/vcs/apply`, `/file/status`,
`/find/symbol`, `/provider`, `/provider/{id}/oauth/authorize`, `/mcp`, `/skill`, `/lsp`,
`/event`.

---

## Requirements traced from your own session history

Mined with `mem20ocaskz` from opencode's session database (4,515 user prompts, 163
sessions). Full traceable index: `opencode-feature-asks.md` in this directory.

| Ask (verbatim) | Date | Roadmap step |
|---|---|---|
| "mem20 and all subsystems should have a webfrontend that allows full control of that subsystem via human hands" | 2026-09-24 | 19 |
| "the desktop client needs to retain the chat abilities as well" | 2026-09-11 | 9, 18 |
| "the kanban frontend should really live inside the mem20agentz frontend as a tab just like it did for hermes" | 2026-09-11 | 8 |
| "the hermes dashboard is a fully functional framework, lots of pages and tabs and settings" | 2026-09-11 | 4, 18 |
| "you dont all stay in sync" (desktop client / gateway / office / CLI) | 2026-09-08 | 17 |
| "can opencode use subagents so the agent doesnt get so flustered" | 2026-09-23 | 16 |
| "does opencode have tts and stt" | 2026-09-20 | 16 |
| "a dropdown showing only the models that can use the frontend, and the list has to auto populate as I add new api keys daily" | 2026-08-30 | 15 |
| "answer the question then wait for instructions" | 2026-09-08 | 9 |
| "i read 1 word and the whole screen's gone" | 2026-09-08 | 9, 18 |
| "each contact should have their own chat history" | 2026-08-30 | 8 |
| "first off the desktop icon doesnt do anything" | 2026-09-11 | 18 |
| "i want a rollback on failed promotion" | 2026-09-27 | 11 |

---

## Kanban operating rules

**Columns:** `Backlog → Ready → In Progress → Review → Done`, plus `Blocked`.

**WIP limit: 1.** One step in `In Progress` across the whole board. An agent that wants to
start a second step finishes or parks the first. This is the rule that keeps an AI from
quietly leaving five things half-done.

**Rules that make this AI-executable:**

1. **One step, one agent, one session.** Never hold two steps at once.
2. **No step starts before its dependencies are `Done`.** The dependency column is not advisory.
3. **Every exit criterion is a command that exits 0.** "It looks right" is not an exit criterion.
4. **A criterion that cannot be automated does not go in this roadmap.** If it matters, it
   becomes a documented manual gate in step 19 instead of a fake automated one.
5. **Prove the defect before the fix.** For any bug found in a step, write the failing
   reproduction first, then fix, then re-run the same reproduction.
6. **Never remove a feature to make a step pass.** A step that cannot be completed without
   dropping something is `Blocked`, not done.
7. **Re-derive every headline number by execution** before reporting a step complete.
8. **No mock data anywhere in the shipped client.** Every surface reads the live server.
9. **Bounded tests only.** No unbounded loops, no `fail_for=None`, every test terminates.
10. **Never claim a step `Done` on self-report.** Paste the real command output into the PR
    description or the step stays `Review`.

---

## Lane A — Contract (no UI until the contract is frozen)

Steps 0–3 exist because opencode's API is large and partly experimental. Building UI against
an unfrozen surface produces rework, not speed.

### Step 0 — Ground the substrate
**Goal:** turn the assumptions in the table above into generated, checkable facts.

- **Deliverables:** a script that resolves the opencode binary version, the SDK version and
  the SDK's exported entry points, and dumps every endpoint URL and client group to
  `contract/sdk-surface.json`.
- **Depends on:** nothing.
- **Exit criterion:** `python tools/ground_substrate.py --out contract/sdk-surface.json` exits 0,
  reports version 1.18.x, and the emitted JSON contains at least 150 endpoint URLs and at
  least 30 client groups. Re-running it produces a byte-identical file.
- **Notes:** derive the endpoint list from the SDK's generated `sdk.gen.js`, not by scraping
  documentation.

### Step 1 — Freeze the API contract
**Goal:** one pinned, versioned description of what this client may call.

- **Deliverables:** `contract/opencode-contract.json` (generated, not hand-written),
  `contract/SDK_VERSION` pinning `1.18.18`, and `contract/COMPAT.md` stating which groups are
  used, which are ignored, and which are marked experimental (`/experimental/*`, `/sync/*`,
  `/tui/*` are experimental — use at your own risk and isolate them behind one module).
- **Depends on:** 0.
- **Exit criterion:** a contract test fails when the installed SDK version differs from
  `contract/SDK_VERSION`: `pytest contract/test_contract.py -q` exits 0 when they match and
  non-zero when the pin is deliberately bumped in a test fixture.
- **Notes:** the failing-then-passing behaviour must be demonstrated, not assumed.

### Step 2 — Decide transport and SDK surface
**Goal:** settle v1 vs v2 SDK, and SSE vs polling vs WebSocket, with evidence.

- **Deliverables:** `docs/DECISION-transport.md` recording the choice, the alternatives, and
  the measured evidence; one thin spike that streams a real session event stream.
- **Depends on:** 1.
- **Exit criterion:** the spike receives at least 20 real events from a live `opencode serve`
  in under 30 seconds, with zero dropped or reordered events, and the decision doc cites that
  measurement. If SSE is chosen, the doc must record reconnect behaviour and whether
  `Last-Event-ID` replay works.
- **Notes:** this estate already found that opencode's own `opencode db` CLI silently drops
  rows. Apply the same distrust here: measure the event stream, do not trust a doc claim.

### Step 3 — Security and network posture
**Goal:** fail-closed on exposure, decided before a single port is opened.

- **Deliverables:** `docs/DECISION-security.md` covering bind address, authentication,
  CORS allowlist, and the secret path (`/opt/mem20/secrets/.env` only); a config module that
  refuses to start when a required secret is absent.
- **Depends on:** 1.
- **Exit criterion:** with no auth configured the server refuses to bind to anything but
  `127.0.0.1` and exits non-zero with a named error; with auth configured it requires the
  credential on every request, proven by a test that gets 401 without it and 200 with it.
- **Notes:** surface the security trade-off and get an explicit decision. Do not default
  silently to exposure.

---

## Lane B — Spine

### Step 4 — Repo and design system
**Goal:** the scaffold every later step builds inside.

- **Deliverables:** the client repo with strict TypeScript, a component library, a token
  set (colour, type, spacing), and a dev command that runs the app against a live server.
- **Depends on:** 2.
- **Exit criterion:** `npm run typecheck` and `npm run lint` exit 0; the dev server boots and
  renders a shell that shows the connected server's `/api/health` result; a story renders
  every token.
- **Notes:** the 2026-09-11 complaint — *"isnt even worth calling code"*, *"doesnt even have 1
  adjustable setting and no tabs or pages"* — is aimed at a UI with no structure. Ship the
  navigation shell and theme controls in this step, not later.

### Step 5 — Process broker
**Goal:** exactly one owner of the opencode process.

- **Deliverables:** a service that starts, stops, restarts and health-checks `opencode
  serve`, owns its log, and is the only thing in the system that spawns opencode.
- **Depends on:** 3, 4. Step 4 for the repo it lives in, and Step 3 because the
  security posture is what the broker binds.
- **Exit criterion:** with the broker running, killing opencode brings it back automatically
  within 10 seconds and `/api/health` returns healthy again; a test asserts exactly one
  opencode process exists after 20 rapid refresh requests.
- **Notes:** on this estate a long-lived server must be a systemd unit — enabled, active,
  `MainPID` with `PPID=1`, one listener, no orphan. Verify with `systemctl restart` before
  calling this done.

### Step 6 — Typed client layer
**Goal:** no hand-written `fetch` anywhere in the app.

- **Deliverables:** a generated, typed client for every endpoint the contract allows, plus
  error and retry handling, generated from `contract/opencode-contract.json`.
- **Depends on:** 1, 5.
- **Exit criterion:** `grep -rn "fetch(" src/` returns no call sites outside the generated
  client; every contract endpoint has a typed function or an explicit documented omission;
  a contract test fails if a used endpoint disappears from the contract.
- **Notes:** a used-but-undocumented endpoint is a defect, not a shortcut.

### Step 7 — Event stream
**Goal:** live updates without polling and without losing events.

- **Deliverables:** an SSE subscription manager with reconnect, backoff, and a visible
  connection state in the UI.
- **Depends on:** 6.
- **Exit criterion:** starting a real session in the UI updates the view with no polling; the
  server is killed and restarted and the client reconnects and resyncs automatically; a test
  asserts no event is applied out of order and that duplicate events are idempotent.
- **Notes:** surface degraded state honestly. "Reconnecting" must be visible, never a silent
  stale view.

---

## Lane C — Core chat

### Step 8 — Sessions and project scope
**Goal:** navigate, create, fork and scope sessions per project directory.

- **Deliverables:** session list with search, create, rename, fork, delete, archive; a project
  and directory picker; child-session tree (`/session/{id}/children`).
- **Depends on:** 7.
- **Exit criterion:** create, fork and rename a real session and observe each reflected in a
  fresh `opencode session list`; switching directory changes the scoped session set; a session
  with children shows the tree.
- **Notes:** cites *"the kanban frontend should really live inside the mem20agentz frontend as
  a tab"* — project scoping is the tab/panel boundary, so get the scope model right here.

### Step 9 — Streaming message and part renderer
**Goal:** render a live turn correctly and readably.

- **Deliverables:** renderers for `text`, `reasoning`, `tool` calls with live state, `patch`,
  and file parts; copy, collapse and re-run affordances.
- **Depends on:** 8.
- **Exit criterion:** a real streamed turn renders every part type with no console errors; tool
  calls show pending/running/complete/error distinctly; the view stays scrolled to the newest
  content while streaming and does not jump when the user scrolls up.
- **Notes:** directly answers *"answer the question then wait for instructions"* and *"i read 1
  word and the whole screen's gone"* — collapse streaming noise by default, answer first, and
  never let the viewport move out from under the reader.

### Step 10 — Permissions and questions
**Goal:** make the two TUI-blocking interaction types first-class in a GUI.

- **Deliverables:** live permission requests (`/permission/{requestID}/reply`) and questions
  (`/question/{requestID}/reply`, `/reject`) surfaced as blocking, queueing UI with a keyboard
  and mouse path.
- **Depends on:** 9.
- **Exit criterion:** trigger a real permission request and a real question from the server and
  answer both from the GUI; the reply is visible in the resulting session transcript; a request
  that arrives while another is pending is queued, not dropped.
- **Notes:** this is the single most important step for feeling like a real client. A GUI that
  cannot answer a permission prompt is a toy.

### Step 11 — Interrupt, revert, undo, context meter
**Goal:** the recovery controls a TUI user expects.

- **Deliverables:** abort a running turn, revert to a prior point, unrevert, per-session
  token and cost meter (`/session/{id}/context`), todo display (`/session/{id}/todo`).
- **Depends on:** 9.
- **Exit criterion:** abort genuinely stops generation; revert then unrevert returns the session
  to the exact prior state, verified by comparing message ids before and after; the context
  meter matches the server's reported numbers.
- **Notes:** cites *"i want a rollback on failed promotion"* — revert is the same muscle.

### Step 12 — Files, search, symbols
**Goal:** navigate the codebase from inside the client.

- **Deliverables:** file tree for the scoped directory, file content viewer, changed-files
  status (`/file/status`), full-text search (`/find`), symbol search (`/find/symbol`).
- **Depends on:** 8.
- **Exit criterion:** open, edit-preview and search real files in the scoped project; symbol
  search returns a correct hit set; the tree respects the active project scope and cannot
  escape it.

---

## Lane D — Power surface

### Step 13 — Diff and VCS review
**Goal:** review and apply changes without leaving the client.

- **Deliverables:** per-session diff view, working-tree diff (`/vcs/diff`), status
  (`/vcs/status`), staged apply (`/vcs/apply`).
- **Depends on:** 12.
- **Exit criterion:** a real change made in a session appears in the diff view with correct
  additions and deletions; applying through the UI produces the same working-tree state as
  applying from a terminal, verified by `git status --porcelain` output comparison.
- **Notes:** read-only by default. An apply action needs a confirmation and must never be the
  default button.

### Step 14 — Embedded terminal
**Goal:** a real PTY in the client, for the things a GUI should not reimplement.

- **Deliverables:** terminal view backed by `/pty` and `/pty/{id}/connect-token`, shell picker
  from `/pty/shells`.
- **Depends on:** 6.
- **Exit criterion:** a real interactive shell runs in the embedded terminal, survives a client
  reload by reconnecting, and correctly reports a non-UTF-8 or high-throughput stream without
  corrupting state.
- **Notes:** deliberately late. A terminal can mask a broken core; build chat first.

### Step 15 — Models, providers, auth
**Goal:** manage credentials and pick models without editing config files.

- **Deliverables:** provider list, credential health, the full OAuth flow
  (`/provider/{id}/oauth/authorize`, `/oauth/callback`), and a model picker.
- **Depends on:** 8.
- **Exit criterion:** complete a real OAuth authorisation end to end and confirm the new
  credential is usable by an actual model call; a deliberately broken credential is shown as
  failing with the reason, not as silently absent.
- **Notes:** cites *"a dropdown showing only the models that can use the frontend, and the list
  has to auto populate as I add new api keys daily"* — the picker must derive itself from live
  provider state, never a hard-coded list. Never render secret values; mask them.

### Step 16 — MCP, skills, agents, commands, LSP
**Goal:** the extension and tooling surface.

- **Deliverables:** MCP server list with connect/disconnect and auth (`/mcp`), skills (`/skill`),
  agents (`/agent`), commands (`/command`), LSP and formatter status.
- **Depends on:** 8.
- **Exit criterion:** connect and disconnect a real MCP server and see the tool list change;
  switching agent changes the agent used for the next turn, verified in the transcript; a
  configured LSP shows as attached with its diagnostics.
- **Notes:** cites *"can opencode use subagents so the agent doesnt get so flustered"* and the
  TTS/STT thread — an agent or plugin set configured here is how voice and subagent work get a
  GUI surface rather than only a config file.

---

## Lane E — Ship

### Step 17 — Multi-workspace, worktrees, background sessions
**Goal:** many projects and many agents at once, coherently.

- **Deliverables:** workspace switcher, worktree management (`/experimental/worktree`,
  `/worktree/reset`), background session awareness (`/experimental/session/{id}/background`),
  and a consistent view of state across every surface.
- **Depends on:** 8, 16.
- **Exit criterion:** two workspaces with live sessions can be switched between without losing
  state; a worktree created here appears in a terminal `git worktree list`; a background
  session's completion is visible in the UI without a manual refresh.
- **Notes:** cites *"you dont all stay in sync"* — the acceptance test is that the same fact
  shown on two surfaces is never contradictory.

### Step 18 — Desktop packaging, service, accessibility, performance
**Goal:** installable, reachable, and usable by a human for hours.

- **Deliverables:** desktop shell packaging decision made and executed; a systemd unit; a
  desktop launcher; keyboard navigation throughout; accessible names, focus order and contrast
  checks; a measured performance budget.
- **Depends on:** 17.
- **Exit criterion:** `systemctl restart` brings the service back with `MainPID` `PPID=1` and
  exactly one listener; the launcher starts the client with one action; a full keyboard-only
  pass can reach and operate every primary control; a long session (100+ messages) stays
  responsive under the stated budget, measured and reported.
- **Notes:** cites *"first off the desktop icon doesnt do anything"* — an icon that does nothing
  is a shipped defect. Verify the launcher actually launches.

### Step 19 — Test suite, dogfood QA, release gate
**Goal:** an honest release, with the gaps written down.

- **Deliverables:** full automated suite; a dogfood pass driving the real client through every
  step above; a written **known-gaps** document listing what is not finished, what is untested,
  and what is out of scope.
- **Depends on:** 18.
- **Exit criterion:** the entire suite passes from a clean checkout; the dogfood pass exercises
  every one of the 20 steps against a live server with real sessions; the known-gaps document
  exists and every entry in it is reproducible.
- **Notes:** a partial pass presented as a clean one is worse than a documented failure. If
  something is a mock, say so in that document. Also the step that satisfies *"full control of
  that subsystem via human hands"* — this is where the client is judged against the whole
  roadmap, not just its own tests.

---

## Dependency spine

```
0 → 1 → 2 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11
                            │         └→ 12 → 13
                            ├→ 14
                            ├→ 15
                            └→ 16 → 17 → 18 → 19
3 (security) gates 5 onward
```

Steps 12–16 may run in any order once 8 is `Done`, but only one at a time.

---

## What this roadmap deliberately does not do

- **No new agent runtime.** opencode already is one.
- **No replacement for the built-in `opencode web`.** That stays as the minimal fallback; this
  is the modern client. Step 19 should still record honestly whether it is better.
- **No secret storage.** Keys live in `/opt/mem20/secrets/.env` and are read, never copied.
- **No mock or fixture mode in the shipped client.** Every surface is live.
- **No removal of an existing capability** to make a step pass.

---

## Provenance

- Endpoint and SDK facts: `/opt/mem20/mem20ocaskz` step 0 output, opencode 1.18.34,
  SDK 1.18.18, measured 2026-10-03.
- Requirement quotes: `opencode-feature-asks.md`, mined from opencode's session database with
  `mem20ocaskz` (`python -m mem20ocaskz index`). Every quote carries a session id and date.
- Regenerate the contract and the requirement index rather than editing them by hand.