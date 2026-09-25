# Accessibility Pass

Run before FINAL_POLISH. Tool: `accessibility_tool.py`

## Checklist
- [ ] Subtitles on/off + size
- [ ] Colorblind presets (deuteranopia, protanopia, tritanopia) — never color-only signals
- [ ] Remappable controls
- [ ] Invert look / hold-to-toggle
- [ ] UI contrast vs art pillars
- [ ] Flash/intensity options if VFX heavy
- [ ] VR: comfort vignette, snap/smooth turn (see text_to_vr.md)
- [ ] Screen reader notes for menus (desktop)

## Output
`qa/accessibility_report.md` — FAIL if color-only win/lose or no remapping on keyboard+gamepad slice.
