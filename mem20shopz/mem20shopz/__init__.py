"""mem20shopz — the mem20 storefront.

One FastAPI process serves the storefront and the API from a single origin. The
payment path is deliberately dull: verify, de-duplicate, provision once, and
refuse anything that is not fully configured.
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
