"""Safe YAML-subset loader for mem20orcaz.

A pure-standard-library replacement for PyYAML supporting the configuration
subset used by OrKa-style workflow YAML: block mappings, block sequences,
inline ``[a, b]`` / ``{k: v}`` flow collections, quoted strings, booleans,
numbers, null and comments. Unsupported input raises ``ConfigError`` rather
than silently misparsing.

This parses *config* documents (orchestrator + agents sections), not arbitrary
YAML. Anything needing the full YAML spec keeps that requirement explicit.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

ParserLine = Tuple[int, str]  # (indent, content-without-comment)


class ConfigError(ValueError):
    """Raised for malformed or unsupported YAML configuration input."""


_HEADER_C = re.compile(r"^#")
_RE_FLOW = re.compile(r"^(\[[^\]]*\]|\{[^\}]*\})\s*$")


class Parser:
    """Internal recursive-descent YAML-parser."""

    def __init__(self, text: str) -> None:
        self._lines = self._preclean(text)

    # -- line handling ------------------------------------------------------
    @staticmethod
    def _strip_comment(line: str) -> str:
        quote: Optional[str] = None
        i = 0
        while i < len(line):
            ch = line[i]
            if quote:
                if ch == quote and (i == 0 or line[i - 1] != "\\"):
                    quote = None
            elif ch in ("'", '"'):
                quote = ch
            elif ch == "#" and (i == 0 or line[i - 1] in (" ", "\t", ":", "-")):
                return line[:i].rstrip()
            i += 1
        return line.rstrip()

    def _preclean(self, text: str) -> List[ParserLine]:
        out: List[ParserLine] = []
        for ln in text.splitlines():
            indent = len(ln) - len(ln.lstrip(" "))
            if "\t" in ln[:indent]:
                raise ConfigError("tabs are not allowed for YAML indentation")
            content = self._strip_comment(ln[indent:]).strip()
            if not content or _HEADER_C.match(content):
                continue
            out.append((indent, content))
        return out

    # -- public entry -------------------------------------------------------
    def parse(self) -> Any:
        if not self._lines:
            return None
        value, _pos = self._parse_block(self._lines[0][0], 0, "$")
        return value

    # -- core recursive descent ---------------------------------------------
    def _parse_block(self, indent: int, pos: int, path: str) -> Tuple[Any, int]:
        """Parse a uniformly-indented block starting at line ``pos``.

        Returns ``(value, next_pos)`` where ``next_pos`` is the first line whose
        indent is lower than ``indent`` (the caller owns it).
        """
        if pos >= len(self._lines):
            return None, pos

        cur_indent, content = self._lines[pos]
        if cur_indent != indent:
            raise ConfigError(f"{path}: unexpected indent {cur_indent} (expected {indent})")
        base = _token(content)
        if base[0] == "-":
            return self._seq(indent, pos, path)
        if _key_content(content) is not None:
            return self._map(indent, pos, path)
        return self._scalar_block(indent, pos, path)

    def _scalar_block(self, indent: int, pos: int, path: str) -> Tuple[Any, int]:
        _, content = self._lines[pos]
        nxt = pos + 1
        while nxt < len(self._lines) and self._lines[nxt][0] > indent:
            raise ConfigError(f"{path}: unexpected indented lines under a scalar")
        if nxt < len(self._lines) and self._lines[nxt][0] == indent:
            raise ConfigError(f"{path}: multiple sibling scalars on one level")
        return _scalar(content, path), nxt

    def _map(self, indent: int, pos: int, path: str) -> Tuple[Dict[str, Any], int]:
        result: Dict[str, Any] = {}
        i = pos
        while i < len(self._lines):
            cur_indent, content = self._lines[i]
            if cur_indent < indent:
                break
            if cur_indent != indent:
                raise ConfigError(f"{path}: bad indent {cur_indent} for mapping key")
            split = _split_key(content)
            if split is None:
                raise ConfigError(f"{path}: expected 'key: value', got {content!r}")
            key, raw_val = split
            if raw_val is not None and raw_val[0] in ("|", ">"):
                # literal / folded block scalar
                parts: List[str] = []
                j = i + 1
                while j < len(self._lines) and self._lines[j][0] > indent:
                    parts.append(self._lines[j][1])
                    j += 1
                body = "\n".join(parts)
                val = body.rstrip("\n") if raw_val[0] == "|" else " ".join(x.strip() for x in parts)
                i = j
            elif raw_val is None:
                # value on following nested block
                if i + 1 < len(self._lines) and self._lines[i + 1][0] > indent:
                    child_indent = self._lines[i + 1][0]
                    val, i = self._parse_block(child_indent, i + 1, f"{path}.{key}")
                else:
                    val, i = None, i + 1
            else:
                i += 1
                if _RE_FLOW.match(raw_val):
                    val = _flow(raw_val, f"{path}.{key}")
                elif raw_val and raw_val[0] in ("[", "{") and not _balanced_flow(raw_val):
                    # multi-line flow collection: fold continuation lines
                    folded = raw_val
                    while i < len(self._lines) and not _balanced_flow(folded):
                        folded += " " + self._lines[i][1]
                        i += 1
                    if not _balanced_flow(folded):
                        raise ConfigError(f"{path}.{key}: unbalanced flow collection")
                    val = _flow(folded, f"{path}.{key}")
                else:
                    val = _scalar(raw_val, f"{path}.{key}")
            result[key] = val
        return result, i

    def _seq(self, indent: int, pos: int, path: str) -> Tuple[List[Any], int]:
        items: List[Any] = []
        i = pos
        while i < len(self._lines):
            cur_indent, content = self._lines[i]
            if cur_indent < indent:
                break
            if cur_indent != indent:
                raise ConfigError(f"{path}: bad indent {cur_indent} for sequence item")
            tok = _token(content)
            if tok[0] != "-":
                break
            rest = content[1:].strip()
            if not rest:
                # item on following nested block
                if i + 1 < len(self._lines) and self._lines[i + 1][0] > indent:
                    child_indent = self._lines[i + 1][0]
                    val, i = self._parse_block(child_indent, i + 1, f"{path}[{len(items)}]")
                else:
                    val, i = None, i + 1
            elif rest.startswith("-"):
                # compact nested sequence: "- - a" (inner items at indent+2)
                nested_indent = indent + 2
                item_lines = [(nested_indent, rest)]
                j = i + 1
                while j < len(self._lines) and self._lines[j][0] >= nested_indent:
                    item_lines.append(self._lines[j])
                    j += 1
                sub = Parser.from_lines(item_lines)
                val, _ = sub._parse_block(nested_indent, 0, f"{path}[{len(items)}]")
                items.append(val)
                i = j
            elif _key_content(rest) is not None and ":" in rest:
                # inline child mapping, possibly with continuation block
                item_lines = [(indent + _MIN_CHILD, rest)]
                j = i + 1
                if j < len(self._lines) and self._lines[j][0] > indent:
                    cc = self._lines[j][0]
                    while j < len(self._lines) and self._lines[j][0] >= cc:
                        item_lines.append(self._lines[j])
                        j += 1
                sub = Parser.from_lines(item_lines)
                val, _ = sub._parse_block(indent + _MIN_CHILD, 0, f"{path}[{len(items)}]")
                i = j
                items.append(val)
            else:
                items.append(_scalar(rest, f"{path}[{len(items)}]"))
                i += 1
        return items, i

    @classmethod
    def from_lines(cls, lines: List[ParserLine]) -> "Parser":
        p = cls.__new__(cls)
        p._lines = list(lines)
        return p


_MIN_CHILD = 2


def _token(content: str) -> str:
    return content.split(" ", 1)[0]


def _split_key(content: str) -> Optional[Tuple[str, Optional[str]]]:
    """Split ``key: value`` at the first unquoted ``: `` boundary.

    Returns ``None`` when the line has no mapping boundary (i.e. it is a plain
    scalar or a sequence token). ``_key_content`` therefore only matches real
    mapping lines.
    """
    quote: Optional[str] = None
    for i, ch in enumerate(content):
        if quote:
            if ch == quote and (i == 0 or content[i - 1] != "\\"):
                quote = None
        elif ch in ("'", '"'):
            quote = ch
        elif ch == ":" and (i + 1 >= len(content) or content[i + 1] in (" ", "", "\t")):
            key = content[:i].strip().strip("'\"")
            val = content[i + 1:].strip()
            return key, (val if val else None)
    return None


def _key_content(content: str) -> Optional[Tuple[str, Optional[str]]]:
    if not content or content[0] in "-{[":
        return None
    return _split_key(content)


def _scalar(raw: str, path: str) -> Any:
    v = raw.strip()
    if not v:
        return None
    if v.lower() in ("null", "~"):
        return None
    if v.lower() == "true":
        return True
    if v.lower() == "false":
        return False
    if v.startswith("'") and v.endswith("'") and len(v) >= 2:
        return v[1:-1].replace("''", "'")
    if v.startswith('"') and v.endswith('"') and len(v) >= 2:
        return _unquote(v)
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    if re.fullmatch(r"-?\d+\.\d+", v):
        return float(v)
    if re.fullmatch(r"-?\d+\.\d+[eE][+-]?\d+", v):
        return float(v)
    return v


def _unquote(v: str) -> str:
    import codecs

    body = v[1:-1]
    out: List[str] = []
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == "\\" and i + 1 < len(body):
            nxt = body[i + 1]
            simple = {"n": "\n", "t": "\t", '"': '"', "\\": "\\", "r": "\r"}
            if nxt in simple:
                out.append(simple[nxt])
                i += 2
                continue
            if nxt == "u" and i + 4 < len(body):
                try:
                    out.append(chr(int(body[i + 2:i + 6], 16)))
                    i += 6
                    continue
                except ValueError:
                    pass
            out.append(nxt)
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _flow(raw: str, path: str) -> Any:
    """Parse inline flow ``[...]`` / ``{...}`` collections (simplified)."""
    raw = raw.strip()
    if len(raw) < 2:
        raise ConfigError(f"{path}: malformed flow collection {raw!r}")
    inner = raw[1:-1]
    items = _split_flow(inner, path)

    if raw.startswith("["):
        return [_scalar(it, path) for it in items]
    result: Dict[str, Any] = {}
    for it in items:
        if ":" not in it:
            raise ConfigError(f"{path}: expected key: value in flow map, got {it!r}")
        key, _, val = it.partition(":")
        result[key.strip().strip("'\"")] = _scalar(val.strip(), path)
    return result


def _balanced_flow(raw: str) -> bool:
    """Check that bracket/quote chars in a flow token are balanced."""
    depth = 0
    quote: Optional[str] = None
    for i, ch in enumerate(raw):
        if quote:
            if ch == quote and (i == 0 or raw[i - 1] != "\\"):
                quote = None
        elif ch in ("'", '"'):
            quote = ch
        elif ch in ("[", "{"):
            depth += 1
        elif ch in ("]", "}"):
            depth -= 1
            if depth < 0:
                return False
    return depth == 0 and quote is None


def _split_flow(inner: str, path: str) -> List[str]:
    items: List[str] = []
    buf: str = ""
    depth = 0
    quote: Optional[str] = None
    for ch in inner:
        if quote:
            buf += ch
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            buf += ch
        elif ch in ("[", "{"):
            depth += 1
            buf += ch
        elif ch in ("]", "}"):
            depth -= 1
            buf += ch
        elif ch == "," and depth == 0:
            items.append(buf.strip())
            buf = ""
        else:
            buf += ch
    if quote or depth != 0:
        raise ConfigError(f"{path}: unbalanced flow collection {inner!r}")
    if buf.strip():
        items.append(buf.strip())
    return [it for it in items if it != ""]


def yaml_safe_load(text: str) -> Any:
    """Parse a YAML document string (subset) into Python objects."""
    return Parser(text).parse()


class YAMLLoader:
    """Loads and validates a mem20orcaz workflow configuration."""

    def __init__(self, path: Optional[str] = None) -> None:
        self.path: Optional[str] = path
        self.config: Dict[str, Any] = {}
        self.orchestrator_cfg: Dict[str, Any] = {}
        self.agent_cfgs: List[Dict[str, Any]] = []
        if path:
            self.load_yaml(path)

    def load_yaml(self, path: str) -> None:
        self.path = path
        with open(path, encoding="utf-8") as fh:
            parsed = yaml_safe_load(fh.read())
        self.config = parsed if isinstance(parsed, dict) else {}
        self.orchestrator_cfg = self.config.get("orchestrator", {})
        self.agent_cfgs = self.config.get("agents", [])
        if not isinstance(self.agent_cfgs, list):
            raise ConfigError(f"{path}: 'agents' should be a list")

    def parse(self, text: str) -> Dict[str, Any]:
        """Parse YAML text in place and return the config document."""
        parsed = yaml_safe_load(text)
        self.config = parsed if isinstance(parsed, dict) else {}
        self.orchestrator_cfg = self.config.get("orchestrator", {})
        self.agent_cfgs = self.config.get("agents", [])
        if not isinstance(self.agent_cfgs, list):
            raise ConfigError("'agents' should be a list")
        return self.config

    def get_orchestrator(self) -> Dict[str, Any]:
        return self.orchestrator_cfg

    def get_agents(self) -> List[Dict[str, Any]]:
        return self.agent_cfgs

    def validate(self) -> bool:
        if "orchestrator" not in self.config:
            raise ConfigError("Missing 'orchestrator' section in config")
        if "agents" not in self.config:
            raise ConfigError("Missing 'agents' section in config")
        if not isinstance(self.config["agents"], list):
            raise ConfigError("'agents' should be a list")
        ids: list[str] = []
        for cfg in self.config["agents"]:
            if not isinstance(cfg, dict):
                raise ConfigError("each 'agents' entry should be a mapping")
            if not cfg.get("id"):
                raise ConfigError("each agent entry requires a non-empty 'id'")
            ids.append(cfg["id"])
        if len(set(ids)) != len(ids):
            raise ConfigError("agent ids must be unique")
        self._validate_templates()
        return True

    def _validate_templates(self) -> None:
        errors: List[str] = []
        for cfg in self.config["agents"]:
            prompt = cfg.get("prompt") or ""
            if isinstance(prompt, str) and "{{" in prompt:
                if prompt.count("{{") != prompt.count("}}"):
                    errors.append(f"Agent '{cfg.get('id', '?')}': unbalanced template braces")
        if errors:
            raise ConfigError("Template validation failed:\n" + "\n".join(errors))

    def agent_config_map(self) -> Dict[str, Dict[str, Any]]:
        return {cfg.get("id"): cfg for cfg in self.agent_cfgs if cfg.get("id")}

    def initial_queue(self) -> List[str]:
        q = self.orchestrator_cfg.get("queue") or self.orchestrator_cfg.get("agents") or []
        if isinstance(q, str):
            return [x.strip() for x in q.split(",") if x.strip()]
        return [x for x in q if isinstance(x, str)]

    def orchestrator_id(self) -> str:
        return self.orchestrator_cfg.get("id") or "default"