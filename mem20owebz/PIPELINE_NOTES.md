# Pipeline Execution Notes - START_HERE.md Follow-through

## Flow to Follow
```
1. DEPENDENCIES.md → Check/verify all deps installed
2. CREDITS.md → Get keys and verify access
3. FIRST_GAME_WALKTHROUGH.md → Understand the full walkthrough
4. docker-compose.full.yml up -d → Launch the stack
5. WebUI setup → Create admin, configure TTS, bridge, tools
6. Game creation → COPY TEMPLATE → Fill HUMAN fields → Run pipeline
```

---

## Progress Log

### Step 0: File Discovery
- [x] Found START_HERE.md at `/home/jayson/Desktop/jayson-openwebui/START_HERE.md`
- [x] Found DEPENDENCIES.md, CREDITS.md, FIRST_GAME_WALKTHROUGH.md
- [x] Found prod.md at Desktop root
- [x] Unity Editor installed at `/home/jayson/Unity/Hub/Editor/6000.5.9f1/Editor/Unity`

### Step 1: DEPENDENCIES.md Review
Need to check what dependencies are actually installed vs expected.

### Step 2: CREDITS.md Review  
Need to find API keys and access credentials.

### Step 3: FIRST_GAME_WALKTHROUGH.md Review
Need to understand the complete game creation flow.

### Step 4: Stack Launch
Need to verify docker compose works with local Unity.

### Step 5: WebUI Setup
Document what's configured in Open WebUI.

### Step 6: Game Creation
Create proper Unity project + build.

---

## Key Questions to Answer
1. What deps are MISSING from DEPENDENCIES.md?
2. What keys are in CREDITS.md?
3. What does FIRST_GAME_WALKTHROUGH.md say about Unity builds?
4. Can we actually do headless builds with local Unity?

---

*Notes will be refined into final pipeline skill*