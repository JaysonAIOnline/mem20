#!/usr/bin/env python3
"""Static verification of the mem20 decomposition (no runtime/MCP dependency).

Checks:
  1. All expected module files exist.
  2. Exactly 97 tool registrations across server.py + mixins.
  3. Every dispatched tool has a handler method defined somewhere.
  4. Mem20MCPServer inherits the five mixin classes.
  5. memory.py contains no live eval() call.

Exit code 0 = PASS, 1 = FAIL.
"""
import ast
import os
import re
import sys

MCP_DIR = os.environ.get("MEM20_MCP_DIR", "/home/jayson/mem20/mcp")
REPO = os.path.dirname(MCP_DIR)
MEMORY = os.environ.get("MEM20_ENGINE", os.path.join(REPO, "memory_engine", "memory.py"))
EXPECTED_TOOLS = 97
MIXINS = ["MemoryToolsMixin", "CognitiveToolsMixin", "RoadmapToolsMixin",
          "WorldToolsMixin", "BlenderToolsMixin", "UnityToolsMixin",
          "IntegrationToolsMixin"]
MODULE_FILES = [
    "server.py", "memory_tools.py", "cognitive_tools.py", "roadmap_tools.py",
    "health.py",
    "tools/__init__.py", "tools/world_tools.py", "tools/blender_tools.py",
    "tools/unity_tools.py", "tools/integration_tools.py",
    "resources/__init__.py", "prompts/__init__.py", "mcp_server.py",
]


def read(p):
    with open(p) as f:
        return f.read()


def main():
    failures = []

    # 1. files exist
    for rel in MODULE_FILES:
        if not os.path.exists(os.path.join(MCP_DIR, rel)):
            failures.append(f"missing file: {rel}")

    # 2. registration count
    reg_files = ["server.py", "memory_tools.py", "cognitive_tools.py",
                 "roadmap_tools.py", "tools/world_tools.py", "tools/blender_tools.py",
                 "tools/unity_tools.py", "tools/integration_tools.py"]
    total_regs = 0
    for f in reg_files:
        src = read(os.path.join(MCP_DIR, f))
        total_regs += len(re.findall(r'self\.tools\["[^"]+"\]\s*=\s*mt\.Tool\(', src))
    if total_regs != EXPECTED_TOOLS:
        failures.append(f"registration count = {total_regs}, expected {EXPECTED_TOOLS}")
    else:
        print(f"[ok] registrations = {total_regs}")

    # 3 + 4. parse server.py
    server_src = read(os.path.join(MCP_DIR, "server.py"))
    tree = ast.parse(server_src)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef)
               and n.name == "Mem20MCPServer")
    bases = [b.id for b in cls.bases if isinstance(b, ast.Name)]
    for m in MIXINS:
        if m not in bases:
            failures.append(f"Mem20MCPServer does not inherit {m}")
    if set(MIXINS).issubset(set(bases)):
        print(f"[ok] inherits mixins: {', '.join(bases)}")

    # gather all handler defs across modules
    handler_defs = set()
    for f in reg_files:
        t = ast.parse(read(os.path.join(MCP_DIR, f)))
        for node in ast.walk(t):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("_"):
                handler_defs.add(node.name)

    # dispatch tools -> handlers (from server.py _execute_tool)
    ex = next("".join(read(os.path.join(MCP_DIR, "server.py")).splitlines(keepends=True)[n.lineno - 1:n.end_lineno])
              for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "_execute_tool")
    missing = []
    for m in re.finditer(r'tool_name == "([^"]+)"', ex):
        rest = ex[m.end():m.end() + 400]
        h = re.search(r'self\._([a-zA-Z0-9_]+)\(', rest)
        if not h:
            failures.append(f"dispatch tool {m.group(1)} has no handler call")
            continue
        handler = "_" + h.group(1)
        if handler not in handler_defs:
            missing.append(m.group(1))
    if missing:
        failures.append(f"dispatched tools missing handler: {missing}")
    else:
        print(f"[ok] all {len(re.findall(r'tool_name == \"', ex))} dispatched tools resolve to a handler")

    # 5. no live eval() in memory engine
    mem_src = read(MEMORY)
    live_eval = 0
    for line in mem_src.splitlines():
        s = line.lstrip()
        if "eval(" in line and not s.startswith("#") and "``eval()``" not in line:
            live_eval += 1
    if live_eval:
        failures.append(f"memory.py has {live_eval} live eval() call(s)")
    else:
        print("[ok] memory.py has no live eval() call")

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print("  - " + f)
        sys.exit(1)
    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    main()
