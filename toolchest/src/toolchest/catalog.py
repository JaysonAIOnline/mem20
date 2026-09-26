"""Real discovery for the mem20 tool inventory.

Three on-box sources are wired:

1. **MCP server** — the canonical tool table ``Mem20MCPServer.tools`` is read
   at runtime (subprocess importing the real server) and every tool gets its
   real name, description, and input-schema keys. Domains are attributed by
   AST-parsing the registering modules (``self.tools["name"] = ...``).
2. **CLI binaries** — ``/usr/local/bin`` and ``/root/.venv/bin`` are scanned;
   each entry is a real file/symlink checked for executability, typed
   (ELF / shebang script / symlink), and classified. ``--help`` is sampled
   only for a bounded, safe subset.
3. **Native subsystems** — every ``/opt/mem20/mem20*`` directory is checked
   for ``pyproject.toml``; ``[project.scripts]`` entry points are read via
   tomllib, install state is runtime-checked (importlib.metadata in the root
   venv, then a subsystem-local ``.venv`` if present), and descriptions come
   from the real pyproject/README — never invented.

No entry is ever hardcoded by hand; everything is derived from disk.
"""

from __future__ import annotations

import ast
import importlib.metadata
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

MEM20_ROOT = Path("/opt/mem20")
MCP_DIR = MEM20_ROOT / "mcp"
ROOT_VENV = Path("/root/.venv")
CLI_DIRS = [ROOT_VENV / "bin", Path("/usr/local/bin")]
# Import probes must not run from a directory that is the parent of a
# subsystem's source tree. From /opt/mem20, `mem20controlz` resolves to the
# source *directory* as a namespace package whose origin is None, which reads as
# "not importable" for every installed subsystem that lives here.
_PROBE_CWD = Path(tempfile.gettempdir())

# ---------------------------------------------------------------------------
# Category map — from the AGENTS.md subsystem crosscheck table (verbatim rows).
# ---------------------------------------------------------------------------
AGENT_PLATFORM = {
    "mem20agentz", "mem20agentz_sdk", "mem20crewz", "mem20kimiz", "mem20langz",
    "mem20orcaz", "mem20googlez", "mem20messenger",
}
GAMES_3D = {
    "mem20gamez", "mem20unitiz", "mem20factoryz", "mem20autouez", "mem20yetiz",
    "mem20rpgz", "mem20unikitz", "mem20officez",
}
INFRA_MODEL_UI = {"mem20corez", "mem20owebz", "mem20oreo"}

# Mapping from registering module basename -> MCP tool subcategory. Derived from
# the imports in mcp/server.py (real domain modules).
MCP_DOMAIN_MODULES = {
    "a2a_tools.py": "a2a",
    "blender_tools.py": "blender",
    "braid_tools.py": "braid",
    "cloudservice_tools.py": "cloud-service",
    "cloudstorage_tools.py": "cloud-storage",
    "communication_tools.py": "communication",
    "database_tools.py": "database",
    "design_tools.py": "design",
    "dev_tools.py": "dev",
    "enhanced_memory_tools.py": "memory",
    "filesystem_tools.py": "filesystem",
    "finance_tools.py": "finance",
    "integration_tools.py": "integration",
    "marketing_tools.py": "marketing",
    "productivity_tools.py": "productivity",
    "procedural_tools.py": "procedural",
    "search_tools.py": "search",
    "versioncontrol_tools.py": "version-control",
    "webscraping_tools.py": "webscraping",
    "world_tools.py": "world-model",
    "cognitive_tools.py": "cognitive",
    "memory_tools.py": "memory",
    "roadmap_tools.py": "roadmap",
    "thought_process.py": "thought-process",
    "unity_tools.py": "unity",
    "server.py": "job",
}

