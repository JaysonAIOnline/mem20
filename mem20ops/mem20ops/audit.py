"""Cloudflare audit workflows: DNS inventory and Pages project inspection."""

from __future__ import annotations

import re
from typing import Any

from .cloudflare import CloudflareAPI, build_client, fetch_text, resolve_account_id

TITLE_RE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)
HEADING_RE = re.compile(r"<h[1-3][^>]*>(.*?)</h[1-3]>", re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")


def _strip_tags(fragment: str) -> str:
    return re.sub(r"\s+", " ", TAG_RE.sub("", fragment)).strip()


def audit_dns(
    zone_name: str,
    pattern: str | None = None,
    client: CloudflareAPI | None = None,
) -> dict[str, Any]:
    """Inventory a zone: type counts, full record list, and shadowing findings."""
    cf = client or build_client()
    zone_id = cf.get_zone_id(zone_name)
    records = cf.dns_records(zone_id)

    type_counts: dict[str, int] = {}
    origin_groups: dict[str, list[str]] = {}
    rows: list[dict[str, Any]] = []

    for record in records:
        rtype = record.get("type", "?")
        type_counts[rtype] = type_counts.get(rtype, 0) + 1
        content = str(record.get("content", ""))
        origin_groups.setdefault(content, []).append(record.get("name", ""))
        rows.append(
            {
                "type": rtype,
                "name": record.get("name", ""),
                "content": content,
                "proxied": record.get("proxied"),
                "ttl": record.get("ttl"),
                "id": record.get("id"),
            }
        )

    if pattern:
        rows = [r for r in rows if re.search(pattern, r["name"], re.IGNORECASE)
                or re.search(pattern, r["content"], re.IGNORECASE)]

    rows.sort(key=lambda r: (r["type"], r["name"]))

    wildcards = [r for r in records if r.get("name", "").startswith("*.")]
    email_records = [r for r in records if r.get("type") in {"MX", "TXT"}]

    return {
        "zone": zone_name,
        "zone_id": zone_id,
        "total_records": len(records),
        "matched_records": len(rows),
        "type_counts": dict(sorted(type_counts.items())),
        "records": rows,
        "findings": {
            "wildcards": [
                {"name": r.get("name"), "content": r.get("content"), "proxied": r.get("proxied")}
                for r in wildcards
            ],
            "wildcard_shadows_unlisted_hosts": bool(wildcards),
            "email_routing_records": len(email_records),
            "origin_groups": {
                origin: sorted(names) for origin, names in sorted(origin_groups.items())
            },
        },
    }


def inspect_pages(
    account_id: str | None = None,
    project: str | None = None,
    client: CloudflareAPI | None = None,
    fetch_live: bool = True,
) -> dict[str, Any]:
    """List Pages projects, or inspect one project and its live deployment."""
    cf = client or build_client()
    account = account_id or resolve_account_id()

    if project is None:
        projects = cf.pages_projects(account)
        return {
            "account_id": account,
            "total": len(projects),
            "projects": [
                {
                    "name": p.get("name"),
                    "subdomain": p.get("subdomain"),
                    "domains": p.get("domains", []),
                    "created_on": p.get("created_on"),
                    "production_branch": p.get("production_branch"),
                    "latest_deployment": (p.get("latest_deployment") or {}).get("created_on"),
                }
                for p in projects
            ],
        }

    detail = cf.pages_project(account, project)
    deployments = cf.pages_deployments(account, project)
    result: dict[str, Any] = {
        "account_id": account,
        "name": detail.get("name", project),
        "subdomain": detail.get("subdomain"),
        "domains": detail.get("domains", []),
        "created_on": detail.get("created_on"),
        "production_branch": detail.get("production_branch"),
        "latest_deployment": {
            "created_on": (detail.get("latest_deployment") or {}).get("created_on"),
            "environment": (detail.get("latest_deployment") or {}).get("environment"),
            "url": (detail.get("latest_deployment") or {}).get("url"),
        },
        "deployments": [
            {
                "created_on": d.get("created_on"),
                "environment": d.get("environment"),
                "trigger": (d.get("deployment_trigger") or {}).get("type")
                if isinstance(d.get("deployment_trigger"), dict)
                else d.get("deployment_trigger"),
                "is_skipped": d.get("is_skipped"),
            }
            for d in deployments[:10]
        ],
        "deployment_count": len(deployments),
    }

    subdomain = detail.get("subdomain")
    if fetch_live and subdomain:
        status, body = fetch_text(f"https://{subdomain}/")
        title_match = TITLE_RE.search(body)
        result["live"] = {
            "url": f"https://{subdomain}/",
            "status": status,
            "bytes": len(body),
            "title": _strip_tags(title_match.group(1)) if title_match else None,
            "headings": [
                _strip_tags(h) for h in HEADING_RE.findall(body) if _strip_tags(h)
            ][:10],
        }
    return result


def delete_pages_project(
    project: str,
    account_id: str | None = None,
    confirm: bool = False,
    client: CloudflareAPI | None = None,
) -> dict[str, Any]:
    """Delete a Pages project. Requires ``confirm=True``; reports before/after state."""
    if not confirm:
        raise ValueError("refusing to delete without --confirm")
    cf = client or build_client()
    account = account_id or resolve_account_id()

    before = cf.pages_project(account, project)
    cf.delete_pages_project(account, project)

    remaining = [p.get("name") for p in cf.pages_projects(account)]
    return {
        "deleted": project,
        "existed": bool(before),
        "previous_subdomain": before.get("subdomain"),
        "previous_domains": before.get("domains", []),
        "still_present": project in remaining,
        "remaining_projects": remaining,
    }
