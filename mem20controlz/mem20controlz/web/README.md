# mem20 control plane — web console

Vite + React (plain JavaScript, no TypeScript). Dependencies are `react` and
`react-dom` only; there is no UI framework.

## Build

```bash
npm install
npm run build     # emits ./dist
```

The backend serves `./dist`, so the production bundle calls **same-origin**
`/api/*`. No dev-server proxy is required for the build.

For `npm run dev` only, opt in to a proxy if the API is not on the same origin:

```bash
MEM20_CONTROL_API_TARGET=http://127.0.0.1:8000 npm run dev
```

Alternatively set `VITE_API_BASE` at build time to point the bundle at another
origin.

## Layout

```
src/
  main.jsx               entry
  App.jsx                shell: nav menu + top bar + view switch
  api.js                 fetch wrapper: 20s AbortController timeout, ApiError
  hooks.js               useResource(path, {pollMs, enabled}) + clock formatting
  status.js              status vocabulary -> colour tone (ok/degraded/unreachable/unknown)
  styles.css             dark dense operations-console styling
  components/            StatusPill, Banner, Stdout, shared ui primitives
  tabs/                  Overview, Subsystems, CliCoverage, Websites
  views/                 Sites, Dns, Health, Logs, Pages (Websites sub-tabs)
```

## Navigation

A left nav menu selects one of four views: **Overview**, **Subsystems**,
**CLI coverage**, **Websites**. The Websites view has its own tab bar:
**Sites / DNS / Health / Logs / Pages**. Nothing in this app is one long scroll —
the shell is a fixed-height grid and each panel scrolls internally.

## Honesty rules enforced in the UI

1. A green/ok pill is only ever produced by a literal `status: "ok"` from the
   API. `degraded`, `unreachable`, `unknown`, a missing status, and any
   unrecognised status string all render in their own tone, never green.
2. `status_reason` is always shown for a panel; when absent the UI says so
   explicitly instead of hiding the field.
3. A `counts` key the API did not send renders as `—` with the label
   "key absent from the counts object" — it is never filled in with a 0.
4. Failed requests surface the error text, the HTTP status, and the endpoint.
   A failed request never renders as an empty table.
5. No placeholder or invented metrics anywhere. Panels that have not been
   fetched say they have not been fetched.
6. Plain boolean data fields (`proxied`, `dns_present`, …) are rendered
   neutrally — they are data, not health signals.

## Endpoints consumed

`GET /api/health`, `GET /api/registry` (polled every 10s),
`GET /api/cli/coverage`, `GET /api/websites/manifest`,
`GET /api/websites/sites`, `GET /api/websites/dns`, `POST /api/websites/dns`,
`DELETE /api/websites/dns/{id}`, `GET /api/websites/health`,
`GET /api/websites/logs`, `GET /api/websites/pages`.

Writes (DNS create/delete) are always behind an inline confirm step, and the
API's rejection message is shown verbatim when one is returned.
