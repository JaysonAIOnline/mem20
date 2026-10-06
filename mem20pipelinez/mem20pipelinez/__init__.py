"""mem20 production pipeline runtime for game-maker and software pipelines.

Crew runtime grouping reviewed packages for joint integration under the
package-review rulings. Member systems live in their own directories;
this runtime provides the registry, CLI surface, and shared surface.
"""

from __future__ import annotations

__version__ = "0.1.0"

MEMBERS = (
    "mem20assetintakecatalogingandvalidationpipelinez",
    "mem20audiovoiceandmusicpipelinez",
    "mem20executablegameconceptandscopepipelinez",
    "mem20gameplaysystemsdataandbalancepipelinez",
    "mem20leveldesignworldbuildingandnavigationpipelinez",
    "mem20narrativedialogueandlocalizationpipelinez",
    "mem20personalworkflowtwinz",
    "mem20productionplanningandtaskorchestrationpipelinez",
    "mem20realtimestyletransferpipelinez",
    "mem20rigginganimationandmotionpipelinez",
    "mem20securebuildtodevicepipelinez",
    "mem20versioncontrollargeassetandrecoverypipelinez",
)

__all__ = ["__version__", "MEMBERS"]
