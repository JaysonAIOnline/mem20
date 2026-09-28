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

# 3. Purge any namespace-package entries pytest cached during collection.
#    pytest walks the directory tree before running tests, and because every
#    package here lives at <project>/<name>/, that walk can leave `mem20gamez`
#    (and friends) in sys.modules as a bare namespace package - no __init__, no
#    attributes, no submodules. sys.path was already correct by then, so the only
#    cure is to drop the stale entries and let the real package import. This is
#    what made mem20gamez report "no attribute DQNAgent" and mem20ucgz report
#    "no module graph", when both were present and correct all along.
for _name, _module in list(sys.modules.items()):
    if _name.startswith("mem20") or _name in {"braid", "bpy", "mcp", "toolchest"}:
        _file = getattr(_module, "__file__", None)
        if _file is None and getattr(_module, "__path__", None) is not None:
            del sys.modules[_name]

# 4. Nothing to reorder.
#    Tried putting the editable-install finders ahead of PathFinder; it made no
#    difference, because the real problem was the repo root on sys.path (step 1)
#    and the stale namespace entries above, not finder precedence.

