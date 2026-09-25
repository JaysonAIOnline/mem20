"""
Advanced Video Understanding Pipeline
=====================================

Steps:
1. Extract audio → transcribe (Whisper / faster-whisper / OpenAI)
2. Extract key frames (scene changes or evenly spaced)
3. Describe key frames with a vision model
4. Combine transcript + visual descriptions into a rich summary

Requires: ffmpeg, and optionally faster-whisper or an STT API
"""

import subprocess
import tempfile
import os
from pathlib import Path
from typing import List, Dict, Optional
import json

OUTPUT_DIR = Path.home() / "jayson_3d" / "video_analysis"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def extract_audio(video_path: str, output_audio: Optional[str] = None) -> dict:
    """Extract audio track as wav."""
    video_path = Path(video_path)
    if output_audio is None:
        output_audio = OUTPUT_DIR / f"{video_path.stem}_audio.wav"
    else:
        output_audio = Path(output_audio)

    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        str(output_audio)
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return {
            "success": result.returncode == 0,
            "audio_path": str(output_audio) if result.returncode == 0 else None,
            "stderr": result.stderr[-1000:]
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def extract_keyframes(
    video_path: str,
    max_frames: int = 12,
    method: str = "fps"  # "fps" or "scene"
) -> dict:
    """
    Extract key frames.
    method="fps" → evenly spaced
    method="scene" → scene change detection (needs more tuning)
    """
    video_path = Path(video_path)
    out_dir = OUTPUT_DIR / f"{video_path.stem}_frames"
    out_dir.mkdir(parents=True, exist_ok=True)

    if method == "fps":
        # One frame every N seconds (rough)
        cmd = [
            "ffmpeg", "-y", "-i", str(video_path),
            "-vf", f"fps=1/5",  # 1 frame every 5 seconds
            "-frames:v", str(max_frames),
            str(out_dir / "frame_%04d.jpg")
        ]
    else:
        # Simple scene detection
        cmd = [
            "ffmpeg", "-y", "-i", str(video_path),
            "-vf", "select='gt(scene,0.3)',showinfo",
            "-vsync", "vfr",
            "-frames:v", str(max_frames),
            str(out_dir / "frame_%04d.jpg")
        ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        frames = sorted(out_dir.glob("frame_*.jpg"))
        return {
            "success": result.returncode == 0,
            "frames": [str(f) for f in frames],
            "output_dir": str(out_dir)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def transcribe_audio(audio_path: str, language: str = "en") -> dict:
    """
    Transcribe using faster-whisper if available, otherwise return instructions
    for Open WebUI's built-in STT.
    """
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segments, info = model.transcribe(audio_path, language=language)
        text = " ".join([seg.text for seg in segments])
        return {
            "success": True,
            "text": text,
            "language": info.language
        }
    except ImportError:
        return {
            "success": False,
            "message": "faster-whisper not installed. Use Open WebUI Audio STT instead, or pip install faster-whisper",
            "audio_path": audio_path
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def full_video_understanding(video_path: str, max_frames: int = 10) -> dict:
    """
    Complete pipeline entry point.
    Returns everything needed for Jayson to produce a rich summary.
    """
    video_path = str(Path(video_path).resolve())
    results = {"video": video_path}

    # 1. Audio
    audio_res = extract_audio(video_path)
    results["audio"] = audio_res

    # 2. Transcription
    if audio_res.get("success") and audio_res.get("audio_path"):
        transcript = transcribe_audio(audio_res["audio_path"])
        results["transcript"] = transcript
    else:
        results["transcript"] = {"success": False, "message": "No audio extracted"}

    # 3. Key frames
    frames_res = extract_keyframes(video_path, max_frames=max_frames)
    results["frames"] = frames_res

    # 4. Guidance for vision description
    if frames_res.get("success") and frames_res.get("frames"):
        results["vision_prompt"] = f"""
Here are {len(frames_res['frames'])} key frames from a video.
Describe what is happening visually across the frames.
Note important objects, actions, text on screen, and overall narrative.
Combine this later with the transcript for a full understanding.
"""
        results["next_step"] = "Send frames + vision_prompt to a vision model, then combine with transcript."

    return results
