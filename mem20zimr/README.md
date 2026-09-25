# mem20zimr — RM-002 Zero-Install Microapp Runtime

mem20 absorption of the FreeStack RM-002 Zero-Install Microapp Runtime: signed portable microapps that execute without traditional installation or dependency pollution. Standard-library only.

## Quick demo
```bash
export PYTHONPATH="$PWD/src"
./scripts/demo.sh
```

## Tests
```bash
export PYTHONPATH="$PWD/src"
python -m unittest discover -s tests -v
```

## Start the local runtime API / desktop
```bash
export PYTHONPATH="$PWD/src"
python -m mem20zimr.cli serve
```
Open `http://127.0.0.1:8765/`.

## Build and launch a signed Python microapp
```bash
export PYTHONPATH="$PWD/src"
export FREESTACK_SIGNING_SECRET='replace-in-production'
python -m mem20zimr.cli build examples/hello_py release/hello_py.fsmicro \
  --app-id demo.hello --entrypoint main.py --modes local,hybrid,cloud
python -m mem20zimr.cli launch release/hello_py.fsmicro --payload '{"name":"RM-002"}'
```

## Browser microapp
```bash
python -m mem20zimr.cli build examples/hello_web release/hello_web.fsmicro \
  --app-id demo.web --kind web --entrypoint index.html --modes browser
```

## Edge/cloud peer execution
Start a trusted mem20zimr runtime on the peer, then:
```bash
export FREESTACK_CLOUD_ENDPOINT='http://peer-host:8765'
python -m mem20zimr.cli launch release/hello_py.fsmicro --mode cloud
```

## API surface
- `GET /` , `GET /health`, `GET /metrics`
- `GET /v1/jobs`, `/v1/jobs/<id>`, `/v1/jobs/<id>/events` (+ SSE `?stream=1`)
- `POST /v1/launch`, `POST /v1/jobs/<id>/cancel`
- `GET|POST /v1/microapps`, `DELETE /v1/microapps/<app_id>/<version>`
- `POST /v1/feedback`, `POST /v1/remote/execute`, `GET /v1/browser/<job_id>/<path>`

## Safety boundaries
Bundles are verified by signer trust plus content digest. Python microapps run in isolated interpreter mode in ephemeral directories with minimal environment, time/CPU/memory/output limits, bounded retries/concurrency, and path escape protection. This is a capability-scoped process sandbox foundation; not a replacement for a hardened OS/container boundary for hostile native code.

## Provenance
Absorbed from FreeStack RM-002_Zero_Install_Microapp_Runtime.zip (2026-08-09), renamed `freestack_zero_install` → `mem20zimr`. Env names (`FREESTACK_*`) and the `fs-microapp` script alias retained for upstream integrity. Original upstream tests: 15/15; renamed tree verified 15/15. No behavioral change. This package's bundled signature secret is the lab default — replace in production uses.