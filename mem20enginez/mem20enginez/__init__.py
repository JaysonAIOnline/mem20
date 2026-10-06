"""mem20 engine runtime.

Crew runtime grouping reviewed packages for joint integration under the
package-review rulings. Member systems live in their own directories;
this runtime provides the registry, CLI surface, and shared surface.
"""

from __future__ import annotations

__version__ = "0.1.0"

MEMBERS = (
    "mem20adaptiveachievementenginez",
    "mem20adaptivedispatchenginez",
    "mem20adaptiveforgettingenginez",
    "mem20adaptivepersonalityruntimez",
    "mem20apprenticeshipruntimez",
    "mem20chaosnativeapplicationruntimez",
    "mem20communitychallengeenginez",
    "mem20communitypulseenginez",
    "mem20completionconfidenceenginez",
    "mem20crdtcollaborationenginez",
    "mem20crosslanguagerefactorenginez",
    "mem20customerlifecycleenginez",
    "mem20dynamicnarrativeenginez",
    "mem20featuredependencygraphenginez",
    "mem20generativebrandworldenginez",
    "mem20liveprojectdemonstrationenginez",
    "mem20liveschemamorphingenginez",
    "mem20mixedinitiativefocusenginez",
    "mem20mobileedgeagentruntimez",
    "mem20multilingualliveconversationenginez",
    "mem20offergenomeenginez",
    "mem20outcomeverificationruntimez",
    "mem20peertopeerappruntimez",
    "mem20predictiverecallenginez",
    "mem20privatelocalreasoningenginez",
    "mem20protocolautodiscoveryenginez",
    "mem20runtimebugpredictionenginez",
    "mem20runtimecompatibilityenginez",
    "mem20servicebundlingenginez",
    "mem20speculativeworkflowenginez",
)

__all__ = ["__version__", "MEMBERS"]
