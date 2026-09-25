# RPG Recipe: Fantasy Longsword / Arming Sword

**Prefix:** `SWD_`  
**Target Length:** ~1.05–1.15 m overall

## Base Modeling (No final primitives)

1. **Blade**
   - Bezier Curve for the side profile (including tip and tang)
   - Second curve or mesh for the cross-section (diamond or lenticular)
   - Use Curve + Bevel Object or Screw-style loft, then convert
   - Or: Start with a plane, extrude, then use proportional editing + Knife for the fuller (blood groove)
   - Add supporting loops along the edges for sharp bevels

2. **Fuller (groove)**
   - Boolean cutter (long thin shape) or inset + extrude inward
   - Keep non-destructive

3. **Guard (Crossguard)**
   - Curve profile spun or carefully modeled
   - Boolean for decorative cutouts
   - Heavy bevels

4. **Grip / Handle**
   - Curve for the shape + Screw or loft
   - Or subdivided cylinder that is then shaped with proportional tools + supporting loops
   - Add leather wrap later via GN or modeled spiral

5. **Pommel**
   - Custom modeled or curve lathed
   - Can be spherical, disc, or ornate

## Geometry Nodes Details
- Rivets / pins on the guard and pommel (`GN_Detail_Rivets`)
- Optional engraving lines on the blade (panel-lines style but shallower)
- Leather wrap on grip: Curve spiral + Curve to Mesh with flat profile
- Optional runes as Boolean or GN decals

## Materials
- Blade: High metallic, anisotropic if possible, edge wear
- Guard & Pommel: Darker metal or bronze
- Grip: Leather (procedural noise + subsurface slight)
- Optional glowing runes (emissive)

## UV & Bake Notes
- Blade can be a single long island or split
- Guard often needs careful seam placement
- High → Low bake for the ornate version is highly recommended for games

## Export Tips
- Origin at the balance point or grip center
- Separate materials for LOD switching if needed
- Provide both “clean” and “battle-worn” material variants
