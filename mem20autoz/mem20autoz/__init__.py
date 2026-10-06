"""mem20 autonomous systems runtime.

Crew runtime grouping reviewed packages for joint integration under the
package-review rulings. Member systems live in their own directories;
this runtime provides the registry, CLI surface, and shared surface.
"""

from __future__ import annotations

__version__ = "0.1.0"

MEMBERS = (
    "mem20autonomouscodesurgeonz",
    "mem20autonomousdealdeskz",
    "mem20autonomousmicrosaasfoundryz",
    "mem20autonomousrecoverydirectorz",
    "mem20autonomousreviewswarmz",
    "mem20autonomoussoftwarefoundryz",
    "mem20autonomoustrafficcontrollerz",
    "mem20autonomousworkcellsz",
    "mem20dailydecisioncopilotz",
    "mem20databaseautopilotz",
    "mem20deviceenrollmentautopilotz",
    "mem20realtimeeventautopilotz",
    "mem20smartmeetingcopilotz",
    "mem20uniteconomicsautopilotz",
)

__all__ = ["__version__", "MEMBERS"]