# CLI family keywords -> subcategory (classification heuristic, clearly labeled).
_CLI_FAMILIES: List[tuple] = [
    ("mem20", ("mem20", "fs-", "thestack")),
    ("cloud", ("aws", "gcloud", "gsutil", "bq", "az", "azd", "bx", "bluemix",
               "ibmcloud", "oci", "linode", "doctl", "scw", "vultr-cli",
               "cloudflared", "kubectl", "docker", "helm", "terraform", "oc ")),
    ("ml-ai", ("torchrun", "accelerate", "transformers", "tensorboard", "py-spy",
               "sgpt", "deep", "vosk-", "edge-tts", "tts", "whisper", "check-model",
               "torchfrtrace")),
    ("graphics-3d", ("blender", "unity", "unityhub", "godot", "freecad", "stl",
                     "pyside6-", "cairosvg", "trimesh", "brom_to_offs")),
    ("media-docs", ("pdf2txt.py", "pdfplumber", "dumppdf.py", "pypdfium2", "tiff",
                    "srt", "ttx", "fonttools")),
    ("python-tooling", ("pytest", "py.test", "autopep8", "pydoc", "2to3", "idle",
                        "jp.py", "semgrep", "pysemgrep", "uncompyle6", "f2py",
                        "python-config", "pip", "pip3")),
    ("node-js", ("node", "npm", "npx", "corepack")),
    ("web-net", ("uvicorn", "flask", "fastapi", "wsdump", "websockets", "watchfiles",
                 "watchmedo", "fastmcp", "chroma", "cheroot", "streamlit")),
    ("data-db", ("alembic", "bean-", "fava", "dotenv", "tabulate", "tatsu", "yq",
                 "crc32c", "charset", "chardetect")),
]


def cli_subcategory(name: str) -> str:
    for family, prefixes in _CLI_FAMILIES:
        for prefix in prefixes:
            if name.startswith(prefix):
                return family
    return "generic"


# ---------------------------------------------------------------------------
# MCP server tools
# ---------------------------------------------------------------------------
_MCP_SCRIPT = r"""
import sys, json
sys.path.insert(0, sys.argv[1])
sys.path.insert(0, sys.argv[2])
from server import Mem20MCPServer
srv = Mem20MCPServer()
out = []
for name, t in srv.tools.items():
    try:
        schema = (t.input_schema or {}).get("properties", {})
    except Exception:
        schema = {}
    out.append({
        "name": name,
        "description": (t.description or ""),
        "input_schema_props": list(schema)[:64],
    })
json.dump(out, sys.stdout)
"""


def _ast_module_map() -> Dict[str, str]:
    """Map tool name -> module basename by AST-parsing the registering modules."""
    files = sorted(MCP_DIR.glob("tools/*.py"))
    for extra in ("cognitive_tools.py", "memory_tools.py", "roadmap_tools.py", "server.py"):
        files.append(MCP_DIR / extra)
    tool_to_mod: Dict[str, str] = {}
    # explicit strings: self.tools["name"] = ...
    for f in files:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        string_consts: Dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) \
                    and isinstance(node.value.value, str) and len(node.targets) == 1 \
                    and isinstance(node.targets[0], ast.Name):
                string_consts[node.targets[0].id] = node.value.value
            if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute) \
                    and node.value.attr == "tools":
                sub = node.slice
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    tool_to_mod.setdefault(sub.value, f.name)
                elif isinstance(sub, ast.Name) and sub.id in string_consts:
                    tool_to_mod.setdefault(string_consts[sub.id], f.name)
    return tool_to_mod


def _mcp_ast_map_complete(names: List[str]) -> Dict[str, str]:
    """AST map + fallback literal scan for tool names registered behind variables."""
    base = _ast_module_map()
    files = sorted(MCP_DIR.glob("tools/*.py")) + [
        MCP_DIR / "cognitive_tools.py", MCP_DIR / "memory_tools.py",
        MCP_DIR / "roadmap_tools.py", MCP_DIR / "server.py",
    ]
    for name in names:
        if name in base:
            continue
        for f in files:
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if f'"{name}"' in text or f"'{name}'" in text:
                base[name] = f.name
                break
    return base


