# mem20greenz — greenroom for clones

Stage clones of external software and websites, build original
cleanroom baselines from observed behavior, verify, then promote.

## Status

Working slice: sqlite registry (`staged → captured → baselined →
verified → promoted`, `dropped` terminal), same-origin website mirror,
git clone helper, concept-baseline writer, full CLI, hermetic tests.

## Rules (cleanroom)

- Never copy code, markup, assets, or trademarks from a source.
- Capture only the concept and observable behavior.
- Every baseline states what we keep versus what we add.

## Tests

```bash
python -m pytest tests -v   # from this directory
python -m pytest mem20greenz  # from /opt/mem20
```

## First project

Mem20Teamz (from Teamily) — registered once its concept baseline lands.
