"""General filesystem integration + the BLANK TEMPLATE module for new optional integrations.

This is the "3rd module": it hosts the always-available filesystem tools (fs_read /
fs_write / fs_list) and a documented blank scaffold (`register_integration_template`)
showing how to add a new OPTIONAL integration (e.g., Figma) as its own pluggable
mixin under `tools/`. Per 2.1 packaging, Blender and Unity live in their own optional
modules (tools/blender_tools.py, tools/unity_tools.py) and require the applications installed.
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
