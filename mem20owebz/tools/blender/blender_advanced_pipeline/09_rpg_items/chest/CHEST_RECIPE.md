# RPG Recipe: Treasure Chest

**Prefix:** `CHT_`  
**Scale:** 0.6–1.0 m wide

## Base Modeling

1. **Main Box**
   - Build with carefully extruded planes or a refined cube that is immediately reshaped
   - Better: create the four sides + bottom as separate boards (real wood planks) then join
   - Add plank seams with inset or GN panel lines

2. **Lid**
   - Same board technique, slightly curved or flat
   - Hinge area needs clean topology

3. **Metal Bands / Straps**
   - Curve → Curve to Mesh with flat rectangular profile
   - Or Boolean / Solidify strips
   - Rivets via Geometry Nodes

4. **Lock / Latch / Hinges**
   - Small hard-surface pieces (Boolean friendly)
   - Keep as separate objects for animation if the chest opens

5. **Interior**
   - Optional simple box insert
   - Can hold other RPG props later

## Geometry Nodes
- Rivets on all metal bands
- Optional wood grain direction via attributes
- Rope handles (`GN_Cable`)

## Materials
- Wood (procedural or texture, strong anisotropy or grain)
- Aged iron / brass bands
- Interior darker wood or velvet

## Animation Note
If the chest needs to open, keep lid as separate object with proper pivot. The pipeline still applies — just plan the hierarchy early.
