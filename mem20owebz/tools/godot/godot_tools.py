"""
title: Godot Tools
author: Jayson
version: 1.0
description: Helpers for Godot 4.x project layout, import, scenes, and export presets (pairs with asset_assembly + production run).
"""

from pydantic import BaseModel, Field
from typing import Optional
import json


class Tools:
    class Valves(BaseModel):
        godot_bin: str = Field(default="godot", description="Godot CLI binary name or path")
        project_path: str = Field(default="projects/my_game/engine_project", description="Godot project root")

    def __init__(self):
        self.valves = self.Valves()

    def godot_project_skeleton(self, game_name: str, perspective: str = "third_person") -> str:
        """
        Propose a clean Godot 4 project layout mapped to Jayson asset_assembly.
        :param game_name: Project name
        :param perspective: first_person | third_person | top_down | racing
        """
        return json.dumps({
            "engine": "Godot 4.x",
            "game_name": game_name,
            "perspective": perspective,
            "folders": {
                "res://scenes/": "Main, levels, UI",
                "res://scenes/levels/": "One scene per LVL_ id",
                "res://actors/": "Characters, enemies (CH_/CR_)",
                "res://props/": "PR_ assets",
                "res://weapons/": "WP_",
                "res://vehicles/": "VH_",
                "res://ui/": "UI_ screens and HUD",
                "res://audio/": "VO_/MUS_/SFX_ mapped from audio/",
                "res://assets/imported/": "Only validated assets from art/ (not _incoming)",
                "res://scripts/": "Gameplay code",
                "res://export/": "Export presets notes",
            },
            "rules": [
                "Import only assets with status=validated or integrated in assets_master.csv",
                "Scene names match LVL_ / SCN_ ids",
                "Keep default_env and project.godot under version control",
            ],
            "next": "Create project in editor or `godot --path <dir> --editor` then run godot_import_plan",
        }, indent=2)

    def godot_import_plan(self, asset_ids_csv: str, source_root: str = "art/") -> str:
        """
        Plan importing a list of manifest asset IDs into Godot.
        :param asset_ids_csv: Comma-separated asset ids
        :param source_root: Host folder root from asset_assembly
        """
        ids = [a.strip() for a in asset_ids_csv.split(",") if a.strip()]
        return json.dumps({
            "imports": [
                {
                    "asset_id": i,
                    "from": f"{source_root}/... (resolve via assets_master.csv path)",
                    "to": f"res://assets/imported/{i}/",
                    "import_hints": "Prefer glTF/GLB; set mesh compression; generate collision only if needed",
                }
                for i in ids
            ],
            "command_hints": [
                "Open Godot → Import dock, or copy files into res:// and reimport",
                f"CLI check: {self.valves.godot_bin} --path {self.valves.project_path} --headless --quit",
            ],
        }, indent=2)

    def godot_export_presets(self, platforms_csv: str = "Windows,Linux,Android") -> str:
        """
        Checklist for Godot export presets matching Jayson export_targets.
        :param platforms_csv: Windows, Linux, Android, Web, etc.
        """
        platforms = [p.strip() for p in platforms_csv.split(",") if p.strip()]
        presets = {
            "Windows": ["Executable template", "x86_64", "embed PCK optional", "export to builds/windows/"],
            "Linux": ["x86_64 binary", "export to builds/linux/", "chmod +x"],
            "Android": ["Install Android build template", "keystore", "arm64-v8a", "export APK/AAB"],
            "Web": ["Web export template", "SharedArrayBuffer notes", "not a substitute for Quest native"],
        }
        return json.dumps({
            "requested": platforms,
            "steps": {p: presets.get(p, ["Add preset in Project → Export"]) for p in platforms},
            "vr_note": "Quest uses Android export + Meta packaging; follow export_targets.md Quest section",
            "qa": "qa_inspect export after each preset smoke test",
        }, indent=2)

    def godot_slice_scene_checklist(self, level_id: str = "LVL_01") -> str:
        """Vertical slice scene requirements in Godot."""
        return json.dumps({
            "main_scene": "res://scenes/main.tscn",
            "level_scene": f"res://scenes/levels/{level_id}.tscn",
            "must_have": [
                "Player spawn",
                "Win/lose or finish trigger",
                "HUD instance",
                "Audio bus layout",
                "Only integrated P0 assets",
            ],
            "run": f"{self.valves.godot_bin} --path {self.valves.project_path}",
        }, indent=2)
