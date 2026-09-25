# Localization Pack

## Inputs
Production package language list (default: source language only).

## String table
| key | en | notes | max_chars |
|-----|----|-------|-----------|
| ui.play | Play | HUD | 12 |
| ui.settings | Settings | | 16 |

## Rules
- Never concatenate sentences in code — use format tokens `{name}`
- VO lines get `VO_<id>` keys matching audio asset IDs
- Fonts must cover target scripts

## Outputs
- `design/loc/strings.csv`
- `design/loc/fonts.md`
- Optional: per-locale VO folder under `audio/voice/<locale>/`

Skip extra locales in vertical slice unless HUMAN asked.
