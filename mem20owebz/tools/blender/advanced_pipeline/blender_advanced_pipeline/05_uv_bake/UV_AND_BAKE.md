# Stage 5 – UV Unwrapping & Baking

## UV Goals
- Consistent texel density (recommend 10.24 px/cm for 4k textures on ~1m objects)
- Minimal distortion (< 2.5%)
- Clean packing
- UDIM support if the asset is large
- Seams placed on hard edges / hidden areas where possible

## Recommended Workflow

1. **Seam Placement**
   - Mark seams on hard edges that already exist from modeling
   - For cylindrical parts: one longitudinal seam + circular seams at major diameter changes
   - Avoid seams across important panel lines if possible

2. **Unwrap**
   - Use “Unwrap” (Angle Based) first
   - Follow with “Minimize Stretch”
   - For hard surface: sometimes “Conformal” gives better results

3. **Packing**
   - UV Packmaster 3 (highly recommended) or native Pack Islands with good margin
   - Average Island Scale
   - Check texel density with a checker texture + addon or custom GN

4. **UDIM** (if needed)
   - Assign tiles by material or by logical parts (body = 1001, nozzle = 1002, etc.)

## Baking Pipeline

### High → Low
1. High poly in `COL_THR_High` (with all GN details applied or realized if necessary)
2. Low poly in `COL_THR_Low` (decimated or manually retopologized)
3. Cage object (inflated low poly) in `COL_THR_Cages`
4. Bake settings:
   - Type: Normal, AO, Curvature, Thickness, ID, Diffuse (if needed)
   - Cage: Extrusion + Cage object
   - Margin: 4–16 px
   - Selected to Active

### Expert Tips
- Realize Instances only at bake time
- Use “Clear Image” carefully
- Bake in 16-bit float for normals when possible
- Store bake maps with clear names: `BAK_THR_Normal_4k.png`, etc.

## Scripts
A basic bake helper can be added later. For now, use the manual workflow above with strict naming.
