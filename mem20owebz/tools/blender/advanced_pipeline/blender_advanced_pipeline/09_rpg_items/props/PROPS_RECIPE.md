# RPG Recipe: Common Props (Barrel, Crate, Banner, Torch)

**Prefix:** `PRP_`  

## Barrel
- Curve profile for the staves (or Array of boards around a circle).
- Metal hoops via Curve → Curve to Mesh.
- Lid as separate object.
- GN for rivets on hoops.

## Crate
- Board construction (same as chest but simpler).
- Optional broken/open variants.

## Banner / Flag
- Plane with Subdivision + Cloth or simple Wave modifier for movement.
- Pole as separate curve-based mesh.
- GN or texture for heraldry.

## Torch / Sconce
- Handle + bowl.
- Flame as particle system or animated emissive mesh (separate).

All follow the same non-destructive + naming rules.
