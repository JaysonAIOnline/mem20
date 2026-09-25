"""mem20 agentz — the agent platform, built directly into mem20.

Full-fidelity cleanroom: every known capability of the absorbed agent platform
re-implemented on mem20 natives under mem20 branding. See docs/PLAN.md for the
feature inventory + architecture map.
"""

__version__ = "0.1.0"
__all__ = ["__version__", "config", "profiles", "sessions"]

from . import config, profiles, sessions  # noqa: F401,E402