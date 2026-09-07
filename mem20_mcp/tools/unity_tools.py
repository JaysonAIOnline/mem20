"""OPTIONAL Unity integration (shipped as a separate, pluggable module).

Unity is NOT a required dependency. The build/test tools degrade gracefully: when
Unity is not installed (or MEM20_UNITY_EXECUTABLE is unset / the default path is
absent), they return an informative message instead of failing.
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
