"""Repair sys.path so `import mem20googlez` finds the real package.

The package lives at mem20googlez/mem20googlez/, so the outer mem20googlez/
directory is a namespace portion that shadows it when the repo root is on
sys.path. See /opt/mem20/mem20_pathfix.py.
"""

import importlib.util
import os

_spec = importlib.util.spec_from_file_location(
    "mem20_pathfix", os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "mem20_pathfix.py"))
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
_module.apply(os.path.dirname(os.path.abspath(__file__)))
