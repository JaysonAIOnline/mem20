# RPG Recipe: Mage / Wizard Staff

**Prefix:** `STF_`  
**Scale:** 1.6–1.9 m tall

## Base Modeling

1. **Shaft**
   - Bezier Curve (slight taper and organic bends)
   - Curve to Mesh with circular profile that varies in radius along the length (use radius attribute or multiple profiles)
   - Or lathed then deformed with proportional editing / Lattice for organic feel

2. **Grip Area**
   - Thicker section or wrapped
   - Supporting loops for later leather/cloth wrap

3. **Head / Crystal Holder**
   - Custom modeled claw, cage, or organic growth
   - Boolean or carefully joined to the shaft
   - Crystal itself: modeled or Icosphere refined + Subdivision

4. **Butt Cap**
   - Small metal or bone piece

## Geometry Nodes
- Leather or cord wrapping (spiral curve + Curve to Mesh)
- Small runes or metal bands
- Optional floating particle / energy effects (separate system)
- Vines or roots growing along the shaft for nature-themed staffs

## Materials
- Wood or bone shaft
- Metal fittings
- Crystal: Glass + emission + volume for magical core
- Wrap: Leather or cloth

## Tips
Keep the crystal as a separate object so you can easily swap different gem types (fire, ice, arcane, etc.).
