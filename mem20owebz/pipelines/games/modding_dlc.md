# Modding / Data-only DLC Layout

Optional. Enable only if HUMAN checked modding in §11.6.

```
mods/_example/
  manifest.json    # id, version, depends
  data/            # tables, strings — no engine binaries
  assets/          # optional overlays
```

## Rules
- P0 slice ships **without** requiring mods
- Data-driven quests/economy prefer JSON/CSV the game already loads
- DLC = extra folders the assembler copies into `release/` as optional packs
