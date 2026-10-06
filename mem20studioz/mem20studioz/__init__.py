"""mem20 studio runtime.

Crew runtime grouping reviewed packages for joint integration under the
package-review rulings. Member systems live in their own directories;
this runtime provides the registry, CLI surface, and shared surface.
"""

from __future__ import annotations

__version__ = "0.1.0"

MEMBERS = (
    "mem20aigamestudiobuilderz",
    "mem20aiproductionstudiooperatingsystemz",
    "mem20assetremixstudioz",
    "mem20protocolinventionstudioz",
    "mem20webgpucomputestudioz",
)

__all__ = ["__version__", "MEMBERS"]
