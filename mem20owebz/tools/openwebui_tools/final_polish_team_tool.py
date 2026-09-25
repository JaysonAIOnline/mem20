"""
title: Final Polish Team
author: Jayson
version: 1.0
description: Multi-agent final polish pass to maximize fidelity to the Production Package (target 94%+).
"""

from pydantic import BaseModel, Field
from typing import Optional
import json
from datetime import datetime


class Tools:
    class Valves(BaseModel):
        fidelity_target: float = Field(default=0.94, description="Minimum fidelity score 0-1")
        max_polish_rounds: int = Field(default=3, description="Max full-team polish rounds")

    def __init__(self):
        self.valves = self.Valves()

    def start_final_polish(
        self,
        project_name: str,
        production_package_summary: str,
        deliverable_inventory: str,
    ) -> str:
        """
        Start a supervised final polish campaign against the production package.
        :param project_name: Project name
        :param production_package_summary: Key [HUMAN] intents, pillars, slice criteria
        :param deliverable_inventory: Comma-separated list of finished artifacts to polish
        """
        agents = [
            {"id": "FidelityAuditor", "job": "Score each deliverable vs package sections; list gaps"},
            {"id": "ConsistencyEditor", "job": "Align names, tone, numbers, and continuity across docs/assets"},
            {"id": "SystemsBalancer", "job": "Check loop clarity, economy, difficulty vs stated targets"},
            {"id": "NarrativePolisher", "job": "Tighten logline/quests/dialogue against theme and pillars"},
            {"id": "ArtAssetAuditor", "job": "Verify P0 models/UI/textures exist and match art pillars"},
            {"id": "AudioAuditor", "job": "Verify VO/music/SFX coverage and mix targets"},
            {"id": "LevelFlowAuditor", "job": "Check level graphs for soft-locks and readability"},
            {"id": "UIUXAuditor", "job": "Check UI hierarchy, contrast, platform safe zones"},
            {"id": "VRComfortAuditor", "job": "If VR in scope: comfort, locomotion, performance budgets"},
            {"id": "ExportReadiness", "job": "Platform matrix vs actual build notes"},
            {"id": "IntegrationLead", "job": "Merge fix lists; order rework by severity"},
            {"id": "QAGateCaptain", "job": "Re-run qa_inspect + qa_gate; block delivery under target"},
        ]
        return json.dumps({
            "campaign": "FINAL_POLISH",
            "project": project_name,
            "fidelity_target": self.valves.fidelity_target,
            "max_rounds": self.valves.max_polish_rounds,
            "package_summary": production_package_summary,
            "inventory": [x.strip() for x in deliverable_inventory.split(",") if x.strip()],
            "team": agents,
            "protocol": [
                "1. FidelityAuditor scores every inventory item against package (0-100%)",
                "2. Any item < target → assigned specialist produces fix list",
                "3. IntegrationLead prioritizes Critical → Major → Minor",
                "4. Rework via Tight Agent Loop on each gap",
                "5. QAGateCaptain re-scores; repeat until average >= target or max_rounds",
                "6. Only then ALLOW_DELIVERY",
            ],
            "started_at": datetime.utcnow().isoformat() + "Z",
        }, indent=2)

    def score_fidelity(
        self,
        section: str,
        package_requirement: str,
        deliverable_summary: str,
        score_0_to_100: float,
        gaps: str = "",
    ) -> str:
        """
        Record a fidelity score for one package section vs deliverable.
        :param section: e.g. story, systems, assets_3d, ui, vr, vertical_slice
        :param package_requirement: What the package demanded
        :param deliverable_summary: What exists now
        :param score_0_to_100: Estimated fidelity
        :param gaps: Missing or wrong items
        """
        target = self.valves.fidelity_target * 100
        return json.dumps({
            "section": section,
            "requirement": package_requirement,
            "deliverable": deliverable_summary,
            "score": score_0_to_100,
            "target": target,
            "meets_target": score_0_to_100 >= target,
            "gaps": [g.strip() for g in gaps.split(";") if g.strip()],
            "action": "PASS" if score_0_to_100 >= target else "REWORK_REQUIRED",
        }, indent=2)

    def polish_round_summary(
        self,
        project_name: str,
        round_number: int,
        section_scores_csv: str,
        open_criticals: str = "",
    ) -> str:
        """
        Summarize one polish round.
        :param section_scores_csv: format section:score,section:score
        :param open_criticals: remaining critical gaps
        """
        scores = {}
        for part in section_scores_csv.split(","):
            part = part.strip()
            if ":" in part:
                k, v = part.split(":", 1)
                try:
                    scores[k.strip()] = float(v.strip())
                except ValueError:
                    pass
        avg = sum(scores.values()) / len(scores) if scores else 0.0
        target = self.valves.fidelity_target * 100
        criticals = [c.strip() for c in open_criticals.split(";") if c.strip()]
        return json.dumps({
            "project": project_name,
            "round": round_number,
            "section_scores": scores,
            "average_fidelity": round(avg, 2),
            "target": target,
            "open_criticals": criticals,
            "verdict": (
                "READY_FOR_DELIVERY_GATE"
                if avg >= target and not criticals
                else "CONTINUE_POLISH"
            ),
        }, indent=2)

    def fidelity_team_prompts(self) -> str:
        """Return system prompts for each polish agent."""
        return json.dumps({
            "FidelityAuditor": "You compare deliverables only against the Production Package. Score 0-100. No credit for extra scope.",
            "ConsistencyEditor": "You enforce one canon: names, stats, tone. Eliminate contradictions.",
            "SystemsBalancer": "You verify core loop and numbers match package targets. Flag exploits and dead systems.",
            "NarrativePolisher": "You align story/quests with theme and pillars. Cut drift.",
            "ArtAssetAuditor": "You check P0 asset list completeness and art-pillar fit.",
            "AudioAuditor": "You check VO/music/SFX coverage and mix notes.",
            "LevelFlowAuditor": "You hunt soft-locks, dead ends, and unreadable spaces.",
            "UIUXAuditor": "You verify hierarchy, contrast, and platform safe areas.",
            "VRComfortAuditor": "You enforce comfort, locomotion, and perf budgets for VR targets.",
            "ExportReadiness": "You match export matrix to real build notes; mark PREP_ONLY honestly.",
            "IntegrationLead": "You merge fixes, order by severity, prevent duplicate work.",
            "QAGateCaptain": "You run final qa_gate. Block delivery below fidelity target or with Criticals.",
        }, indent=2)
