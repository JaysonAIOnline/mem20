"""mem20 simulator runtime.

Crew runtime grouping reviewed packages for joint integration under the
package-review rulings. Member systems live in their own directories;
this runtime provides the registry, CLI surface, and shared surface.
"""

from __future__ import annotations

__version__ = "0.1.0"

MEMBERS = (
    "mem20audiencereactionsimulatorz",
    "mem20businessmodelsimulatorz",
    "mem20counterfactualmemorysimulatorz",
    "mem20ethicalincentivesimulatorz",
    "mem20gamebalancesimulatorz",
    "mem20lifescenariosimulatorz",
    "mem20productledgrowthsimulatorz",
    "mem20useracceptancesimulatorz",
)

__all__ = ["__version__", "MEMBERS"]
