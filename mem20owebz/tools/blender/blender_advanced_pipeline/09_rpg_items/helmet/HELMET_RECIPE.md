# RPG Recipe: Knight / Fantasy Helmet

**Prefix:** `HLM_`  
**Scale:** Real human head size (~0.25 m)

## Base Modeling

1. **Main Dome / Skull**
   - Start from a carefully refined UV Sphere or better: Curve profiles spun
   - Or use a base head mesh as Shrinkwrap target for correct proportions
   - Add thickness with Solidify

2. **Visor / Faceplate**
   - Separate piece
   - Boolean openings for eyes / breath
   - Hinges if it needs to open

3. **Neck Guard / Gorget area**
   - Overlapping plates or solid
   - Clean edge loops for articulation if needed

4. **Crest / Plume Holder**
   - Small hard-surface attachment
   - Optional plume as particle or separate mesh

## Geometry Nodes
- Rivets everywhere (classic armor look)
- Panel lines / fluting
- Optional decorative etching

## Materials
- Polished or battle-worn steel
- Brass / gold accents
- Leather straps inside
- Plume: simple hair cards or particle system

## Critical Notes
- Topology must support potential facial deformation or at least look good from all angles
- Keep interior clean (player cameras often look inside)
- Origin usually at the base of the neck or center of the head for attachment to character
