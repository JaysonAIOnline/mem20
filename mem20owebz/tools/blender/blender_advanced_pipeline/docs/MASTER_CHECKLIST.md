# Master Pipeline Checklist

Use this before calling any asset “done”.

## Project
- [ ] Correct units (Metric, scale 1.0)
- [ ] Collection hierarchy matches standard
- [ ] Root empty with all custom properties
- [ ] File named with version

## Modeling
- [ ] No final primitives remain
- [ ] Clean quad-dominant topology on high poly
- [ ] Supporting loops present
- [ ] Bevel weights / creases set
- [ ] Boolean cutters organized and named
- [ ] All transforms applied on base objects

## Geometry Nodes
- [ ] Detail density controllable
- [ ] Masks working
- [ ] Node groups named and documented
- [ ] No unnecessary realized geometry until export/bake

## UVs
- [ ] Seams logical
- [ ] Distortion checked
- [ ] Texel density consistent
- [ ] Packed with proper margin

## Baking
- [ ] Cage correct
- [ ] All required maps baked
- [ ] Maps named correctly

## Materials
- [ ] Principled BSDF based
- [ ] Attributes connected
- [ ] Wear controllable globally

## Export
- [ ] LODs created
- [ ] Origins correct
- [ ] Scale/rotation applied
- [ ] Tested in target application

## Documentation
- [ ] Version noted
- [ ] Any deviations from pipeline recorded
