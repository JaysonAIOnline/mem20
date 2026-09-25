# Text / Image → UI Pipeline

Produce a coherent UI/HUD kit from text specs and/or reference images.

## Inputs
- UI list from Production Package §9.6
- Tone / art pillars
- Platform (desktop, mobile, VR safe zones)
- Optional reference screenshots

## Stages
1. **Inventory screens** — HUD, menus, inventory, dialogue, map, settings
2. **Information hierarchy** — what must be readable at a glance
3. **Layout wireframes** — text descriptions + grid rules (12-col / safe zones)
4. **Component library** — buttons, panels, bars, icons, fonts
5. **Visual pass** — color tokens from art pillars; state styles (idle/hover/active/disabled)
6. **Icon & texture request list** — sizes, export formats
7. **Platform adapt** — scale for Quest/Android vs 4K desktop
8. **QA** — readability, contrast, missing states
9. **Handoff** to TechLead (implementation) + ArtDirector

## Output artifacts
- `ui_screen_list.md`
- `ui_wireframes.md`
- `ui_tokens.json` (colors, spacing, type scale)
- `ui_component_spec.md`
- `ui_icon_asset_list.csv`
- QA report

## Agent roles
UIDesigner → ArtDirector → QA Design → TechLead
