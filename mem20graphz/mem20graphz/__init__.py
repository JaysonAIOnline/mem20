"""mem20 graph systems runtime.

Crew runtime grouping reviewed packages for joint integration under the
package-review rulings. Member systems live in their own directories;
this runtime provides the registry, CLI surface, and shared surface.
"""

from __future__ import annotations

__version__ = "0.1.0"

MEMBERS = (
    "mem20capabilitygapmapperz",
    "mem20crossproductloyaltygraphz",
    "mem20deterministicconfigurationgraphz",
    "mem20dynamicskillgraphz",
    "mem20relationshipcontextgraphz",
    "mem20reversibleexecutiongraphz",
    "mem20semanticobjectgraphz",
)

__all__ = ["__version__", "MEMBERS"]