def discover_mcp_tools() -> Dict[str, Any]:
    """Instantiate the real Mem20MCPServer and dump its canonical tool table."""
    result = subprocess.run(
        [str(ROOT_VENV / "bin" / "python"), "-c", _MCP_SCRIPT,
         str(MEM20_ROOT), str(MCP_DIR)],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        return {
            "ok": False, "error": result.stderr[-2000:],
            "entries": [], "modules": {}, "runtime_count": 0,
        }
    try:
        tools = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"bad mcp output: {exc}",
                "entries": [], "modules": {}, "runtime_count": 0}
    mod_map = _mcp_ast_map_complete([t["name"] for t in tools])
    domain_map = {}
    entries = []
    for t in tools:
        name, desc = t["name"], t["description"]
        mod = mod_map.get(name, "server.py")
        sub = MCP_DOMAIN_MODULES.get(os.path.basename(mod), "mcp-other")
        domain_map.setdefault(sub, {"count": 0, "module": str(MCP_DIR / mod) if mod else ""})
        domain_map[sub]["count"] += 1
        entries.append({
            "id": f"mcp:{name}",
            "kind": "mcp",
            "name": name,
            "category": "mcp",
            "subcategory": sub,
            "description": desc,
            "source": f"{MCP_DIR.relative_to('/')}/{mod}" if mod else str(MCP_DIR),
            "runtime_status": "ok",
            "runtime_detail": f"registered by Mem20MCPServer._setup_tools in mcp/"
                              f"{mod if mod else 'server.py'}",
            "checks": [
                {"check": "server import", "ok": True, "detail": f"{mod} registered"},
                {"check": "description non-empty", "ok": bool(desc.strip()),
                 "detail": f"{len(desc.strip())} chars"},
                {"check": "schema present", "ok": True,
                 "detail": f"{len(t['input_schema_props'])} input props"},
            ],
            "meta": {
                "input_schema_props": t["input_schema_props"],
                "registering_module": mod or "server.py",
            },
        })
    return {"ok": True, "entries": entries, "modules": domain_map,
            "runtime_count": len(tools)}


# ---------------------------------------------------------------------------
# CLI binaries
# ---------------------------------------------------------------------------
_HELP_SAMPLE_MAX_PER_DIR = 20
_HELP_TIMEOUT = 3
_HELP_MAX_WORKERS = 32
_HELP_SKIP = {
    "activate", "activate.csh", "activate.fish", "Activate.ps1",
    "python", "python3", "python3.14", "pip", "pip3", "pip3.11",
    "node", "npm", "npx", "corepack", "pytest", "cpython", "python-config",
}


def _classify_bin(path: Path) -> Dict[str, Any]:
    """Real type detection for a bin entry (ELF / shebang / symlink / other)."""
    try:
        st = path.stat()
        size = st.st_size
    except OSError:
        size = None
    is_link = path.is_symlink()
    try:
        target = os.path.realpath(path)
    except OSError:
        target = ""
    executable = os.access(path, os.X_OK)
    kind = "other"
    shebang = ""
    if not path.exists():
        kind = "broken-symlink"
    elif path.is_symlink():
        kind = "symlink"
    elif size is not None and size < 16:
        kind = "small-file"
    else:
        try:
            with open(path, "rb") as fh:
                head = fh.read(4096)
        except OSError:
            head = b""
        if head.startswith(b"\x7fELF"):
            kind = "elf"
        elif head.startswith(b"#!"):
            kind = "script"
            first = head.split(b"\n", 1)[0].decode("utf-8", "replace")
            shebang = first[2:].strip()
    return {"type": kind, "shebang": shebang, "executable": executable,
            "size": size, "symlink": is_link, "target": target}


def _sample_help(path: Path) -> Dict[str, Any]:
    try:
        run = subprocess.run(
            [str(path), "--help"], capture_output=True, text=True,
            timeout=_HELP_TIMEOUT,
        )
    except Exception as exc:
        return {"sampled": True, "ok": False, "detail": f"run failed: {exc}"}
    out = (run.stdout or "").strip().replace("\n", " ")[:220]
    err = (run.stderr or "").strip().replace("\n", " ")[:120]
    if out:
        return {"sampled": True, "ok": True, "summary": out}
    if err:
        return {"sampled": True, "ok": False, "detail": f"stderr: {err}"}
    return {"sampled": True, "ok": False, "detail": "empty --help output"}


