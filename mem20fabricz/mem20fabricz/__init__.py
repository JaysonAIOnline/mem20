"""mem20 integration fabric runtime.

Crew runtime grouping reviewed packages for joint integration under the
package-review rulings. Member systems live in their own directories;
this runtime provides the registry, CLI surface, and shared surface.
"""

from __future__ import annotations

__version__ = "0.1.0"

MEMBERS = (
    "mem20apishapeshiftinggatewayz",
    "mem20characterandmascotforgez",
    "mem20collectivemodelintelligencez",
    "mem20contextcompressionforgez",
    "mem20crisisresponsemeshz",
    "mem20crossruntimeeventlatticez",
    "mem20edgetransportfabricz",
    "mem20eventstreamsuperhighwayz",
    "mem20federatedmodellearningmeshz",
    "mem20freestackambientcomputingfabricz",
    "mem20livemodelfusionz",
    "mem20modalitybridgez",
    "mem20modelsleepandwakesystemz",
    "mem20nearbydevicemeshz",
    "mem20offlineresiliencemeshz",
    "mem20personalmodelevolutionz",
    "mem20planetarybatchfabricz",
    "mem20rewardforgez",
    "mem20sensorfusiongatewayz",
    "mem20specialistmodelforgez",
    "mem20syntheticdataforgez",
    "mem20temporaldatabasefabricz",
    "mem20universalintegrationcompilerz",
)

__all__ = ["__version__", "MEMBERS"]
