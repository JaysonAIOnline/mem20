# Version 3.0 Expansion Notes

## Major Additions

### RPG Improvements
- Added: Longbow, Battle Axe, Plate Armor, Furniture, Common Props (barrel, crate, banner, torch)
- Expanded README with clear categories

### Architecture
- New `10_buildings/` module
  - Medieval: houses, keeps, towers, walls
  - Modern: modular skyscraper / facade system

### API Scripting (`11_api_scripts/`)
- Collection hierarchy creator
- Batch rename enforcing conventions
- One-click RPG asset setup
- Ready for further add-on conversion

### Existing Strengths Retained
- All previous Sci-Fi, Geometry Nodes recipes, materials, LODs, export scripts remain fully intact.

## Suggested Next Steps for Users
- Turn the API scripts into a proper Blender add-on
- Build a shared Asset Browser library from the node groups and materials
- Create a city-block generator using the skyscraper modules
- Add destruction / fracture ready versions of buildings and props
