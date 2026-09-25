#!/usr/bin/env python3
"""Write qa/STATUS.md from a simple JSON snapshot of a production run."""
from __future__ import annotations
import json, sys
from pathlib import Path
from datetime import datetime, timezone

TEMPLATE = """# Production status — {project}

Updated: {ts}

| Field | Value |
|-------|--------|
| Stage | {stage} ({stage_id}) |
| Engine | {engine} |
| Genre | {genre} |
| Fidelity avg | {fidelity}% (target 94) |
| Open criticals | {criticals} |
| Verdict | **{verdict}** |

## Blockers
{blockers}

## Next
{next_action}
"""

def main(src: str, dest: str) -> int:
    data = json.loads(Path(src).read_text(encoding="utf-8"))
    blockers = data.get("blockers") or []
    md = TEMPLATE.format(
        project=data.get("project", "unknown"),
        ts=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        stage=data.get("stage_name", "?"),
        stage_id=data.get("stage_id", "?"),
        engine=data.get("engine", "?"),
        genre=data.get("genre", "?"),
        fidelity=data.get("fidelity_avg", 0),
        criticals=len(data.get("criticals") or []),
        verdict=data.get("verdict", "IN_PROGRESS"),
        blockers="\n".join(f"- {b}" for b in blockers) or "- none",
        next_action=data.get("next_action", "Continue current stage; QA before advance."),
    )
    out = Path(dest)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(f"wrote {out}")
    return 0

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: status_dashboard.py snapshot.json qa/STATUS.md")
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2]))
