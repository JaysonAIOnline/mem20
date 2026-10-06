"""Studio: transcripts become markdown deliverables."""

from __future__ import annotations

from pathlib import Path


def export_markdown(room: str, topic: str, messages: list[dict],
                    out_path: str | Path) -> Path:
    """Render a room transcript to a markdown file. Returns its path."""
    if not messages:
        raise ValueError("refusing to export an empty transcript")
    lines = [f"# {room}", ""]
    if topic:
        lines += [f"Topic: {topic}", ""]
    lines.append("## Transcript")
    lines.append("")
    for msg in messages:
        lines.append(f"- **{msg['sender']}**: {msg['text']}")
    lines += ["", f"_Exported {len(messages)} messages._", ""]
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
