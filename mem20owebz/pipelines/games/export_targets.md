# Export / Target Platform Pipelines

Realistic export guidance for builds leaving the Jayson production pipeline.

> Note: Full official console certification requires platform NDAs/SDKs you must obtain yourself.
> These pipelines prepare content and checklists so exports are systematic.

## Common pre-export QA
- [ ] Critical path completable
- [ ] Resolution & UI scale defined
- [ ] Input map documented
- [ ] Performance budget target set
- [ ] Save/load verified
- [ ] QA gate PASS

---

## Windows
- Target: DX11/DX12 or Vulkan
- Controllers: Xbox layout baseline
- Package: installer or portable zip
- Checks: windowed/fullscreen, alt-tab, 16:9/ultrawide

## Linux
- Target: Vulkan preferred
- Package: AppImage / Flatpak notes
- Checks: gamepad via SDL, native vs Proton path documented

## Android
- Target: OpenGL ES / Vulkan
- Aspect ratios: 16:9, 18:9, 19.5:9, foldables if claimed
- Input: touch + optional controller
- Checks: thermal throttling plan, install size, permissions list
- Store: package id, version code, signed build checklist

---

## Meta Quest 2
- Target: Android (Quest)
- Render: forward, fixed foveated if used
- Refresh: 72/90 Hz targets documented
- Input: Touch controllers only unless hand-tracking claimed
- Checks: comfort (locomotion, vignetting), guardian-safe movement, performance headroom

## Meta Quest 3
- Same as Quest 2 plus:
- Higher res & optional color passthrough features if used
- Dynamic resolution policy
- Mixed reality boundary rules if MR features exist

---

## PlayStation VR (PS4 VR)
- Requires PS4 SDK / dev hardware (external)
- Checklist only in open pipeline:
  - Move / DualShock input mapping
  - Reprojection assumptions
  - Comfort modes
  - Tracking loss behavior

## PlayStation VR2 (PS5 VR)
- Requires PS5 SDK / dev hardware (external)
- Checklist:
  - Sense controller mapping
  - Eye/adaptive triggers usage (if any)
  - HDR / OLED brightness safety
  - Social screen (TV mirror) behavior

## PS3 (legacy)
- Historical/target only — modern Unity/Unreal do not ship PS3
- Pipeline role: asset constraint sheet (polycounts, textures, audio formats) if remastering or emulating
- Prefer documenting limits over claiming automated export

---

## Export handoff template
For each target produce:
1. `platform_profile.md` — constraints & input
2. `build_notes.md` — how to produce the build
3. `qa_export_report.json` — from QA Export agent
4. Binary or package path (when SDK available)

If SDK is not available, mark export as **PREP_ONLY** and keep asset/platform budgets enforced upstream.
