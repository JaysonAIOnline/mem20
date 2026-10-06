"""mem20 interface and workspace runtime.

Crew runtime grouping reviewed packages for joint integration under the
package-review rulings. Member systems live in their own directories;
this runtime provides the registry, CLI surface, and shared surface.
"""

from __future__ import annotations

__version__ = "0.1.0"

MEMBERS = (
    "mem20adaptiveinterfacecomposerz",
    "mem20musicvisualsynchronizerz",
    "mem20parallelworkstreamcomposerz",
    "mem20spatialcommanduniversez",
    "mem20spatialexperiencedesignerz",
    "mem20visualagentblackboardz",
    "mem20visualdataflowcomposerz",
    "mem20voicetoactionswitchboardz",
)

__all__ = ["__version__", "MEMBERS"]
