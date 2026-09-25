"""
title: Advanced Video Understanding
author: Jayson
version: 1.0.0
description: Extracts audio transcript + key frames from a video and prepares everything for a rich summary.
requirements: 
"""

import subprocess
from pathlib import Path
from typing import Optional

OUT_DIR = Path.home() / "jayson_3d" / "video_analysis"
OUT_DIR.mkdir(parents=True, exist_ok=True)


class Tools:
    def analyze_video(
        self,
        video_path: str,
        max_frames: int = 10,
        language: str = "en"
    ) -> dict:
        """
        Full video understanding pipeline.
        - Extracts audio and attempts transcription
        - Extracts key frames
        - Returns everything needed for a rich summary
        """
        video_path = Path(video_path).resolve()
        if not video_path.exists():
            return {"success": False, "error": f"Video not found: {video_path}"}

        results = {
            "video": str(video_path),
            "success": True
        }

        # 1. Extract audio
        audio_path = OUT_DIR / f"{video_path.stem}_audio.wav"
        cmd_audio = [
            "ffmpeg", "-y", "-i", str(video_path),
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            str(audio_path)
        ]
        try:
            r = subprocess.run(cmd_audio, capture_output=True, text=True, timeout=120)
            if r.returncode == 0:
                results["audio_path"] = str(audio_path)
            else:
                results["audio_error"] = r.stderr[-800:]
        except Exception as e:
            results["audio_error"] = str(e)

        # 2. Try local transcription (faster-whisper) if available
        transcript = None
        if results.get("audio_path"):
            try:
                from faster_whisper import WhisperModel
                model = WhisperModel("base", device="cpu", compute_type="int8")
                segments, info = model.transcribe(results["audio_path"], language=language)
                transcript = " ".join(seg.text for seg in segments).strip()
                results["transcript"] = transcript
                results["detected_language"] = info.language
            except ImportError:
                results["transcript_note"] = (
                    "faster-whisper not installed. "
                    "You can transcribe the audio_path using Open WebUI's built-in STT instead."
                )
            except Exception as e:
                results["transcript_error"] = str(e)

        # 3. Extract key frames
        frames_dir = OUT_DIR / f"{video_path.stem}_frames"
        frames_dir.mkdir(parents=True, exist_ok=True)

        cmd_frames = [
            "ffmpeg", "-y", "-i", str(video_path),
            "-vf", "fps=1/4",          # roughly one frame every 4 seconds
            "-frames:v", str(max_frames),
            str(frames_dir / "frame_%04d.jpg")
        ]
        try:
            r = subprocess.run(cmd_frames, capture_output=True, text=True, timeout=180)
            frames = sorted(str(p) for p in frames_dir.glob("frame_*.jpg"))
            results["frames"] = frames
            results["frames_dir"] = str(frames_dir)
        except Exception as e:
            results["frames_error"] = str(e)
            results["frames"] = []

        # 4. Vision prompt
        if results.get("frames"):
            results["vision_prompt"] = f"""Here are {len(results['frames'])} key frames extracted from a video.

Describe what is happening visually:
- Main subjects and actions
- Setting / environment
- Any text visible on screen
- Overall narrative or purpose of the video

Be clear and structured."""
            results["next_step"] = (
                "1. Send the frames + vision_prompt to a vision model.\n"
                "2. Combine the visual description with the transcript (if available) "
                "to produce a complete understanding of the video."
            )

        return results
