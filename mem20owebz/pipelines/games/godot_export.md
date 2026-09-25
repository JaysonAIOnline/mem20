# Godot Export Pipelines — Investigation (2.0)

How Godot 4 actually ships builds, mapped to Jayson `export_targets` + `asset_assembly`.

---

## 1. Mental model

| Piece | Role |
|-------|------|
| **Editor binary** | Required for `--export-*` (not an export template alone) |
| **Export templates** | Must **match editor version exactly** (Editor → Manage Export Templates) |
| **`export_presets.cfg`** | Per-platform presets (safe to commit) |
| **`.godot/export_credentials.cfg`** | Keystores/passwords (**do not commit**) |
| **Output path** | Relative to **project path**, not shell cwd |

Jayson stages: only export **after** ASSEMBLY + QA Build; outputs land under `builds/<platform>/` then `release/installer/`.

---

## 2. Platforms vs Jayson matrix

| Jayson target | Godot support | Notes |
|---------------|---------------|--------|
| Windows | First-class | Preset "Windows Desktop" → `.exe` (+ optional `.pck`) |
| Linux | First-class | `.x86_64` binary typical |
| Android | First-class | JDK **17**, Android SDK, templates, keystore; APK (test) or AAB (Play) |
| Meta Quest 2/3 | Via **Android** | OpenXR, Gradle build, Meta/vendor XR features; developer mode + ADB |
| PS VR / PS3 | **Not** native Godot | Stay PREP_ONLY / other engine |
| Web | Supported | `.zip`; not a Quest substitute |

---

## 3. One-time machine setup

### Desktop (Windows / Linux export)
1. Install Godot **editor** (version pinned in Production Package §11.1)
2. Install **export templates** for that exact version
3. Create presets: Project → Export → Add → Windows / Linux
4. Set **Export Path** e.g. `../../builds/windows/GameName.exe`

### Android (+ Quest)
1. **OpenJDK 17** (21 often breaks Gradle for Godot)
2. Android SDK (command-line tools + platform packages)
3. Editor Settings → Export → Android: **Java SDK path**, **Android SDK path**
4. Project → Install Android Build Template (if using Gradle / custom build)
5. Keystore for release:
   ```bash
   keytool -v -genkey -keystore mygame.keystore -alias mygame -keyalg RSA -validity 10000
   ```
6. Preset: package name `com.studio.game`, XR Mode **OpenXR** for Quest, enable Gradle when required

### Quest-specific
- Separate Android preset named e.g. `Meta Quest`
- XR Mode: OpenXR; vendor plugins as needed (Godot 4.6+ vendor plugin optional but useful for stores)
- Device: developer mode, ADB visible
- Still an APK/AAB pipeline — not a separate Godot “Quest export type”

---

## 4. CLI export (CI / production run Stage 6)

Editor binary + headless:

```bash
# From anywhere; path points at project.godot directory
godot --headless --path projects/<game>/engine_project \
  --export-release "Windows Desktop" builds/windows/GameName.exe

godot --headless --path projects/<game>/engine_project \
  --export-release "Linux/X11" builds/linux/GameName.x86_64

godot --headless --path projects/<game>/engine_project \
  --export-release "Android" builds/android/GameName.apk
```

Also available:
```bash
godot --headless --path <project> --export-debug "Windows Desktop" builds/windows/GameName_debug.exe
godot --headless --path <project> --export-pack "Windows Desktop" builds/windows/GameName.pck
```

**Rules**
- Preset **name** must match `export_presets.cfg` exactly (quote if spaces)
- Output path is relative to **project**, or absolute
- Templates must be installed or export fails silently/with error

---

## 5. Recommended preset set for Jayson projects

| Preset name | Platform | Export path pattern |
|-------------|----------|---------------------|
| Windows Desktop | Windows | `res://../../builds/windows/<Game>.exe` or absolute under `builds/windows/` |
| Linux/X11 | Linux | `builds/linux/<Game>.x86_64` |
| Android | Phone/sideload | `builds/android/<Game>.apk` |
| Android Play | Store | `builds/android/<Game>.aab` |
| Meta Quest | Android+OpenXR | `builds/quest/<Game>.apk` |

After export, **ReleaseManager** copies into `release/installer/` with `README_PLAYER.md`.

---

## 6. Pipeline binding (production run)

```
Stage 4 ASSEMBLY  → Godot project + integrated assets only
Stage 5 POLISH    → still engine-open, fix issues
Stage 6 RELEASE   → CLI or editor export per preset in package matrix
                  → QA Export
                  → human cold install test
```

Hard rules:
- Never export from `_incoming`
- Never commit `export_credentials.cfg`
- Pin Godot version in Production Package §11.1
- Android/Quest needs JDK17 + SDK on the **build machine** (your cloud VM later)

---

## 7. CI sketch (optional 2.0 follow-up)

```yaml
# Conceptual — pin URLs to your Godot version
- install Godot editor + export templates (same version)
- checkout project (export_presets.cfg committed)
- inject credentials on runner only
- godot --headless --path . --export-release "Linux/X11" builds/linux/game.x86_64
- upload builds/
```

Community actions exist (e.g. godot-export GitHub Action patterns); pin versions carefully.

---

## 8. Gaps / honesty

| Want | Reality |
|------|---------|
| One button all platforms | Editor “Export All” or multiple CLI calls; official per-preset CLI |
| Quest as first-class | Android + OpenXR + device setup |
| PS VR / PS3 | Not Godot native → PREP_ONLY |
| Secrets in git | Use `export_credentials.cfg` local/CI secrets only |

---

## 9. Quick checklist before first export

- [ ] Editor version == template version  
- [ ] Presets exist with correct names  
- [ ] Export paths under `builds/<platform>/`  
- [ ] Desktop: smoke run executable  
- [ ] Android: JDK17 + SDK paths set  
- [ ] Release keystore only on secure machine  
- [ ] Quest: OpenXR preset + device ADB  
- [ ] Manifest + QA Export signed off  

See also: `godot_pipeline.md`, `export_targets.md`, `asset_assembly.md`.
