# Level/Quest Specs - The Unreliable Prophecy
## Vertical Slice Edition

---

## 1. Quietvale (L01) - Tutorial Village

**Type:** Starter region
**Encounters:** 1-2 weak enemies (Misfiled Skeleton)
**Secrets:** None required
**Performance:** Low (tutorial)

### Layout:
```
House → Square → Woods Path → Bureaucrat Scene → Leave Gate
```

### Key Spots:
- **Wake Up** - Initial sequence
- **Exit House** - First interaction
- **Square** - Bureaucrat delivers Prophecy  
- **Woods Path** - First combat + ability tutorial
- **Leave Gate** - Tutorial completion

---

## 2. Bureaucracy Hills (L02) - First Regional

**Type:** Main region
**Enemies:** Misfiled Skeleton, Ink Blot, Unauthorized Imp, Compliance Officer
**Performance:** Medium

### Layout:
```
Hills Path → Annex Entrance → Department Wings → Amendment Delivery → Side Quest Area
```

### Key Spots:
- **Start** - After Quietvale gate
- **Path** - Early encounters
- **Annex** - First enemy variety
- **Department Area** - Amendment delivery point
- **Side Quest Marker** - SQ01 location

---

## 3. Encounter Recipes

### E01 - Woods Tutorial
| Field | Value |
|-------|-------|
| ID | E01 |
| Setup | Player entering woods, hear sound |
| Enemy mix | 2 Misfiled Skeleton |
| Player resources | Full HP, basic attack |
| Intended duration | <15 seconds |

### E02 - Hills Common
| Field | Value |
|-------|-------|
| ID | E02 |
| Setup | Found in path areas |
| Enemy mix | Ink Blot + Unauthorized Imp |
| Player resources | Standard |
| Intended duration | 10-25 seconds |

### E03 - Compliance Officer
| Field | Value |
|-------|-------|
| ID | E03 |
| Setup | Mid-region, patrol areas |
| Enemy mix | Compliance Officer (inspect first) |
| Player resources | Documents if available |
| Intended duration | Variable (escalates) |

### E04 - Amendment Delivery
| Field | Value |
|-------|-------|
| ID | AMD01 |
| Setup | Scheduled at specific location |
| Enemy mix | Officer trio + paperwork barrage |
| Player resources | Prepared (forms to counter) |
| Intended duration | 30-45 seconds |

---

## 4. Quest Templates (Vertical Slice P0)

### M01 - Ordinary Life / Prophecy Arrival
| Field | Value |
|-------|-------|
| ID | M01 |
| Name | Ordinary Life |
| Type | main |
| Start | Quietvale, tutorial complete |
| Objectives | 1. Receive Prophecy 2. Sign forms 3. Acquire Binder |
| Fail states | None (tutorial) |
| Rewards | Quest marker, Binder item |

### SQ01 - Side Quest Template
```
"The Department of {Department} has lost {Item}. Retrieve from {Location} before {Deadline}."
```

**Implementation:** Procedural side content, template-driven

---

## 5. UI/Quest Tracker Specs

**Style:** Parchment-styled (matches Prophecy Binder)
**Features:**
- Main bold quest titles
- Side quests below
- "Stamp on complete" visual
- "Amendment Pending" tag system

---

*These specs drive the Unity implementation for the vertical slice*