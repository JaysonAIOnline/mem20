# Quest Tracker UI Specification - The Unreliable Prophecy

## Design Overview
Quest Tracker styled as parchment document that becomes messier as amendments are discovered.

## Structure

### Main Section
- **Active Quest Title / ID**
- **Status Badge:** [ACTIVE] / [COMPLETED] / [FAILED]
- **Amendment Status:** "Pending Review" tag appears when relevant
- **Progress Bar:** Steps completed / total

### Quest List Layout
```
[ACTIVE] M01: Ordinary Life
  └─ Receive Prophecy  ✓
  └─ Sign forms       ✓
  └─ Acquire Binder   ⏳
[ACTIVE] M02: Leaving Home  
  └─ Reach Hills Gate ⏳
  └─ NPC Dialog       ○
[PENDING] SQ01: Lost Form
  └─ [Locked until M02 complete]
```

### Amendment System
When an amendment is discovered:
1. Current quest gains "AMENDMENT PENDING" tag
2. Text strikethrough appears on affected objective
3. Footnote appears at bottom with amendment text
4. Reliability rating decreases (-5% per amendment)

### Visual Elements
- **Font:** Readable serif (TextMeshPro)
- **Color:** Cream parchment (#F5E9DA) with institutional ink blue (#2C3E50)
- **Stamp:** Red rubber stamp marks on completion
- **Animation:** Gentle paper flutter when opened

## Unity Implementation Notes
- Canvas: Screen Space - Overlay
- Scroll Rect for quest list
- Button interaction for quest details
- TextMeshProUGUI for all text
- Image component for stamp VFX

## Sample UI Mockup
```
┌─────────────────────────────────────────────┐
│  QUEST TRACKER     [Close]                 │
├─────────────────────────────────────────────┤
│  ACTIVE QUESTS (2)                        │
│                                             │
│  [ACTIVE] M01 - Ordinary Life             │
│  ┌─ Sign Prophecy  ✓                      │
│  ├─ Wait for Bureaucrat  ✓                │
│  ├─ Obtain Binder  ⏳                      │
│                                             │
│  [ACTIVE] M02 - Leaving Home              │
│  ┌─ Talk to Old Wizard  ✓                │
│  ├─ Enter Woods  ○                        │
│  ├─ First Combat  ○                        │
│                                             │
│  AMENDMENT PENDING: Quest 02              │
│  New requirement added                    │
└─────────────────────────────────────────────┘
```