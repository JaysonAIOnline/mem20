# Modern Skyscraper / High-Rise Recipe

**Prefix:** `SKY_`  

## Philosophy
Modern skyscrapers are perfect for Geometry Nodes + modular design. Avoid modeling every floor by hand.

## Recommended Workflow

### 1. Core Structure
- Create a floor plate (outline of one typical floor) as a curve or mesh.
- Use Geometry Nodes or Array + Curve to stack floors with controlled variation.
- Separate core (elevator/stair shaft) from the outer shell.

### 2. Facade System (most important)
Build a modular facade panel library:
- Curtain wall glass panel
- Spandrel panel
- Vertical fin / mullion
- Corner piece
- Ground-floor special (lobby height)

Then use Geometry Nodes to:
- Instance panels on a facade grid
- Control panel type by attribute or random seed
- Add variation in material / opacity

### 3. Setbacks & Form
- Use multiple stacked profiles or Boolean to create setbacks, tapered tops, or distinctive crowns.
- Roof: mechanical equipment, helipad, spire as separate detailed assets.

### 4. Ground Level & Podium
- Often different scale and more detailed (lobby, retail, plaza).
- Treat as a separate “base” asset that the tower sits on.

## Geometry Nodes Power
- Floor plate generator
- Facade instancer with LOD switching (simpler panels at distance)
- Window light randomization (for night scenes)
- Antenna / rooftop clutter scatter

## Materials
- Glass (with slight tint, reflections, and interior emission for night)
- Metal panels / aluminum
- Concrete
- Strong use of lightmaps or emission for windows in game engines

## Performance Tips
- Heavy use of instances
- Aggressive LODs (facade becomes simple extruded box + texture at far distance)
- Separate interior only if the player can enter

This approach scales from a single tower to an entire city block.
