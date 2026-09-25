"""
title: Status Dashboard
author: Jayson
version: 1.0
description: Snapshot a production run for qa/STATUS.md (pairs with scripts/status_dashboard.py).
"""

from pydantic import BaseModel, Field
import json
from datetime import datetime


class Tools:
    class Valves(BaseModel):
        fidelity_target: float = Field(default=94.0)

    def __init__(self):
        self.valves = self.Valves()

    def snapshot_status(
        self,
        project_name: str,
        stage_id: int,
        stage_name: str,
        engine: str,
        genre: str,
        fidelity_avg: float = 0,
        blockers: str = "",
        next_action: str = "",
    ) -> str:
        """Emit JSON you can save and feed to scripts/status_dashboard.py."""
        crit = [b.strip() for b in blockers.split(";") if b.strip()]
        verdict = "BLOCKED" if crit else (
            "READY_FOR_ADVANCE" if fidelity_avg >= self.valves.fidelity_target else "IN_PROGRESS"
        )
        return json.dumps({
            "project": project_name,
            "stage_id": stage_id,
            "stage_name": stage_name,
            "engine": engine,
            "genre": genre,
            "fidelity_avg": fidelity_avg,
            "criticals": crit,
            "blockers": crit,
            "verdict": verdict,
            "next_action": next_action or "QA then production_run_advance",
            "ts": datetime.utcnow().isoformat() + "Z",
        }, indent=2)
