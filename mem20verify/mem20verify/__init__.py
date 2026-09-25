"""mem20verify — verification toolkit for the mem20 estate.

Every check here executes something real against the live system or the real
source tree. A check that cannot run reports the error and exits non-zero; it
never reports a pass it did not earn.
"""

from .dataintegrity import IntegrityResult
from .linters import ALL_CHECKS, Issue
from .outage import OutageResult
from .systemd import UnitReport, check_unit, sweep
from .testrun import (
    BaselineVerdict,
    TestResult,
    attribute,
    discover_packages,
    run_package,
)

__all__ = [
    "ALL_CHECKS",
    "BaselineVerdict",
    "IntegrityResult",
    "Issue",
    "OutageResult",
    "TestResult",
    "UnitReport",
    "attribute",
    "check_unit",
    "discover_packages",
    "run_package",
    "sweep",
]
__version__ = "0.1.0"
