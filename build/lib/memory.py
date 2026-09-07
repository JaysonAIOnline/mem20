# Thin shim so `import memory` (used throughout the MCP layer) resolves to the
# single, unified engine in `memory_engine/`. This keeps the live deployment, a
# clean clone, and the GitHub source all pointing at one engine module.
import sys

import memory_engine.memory as _mem20_engine

sys.modules[__name__] = _mem20_engine
