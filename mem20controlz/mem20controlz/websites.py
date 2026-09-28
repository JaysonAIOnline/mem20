"""Websites manager: fleet deploys, health, logs, and Cloudflare DNS management.

This is Step 7 of the fleet build. It deliberately reuses mem20ops for every
Cloudflare operation rather than reimplementing an API client, so there is one
place that knows how to talk to Cloudflare.

Reads are free. Writes (DNS mutation, deploy) are explicit, named, and audited.
"""

from __future__ import annotations

import subprocess
from typing import Any

from mem20ops import audit
from mem20ops.cloudflare import CloudflareAPI, build_client, resolve_account_id

# The four sites this fleet serves, plus the origin host. Kept here so the
# Websites manager can show the intended shape next to what actually exists.
FLEET_SITES: list[dict[str, str]] = [
    {"host": "control.jaysonai.online", "role": "control plane", "state": "planned"},
    {"host": "shop.jaysonai.online", "role": "sales site", "state": "planned"},
    {"host": "market.jaysonai.online", "role": "marketing command center", "state": "planned"},
    {"host": "docs.jaysonai.online", "role": "documentation wiki", "state": "planned"},
    {"host": "jaysonai.online", "role": "fleet landing (apex)", "state": "planned"},
    {"host": "www.jaysonai.online", "role": "apex alias", "state": "planned"},
    {"host": "jnet1.jaysonai.online", "role": "box origin", "state": "live"},
    {"host": "mem20.jaysonai.online", "role": "mem20 pages site (kept)", "state": "live"},
]

DEFAULT_ZONE = "jaysonai.online"
# The units this fleet depends on, and which systemd manager owns each one.
# Scope matters: the system manager cannot see a user unit and reports it as
# inactive/dead, so asking the wrong manager invents a failure that never
# happened. These are (unit, is_user_unit) pairs.
UNIT_CANDIDATES = (
    ("mcp-server.service", False),
    ("mem20controlz.service", False),
    ("mem20cviz.service", True),
    ("mem20ucgz.service", True),
    ("mem20sensorz.service", False),
)


def site_inventory() -> dict[str, Any]:
    """What the fleet is supposed to serve, and what Cloudflare actually serves."""
    try:
        client = build_client()
        zone_id = client.get_zone_id(DEFAULT_ZONE)
        records = client.dns_records(zone_id)
        api_error = None
    except Exception as exc:  # noqa: BLE001 - surfaced to the panel, never hidden
        client = None
        zone_id = None
        records = []
        api_error = f"{type(exc).__name__}: {exc}"

    live_hosts = {r.get("name", "").lower() for r in records}
    sites = []
    for site in FLEET_SITES:
        host = site["host"].lower()
        sites.append(
            {
                **site,
                "dns_present": host in live_hosts,
                "observed": host in live_hosts and site["state"] == "planned",
            }
        )

    return {
        "zone": DEFAULT_ZONE,
        "zone_id": zone_id,
        "api_error": api_error,
        "record_count": len(records),
        "wildcards": [r.get("name") for r in records if r.get("name", "").startswith("*.")],
        "sites": sites,
    }


def dns_records(zone: str = DEFAULT_ZONE, pattern: str | None = None) -> dict[str, Any]:
    """Full DNS inventory, reusing the audited mem20ops implementation."""
    report = audit.audit_dns(zone, pattern=pattern)
    return {
        "zone": report["zone"],
        "total_records": report["total_records"],
        "matched_records": report["matched_records"],
        "type_counts": report["type_counts"],
        "records": report["records"],
        "findings": report["findings"],
    }


def dns_create(
    zone: str,
    record_type: str,
    name: str,
    content: str,
    proxied: bool = False,
    ttl: int = 1,
    client: CloudflareAPI | None = None,
) -> dict[str, Any]:
    """Create one DNS record. Explicit write endpoint; audited by the ledger."""
    cf = client or build_client()
    zone_id = cf.get_zone_id(zone)
    created = cf.create_dns_record(
        zone_id,
        {
            "type": record_type,
            "name": name,
            "content": content,
            "proxied": bool(proxied),
            "ttl": int(ttl),
        },
    )
    return {
        "created": True,
        "record": {
            "id": created.get("id"),
            "type": created.get("type"),
            "name": created.get("name"),
            "content": created.get("content"),
            "proxied": created.get("proxied"),
        },
    }


def dns_delete(
    zone: str, record_id: str, client: CloudflareAPI | None = None
) -> dict[str, Any]:
    """Delete one DNS record by id. Explicit write endpoint."""
    cf = client or build_client()
    zone_id = cf.get_zone_id(zone)
    cf.delete_dns_record(zone_id, record_id)
    return {"deleted": True, "record_id": record_id, "zone": zone}


def health(unit: str = "mcp-server.service", user: bool = False) -> dict[str, Any]:
    """systemd unit health, reusing the mem20ops service-status implementation.

    ``user=True`` asks the per-user manager. The scope is reported back so the
    panel can say which manager answered, and a unit that does not exist is
    named as missing rather than inferred from a dead-looking status.
    """
    from mem20ops import runtime

    result = runtime.service_status(unit, user=user)
    result["active"] = bool(result.get("exists")) and result.get("active_state") == "active"
    return result


def fleet_health() -> dict[str, Any]:
    """Health across the units this fleet depends on.

    A unit that does not exist is reported as ``not-found`` rather than
    "inactive": "inactive" would imply a service that was started and failed,
    which is a different claim than the truth.
    """
    units = []
    for unit, is_user in UNIT_CANDIDATES:
        try:
            units.append(health(unit, user=is_user))
        except Exception as exc:  # noqa: BLE001 - reported per unit
            units.append(
                {
                    "unit": unit,
                    "scope": "user" if is_user else "system",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    return {
        "units": units,
        "count": len(units),
        "healthy": sum(1 for u in units if u.get("active")),
    }


def logs(unit: str, lines: int = 100) -> dict[str, Any]:
    """Bounded journal tail for a unit.

    ``lines`` is clamped to at least 1 before it reaches the slice: a zero or
    negative value would otherwise slice from the front and return the whole
    buffer, which is the opposite of bounded.
    """
    count = max(1, int(lines))
    proc = subprocess.run(
        ["journalctl", "-u", unit, "-n", str(count), "--no-pager"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    text = proc.stdout or ""
    return {
        "unit": unit,
        "lines": text.splitlines()[-count:],
        "exit_code": proc.returncode,
    }


def pages() -> dict[str, Any]:
    """Cloudflare Pages projects, reusing the audited mem20ops implementation."""
    try:
        account = resolve_account_id()
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}", "projects": []}
    try:
        result = audit.inspect_pages(account_id=account, fetch_live=False)
    except Exception as exc:  # noqa: BLE001 - surfaced, never hidden
        return {
            "error": f"{type(exc).__name__}: {exc}",
            "account_id": account,
            "projects": [],
            "total": 0,
        }
    return {"account_id": account, "projects": result["projects"], "total": result["total"]}


def manifest() -> dict[str, Any]:
    """Describe this manager's capabilities for the UI."""
    return {
        "capabilities": [
            "site inventory (planned vs live)",
            "DNS read: full zone inventory with type counts and wildcard detection",
            "DNS write: create and delete single records",
            "service health per systemd unit",
            "bounded journal tail per unit",
            "Cloudflare Pages project listing",
        ],
        "writes_require": "explicit POST with the full record fields; nothing is implicit",
        "reuses": "mem20ops (dns-audit, pages-inspect, service-status) - one Cloudflare client",
        "zone": DEFAULT_ZONE,
        "fleet_sites": FLEET_SITES,
    }
