"""mem20 companion, coach and assistant runtime.

Crew runtime grouping reviewed packages for joint integration under the
package-review rulings. Member systems live in their own directories;
this runtime provides the registry, CLI surface, and shared surface.
"""

from __future__ import annotations

__version__ = "0.1.0"

MEMBERS = (
    "mem20ambientdevicecompanionz",
    "mem20conflictdeescalationassistantz",
    "mem20contextawarelearningcoachz",
    "mem20conversationalactiondesktopz",
    "mem20humancapabilityacceleratorz",
    "mem20humancapabilitysuperplatformz",
    "mem20personalautomationcanvasz",
    "mem20personalintelligencecompanionz",
    "mem20universalcompaniondevicesdkz",
)

__all__ = ["__version__", "MEMBERS"]
