"""OPTIONAL Blender integration (shipped as a separate, pluggable module).

Blender is NOT a required dependency. These tools degrade gracefully: when Blender
is not installed (or MEM20_BLENDER_EXECUTABLE is unset), the runner returns an
informative message instead of failing. See server._run_blender_script.
"""
import mcp_types as mt

import os
import sys
import json
import re
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional


sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
