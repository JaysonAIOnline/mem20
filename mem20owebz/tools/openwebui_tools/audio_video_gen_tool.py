"""
title: Audio & Video Generation
author: Jayson
version: 1.0
description: Text-to-audio (TTS + music/sfx guidance) and text-to-video planning with strong defaults.
"""

from pydantic import BaseModel, Field
from typing import Optional
import json


class Tools:
    class Valves(BaseModel):
        # Local Kokoro is already in the stack; these are for extra providers
        elevenlabs_api_key: str = Field(default="", description="ElevenLabs API key")
        openai_api_key: str = Field(default="", description="OpenAI API key for TTS")
        preferred_voice: str = Field(default="warm_narrator", description="Default voice style")

    def __init__(self):
        self.valves = self.Valves()

    def text_to_speech(
        self,
        text: str,
        voice: Optional[str] = None,
        style: str = "clear",
        provider: str = "kokoro",
    ) -> str:
        """
        Convert text to speech. Prefers local Kokoro; can guide external high-quality voices.
        :param text: Text to speak
        :param voice: Voice name or style (warm_narrator, energetic, calm, character, etc.)
        :param style: clear, dramatic, conversational, whisper
        :param provider: kokoro (local), elevenlabs, openai
        """
        voice = voice or self.valves.preferred_voice

        plan = {
            "task": "text_to_speech",
            "text": text[:500] + ("..." if len(text) > 500 else ""),
            "full_length_chars": len(text),
            "voice": voice,
            "style": style,
            "provider": provider,
            "local_first": {
                "kokoro": "Already running in Jayson stack on port 8880. Use Open WebUI Audio settings → point TTS to http://host.docker.internal:8880/v1",
                "recommendation": "Use Kokoro for free unlimited local speech. Switch to ElevenLabs/OpenAI only when you need specific celebrity-style or ultra-premium voices.",
            },
            "external": {
                "elevenlabs": {
                    "env": "ELEVENLABS_API_KEY",
                    "notes": "Best emotional range. Create voice or use preset.",
                },
                "openai": {
                    "env": "OPENAI_API_KEY",
                    "model": "gpt-4o-mini-tts or tts-1-hd",
                    "voices": ["alloy", "echo", "fable", "onyx", "nova", "shimmer"],
                },
            },
            "audio_direction": {
                "pacing": "Slightly slower than normal conversation for clarity",
                "emphasis": "Stress key nouns and emotional turns",
                "breathing": "Natural pauses at commas and periods",
            },
            "next_step": "If using local Kokoro, just enable Voice Mode in Open WebUI. For external, call the provider then attach the audio file.",
        }
        return json.dumps(plan, indent=2)

    def text_to_audio_scene(
        self,
        description: str,
        duration_seconds: int = 30,
        include_music: bool = True,
        include_sfx: bool = True,
    ) -> str:
        """
        Design a full audio scene (narration + music + sfx) from a description.
        :param description: What the scene should sound like
        :param duration_seconds: Target length
        :param include_music: Whether to plan background music
        :param include_sfx: Whether to plan sound effects
        """
        return json.dumps({
            "task": "audio_scene",
            "description": description,
            "duration_seconds": duration_seconds,
            "layers": {
                "narration": "Main spoken line or VO – use text_to_speech tool",
                "music": "Subtle underscore matching mood" if include_music else None,
                "sfx": "Environmental and action sounds" if include_sfx else None,
            },
            "suggested_tools": [
                "Kokoro / ElevenLabs for voice",
                "Musicgen / Stable Audio / Suno-style for music (external)",
                "Freesound or generated SFX libraries",
            ],
            "mix_notes": "Voice on top, music -12 to -18 LUFS under dialogue, SFX supporting not masking",
        }, indent=2)

    def text_to_video(
        self,
        prompt: str,
        duration_seconds: int = 5,
        style: str = "cinematic",
        provider: str = "luma",
    ) -> str:
        """
        Plan / generate a short video from text (Luma Dream Machine, Runway, Kling, etc.).
        :param prompt: Detailed visual + motion description
        :param duration_seconds: Target length
        :param style: cinematic, anime, realistic, product, documentary
        :param provider: luma, runway, kling, minimax, etc.
        """
        plan = {
            "task": "text_to_video",
            "prompt": prompt,
            "duration_seconds": duration_seconds,
            "style": style,
            "provider": provider,
            "providers": {
                "luma": {
                    "name": "Luma Dream Machine",
                    "notes": "Excellent motion and cinematic quality. Use LUMA_API_KEY.",
                    "endpoint_hint": "https://api.lumalabs.ai/dream-machine/v1/generations",
                },
                "runway": {
                    "name": "Runway Gen-3 / Gen-4",
                    "notes": "Strong control and quality. Requires RUNWAY_API_KEY.",
                },
                "kling": {
                    "name": "Kling AI",
                    "notes": "Good longer clips and motion.",
                },
            },
            "prompt_tips": [
                "Describe camera move (pan, dolly, orbit, handheld)",
                "Describe lighting and time of day",
                "Describe subject action clearly",
                "Keep one main action per short clip",
            ],
            "workflow": [
                "1. Generate clip with chosen provider",
                "2. Download mp4",
                "3. Optionally run Video Understanding tool for QC",
                "4. Use in storyline / edit",
            ],
        }
        return json.dumps(plan, indent=2)
