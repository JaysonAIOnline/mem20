# Save / Load + Settings Schema

Bind to production package §11.4. Run during DESIGN_SPINE or ASSEMBLY.

## Schema (engine-agnostic)

```json
{
  "save_version": 1,
  "slots": "unlimited | numbered",
  "autosave": {"enabled": true, "interval_sec": 120, "max_slots": 3},
  "what_is_saved": ["player_transform", "inventory", "quest_flags", "unlocks", "settings"],
  "settings": {
    "audio": ["master", "music", "sfx", "voice"],
    "video": ["resolution", "window_mode", "vsync", "quality_preset"],
    "gameplay": ["subtitles", "camera_sensitivity", "invert_y", "colorblind_mode"],
    "accessibility": ["see accessibility.md"]
  }
}
```

## Deliverables
- `design/systems/save_schema.json`
- `design/systems/settings_schema.json`
- TechLead implementation notes per engine (Godot: ConfigFile + user:// ; Unity: PlayerPrefs or JSON)

## QA
No silent overwrite of slot 0; corrupt save must fail safe to defaults.
