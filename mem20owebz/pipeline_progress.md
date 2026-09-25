---
title: Stage 3: ASSET_PRODUCTION Ready
---

## Updated Pipeline Progress

```
Stage 0: PACKAGE_LOCK  ✓ PASS
Stage 1: DESIGN_SPINE   ✓ COMPLETE  
Stage 2: SPACES_UI_VR   ✓ SKIPPED (no VR in scope)
Stage 3: ASSET_PRODUCTION → IN PROGRESS
Stage 4: ASSEMBLY
Stage 5: FINAL_POLISH  
Stage 6: RELEASE_PACKAGE
Stage 7: DONE
```

## Generated Artifacts

1. `world_bible_gen.md` - World design (Quietvale + Hills)
2. `level_specs_gen.md` - Level/quest specifications
3. `ui_specs_gen.md` - Quest Tracker UI design
4. `projects/unreliable_prophecy/PRODUCTION_PACKAGE.md` - Active package
5. `projects/unreliable_prophecy/assets_manifest.csv` - P0 tracking
6. `projects/unreliable_prophecy/STRUCTURE.md` - Project tree
7. `projects/unreliable_prophecy/stage2_skipped.md` - Skip documentation
8. `projects/unreliable_prophecy/stage3_workflow.md` - Stage 3 process

## Stage 3: ASSET_PRODUCTION

**Ready to generate assets using:**
- Text-to-3D (Tripo, Meshy, Luma APIs via tools)
- Kokoro TTS for dialogue
- 3D Screenshots for documentation

**P0 Assets Required:** 15 items (characters, props, UI, audio)

**Next Step:** Generate assets into `projects/unreliable_prophecy/_incoming/`

---

## CLI Monitoring

```bash
# Check pipeline state
python3 run_pipeline_queued.py status

# View generated files
ls -la projects/unreliable_prophecy/
ls -la projects/unreliable_prophecy/manifests/
```

## WebUI Alternative

1. http://localhost:3000
2. Admin → Connections → Add bridge (URL: `http://host.docker.internal:4000/v1`)
3. Admin → Tools → Paste all tools from `tools/openwebui_tools/`
4. Chat: "Run Stage 3: Generate P0 art/audio into project folder"

---

*Pipeline runner: run_pipeline_queued.py*
*Stage: 3/7 - ASSET_PRODUCTION*