"""Package conftest: make `import mem20gamez` resolve to the real package.

The estate root /opt/mem20 holds the outer project directory
``mem20gamez/`` (no ``__init__.py``). When pytest runs with the estate
root on sys.path, Python matches that outer directory as a namespace
package and it shadows the real installed package::

    AttributeError: module 'mem20gamez' has no attribute 'DQNAgent'

The estate root conftest fixes this globally, but it only loads when the
estate root is the pytest rootdir. This package declares its own rootdir
(see ``[tool.pytest.ini_options]`` in pyproject.toml, the same stanza the
sibling packages carry), so apply the same correction here: drop the
estate root from sys.path and lead with this project root. Idempotent
with the root conftest when both load during whole-estate runs.
"""

import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_ESTATE_ROOT = os.path.dirname(_PROJECT_ROOT)

# 1. The estate root must not contribute a namespace portion.
sys.path[:] = [p for p in sys.path if p not in ("", ".", _ESTATE_ROOT)]

# 2. This project root leads, so the real package (with __init__.py) wins.
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# 3. Drop a stale namespace entry if one was cached before this fix ran.
_mod = sys.modules.get("mem20gamez")
if (_mod is not None and getattr(_mod, "__file__", None) is None
        and getattr(_mod, "__path__", None) is not None):
    del sys.modules["mem20gamez"]
