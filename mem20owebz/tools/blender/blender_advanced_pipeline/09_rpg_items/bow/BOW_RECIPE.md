# RPG Recipe: Longbow / Recurve Bow

**Prefix:** `BOW_`  
**Scale:** ~1.6–1.8 m unstrung

## Base Modeling
1. **Limbs** – Single Bezier Curve for the elegant recurve profile. Use taper (radius attribute) for thickness variation. Curve to Mesh with elliptical profile.
2. **Grip / Riser** – Thicker central section, either part of the same curve or separate joined mesh with supporting loops.
3. **Tips / Nocks** – Small reinforced ends, possibly metal or horn.
4. **String** – Separate curve (or GN) that can be tensioned. Keep as a thin curve-to-mesh for flexibility.

## Geometry Nodes
- Leather grip wrap
- Small metal reinforcements / rivets at tips
- Optional sinew bindings

## Materials
- Wood (strong grain anisotropy)
- Leather
- String (simple emission or cloth-like)
- Optional magical glow on limbs

## Notes
Origin at the grip center. Provide both strung and unstrung versions if needed for animation.
