"""Root conftest: stop the repo root from shadowing the nested mem20 packages.

The failure this fixes
----------------------
Running pytest from /opt/mem20 fails for the nested packages with:

    ImportError: cannot import name 'ActionSpec' from 'mem20unitiz'
                 (unknown location)

Cause: each package lives at <project>/<name>/, so the *outer* project
directory /opt/mem20/mem20unitiz has no __init__.py. When the repo root is on
sys.path (it is, because it is the cwd), Python matches that directory as a
namespace package and it wins over the correctly-installed real package. The
result is a module with __file__ = None and no exported names.

Adding __init__.py to the outer directories would be the wrong fix: it would
turn every project directory into a package containing a package.

The fix
-------
Drop the repo root from sys.path so it cannot contribute a namespace portion,
then put each project root on sys.path. The real package is then found either
via the editable install or via the project root. Verified to resolve
mem20unitiz and mem20googlez to their real __init__.py from the repo root.

The canonical way to run the estate's suites is still:

    mem20verify tests

which additionally honours per-package venvs and a per-package timeout.
"""

import importlib
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))

SKIP = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", "site-packages",
    "secrets", "backups", "data", "store", "build", "dist", "mem", "packaging",
    "roadmaps", "notes", "proof", "verification", "systemd", "docs",
}


def _project_roots():
    roots = []
    for name in sorted(os.listdir(ROOT)):
        if name in SKIP or name.startswith("."):
            continue
        path = os.path.join(ROOT, name)
        if not os.path.isdir(path):
            continue
        if os.path.exists(os.path.join(path, "pyproject.toml")) or \
                os.path.isfile(os.path.join(path, "__init__.py")) or \
                os.path.isdir(os.path.join(path, "tests")):
            roots.append(path)
    return roots


# 1. the repo root must not be able to form namespace portions
sys.path[:] = [p for p in sys.path if p not in ("", ".", ROOT)]

# 2. each real project root goes on the path instead
for _project in reversed(_project_roots()):
    if _project not in sys.path:
        sys.path.insert(0, _project)

# 3. Purge any namespace-package entries cached before this file ran.
#    A purge alone is not enough: pytest creates the bad entries *during* its
#    collection walk, which happens after this module is imported, so a
#    conftest-load purge has nothing to remove by then.
for _name, _module in list(sys.modules.items()):
    if _name.startswith("mem20") or _name in {"braid", "bpy", "mcp", "toolchest"}:
        _file = getattr(_module, "__file__", None)
        if _file is None and getattr(_module, "__path__", None) is not None:
            del sys.modules[_name]

# 4. Proactively import each real package so collection cannot shadow it.
#    Binding the real module into sys.modules first turns the later
#    `import mem20x` into a cache hit, so a bare namespace portion (no
#    __file__, no __path__ to src/) can never win. This is what deterministically
#    fixed mem20ucgz / mem20zimr collection errors and the mem20gamez
#    "no attribute DQNAgent" failure under the estate default
#    --import-mode=importlib, without changing that default.
def _importable(project):
    mod = os.path.basename(project).replace("-", "_")
    for candidate in (os.path.join(project, "src", mod), os.path.join(project, mod)):
        if os.path.isfile(os.path.join(candidate, "__init__.py")):
            return mod, os.path.dirname(candidate)
    return None


for _project in _project_roots():
    _found = _importable(_project)
    if not _found:
        continue
    _mod, _parent = _found
    if _parent not in sys.path:
        sys.path.insert(0, _parent)
    try:
        importlib.import_module(_mod)
    except Exception:
        # A package whose import needs optional native deps may not load here;
        # that is fine. We only need the ones pytest will import in this session
        # to be pre-bound, and any that fail still import normally on demand.
        pass

