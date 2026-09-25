# Medieval Architecture Recipes

**Prefix examples:** `BLD_Keep_`, `BLD_House_`, `BLD_Tower_`, `BLD_Wall_`

## Core Principles for Buildings
- Modular where possible (wall sections, window modules, roof modules)
- Real-world scale (or heroic 1.1–1.2×)
- Clean topology for LODs and potential destruction
- Heavy use of Geometry Nodes for repetitive elements (bricks, tiles, battlements)
- Separate materials for stone, wood, thatch/slate, plaster

## 1. Simple Medieval House / Cottage
1. **Walls** – Extruded floor plan (or curve outline → mesh). Solidify. Add window/door openings with Boolean or inset.
2. **Roof** – Separate object. Gable or hip. Use Array of planks or GN tiles.
3. **Chimney** – Simple Boolean or joined box.
4. **Details** – Timber framing (curves or extruded beams), shutters, door as separate asset.

## 2. Stone Keep / Small Castle Tower
1. **Main volume** – Multi-level extruded plan or stacked cylinders refined into polygonal form.
2. **Battlements / Crenellations** – Geometry Nodes array of merlons + embrasures, or Boolean.
3. **Arrow slits / Windows** – Boolean cutters.
4. **Spiral staircase (optional)** – Curve + Screw or Array along curve.
5. **Roof / Turret top** – Conical or flat with parapet.

## 3. Curtain Wall / Fortification Section
- Modular wall segment with walkway, merlons, and optional tower junction.
- Designed to Array and Mirror for longer walls.

## Geometry Nodes Recommendations
- `GN_Brick_Wall` – procedural or instanced brick pattern with variation
- `GN_Roof_Tiles`
- `GN_Battlements`
- `GN_Timber_Frame`

## Materials
- Weathered stone (procedural noise + moss masks)
- Aged wood
- Thatched or slate roof
- Plaster with cracks

## LOD & Game Tips
Create wall modules that share the same texel density and material set so they can be freely combined.
