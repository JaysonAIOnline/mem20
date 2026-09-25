"""
title: Text & Image to 3D
author: Jayson
version: 1.1
description: Generate 3D models from text or images via Luma, Meshy, Tripo and similar APIs. Returns guidance + ready API call patterns.
"""

from pydantic import BaseModel, Field
from typing import Optional
import json
import os


class Tools:
    class Valves(BaseModel):
        luma_api_key: str = Field(default="", description="Luma AI API key")
        meshy_api_key: str = Field(default="", description="Meshy API key")
        tripo_api_key: str = Field(default="", description="Tripo3D API key")
        preferred_provider: str = Field(default="luma", description="luma | meshy | tripo | auto")

    def __init__(self):
        self.valves = self.Valves()

    def text_to_3d(
        self,
        prompt: str,
        provider: Optional[str] = None,
        style: str = "realistic",
        output_format: str = "glb",
    ) -> str:
        """
        Create a 3D model from a text description.
        :param prompt: Detailed description of the 3D object/scene
        :param provider: luma, meshy, tripo, or auto
        :param style: realistic, stylized, lowpoly, sculpt
        :param output_format: glb, obj, fbx
        """
        provider = (provider or self.valves.preferred_provider or "luma").lower()

        plan = {
            "task": "text_to_3d",
            "prompt": prompt,
            "style": style,
            "output_format": output_format,
            "recommended_provider": provider,
            "workflow": [
                "1. Call the chosen provider API with the prompt",
                "2. Download the resulting .glb / .obj",
                "3. Optionally refine in Blender using Jayson Blender tools",
                "4. Generate turntable screenshots with the 3D Screenshots tool",
                "5. Import into Unity if needed",
            ],
            "api_patterns": {},
            "tips": [
                "Be very specific about shape, materials, scale, and silhouette",
                "Mention 'single object, clean topology, centered' for better results",
                "Iterate: generate → review screenshots → refine prompt or sculpt in Blender",
            ],
        }

        # Luma Dream Machine / Genie style
        plan["api_patterns"]["luma"] = {
            "note": "Luma AI (Dream Machine / Genie 3D). Set LUMA_API_KEY or valves.luma_api_key",
            "endpoint_example": "https://api.lumalabs.ai/dream-machine/v1/generations",
            "body_example": {
                "prompt": prompt,
                "model": "ray-v2",  # or current 3D model name
                "aspect_ratio": "16:9",
            },
            "env": "LUMA_API_KEY",
        }

        # Meshy
        plan["api_patterns"]["meshy"] = {
            "note": "Meshy text-to-3D. Set MESHY_API_KEY",
            "endpoint_example": "https://api.meshy.ai/openapi/v2/text-to-3d",
            "body_example": {
                "mode": "preview",
                "prompt": prompt,
                "art_style": style,
                "should_remesh": True,
            },
            "env": "MESHY_API_KEY",
        }

        # Tripo
        plan["api_patterns"]["tripo"] = {
            "note": "Tripo3D. Set TRIPO_API_KEY",
            "endpoint_example": "https://api.tripo3d.ai/v2/openapi/task",
            "body_example": {
                "type": "text_to_model",
                "prompt": prompt,
            },
            "env": "TRIPO_API_KEY",
        }

        plan["next_action"] = (
            f"Use provider '{provider}'. "
            "If you have the API key configured as a tool valve or env var, call the provider. "
            "Otherwise return the prepared prompt and ask the user to run the generation, then feed the .glb back for Blender refinement."
        )

        return json.dumps(plan, indent=2)

    def image_to_3d(
        self,
        image_description: str,
        provider: Optional[str] = None,
        notes: str = "",
    ) -> str:
        """
        Create a 3D model from an image (or detailed description of an uploaded image).
        :param image_description: Description of the image or what to extract
        :param provider: luma, meshy, tripo, or auto
        :param notes: Extra instructions (e.g. 'focus on the character only')
        """
        provider = (provider or self.valves.preferred_provider or "meshy").lower()

        plan = {
            "task": "image_to_3d",
            "image_description": image_description,
            "notes": notes,
            "recommended_provider": provider,
            "workflow": [
                "1. Upload / pass the image to the provider's image-to-3D endpoint",
                "2. Download the mesh (.glb preferred)",
                "3. Clean up in Blender (origin, scale, materials)",
                "4. Run 3D Screenshots tool for multi-angle review",
                "5. Iterate if topology or silhouette needs work",
            ],
            "providers": {
                "luma": "Strong for cinematic / Dream Machine related 3D assets",
                "meshy": "Excellent dedicated image-to-3D and text-to-3D",
                "tripo": "Fast image-to-3D, good for characters and objects",
            },
            "refinement_prompt_for_blender": (
                f"Import the generated model. Center it, apply reasonable scale, "
                f"and improve: {notes or image_description}. Keep clean topology."
            ),
        }
        return json.dumps(plan, indent=2)

    def refine_3d_plan(self, current_issues: str, goal: str = "production ready") -> str:
        """
        Plan the next Blender refinement steps for a generated 3D model.
        :param current_issues: What is wrong (e.g. 'messy topology, floating parts')
        :param goal: Target quality
        """
        return json.dumps({
            "goal": goal,
            "issues": current_issues,
            "blender_steps": [
                "Import GLB/OBJ",
                "Origin to geometry + center at world origin",
                "Apply scale/rotation",
                "Merge by distance / cleanup loose geometry",
                "Remesh or retopo if needed",
                "UV unwrap if materials require it",
                "Export clean GLB",
                "Generate turntable screenshots",
            ],
            "suggested_jayson_tools": [
                "Blender tools (run_bpy / export_glb)",
                "3D Screenshots tool",
                "Unity import tool if game-ready",
            ],
        }, indent=2)
