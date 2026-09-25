# Stage 3: ASSET_PRODUCTION Workflow

## Pipeline Action

**Goal:** Generate P0 art/audio into `_incoming`, assign IDs, manifest, validate

**Tools:**
- text_image_to_3d_tool → 3D assets
- audio_video_gen_tool → Audio/Voice
- Blender (local) → Refinement
- 3D Screenshots → Shots

**QA:** qa_inspect 3d_asset + audio; all P0 validated

## Asset Ingestion Process

```
1. Generate assets into _incoming/
2. Assign unique asset IDs  
3. Update assets_master.csv with status = "generated"
4. QA inspect (spot-check 20%)
5. Move validated to assets/ folder
6. Update manifest status = "integrated"
```

## Folder Structure

```
projects/unreliable_prophecy/
├── _incoming/
│   ├── characters/    ← Generated 3D characters
│   ├── props/         ← Generated 3D props  
│   ├── environments/  ← Generated 3D environments
│   ├── ui/            ← 2D/UI mockups
│   ├── audio/         ← TTS voice, SFX, music
│   └── vfx/           ← Particle effects
├── assets/
│   ├── Characters/    ← Validated characters
│   ├── Props/         ← Validated props
│   ├── Environments/  ← Validated environments
│   └── Audio/         ← Validated audio
└── manifests/
    └── assets_master.csv  ← Asset tracker
```

## Next Actions

1. **Generate assets** using text-to-3D tools (Tripo, Meshy, Luma)
2. **Generate audio** using Kokoro TTS for dialogue
3. **Create blank manifest** for tracking

---

## CLI Command to Check Progress

```bash
python3 /home/jayson/Desktop/jayson-openwebui/run_pipeline_queued.py status
```