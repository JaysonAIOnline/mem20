# Game Development Pipeline Documentation

## Pipeline Architecture

### 7-Stage Process
1. PACKAGE_LOCK - Verify inputs and scope
2. DESIGN_SPINE - Generate world and level specs  
3. SPACES_UI_VR - VR specs (skip if no VR)
4. ASSET_PRODUCTION - Generate 3D assets
5. ASSEMBLY - Create Unity project
6. FINAL_POLISH - QA and validation
7. DONE - Ready for build

### Data Flow
```
prod.md → CLI runner → Generation Scripts → GLB files → Unity Project → Release ZIP
```

### Key Decisions Log
- VR not in scope for Windows-only target
- Unity 6 LTS + URP selected
- Local Blender used for asset generation
- Direct file output preferred over WebUI

### Common Commands
```bash
# Pipeline status
python3 run_pipeline_queued.py status

# Generate assets  
python3 tools/blender/generate_assets.py

# Package release
python3 tools/release/final_release.py
```