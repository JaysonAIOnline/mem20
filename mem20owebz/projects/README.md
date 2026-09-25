# Projects

Put **filled** production packages here.

```
projects/<game_name>/
  PRODUCTION_PACKAGE.md
  manifests/assets_master.csv
  art/_incoming/   audio/_incoming/
  engine_project/    # Godot or Unity
  builds/  release/installer/  qa/
```

## Start

```bash
mkdir -p projects/my_first_game/manifests
cp ../PRODUCTION_PACKAGE_TEMPLATE.md projects/my_first_game/PRODUCTION_PACKAGE.md
```

Fill HUMAN sections (including **engine**). See `asset_assembly.md` and `FIRST_GAME_WALKTHROUGH.md`.

Do not mix two games in one folder.
