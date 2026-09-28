"""Import-shadow detection.

Why this exists: the outer directory of a nested package (mem20unitiz/) has no
``__init__.py``, so when a directory containing it is on ``sys.path`` Python
registers a *namespace portion* that outranks the real regular package found
later on the path. ``import mem20unitiz`` then yields an empty namespace module
with ``__file__ = None`` and no attributes.

This is a known and deliberate condition in this estate: ``testrun`` already
runs each suite from its own package root to avoid it. This module does not
re-report it as a fresh discovery. It reports the per-package baseline so a
sweep can see which packages are shadow-prone, and so newly added packages are
caught at the point they are introduced.

The probe must run in a *fresh interpreter started from the estate root*.
``python /some/script.py`` puts the script's directory on ``sys.path[0]``, not
the working directory, so a probe run that way silently measures the wrong
thing and reports a clean result. ``python -c`` puts the working directory at
``sys.path[0]``, which is the condition under investigation.

Resolution uses ``importlib.util.find_spec`` and never imports the module, so
no package code is executed and nothing on disk is written.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field

DEFAULT_ROOT = "/opt/mem20"
DEFAULT_PYTHON = "/root/.venv/bin/python"
# A neutral cwd that cannot contain a package directory of the same name.
CONTROL_ROOT = "/"

SHADOWED = "shadowed-by-sibling"
UNREACHABLE = "unreachable-from-interpreter"
RESOLVES = "resolves"
NOT_FOUND = "not-found"
ERROR = "error"
# What the child interpreter reports when the only thing on sys.path matching
# the name is a directory with no __init__.py (a PEP 420 namespace portion).
# This is a raw probe token; classification happens in check_package.
RAW_NAMESPACE = "namespace"

# Runs in the child interpreter. find_spec never executes the module.
_PROBE = (
    "import sys,json,importlib.util\n"
    "name=sys.argv[1]\n"
    "try:\n"
    "    spec=importlib.util.find_spec(name)\n"
    "except BaseException as exc:\n"
    "    print(json.dumps({'resolution':'error',"
    "'error':type(exc).__name__+': '+str(exc)[:160]}))\n"
    "    raise SystemExit(0)\n"
    "if spec is None:\n"
    "    print(json.dumps({'resolution':'not-found'}))\n"
    "elif spec.origin in (None,'namespace'):\n"
    "    print(json.dumps({'resolution':'namespace',"
    "'search_path':list(spec.submodule_search_locations or [])}))\n"
    "else:\n"
    "    print(json.dumps({'resolution':'resolves','origin':spec.origin}))\n"
)

_NAME_RE = re.compile(r'^\s*name\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)


@dataclass
class ShadowReport:
    package: str
    import_name: str = ""
    layout: str = ""
    resolution: str = ERROR
    origin: str = ""
    search_path: list[str] = field(default_factory=list)
    control: str = ""
    problems: list[str] = field(default_factory=list)

    @property
    def shadowed(self) -> bool:
        return self.resolution in (SHADOWED, UNREACHABLE)

    @property
    def ok(self) -> bool:
        return not self.problems and self.resolution == RESOLVES

    def as_dict(self) -> dict:
        return {
            "package": self.package,
            "import_name": self.import_name,
            "layout": self.layout,
            "resolution": self.resolution,
            "origin": self.origin,
            "search_path": self.search_path,
            "control": self.control,
            "shadowed": self.shadowed,
            "ok": self.ok,
            "problems": self.problems,
        }


def import_name_for(package_dir: str, fallback: str) -> str:
    """Read the distribution name from pyproject, falling back to the dir name."""
    pyproject = os.path.join(package_dir, "pyproject.toml")
    try:
        with open(pyproject, encoding="utf-8", errors="replace") as fh:
            match = _NAME_RE.search(fh.read())
    except OSError:
        return fallback
    return match.group(1).strip() if match else fallback


def detect_layout(package_dir: str, import_name: str) -> str:
    """`src` is immune to shadowing; a nested flat package is not."""
    if os.path.isdir(os.path.join(package_dir, "src", import_name)):
        return "src"
    if os.path.isfile(os.path.join(package_dir, import_name, "__init__.py")):
        return "nested-flat"
    return "other"


def probe(import_name: str, root: str = DEFAULT_ROOT,
          python: str = DEFAULT_PYTHON, timeout: int = 30,
          pythonpath: str | None = None) -> dict:
    """Resolve `import_name` from a fresh interpreter whose cwd is `root`.

    `pythonpath`, when given, is exported to the child as PYTHONPATH. It exists
    so a package can be checked before it is installed anywhere.
    """
    env = dict(os.environ)
    if pythonpath:
        env["PYTHONPATH"] = pythonpath
    try:
        proc = subprocess.run([python, "-c", _PROBE, import_name],
                              cwd=root, capture_output=True, text=True,
                              timeout=timeout, check=False, env=env)
    except FileNotFoundError as exc:
        return {"resolution": ERROR, "error": f"interpreter not found: {exc}"}
    except subprocess.SubprocessError as exc:
        return {"resolution": ERROR, "error": f"probe failed: {exc}"}
    if proc.returncode != 0:
        return {"resolution": ERROR,
                "error": (proc.stderr or "probe exited nonzero").strip()[:160]}
    for line in reversed((proc.stdout or "").splitlines()):
        line = line.strip()
        if line:
            try:
                return json.loads(line)
            except ValueError:
                continue
    return {"resolution": ERROR, "error": "probe produced no output"}


def _control_probe(import_name: str, python: str, timeout: int,
                   pythonpath: str | None) -> dict:
    """Same import from a neutral cwd, to separate the two failure modes.

    A package can fail under the estate root for two unrelated reasons, and they
    need different remedies:
      * it IS installed, but a same-named sibling directory outranks it;
      * it is not reachable from this interpreter at all (e.g. it lives in its
        own .venv, as mem20mktz does). Layout is irrelevant in that case, so
        "convert to a src/ layout" would be the wrong advice.
    """
    return probe(import_name, root=CONTROL_ROOT, python=python,
                 timeout=timeout, pythonpath=pythonpath)


def discover(root: str = DEFAULT_ROOT) -> list[str]:
    """Package directories under `root` that declare a pyproject.toml."""
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return []
    found = []
    for name in names:
        if name.startswith(".") or name in ("tests", "test", "__pycache__"):
            continue
        path = os.path.join(root, name)
        if os.path.isdir(path) and os.path.isfile(os.path.join(path, "pyproject.toml")):
            found.append(name)
    return found


def check_package(package: str, root: str = DEFAULT_ROOT,
                  python: str = DEFAULT_PYTHON,
                  pythonpath: str | None = None) -> ShadowReport:
    package_dir = os.path.join(root, package)
    import_name = import_name_for(package_dir, package)
    report = ShadowReport(package=package, import_name=import_name)
    report.layout = detect_layout(package_dir, import_name)

    result = probe(import_name, root=root, python=python, pythonpath=pythonpath)
    report.resolution = result.get("resolution", ERROR)
    report.origin = result.get("origin", "")
    report.search_path = result.get("search_path", [])

    if "error" in result:
        report.problems.append(result["error"])
        return report

    control = _control_probe(import_name, python, 30, pythonpath)
    report.control = control.get("resolution", ERROR)

    if report.resolution == RESOLVES:
        return report

    if report.control == RESOLVES:
        report.resolution = SHADOWED
        report.problems.append(
            "importable on its own, but a same-named directory "
            f"{report.search_path} outranks it when the estate root is the "
            "working directory; run it from the package's own root")
    elif report.resolution == NOT_FOUND:
        report.resolution = UNREACHABLE
        report.problems.append(
            "not importable from this interpreter at all - it is probably "
            "installed only in its own venv, so layout changes would not help")
    elif report.resolution == RAW_NAMESPACE:
        report.resolution = UNREACHABLE
        report.problems.append(
            "only a namespace portion was found, and the package does not "
            "import from a neutral cwd either - not installed in this "
            "interpreter (layout changes would not help)")
    else:
        report.resolution = UNREACHABLE
        report.problems.append(
            f"unexpected probe resolution from the estate root: "
            f"{report.resolution or 'empty'}")
    return report


def sweep(packages=None, root: str = DEFAULT_ROOT,
          python: str = DEFAULT_PYTHON,
          pythonpath: str | None = None) -> list[ShadowReport]:
    if not os.path.isdir(root):
        raise RuntimeError(f"root not found: {root}")
    names = list(packages) if packages else discover(root)
    if not names:
        raise RuntimeError("no packages discovered")
    return [check_package(name, root=root, python=python, pythonpath=pythonpath)
            for name in names]
