# Geometry Nodes Recipe: Cable / Hose Bundles

**Goal:** Procedural cable or hose runs that can follow surfaces, curves, or be freely drawn.

## Inputs
- Guide Curve(s) or start/end points
- Profile Radius
- Profile Resolution
- Noise Amount (for organic slack)
- Bundle Count (how many cables in the bundle)
- Twist Amount
- Material Index / Attribute

## Node Flow (Single Cable)

1. Input Curve (or generate Curve Line between two empties)
2. Resample Curve (length-based)
3. Set Handle Type / Smooth
4. Noise Texture → Set Position (offset along normal for slack)
5. Curve to Mesh (Circle profile)
6. Set Material / Store Attribute
7. Output

## Bundle Version
- Duplicate the curve multiple times with small radial offsets
- Or use a star-shaped profile + twist
- Add slight individual noise per cable

## Surface-Following Version
- Start with a curve drawn on the surface (or projected)
- Sample nearest surface normal
- Offset the curve slightly above the surface
- Then Curve to Mesh

## RPG Usage
- Perfect for potion bottle straps, staff wrappings, sword scabbard straps, chest ropes, magical energy conduits, etc.
- Swap circle profile for a flat leather strap profile when needed.
