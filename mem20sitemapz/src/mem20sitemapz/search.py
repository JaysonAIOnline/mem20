"""Ranked search over the generated sitemap index."""

from __future__ import annotations

from typing import Any

FIELD_WEIGHTS = (
    ("name", 10.0),
    ("entry_points", 8.0),
    ("keywords", 6.0),
    ("dir", 5.0),
    ("modules", 4.0),
    ("description", 3.0),
    ("readme_text", 2.0),
    ("readme_summary", 2.5),
    ("subdirs", 1.5),
    ("docs", 1.0),
    ("dependencies", 1.0),
)


def _haystack(entry: dict[str, Any], field: str) -> str:
    value = entry.get(field)
    if value is None:
        return ""
    if isinstance(value, dict):
        parts = []
        for key, val in value.items():
            parts.append(str(key))
            parts.append(str(val))
        return " ".join(parts)
    if isinstance(value, list):
        return " ".join(str(v) for v in value)
    return str(value)


def score(entry: dict[str, Any], query: str) -> float:
    tokens = [t for t in query.lower().split() if t]
    if not tokens:
        return 0.0
    total = 0.0
    name = str(entry.get("name", "")).lower()
    for token in tokens:
        matched_any = False
        for field, weight in FIELD_WEIGHTS:
            hay = _haystack(entry, field).lower()
            if not hay:
                continue
            if token not in hay:
                continue
            matched_any = True
            bonus = 0.0
            if field == "name":
                if name == token:
                    bonus = weight * 2.0
                elif name.startswith(token):
                    bonus = weight * 1.5
            total += weight + bonus
        if not matched_any:
            return 0.0
    return total


def search(index: dict[str, Any], query: str, limit: int = 20) -> list[dict[str, Any]]:
    results = []
    for entry in index.get("subsystems", []):
        value = score(entry, query)
        if value > 0:
            results.append({"score": round(value, 2), "entry": entry})
    results.sort(key=lambda item: (-item["score"], item["entry"]["name"]))
    return results[:limit]


def find(index: dict[str, Any], name: str) -> dict[str, Any] | None:
    lowered = name.lower()
    for entry in index.get("subsystems", []):
        if lowered in (str(entry.get("name", "")).lower(), str(entry.get("dir", "")).lower()):
            return entry
    hits = search(index, name, limit=1)
    return hits[0]["entry"] if hits else None


def brief(entry: dict[str, Any]) -> str:
    points = [f"{entry['name']} [{entry['category']}]"]
    summary = entry.get("description") or entry.get("readme_summary") or ""
    if summary:
        points.append(summary)
    points.append(
        f"files={entry['file_count']} lines={entry['line_count']} tests={entry['test_files']}"
    )
    langs = ", ".join(f"{k}:{v}" for k, v in list(entry.get("languages", {}).items())[:4])
    if langs:
        points.append(f"langs {langs}")
    scripts = entry.get("entry_points") or {}
    if scripts:
        points.append("entry_points " + ", ".join(sorted(scripts)))
    return " | ".join(points)