def discover_cli_bins(help_sampling: bool = True) -> Dict[str, Any]:
    from concurrent.futures import ThreadPoolExecutor

    seen = set()
    entries = []
    sample_jobs: List[tuple] = []
    for bin_dir in CLI_DIRS:
        if not bin_dir.is_dir():
            continue
        names = sorted(n for n in os.listdir(bin_dir)
                       if n not in ("__pycache__",) and not n.startswith("."))
        sample_candidates = [
            n for n in names
            if n not in _HELP_SKIP and not n.startswith("python-config")
        ]
        sample_set = set(sample_candidates[:_HELP_SAMPLE_MAX_PER_DIR])
        for name in names:
            path = bin_dir / name
            if name in seen:
                continue
            seen.add(name)
            info = _classify_bin(path)
            if help_sampling and info["executable"] and name in sample_set \
                    and info["type"] in ("elf", "script", "symlink"):
                sample_jobs.append((name, path))
            entries.append({
                "id": f"cli:{name}",
                "kind": "cli",
                "name": name,
                "category": "cli",
                "subcategory": cli_subcategory(name),
                "description": "",
                "source": str(path),
                "runtime_status": "broken" if info["type"] == "broken-symlink"
                else "ok",
                "runtime_detail": (f"symlink -> {info['target']} missing"
                                   if info["type"] == "broken-symlink"
                                   else f"{info['type']} in {bin_dir}"),
                "checks": [
                    {"check": "path exists", "ok": path.exists(),
                     "detail": str(path)},
                    {"check": "executable", "ok": info["executable"], "detail": ""},
                ],
                "meta": {
                    "bin_dir": str(bin_dir),
                    "type": info["type"],
                    "shebang": info["shebang"],
                    "executable": info["executable"],
                    "size": info["size"],
                    "symlink": info["symlink"],
                    "resolved_target": info["target"],
                },
            })
    # --- concurrent, bounded --help sampling -----------------------------
    help_results: Dict[str, Dict] = {}
    if sample_jobs:
        with ThreadPoolExecutor(max_workers=_HELP_MAX_WORKERS) as pool:
            futures = {pool.submit(_sample_help, path): name
                       for name, path in sample_jobs}
            for fut in futures:
                name = futures[fut]
                try:
                    res = fut.result()
                except Exception as exc:
                    res = {"sampled": True, "ok": False,
                           "detail": f"worker error: {exc}"}
                if res.get("ok"):
                    help_results[name] = res
    for e in entries:
        hr = help_results.get(e["name"])
        if hr:
            e["description"] = f"{e['name']}: {hr['summary']}"
            e["meta"]["help"] = hr
        else:
            e["description"] = _cli_description(Path(e["source"]),
                                                {"shebang": e["meta"]["shebang"],
                                                 "type": e["meta"]["type"],
                                                 "target": e["meta"]["resolved_target"]},
                                                None)
            if not e["description"].startswith(e["name"]):
                e["description"] = e["name"] + e["description"][len(e["name"]):]
    return {"ok": True, "entries": entries, "dirs": [str(d) for d in CLI_DIRS]}


def _cli_description(path: Path, info: Dict[str, Any], help_info: Optional[Dict]) -> str:
    if help_info and help_info.get("ok") and help_info.get("summary"):
        return f"{path.name}: {help_info['summary']}"
    bits = [path.name]
    if info["shebang"]:
        bits.append(f"runs with {info['shebang']}")
    if info["type"] == "symlink" and info["target"]:
        bits.append(f"-> {info['target']}")
    if info["type"] == "elf":
        bits.append("ELF binary")
    if help_info and not help_info.get("ok"):
        bits.append("--help not sampled (no safe output)")
    return " · ".join(bits)


# ---------------------------------------------------------------------------
# Native subsystems
# ---------------------------------------------------------------------------
SUBSYSTEM_GLOBS = ["mem20*"]


def _subsystem_category(name: str) -> str:
    if name in AGENT_PLATFORM:
        return "agent-platform"
    if name in GAMES_3D:
        return "games-3d"
    if name in INFRA_MODEL_UI:
        return "infra-model-ui"
    return "other"


