"""Prompt rendering for mem20orcaz.

Pure-stdlib replacement for OrKa's SimplifiedPromptRenderer + Jinja2 templates.
Supports ``{{ var }}`` interpolation with dotted paths and a small set of filters
over the context object passed into templates (input / previous_outputs /
agent_id / run_id / metadata / trace_id). Unresolved variables render as an
empty string rather than fabricating content.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional

_VAR_RE = re.compile(r"\{\{\s*(.*?)\s*\}\}")

FILTERS: Dict[str, Callable[[Any], Any]] = {
    "str": str,
    "upper": lambda v: str(v).upper(),
    "lower": lambda v: str(v).lower(),
    "strip": lambda v: str(v).strip(),
}


def _resolve_path(root: Any, path: str) -> Any:
    """Resolve a dotted path (``previous_outputs.retriever.response``) on root."""
    node = root
    for part in path.split("."):
        if not part:
            return None
        if isinstance(node, dict):
            node = node.get(part)
        elif isinstance(node, (list, tuple)):
            try:
                node = node[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            try:
                node = getattr(node, part)
            except (AttributeError, TypeError):
                return None
        if node is None:
            return None
    return node


def _apply_filters(value: Any, chunks: List[str]) -> Any:
    """Apply a chain of filters in order (``[str|upper]``)."""
    for chunk in chunks:
        name = chunk.strip()
        if not name:
            continue
        if name not in FILTERS:
            return None
        value = FILTERS[name](value)
    return value


def render_template(template: str, context: Optional[Dict[str, Any]] = None, allow_unresolved: bool = True) -> str:
    """Render a ``{{ ... }}`` template against ``context``.

    Mirrors OrKa's simplified rendering: dotted paths are resolved over the
    context dict, an optional ``default='...'`` argument provides a fallback,
    and missing variables render as empty strings.
    """
    if not template:
        return template or ""
    ctx = context or {}

    def _sub(match: re.Match) -> str:
        expr = match.group(1).strip()
        if not expr:
            return ""
        default: Any = None
        if "default=" in expr:
            expr, _, default_raw = expr.rpartition("default=")
            expr = expr.strip().rstrip(",").strip()
            default = _coerce_default(default_raw.strip())
        path_part, *filters_part = expr.split("|")
        path = path_part.strip()
        value = _resolve_path(ctx, path)
        if value is None:
            value = default
        if filters_part:
            value = _apply_filters(value, filters_part)
        if value is None:
            return "" if allow_unresolved else match.group(0)
        return str(value)

    return _VAR_RE.sub(_sub, template)


def _coerce_default(raw: str) -> Any:
    raw = raw.strip()
    if raw.startswith("'") and raw.endswith("'") and len(raw) >= 2:
        return raw[1:-1]
    if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
        return raw[1:-1]
    if raw in ("None", ""):
        return None
    if raw in ("True", "true"):
        return True
    if raw in ("False", "false"):
        return False
    return raw


def extract_template_variables(template: str) -> List[str]:
    """Return the variable paths referenced in a template (deduped, ordered)."""
    seen: List[str] = []
    seen_set: set[str] = set()
    for m in _VAR_RE.finditer(template):
        path, _, _ = m.group(1).partition("|")
        var = path.strip()
        if var and var not in seen_set:
            seen.append(var)
            seen_set.add(var)
    return seen


def safe_get_response(agent_id: str, default: Any, previous_outputs: Any) -> Any:
    """Template helper: fetch an agent's response or a default."""
    if isinstance(previous_outputs, dict):
        entry = previous_outputs.get(agent_id)
        if isinstance(entry, dict):
            if entry.get("response") is not None:
                return entry["response"]
            if entry.get("result") is not None:
                return entry["result"]
            return entry
        if entry is not None:
            return entry
    return default


class TemplateSafeObject:
    """Wraps a payload so templates can index it safely (no KeyError)."""

    def __init__(self, data: Any) -> None:
        object.__setattr__(self, "_TemplateSafeObject__data", data)

    def __getattr__(self, name: str) -> Any:
        data = object.__getattribute__(self, "_TemplateSafeObject__data")
        if isinstance(data, dict):
            return TemplateSafeObject(data.get(name))
        return TemplateSafeObject(None)

    def __getitem__(self, key: Any) -> Any:
        data = object.__getattribute__(self, "_TemplateSafeObject__data")
        if isinstance(data, dict):
            return TemplateSafeObject(data.get(key))
        if isinstance(data, (list, tuple)) and isinstance(key, int):
            try:
                return TemplateSafeObject(data[key])
            except IndexError:
                return TemplateSafeObject(None)
        return TemplateSafeObject(None)

    def __bool__(self) -> bool:
        return bool(object.__getattribute__(self, "_TemplateSafeObject__data"))

    def __str__(self) -> str:
        return str(object.__getattribute__(self, "_TemplateSafeObject__data"))

    def unwrap(self) -> Any:
        return object.__getattribute__(self, "_TemplateSafeObject__data")


class SimplifiedPromptRenderer:
    """Renders agent prompts from a template string + the run context."""

    def __init__(self, allow_unresolved: bool = True) -> None:
        self.allow_unresolved = allow_unresolved

    def render(self, template: str, context: Optional[Dict[str, Any]] = None) -> str:
        return render_template(template, context or {}, allow_unresolved=self.allow_unresolved)