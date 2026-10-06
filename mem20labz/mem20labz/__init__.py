"""mem20 laboratory runtime.

Crew runtime grouping reviewed packages for joint integration under the
package-review rulings. Member systems live in their own directories;
this runtime provides the registry, CLI surface, and shared surface.
"""

from __future__ import annotations

__version__ = "0.1.0"

MEMBERS = (
    "mem20autonomoussaleslaboratoryz",
    "mem20continuouscompatibilitylabz",
    "mem20customerdigitaltwinlabz",
    "mem20dependencymutationlabz",
    "mem20executabledesignstresslabz",
    "mem20modelgenomelabz",
    "mem20neuromorphiceventlabz",
    "mem20outcomesimulationlabz",
    "mem20remoteexperimentlabz",
    "mem20webassemblycomponentlabz",
)

__all__ = ["__version__", "MEMBERS"]
