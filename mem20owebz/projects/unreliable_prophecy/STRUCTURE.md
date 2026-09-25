# The Unreliable Prophecy - Project Structure

## Vertical Slice v0.5.0

```
unreliable_prophecy/
├── PRODUCTION_PACKAGE.md          # This file
├── assets_manifest.csv            # P0 asset tracking
├── world_bible.md                  # World design
├── level_specs.md                  # Level/quest design
├── ui_specs.md                     # UI/UX specs
└── pipeline_progress.md            # Stage tracking

projects/unreliable_prophecy/
├── PRODUCTION_PACKAGE.md            # Active production package
├── assets_manifest.csv              # P0 asset tracker
├── _incoming/                       # Drop zone for generated assets
│   ├── characters/
│   ├── props/
│   ├── environments/
│   └── ui/
├── engine_project/                  # Unity project (to be created)
│   ├── Assets/
│   │   ├── Scenes/
│   │   │   ├── Boot.unity
│   │   │   ├── MainMenu.unity
│   │   │   ├── Quietvale.unity
│   │   │   └── BureaucracyHills.unity
│   │   ├── Characters/
│   │   ├── Props/
│   │   ├── UI/
│   │   └── Scripts/
├── release/
│   └── installer/                   # Build output
└── qa/
    └── STATUS.md                    # QA tracking

_artifact_logs/
└── unreliable_prophecy/
    ├── generation_log.md
    └── version_history.md
```

## Status Legend

- P0: Required for vertical slice
- P1: Nice to have
- P2: Post-launch

---

Pipeline running: Stage 3 (ASSET_PRODUCTION) next after Stage 2 skip.