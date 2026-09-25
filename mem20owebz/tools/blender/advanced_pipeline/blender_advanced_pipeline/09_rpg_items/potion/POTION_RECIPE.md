# RPG Recipe: Potion / Alchemy Bottle

**Prefix:** `POT_`  
**Scale:** 0.15–0.25 m tall (hand-sized)

## Base Modeling

1. **Bottle Body**
   - Bezier Curve profile (classic potion shape: wide base, narrow neck)
   - Screw modifier (high steps for smoothness)
   - Or lathed surface
   - Add slight asymmetry if desired (hand-blown look) with noise or proportional

2. **Neck & Lip**
   - Continue the same profile or separate curve
   - Solidify for glass thickness (important for refraction)

3. **Cork / Stopper**
   - Simple lathed form or modeled
   - Slight oversize for “jammed in” look

4. **Optional Liquid**
   - Separate mesh inside (slightly smaller)
   - Or use a volume / fluid simulation for hero shots
   - For real-time: just a mesh with transmission material

## Geometry Nodes
- Wax seal or string wrap around the neck (`GN_Cable` style with flat profile)
- Label (can be a plane or GN projected)
- Small bubbles inside liquid (scatter)

## Materials (Key)
- Glass: Transmission 1.0, IOR 1.45–1.52, slight roughness, volume absorption for color
- Liquid: Separate material with volume or thin transmission + emission for magical glow
- Cork: Procedural noise, high roughness
- Wax: Subsurface

## Special Notes
Glass is one of the few cases where starting close to a lathed primitive is acceptable — then immediately refine the profile and add thickness properly. Never leave a default cylinder.
