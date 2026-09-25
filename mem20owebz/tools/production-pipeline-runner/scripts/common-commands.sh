# Common Runtime Scripts

## Pipeline Runner
File: `run_pipeline_queued.py`
Usage: `python3 run_pipeline_queued.py status`

## Asset Generator  
File: `tools/blender/generate_assets.py`
Usage: `python3 tools/blender/generate_assets.py`

## Unity Assembly
File: `tools/unity/unity_assembly.py`
Usage: `python3 tools/unity/unity_assembly.py`

## Release Packager
File: `tools/release/final_release.py`
Usage: `python3 tools/release/final_release.py`

## Bridge Status Check
```bash
curl -s http://localhost:4000/health/liveliness
```

## Key Seeding
```bash
curl -X POST http://localhost:4000/key/generate \
  -H "Authorization: Bearer $MASTER_KEY" \
  -d '{"master_key":"$MASTER_KEY"}'
```