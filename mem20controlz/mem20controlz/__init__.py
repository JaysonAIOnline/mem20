"""mem20controlz - the unified control plane for the mem20 fleet.

One FastAPI service that presents every subsystem as a panel, driving each one
REST-first and falling back to its standardised CLI. It also hosts the Websites
manager (deploy, health, logs, DNS CRUD).

Design rules:

* the registry is derived from the real estate at request time, never hardcoded,
  so a panel can never claim a subsystem that is not there
* status is honest: ``ok`` means a probe actually succeeded, and anything that
  cannot be verified is reported as ``unknown`` rather than optimistic
* every probe is bounded by a timeout, so one wedged subsystem cannot hang the UI
* reads never mutate; writes go through explicit, named endpoints
"""

__version__ = "0.1.0"
