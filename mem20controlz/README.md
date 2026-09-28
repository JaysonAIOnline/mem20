# mem20controlz

Unified control plane for the mem20 fleet: per-subsystem panels (REST first,
standardised CLI fallback), the Websites manager for DNS, site inventory, systemd
health, journals and Cloudflare Pages, and the **Dreams manager** for reviewing
dreams and keeping the ones worth keeping.

One FastAPI process serves both the API and the built frontend from a single
origin, so there is no second web server to operate.

## Run it

The service is managed by systemd on this host:

```sh
systemctl status mem20controlz          # 127.0.0.1:8890
systemctl restart mem20controlz
curl -s http://127.0.0.1:8890/api/health
```

To run it in the foreground instead:

```sh
/root/.venv/bin/python -m mem20controlz --host 127.0.0.1 --port 8890
```

`python -m mem20controlz --describe` prints the Websites manager manifest.

## Authentication

Two independent layers, either of which admits a request:

1. **Cloudflare Access** — a verified identity header, trusted only when
   `CONTROL_TRUST_CF_ACCESS` is set. It is off by default, because a client can
   forge that header when the service is not actually behind Access.
2. **Admin password** — a constant-time check that mints an HMAC-signed session
   cookie valid for 12 hours.

Both read from `/opt/mem20/secrets/.env` (or the environment):

| Key | Purpose |
| --- | --- |
| `MEM20_CONTROL_PASSWORD` | admin password |
| `MEM20_CONTROL_SECRET` | session signing secret |
| `CONTROL_TRUST_CF_ACCESS` | set to `1` only when behind Cloudflare Access |

**Failing closed is deliberate.** With no password configured nothing can log
in, and with no signing secret `POST /api/auth/login` returns `503` rather than
handing out an unsigned session. `/api/health` and `/api/auth/status` stay open
so a load balancer can probe the service and the login screen can ask what the
auth setup is.

## Status honesty

The registry never reports a panel as `ok` unless a verified surface answered.

| Status | Meaning |
| --- | --- |
| `ok` | REST or CLI probe confirmed the surface |
| `degraded` | probe reached it and it failed the contract |
| `unreachable` | probe could not reach it at all |
| `no-health` | the CLI runs but exposes no `health` verb — a probe gap, not a fault |
| `unknown` | nothing could be confirmed |

`no-health` exists so that a working CLI without a health verb is not reported
as broken. A unit that does not exist is reported as `not-found`, not
`inactive`, because "inactive" would claim a service had started and failed.

Every registry response carries `cached`, `age_s` and `stale`. A full sweep
spawns ~30 subprocesses and takes seconds, so it is cached and refreshed in the
background; the age is always reported so cached data is never mistaken for a
live reading. The cache key includes the probe timeouts, because evidence
gathered with a 15s budget is not the same evidence as a 2s budget.

