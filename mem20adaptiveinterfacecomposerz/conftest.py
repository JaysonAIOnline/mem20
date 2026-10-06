"""Package conftest: make `import mem20adaptiveinterfacecomposerz` resolve to the real package.

This package uses src layout (real package at ``src/mem20adaptiveinterfacecomposerz/``) and is
not pip-installed, so nothing on the default sys.path provides it. Worse,
the estate root /opt/mem20 holds the outer project directory
``mem20adaptiveinterfacecomposerz/`` (no ``__init__.py``): when pytest runs with the estate
root on sys.path, Python matches that outer directory as a namespace
package and imports fail with::

    ImportError: cannot import name '...' from 'mem20adaptiveinterfacecomposerz'
                 (unknown location)

The estate root conftest fixes this globally, but it only loads when the
estate root is the pytest rootdir. This package declares its own rootdir
(see ``[tool.pytest.ini_options]`` in pyproject.toml), so correct the
path here: drop the estate root, lead with ``src/`` (the sitemapz
pattern, centralized instead of per-test-file). Idempotent with the root
conftest when both load during whole-estate runs.
"""

import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_ESTATE_ROOT = os.path.dirname(_PROJECT_ROOT)
_SRC = os.path.join(_PROJECT_ROOT, "src")

# 1. The estate root must not contribute a namespace portion.
sys.path[:] = [p for p in sys.path if p not in ("", ".", _ESTATE_ROOT)]

# 2. src/ leads, so the real package (with __init__.py) wins.
for _p in (_SRC, _PROJECT_ROOT):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

# 3. Drop a stale namespace entry if one was cached before this fix ran.
_mod = sys.modules.get("mem20adaptiveinterfacecomposerz")
if (_mod is not None and getattr(_mod, "__file__", None) is None
        and getattr(_mod, "__path__", None) is not None):
    del sys.modules["mem20adaptiveinterfacecomposerz"]
