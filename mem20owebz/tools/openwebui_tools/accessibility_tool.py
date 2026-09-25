"""
title: Accessibility Pass
author: Jayson
version: 1.0
description: Score a vertical slice against the accessibility checklist.
"""

from pydantic import BaseModel, Field
import json


class Tools:
    class Valves(BaseModel):
        fail_on_color_only: bool = Field(default=True)

    def __init__(self):
        self.valves = self.Valves()

    def accessibility_inspect(
        self,
        project_name: str,
        has_subtitles: str = "unknown",
        color_only_signals: str = "unknown",
        remappable_controls: str = "unknown",
        invert_look: str = "unknown",
        vr_in_scope: str = "no",
        notes: str = "",
    ) -> str:
        """
        Inspect accessibility for a slice. Answers: yes / no / unknown / n/a
        """
        def yn(v):
            return (v or "unknown").strip().lower()

        fails = []
        if yn(color_only_signals) == "yes" and self.valves.fail_on_color_only:
            fails.append("Color-only win/lose or routing signals")
        if yn(remappable_controls) == "no":
            fails.append("Controls not remappable")
        if yn(has_subtitles) == "no":
            fails.append("No subtitle toggle")
        if yn(vr_in_scope) == "yes" and yn(invert_look) == "no":
            fails.append("VR in scope without comfort/invert options noted")
        verdict = "FAIL" if fails else "PASS_WITH_NOTES" if "unknown" in (
            yn(has_subtitles), yn(color_only_signals), yn(remappable_controls)
        ) else "PASS"
        return json.dumps({
            "project": project_name,
            "verdict": verdict,
            "fails": fails,
            "notes": notes,
            "pipeline": "pipelines/games/accessibility.md",
        }, indent=2)
