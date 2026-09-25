# Stage A – Project Setup

## 1. Scene Template Checklist

When you create a new `.blend` for this pipeline:

### Units
- Unit System: Metric
- Unit Scale: 1.0
- Length: Meters
- Separate Units: Off

### Scene Settings
- Frame Rate: 24 or 30 (project dependent)
- Clip Start: 0.01 m
- Clip End: 1000 m

### Collections Hierarchy (exact)

```
COL_THR_Root
├── COL_THR_High              ← Final high-poly (for baking & beauty)
├── COL_THR_Low               ← Game / real-time mesh
├── COL_THR_Cutters           ← Boolean cutters (hidden)
├── COL_THR_GN_Details        ← Geometry Nodes detail objects
├── COL_THR_Cages             ← Bake cages
├── COL_THR_References        ← Blueprints / concept images
└── COL_THR_Export            ← Final export-ready objects
```

### Root Empty
Create an Empty named `THR_Thruster_Root` at world origin.  
Parent all major collections or objects to it.  
Add custom properties listed in the naming conventions.

### Viewport
- Enable: Statistics, Relationship Lines
- Matcap or Studio lighting for modeling
- Cavity + Depth of Field off while modeling

### Asset Browser
Create a catalog called `THR_Pipeline` and mark important node groups + materials as assets.

## 2. Python Setup Script

See `setup_scene.py` in this folder.  
Run it from the Scripting workspace to auto-create the entire hierarchy and settings.
