# Jayson Advanced Pipelines

## 1. 3D Model → Screenshots + Description

**Location:** `pipelines/3d_screenshots/pipeline.py`

**What it does:**
- Takes any 3D model (GLB, OBJ, FBX, BLEND)
- Renders 6 clean angles (front, back, left, right, top, 3/4)
- Prepares a vision prompt so Jayson (or any vision model) can write a detailed description

**Main function:** `model_to_screenshots_and_description(model_path)`

**Typical flow:**
1. User or previous step provides a .glb
2. Call the pipeline → get images
3. Feed images + vision prompt to a vision model
4. Get rich text description of the 3D asset

---

## 2. Advanced Video Understanding

**Location:** `pipelines/video_understanding/pipeline.py`

**What it does:**
- Extracts audio and transcribes it
- Extracts key frames
- Prepares everything for a vision model + final summary

**Main function:** `full_video_understanding(video_path)`

**Requires:** `ffmpeg` (usually already present)

**Optional:** `faster-whisper` for local transcription

---

## 3. Local High-Quality TTS (Kokoro)

**Location:** `tts/` + `docker-compose.full.yml`

**How to start:**
```bash
docker compose -f docker-compose.full.yml up -d
```

TTS will be available at: `http://localhost:8880`

**Configure in Open WebUI:**
1. Admin Panel → Settings → Audio
2. TTS Engine: OpenAI
3. API Base URL: `http://host.docker.internal:8880/v1` (or `http://jayson-tts:8880/v1` from inside the network)
4. API Key: any value (or leave as needed by the image)
5. Choose a Kokoro voice

Now Voice Mode and message read-aloud will use high-quality local TTS.

---

## Activation Order Recommendation

1. Start the full stack (`docker-compose.full.yml`)
2. Configure Audio in Admin Panel (point to the TTS service)
3. Turn the Python pipelines into Open WebUI Tools / Functions
4. Give Jayson access to the 3D screenshot and video tools