## API

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/api/health` | open |
| GET | `/api/auth/status` | open; reports posture + whether this caller is admitted |
| POST | `/api/auth/login` | `{"password": "..."}` |
| POST | `/api/auth/logout` | |
| GET | `/api/registry` | cached fleet panels |
| GET | `/api/cli/coverage` | CLI contract audit (slow: runs a full audit) |
| GET | `/api/websites/manifest` | |
| GET | `/api/websites/sites` | |
| GET | `/api/websites/dns` | `?zone=&pattern=` |
| POST | `/api/websites/dns` | `{"zone","type","name","content","proxied","ttl"}` |
| DELETE | `/api/websites/dns/{id}` | `?zone=` |
| GET | `/api/websites/health` | systemd unit health |
| GET | `/api/websites/logs` | `?unit=&lines=` (1–5000) |
| GET | `/api/websites/pages` | Cloudflare Pages projects |
| GET | `/api/dreams/manifest` | what the Dreams manager can do |
| GET | `/api/dreams` | `?kind=&include_hollow=&only_unpromoted=&limit=` |
| GET | `/api/dreams/idle-stats` | idle inventory + who holds the run lock |
| GET | `/api/dreams/hollow` | read-only census of failed-call lineages |
| GET | `/api/dreams/runs` | background run jobs |
| GET | `/api/dreams/runs/{job_id}` | one job, with a bounded log tail |
| POST | `/api/dreams/runs` | `{"dream_id","iterations"}` → starts a job, returns at once |
| GET | `/api/dreams/{dream_id}` | one lineage in full, artifact included |
| GET | `/api/dreams/{dream_id}/chain` | ordered cids and any uncommitted iterations |
| POST | `/api/dreams/{dream_id}/verify` | re-prove every node |
| POST | `/api/dreams/{dream_id}/promote` | `{"force":bool}` → portable roadmap pack |
| POST | `/api/dreams` | `{"seed","foundation","kind"}` → new lineage, free |

Unmatched `/api/*` paths return `404`, never the SPA shell — a mistyped API
route must not come back as a `200` with HTML.

## Dreams

The review surface for `mem20dreamz`. It imports the engine as a library rather
than shelling out to `mem20-dream`, so there is one implementation of the rules
instead of two that can disagree. The exception is a run: that is spawned as the
engine's own CLI, because the CLI owns the lock discipline and the exit-code
contract, and reimplementing them here is how two runs end up dreaming at once.

Four things it is careful about, each because the alternative is a quiet lie:

* **The list never carries an artifact.** A lineage's artifact reaches hundreds of
  kilobytes and the list is polled, so rows carry counts and flags only. The
  detail view fetches one dream, artifact included.
* **Hollow lineages are flagged, not hidden.** Thirty-nine on this host recorded a
  provider error where a panel result should be. A hollow filter exists, and when
  it hides rows the response says how many.
* **A refusal is never flattened.** The engine refuses promotion on a hollow
  lineage and on a damaged chain; those are different facts with different
  remedies, so both are passed through with the engine's own wording. A refusal
  is a `409` with the reason, or a `200` with `promoted: false` — never a generic
  error.
* **"Kept" is labelled by how it is derived.** It is read from the promotions
  directory on disk, not from the ledger, so a pack written elsewhere would not
  show up. The response says which.

### Runs are jobs, not requests

An iteration is a full panel of models; five iterations measure at six to seven
minutes, against a twenty-second browser timeout. So `POST /api/dreams/runs`
spawns the engine CLI and returns a job id at once, and the tab polls it.

The exit codes stay distinct, because they are different facts:

| Exit | Reported as | Meaning |
| --- | --- | --- |
| 0 | `done` | every requested iteration ran |
| 2 | `paused` | a provider dropped; everything that landed was kept |
| 3 | `refused` | another run holds the lock |
| other | `failed` | see the log tail |

`paused` is deliberately not `failed`: telling an operator a partially-successful
run failed invites them to throw away work that is mostly intact.

Run records are held **in memory only**, and `GET /api/dreams/runs` says so. A
restart forgets them — deliberately, because a job record that outlived its
process would report a dead run as live.

A run is bounded at 20 iterations and at the ceiling the idle service itself uses.
Past the ceiling the child is killed and the job is reported `failed` with
`timed_out`.

### The hollow census only reads

`GET /api/dreams/hollow` re-derives hollowness from the stored critiques. It never
marks a lineage and never writes to braid, because both are separate explicit
acts on a store other people read, and a panel that quietly "fixed" thirty-nine
lineages while you were looking at a list would be indistinguishable from one
that corrupted them.

## Frontend

Vite + React in `mem20controlz/web`. The build writes straight into
`mem20controlz/static/`, which is what the app serves, so there is one build
output and no copy step.

```sh
cd mem20controlz/web
npm install
npm run build     # -> ../static
```

`npm run dev` (port 5173) needs `MEM20_CONTROL_API_TARGET` to proxy `/api`.

## Tests

```sh
/root/.venv/bin/python -m pytest tests -q     # 162 tests
/root/.venv/bin/ruff check mem20controlz tests
```

The suite covers the honest-status rules, the bounded log slice, Cloudflare
failure containment, the session lifecycle, fail-closed auth, the fact that every
data route is actually protected rather than most of them, and for dreams: that
the list carries no artifact text, that hollow and unkept filters report what they
hid, that each promotion refusal keeps its own reason, that the run exit codes map
to distinct states, that a second run for one dream is refused before spawning,
that iteration counts are bounded, and that a run past its ceiling is actually
killed.

The run-job tests never spawn anything — `conftest` makes `subprocess.Popen` raise
and the tests patch it with a fake process. The real spawn is verified against the
live service, not in a unit test.

## Reuses

`mem20ops` — one Cloudflare client (`dns-audit`, `pages-inspect`,
`service-status`) and the same `clicheck` discovery the coverage harness uses,
so the panel list cannot drift from the CLI audit.

`mem20dreamz` — the dream engine, as a library. The manager reads and writes
through it rather than reimplementing lineage, promotion or the run lock.
