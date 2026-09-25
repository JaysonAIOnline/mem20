# RPG Recipe: Plate Armor Pieces (Breastplate, Pauldrons, etc.)

**Prefix:** `ARM_`  

## Approach
Treat each major piece as its own asset following the helmet pipeline.

### Breastplate / Cuirass
- Start from a body-derived Shrinkwrap target or carefully proportioned curves.
- Solidify for thickness.
- Boolean or inset for overlapping plates and articulation gaps.
- Heavy use of rivets and panel lines via Geometry Nodes.

### Pauldrons / Spaulders
- Layered plates.
- Origin at the shoulder pivot for character attachment.

## Geometry Nodes
- Dense rivet patterns
- Edge fluting / reinforcing ridges
- Leather straps and buckles (can be separate objects)

## Critical
Keep interior clean. Plan attachment points early (empties or vertex groups for parenting to a character armature).
