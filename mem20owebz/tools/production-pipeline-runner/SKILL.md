---
name: production-pipeline-runner
category: software-development
description: Standalone CLI tool for running game production pipelines outside of Open WebUI. Handles asset generation, assembly, and release packaging with minimal verbosity.
---

# Production Pipeline Runner

## Usage

```
# Check pipeline status
python3 run_pipeline_queued.py status

# Run specific stage
python3 run_pipeline_queued.py run-stage --stage N

# Generate assets using local Blender
python3 tools/blender/generate_assets.py

# Create Unity project structure  
python3 tools/unity/unity_assembly.py

# Build release package
python3 tools/release/final_release.py
```

## Pipeline Stages

```
Stage 0: PACKAGE_LOCK    ✓ PASS - Verify sign-off, engine
Stage 1: DESIGN_SPINE    ✓ COMPLETE - Generate world/level/specs
Stage 2: SPACES_UI_VR    ✓ SKIPPED - No VR in scope
Stage 3: ASSET_PRODUCTION ✓ COMPLETE - Generate GLB assets
Stage 4: ASSEMBLY        ✓ COMPLETE - Unity project ready
Stage 5: FINAL_POLISH    ✓ COMPLETE - QA all pass
Stage 6: RELEASE_PACKAGE ✓ COMPLETE - ZIP package created
Stage 7: DONE           ✓ READY - Import into Unity
```

## Output Paths

- Assets: `projects/{game}/_incoming/*.glb`
- Unity: `projects/{game}/engine_project/`
- Release: `projects/{game}/release/{game}_v{version}.zip`

## Tools

### Local Generation
- `tools/blender/blender_tools.py` - Create 3D primitives, materials
- `tools/blender/generate_assets.py` - Batch generate assets
- `tools/unity/unity_assembly.py` - Create Unity project
- `tools/unity/final_polish.py` - QA validation
- `tools/release/final_release.py` - Create distributable

## API Integration

### Bridge Health Check
```bash
curl -s http://localhost:4000/health/liveliness
```

### Key Seeding (if auth fails)
```bash
curl -X POST http://localhost:4000/key/generate \
  -H "Authorization: Bearer $MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"master_key":"$MASTER_KEY"}'
```

## Pitfalls

1. **Bridge rate limits** - Wait 30s between requests
2. **VR skip** - Document "no VR in scope" to skip Stage 2
3. **GLB location** - Files generate to `/root/jayson_3d/blender/`, copy to project
4. **Headless Unity** - Cannot build without Unity Editor GUI present