# Jayson — Advanced Features Guide

This file covers everything beyond the basic setup.

---

## 1. Password Strength Rules

Already enabled in `docker-compose.yml`:

- Minimum 10 characters
- Must contain uppercase + lowercase + number + special character

You can change the regex if you want stricter/looser rules.

---

## 2. Completely Hide the Sign-Up Button

After you create your admin account:

1. Go to **Admin Panel → Settings → General**
2. Turn **Enable New Sign Ups** → **Off**
3. Save

The Sign Up button will disappear from the login page.

Alternatively you can set `ENABLE_SIGNUP=False` in docker-compose after the first user is created (and restart).

---

## 3. OAuth Login (Google / GitHub)

1. Create OAuth apps:
   - Google: https://console.cloud.google.com/apis/credentials
   - GitHub: https://github.com/settings/developers → OAuth Apps

2. Uncomment and fill these in `docker-compose.yml`:

```yaml
- ENABLE_OAUTH_SIGNUP=True
- GOOGLE_CLIENT_ID=...
- GOOGLE_CLIENT_SECRET=...
# or
- GITHUB_CLIENT_ID=...
- GITHUB_CLIENT_SECRET=...
- OAUTH_PROVIDER_NAME=GitHub
```

3. Restart the container.

You can keep email/password login at the same time or disable it.

---

## 4. Voice Mode + TTS (Ready to configure)

### Fastest (Browser)
- Just click the microphone icon → works immediately
- Uses browser speech recognition + browser TTS

### Better Quality (Recommended)

**Option A – OpenAI (easiest)**
1. Admin Panel → Settings → Audio
2. STT Engine: OpenAI
3. TTS Engine: OpenAI
4. Put your OpenAI key
5. Model: `tts-1` or `tts-1-hd`
6. Voice: `alloy`, `echo`, `nova`, `onyx`, etc.

**Option B – Fully Local (Kokoro / Piper)**
- Run a local TTS server (Kokoro Web or voicebox)
- Point Open WebUI Audio settings to `http://host.docker.internal:PORT/v1`

Voice Mode (hands-free continuous talk) is available once STT + TTS are configured.

---

## 5. Multimedia & Asset Handling

### Images
- Fully supported
- Upload / paste → vision models can analyze them

### Audio
- Upload → automatically transcribed
- Works with Voice Mode

### Video
- YouTube links work best (transcript extracted)
- Direct video files can be uploaded; transcription quality depends on your STT setup
- For better video understanding you can later add a custom pipeline that extracts frames + transcripts

### 3D Models (.glb, .gltf, .obj, .fbx…)
- You can upload the files
- The AI cannot natively understand 3D geometry yet

**Recommended next step for 3D:**
Create a custom Open WebUI Function / Tool that:
1. Takes a 3D file
2. Renders a few camera angles (using Blender headless or three.js)
3. Generates a text description
4. Injects the description + screenshots into the chat

I can help you build that function later if you want.

---

## 6. Better Video Transcription

1. Use a strong STT backend (OpenAI Whisper, faster-whisper, Deepgram, etc.)
2. In Admin → Settings → Audio set the STT engine
3. For long videos, Open WebUI will chunk them automatically (needs ffmpeg in the container — already present in most builds)

---

## 7. Custom Logo (PNG)

Current logo is `logo.svg` (clean wordmark + orange dot).

To use a PNG instead:
1. Create a transparent PNG (recommended 200×60 or square)
2. Place it as `logo.png` in this folder
3. Uncomment the PNG volume line in docker-compose.yml
4. Restart

---

## 8. Even More Aggressive CSS

The current `custom.css` already hides a lot of chrome.
If you want it even more minimal (almost pure chat), tell me and I can strip more elements (sidebar labels, version info, extra buttons, etc.).

---

## Quick Priority Checklist

- [x] Password strength rules
- [x] Ability to hide Sign Up
- [x] OAuth ready (Google + GitHub)
- [x] Voice Mode + TTS configuration path
- [x] Aggressive CSS
- [x] Logo
- [ ] Full 3D pipeline (needs custom function + renderer)
- [ ] Advanced video understanding pipeline

Tell me which of the remaining items you want me to build next.

---

## 9. Multi-Model Support

Open WebUI already supports multiple models at the same time.

### How to use multi-model
1. Connect several providers (Ollama + xAI + OpenAI + Anthropic…)
2. In a chat you can switch models or run side-by-side comparison
3. You can assign different models different roles (e.g. one for coding, one for 3D, one for vision)

### Recommended setup for Jayson
- Main conversational model (Grok / Claude / GPT)
- Vision model (for images & screenshots)
- Coding / tool-calling model (for Blender scripts)
- Optional: local small model for fast responses

Just add the corresponding API keys / Ollama models in Admin Panel or via environment variables.

---

## 10. Full Blender Control (3D Modeling)

See the dedicated folder: `blender/`

**Current status:**
- Architecture defined
- Example high-level tools written (`example_tools.py`)
- Jayson can be given tools to create objects, materials, render, export GLB, and run arbitrary `bpy` code

**To make it live:**
1. Install Blender 4.x on the host
2. Convert the example tools into Open WebUI Tools / Functions
3. Give Jayson the `blender_run_script` tool for full power
4. Optionally add automatic screenshot + description after every change

This is the path to “fully manipulate Blender”.