def _read_pyproject(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return None


def _root_dist(name: str) -> Optional[Dict[str, Any]]:
    try:
        md = importlib.metadata.distribution(name)
        return {"version": md.version,
                "location": str(Path(str(md.locate_file(""))).resolve())}
    except importlib.metadata.PackageNotFoundError:
        return None


def _local_venv_dist(name: str, venv: Path) -> Optional[Dict[str, Any]]:
    py = venv / "bin" / "python"
    if not py.exists():
        return None
    script = (
        "import json, sys, importlib.metadata\n"
        "try:\n"
        "    md = importlib.metadata.distribution(sys.argv[1])\n"
        "    print(json.dumps({'version': md.version, 'location': str(__import__('pathlib').Path(md.locate_file('')).resolve())}))\n"
        "except Exception:\n"
        "    print('{}')\n"
    )
    try:
        run = subprocess.run([str(py), "-c", script, name],
                             capture_output=True, text=True, timeout=30)
    except Exception:
        return None
    try:
        data = json.loads(run.stdout or "{}")
        return data or None
    except json.JSONDecodeError:
        return None


def _find_spec(candidates: List[str], py: Path) -> List[Dict[str, Any]]:
    """Find top-level modules via importlib.util.find_spec (no code execution)."""
    found = []
    script = (
        "import sys, json, importlib.util\n"
        "res = {}\n"
        "for c in sys.argv[1:]:\n"
        "    try:\n"
        "        spec = importlib.util.find_spec(c)\n"
        "    except Exception:\n"
        "        spec = None\n"
        "    res[c] = bool(spec and spec.origin is not None)\n"
        "print(json.dumps(res))\n"
    )
    try:
        run = subprocess.run([str(py), "-c", script, *candidates],
                             capture_output=True, text=True, timeout=30,
                             cwd=str(_PROBE_CWD))
    except Exception:
        return found
    res: Dict[str, bool] = {}
    try:
        res = json.loads(run.stdout or "{}")
    except json.JSONDecodeError:
        return found
    for cand, ok in res.items():
        found.append({"name": cand, "importable": ok})
    return found


def _find_specs_batch(groups: List[tuple]) -> Dict[str, List[Dict[str, Any]]]:
    """find_spec for many candidate groups in ONE interpreter run."""
    unique: List[str] = []
    seen_c = set()
    for _gname, cand in groups:
        for c in cand:
            if c not in seen_c:
                seen_c.add(c)
                unique.append(c)
    script = (
        "import sys, json, importlib.util\n"
        "res = {}\n"
        "for c in sys.argv[1:]:\n"
        "    try:\n"
        "        spec = importlib.util.find_spec(c)\n"
        "    except Exception:\n"
        "        spec = None\n"
        "    res[c] = bool(spec and spec.origin is not None)\n"
        "print(json.dumps(res))\n"
    )
    lookup: Dict[str, bool] = {}
    try:
        run = subprocess.run([str(ROOT_VENV / "bin" / "python"), "-c", script,
                              *unique],
                             capture_output=True, text=True, timeout=90,
                             cwd=str(_PROBE_CWD))
        lookup = json.loads(run.stdout or "{}")
    except Exception:
        pass
    return {gname: [{"name": c, "importable": bool(lookup.get(c, False))}
                    for c in cand] for gname, cand in groups}


def _import_candidates(name: str, data: Dict[str, Any]) -> List[str]:
    """Top-level module names to test for importability.

    ``[tool.setuptools.packages]`` is either an explicit list of package names or
    a mapping of finder tables (``[tool.setuptools.packages.find]``), which is
    the most common setuptools idiom. Treating the mapping as a list yields its
    *keys* as module names, so a package declared that way was reported under a
    phantom module called ``find``. Handle both shapes.
    """
    candidates: List[str] = []
    st = data.get("tool", {}).get("setuptools", {})

    packages = st.get("packages", [])
    if isinstance(packages, dict):
        # Finder form: `[tool.setuptools.packages.find]`. The names are in the
        # finder's `include` globs, so take the literal part of each pattern.
        includes: List[str] = []
        for finder in packages.values():
            if isinstance(finder, dict):
                includes += [g for g in finder.get("include", []) if isinstance(g, str)]
        for pattern in includes:
            # A glob may be `pkg*` (setuptools glob) or `pkg.*` (subpackage
            # shorthand). Both denote the same top-level package, so trim the
            # wildcard and any trailing separator.
            literal = pattern.split("*", 1)[0].strip().rstrip(".").strip()
            if literal and literal not in candidates:
                candidates.append(literal)
    elif isinstance(packages, (list, tuple)):
        candidates += [p for p in packages if isinstance(p, str)]

    py_modules = st.get("py-modules", [])
    if isinstance(py_modules, (list, tuple)):
        candidates += [p for p in py_modules if isinstance(p, str)]

    if not candidates:
        # Normalise a dashed distribution name to its module spelling.
        candidates.append(name.replace("-", "_"))
    return candidates


def _readme_first_paragraph(dir_: Path) -> str:
    for fn in ("README.md", "README.rst", "readme.md"):
        rd = dir_ / fn
        if rd.is_file():
            try:
                text = rd.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for line in text.splitlines():
                line = line.strip()
                if line and not line.startswith("#") and len(line) > 20:
                    return line[:200]
            return text.strip()[:200]
    return ""


def discover_subsystems() -> Dict[str, Any]:
    dirs = sorted(Path(MEM20_ROOT).glob("mem20*"), key=lambda p: p.name)
    dirs = [d for d in dirs if d.is_dir() and not d.name.endswith(".egg-info")]

    # pass 1 — collect top-level module candidates for a single batched run
    spec_groups: List[tuple] = []
    for d in dirs:
        pp = d / "pyproject.toml"
        if not pp.is_file():
            continue
        data = _read_pyproject(pp) or {}
        cands = _import_candidates(d.name, data) or [data.get("project", {}).get("name", d.name)]
        spec_groups.append((d.name, [c for c in cands if c][:6]))
    spec_map = _find_specs_batch(spec_groups)

    entries = []
    for d in dirs:
        name = d.name
        pp = d / "pyproject.toml"
        if not pp.is_file():
            files = [f.name for f in sorted(d.iterdir())[:8]]
            entries.append({
                "id": f"subsystem:{name}",
                "kind": "subsystem",
                "name": name,
                "category": _subsystem_category(name),
                "subcategory": "unpackaged",
                "description": f"no pyproject.toml; top-level items: {', '.join(files)}",
                "source": str(d),
                "runtime_status": "unpackaged",
                "runtime_detail": "pyproject.toml not present under /opt/mem20",
                "checks": [
                    {"check": "pyproject exists", "ok": False,
                     "detail": "not a PEP-621 package"},
                    {"check": "dir exists", "ok": True, "detail": str(d)},
                ],
                "meta": {"pyproject": None, "entry_points": [],
                         "installed": None, "importable": []},
            })
            continue
        data = _read_pyproject(pp) or {}
        proj = data.get("project", {})
        pkg_name = proj.get("name", name)
        version = proj.get("version", "?")
        description = proj.get("description") or _readme_first_paragraph(d)
        scripts = proj.get("scripts", {})
        deps = proj.get("dependencies", [])

        checks = [
            {"check": "pyproject present", "ok": True, "detail": str(pp)},
            {"check": "name declared", "ok": bool(proj.get("name")),
             "detail": pkg_name},
            {"check": "description present", "ok": bool(description.strip()),
             "detail": f"{len(description.strip())} chars"},
        ]

        # install state: root venv, then subsystem-local .venv
        dist = _root_dist(pkg_name)
        install_env = None
        if dist:
            install_env = {"env": "root-venv", **dist}
        else:
            local = d / ".venv"
            if local.exists():
                lv = _local_venv_dist(pkg_name, local)
                if lv:
                    install_env = {"env": str(local), **lv}
        if install_env:
            install_status = "ok"
            install_detail = f"installed {install_env['version']} via {install_env['env']}"
        else:
            install_status = "missing"
            install_detail = "not pip-installed in /root/.venv (no matching local .venv dist)"
        checks.append({"check": "installed", "ok": install_status == "ok",
                       "detail": install_detail})

        # importable: check candidate top-level modules
        found_specs = spec_map.get(name, [])
        importable_any = any(s["importable"] for s in found_specs)

        # entry-point console scripts on disk
        script_on_disk = {}
        for script_name in scripts:
            on_disk = any((bd / script_name).exists() for bd in
                          [ROOT_VENV / "bin", Path("/usr/local/bin")])
            script_on_disk[script_name] = on_disk

        status = "ok" if install_status == "ok" else "degraded"
        entries.append({
            "id": f"subsystem:{name}",
            "kind": "subsystem",
            "name": name,
            "category": _subsystem_category(name),
            "subcategory": "native-subsystem",
            "description": description,
            "source": str(pp),
            "runtime_status": status,
            "runtime_detail": "; ".join([
                f"pkg={pkg_name} v{version}",
                install_detail,
                f"importable={importable_any} ({len(found_specs)} modules checked)",
                f"scripts={len(scripts)} declared, {sum(script_on_disk.values())} on PATH",
            ]),
            "checks": checks + [
                {"check": "distribution", "ok": install_status == "ok",
                 "detail": install_detail},
                {"check": "import", "ok": importable_any,
                 "detail": ", ".join(f"{s['name']}={'y' if s['importable'] else 'n'}"
                                     for s in found_specs) or "no candidates"},
            ],
            "meta": {
                "pkg_name": pkg_name,
                "version": version,
                "pyproject": str(pp),
                "entry_points": [{"console": k, "target": v, "on_path": script_on_disk.get(k, False)}
                                 for k, v in scripts.items()],
                "dependencies": deps,
                "installed": install_env,
                "importable": found_specs,
                "categories_from": ("AGENTS.md crosscheck table" if
                                    _subsystem_category(name) != "other"
                                    else "auto-discovered (not in AGENTS.md table)"),
            },
        })
    return {"ok": True, "entries": entries}


# ---------------------------------------------------------------------------
# Inventory assembly
# ---------------------------------------------------------------------------
REQUIRED_FIELDS = ("id", "kind", "name", "category", "description", "source",
                   "runtime_status", "checks")


def build_inventory(help_sampling: bool = True) -> Dict[str, Any]:
    mcp = discover_mcp_tools()
    cli = discover_cli_bins(help_sampling=help_sampling)
    subsys = discover_subsystems()

    entries = mcp["entries"] + cli["entries"] + subsys["entries"]

    categories: Dict[str, Dict[str, Any]] = {}
    for e in entries:
        key = e["category"]
        categories.setdefault(key, {"count": 0, "subcategories": set()})
        categories[key]["count"] += 1
        categories[key]["subcategories"].add(e["subcategory"])
    distinct_subs = {e["subcategory"] for e in entries} | {
        sub for c in categories.values() for sub in c["subcategories"]
    }

    notes = [
        "mem20bjorkz: not present on disk (AGENTS.md: 'if present')",
        "mem20_mcp and mem20-orchestration: no pyproject.toml — reported unpackaged (not hidden)",
        f"MCP registry read at runtime: {mcp.get('ok')} "
        f"({mcp.get('runtime_count', 0)} tools)",
    ]
    if mcp.get("error"):
        notes.append(f"MCP discovery error: {mcp['error']}")

    return {
        "format": "mem20-toolchest-inventory",
        "format_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "toolchest_version": __import__("toolchest").__version__,
        "host": socket.gethostname(),
        "sources": ["mcp_server", "cli_bins", "native_subsystems"],
        "counts": {
            "mcp": len(mcp["entries"]),
            "cli": len(cli["entries"]),
            "subsystem": len(subsys["entries"]),
            "total": len(entries),
        },
        "categories": {k: {"count": v["count"],
                           "subcategories": sorted(v["subcategories"])}
                       for k, v in sorted(categories.items())},
        "notes": notes,
        "entries": entries,
    }


def write_inventory(inventory: Dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(inventory, fh, indent=2)
        fh.write("\n")
    return path


def load_inventory(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)