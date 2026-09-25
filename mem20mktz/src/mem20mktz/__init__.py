"""mem20mktz — mem30 Phase 2 marketplace organs on the estate.

Two marketplaces trade real offers (release gate):
  - Inference Marketplace (RM-070) on the Adaptive Inference Scheduler
  - Capability Marketplace (RM-010) on top of the Universal Capability Graph
Plus service bundling (RM-087), adaptive pricing (RM-015), and braid-journaled
resource trades (RM-012) so a composed, priced offer can actually be bought
and the trade becomes a braid node (exit test).
"""
__version__ = "0.1.0"

from .descriptor import (
    MKTZ_DESCRIPTORS,
    all_descriptors,
)
from .service import MarketService

__all__ = ["MKTZ_DESCRIPTORS", "MarketService", "__version__", "all_descriptors"]