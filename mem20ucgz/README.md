# mem20ucgz — RM-001 Universal Capability Graph

mem20 absorption of the FreeStack RM-001 Universal Capability Graph: a typed, versioned graph of capability domains that can be searched, composed, and invoked. SQLite-owned persistent state plane. Standard-library only, no runtime dependencies.

## Test
```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Simulator scenarios
```bash
PYTHONPATH=src python -m mem20ucgz.simulator
```

## API server
```bash
PYTHONPATH=src python -m mem20ucgz.api --db ucg.sqlite3
```

## CLI (URL: http://127.0.0.1:8781)
```bash
PYTHONPATH=src python -m mem20ucgz.cli --url http://127.0.0.1:8781 graph
PYTHONPATH=src python -m mem20ucgz.cli --url http://127.0.0.1:8781 register examples/capability-normalize.json
PYTHONPATH=src python -m mem20ucgz.cli --url http://127.0.0.1:8781 query --provides text/normalized
PYTHONPATH=src python -m mem20ucgz.cli --url http://127.0.0.1:8781 compose --output text/summary --input text/raw
```

## Security / signing
Set `FREESTACK_UCG_SIGNING_KEY` to verify HMAC-SHA256 capability manifests. Set `FREESTACK_UCG_ENFORCE_SIGNATURES=1` to reject unsigned capabilities. (Env names kept from upstream for integrity with existing manifests.)

## Provenance
Absorbed from FreeStack RM-001-Universal-Capability-Graph.zip (2026-08-09), renamed `freestack_ucg` → `mem20ucgz`. Tests pass on the renamed tree: 11/11. Original upstream tests: 11/11. No behavioral change.