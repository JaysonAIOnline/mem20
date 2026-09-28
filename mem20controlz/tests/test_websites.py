"""Websites manager: reads are free, writes are explicit, nothing touches the net."""

import subprocess

import pytest
from mem20ops import audit, runtime

from mem20controlz import websites


class FakeCloudflare:
    def __init__(self, records=(), zone_id="zone-1", raises=None, projects=()):
        self.records = [dict(r) for r in records]
        self.zone_id = zone_id
        self.raises = raises
        self.projects = list(projects)
        self.zone_lookups = []
        self.record_lookups = []
        self.created = []
        self.deleted = []

    def _maybe_raise(self, where):
        if self.raises == where:
            raise RuntimeError(f"cloudflare {where} exploded")

    def get_zone_id(self, zone_name):
        self.zone_lookups.append(zone_name)
        self._maybe_raise("get_zone_id")
        return self.zone_id

    def dns_records(self, zone_id, per_page=200):
        self.record_lookups.append((zone_id, per_page))
        self._maybe_raise("dns_records")
        return [dict(r) for r in self.records]

    def create_dns_record(self, zone_id, payload):
        self.created.append((zone_id, payload))
        self._maybe_raise("create_dns_record")
        return {
            "id": "rec-new",
            "type": payload["type"],
            "name": payload["name"],
            "content": payload["content"],
            "proxied": payload["proxied"],
            "ttl": payload["ttl"],
        }

    def delete_dns_record(self, zone_id, record_id):
        self.deleted.append((zone_id, record_id))
        self._maybe_raise("delete_dns_record")
        return {"success": True}

    def pages_projects(self, account_id):
        self._maybe_raise("pages_projects")
        return [dict(p) for p in self.projects]


def record(name, rtype="A", content="10.0.0.1", proxied=False, ttl=1, rid=None):
    return {
        "id": rid or f"id-{name}",
        "name": name,
        "type": rtype,
        "content": content,
        "proxied": proxied,
        "ttl": ttl,
    }


def no_network_client(monkeypatch):
    monkeypatch.setattr(
        websites,
        "build_client",
        lambda *a, **k: pytest.fail("build_client must not be used"),
    )


def test_manifest_returns_the_documented_keys():
    result = websites.manifest()
    assert set(result) == {
        "capabilities",
        "writes_require",
        "reuses",
        "zone",
        "fleet_sites",
    }
    assert result["zone"] == websites.DEFAULT_ZONE
    assert result["capabilities"]
    assert all(isinstance(c, str) and c for c in result["capabilities"])
    assert "mem20ops" in result["reuses"]


def test_manifest_fleet_sites_are_well_formed():
    sites = websites.manifest()["fleet_sites"]
    assert sites == websites.FLEET_SITES
    for site in sites:
        assert set(site) == {"host", "role", "state"}
        assert site["state"] in {"planned", "live"}


def test_manifest_lists_write_and_read_capabilities():
    caps = " ".join(websites.manifest()["capabilities"])
    assert "DNS read" in caps
    assert "DNS write" in caps
    assert "journal tail" in caps
    assert "Cloudflare Pages" in caps


def test_dns_create_sends_the_exact_payload(monkeypatch):
    no_network_client(monkeypatch)
    client = FakeCloudflare()

    result = websites.dns_create(
        "jaysonai.online",
        "A",
        "shop.jaysonai.online",
        "10.0.0.7",
        proxied=True,
        ttl=300,
        client=client,
    )

    assert client.zone_lookups == ["jaysonai.online"]
    assert client.created == [
        (
            "zone-1",
            {
                "type": "A",
                "name": "shop.jaysonai.online",
                "content": "10.0.0.7",
                "proxied": True,
                "ttl": 300,
            },
        )
    ]
    assert result["created"] is True
    assert result["record"] == {
        "id": "rec-new",
        "type": "A",
        "name": "shop.jaysonai.online",
        "content": "10.0.0.7",
        "proxied": True,
    }


def test_dns_create_defaults_are_dns_but_valid(monkeypatch):
    no_network_client(monkeypatch)
    client = FakeCloudflare()

    websites.dns_create("z.example", "TXT", "z.example", "v=spf1", client=client)

    _, payload = client.created[0]
    assert payload["proxied"] is False
    assert payload["ttl"] == 1
    assert set(payload) == {"type", "name", "content", "proxied", "ttl"}


def test_dns_create_coerces_proxied_and_ttl(monkeypatch):
    no_network_client(monkeypatch)
    client = FakeCloudflare()

    websites.dns_create(
        "z.example", "A", "z.example", "1.1.1.1", proxied=1, ttl="60", client=client
    )

    _, payload = client.created[0]
    assert payload["proxied"] is True
    assert payload["ttl"] == 60
    assert isinstance(payload["ttl"], int)


def test_dns_create_propagates_client_failure(monkeypatch):
    no_network_client(monkeypatch)
    client = FakeCloudflare(raises="create_dns_record")

    with pytest.raises(RuntimeError, match="create_dns_record exploded"):
        websites.dns_create("z.example", "A", "z.example", "1.1.1.1", client=client)


def test_dns_delete_calls_through_with_zone_and_id(monkeypatch):
    no_network_client(monkeypatch)
    client = FakeCloudflare()

    result = websites.dns_delete("jaysonai.online", "rec-42", client=client)

    assert client.zone_lookups == ["jaysonai.online"]
    assert client.deleted == [("zone-1", "rec-42")]
    assert result == {
        "deleted": True,
        "record_id": "rec-42",
        "zone": "jaysonai.online",
    }


def test_dns_delete_propagates_client_failure(monkeypatch):
    no_network_client(monkeypatch)
    client = FakeCloudflare(raises="delete_dns_record")

    with pytest.raises(RuntimeError, match="delete_dns_record exploded"):
        websites.dns_delete("jaysonai.online", "rec-42", client=client)


def test_dns_records_forwards_the_pattern(monkeypatch):
    seen = {}

    def fake_audit_dns(zone_name, pattern=None, client=None):
        seen["zone"] = zone_name
        seen["pattern"] = pattern
        seen["client"] = client
        return {
            "zone": zone_name,
            "zone_id": "zone-1",
            "total_records": 2,
            "matched_records": 1,
            "type_counts": {"A": 2},
            "records": [{"name": "a.example", "type": "A"}],
            "findings": {"wildcards": []},
        }

    monkeypatch.setattr(audit, "audit_dns", fake_audit_dns)

    result = websites.dns_records("jaysonai.online", pattern="^shop\\.")

    assert seen == {"zone": "jaysonai.online", "pattern": "^shop\\.", "client": None}
    assert set(result) == {
        "zone",
        "total_records",
        "matched_records",
        "type_counts",
        "records",
        "findings",
    }
    assert result["matched_records"] == 1
    assert result["records"] == [{"name": "a.example", "type": "A"}]


def test_dns_records_defaults_to_no_pattern(monkeypatch):
    seen = {}

    def fake_audit_dns(zone_name, pattern=None, client=None):
        seen["zone"] = zone_name
        seen["pattern"] = pattern
        return {
            "zone": zone_name,
            "total_records": 0,
            "matched_records": 0,
            "type_counts": {},
            "records": [],
            "findings": {},
        }

    monkeypatch.setattr(audit, "audit_dns", fake_audit_dns)

    websites.dns_records()
    assert seen == {"zone": websites.DEFAULT_ZONE, "pattern": None}


def test_dns_records_actually_filters_through_a_fake_client(monkeypatch):
    client = FakeCloudflare(
        records=[
            record("shop.jaysonai.online"),
            record("docs.jaysonai.online", content="10.0.0.2"),
            record("jaysonai.online", rtype="MX", content="mx.provider.com"),
        ]
    )
    monkeypatch.setattr(audit, "build_client", lambda *a, **k: client)

    result = websites.dns_records("jaysonai.online", pattern="^shop")

    assert result["total_records"] == 3
    assert result["matched_records"] == 1
    assert [r["name"] for r in result["records"]] == ["shop.jaysonai.online"]
    assert result["type_counts"] == {"A": 2, "MX": 1}
    assert client.zone_lookups == ["jaysonai.online"]


def test_logs_bounds_the_line_count(monkeypatch):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = list(argv)
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            argv, 0, stdout="\n".join(f"line {i}" for i in range(200)), stderr=""
        )

    monkeypatch.setattr(websites.subprocess, "run", fake_run)

    result = websites.logs("mcp-server.service", lines=5)

    assert "-n" in captured["argv"]
    assert captured["argv"][captured["argv"].index("-n") + 1] == "5"
    assert result["unit"] == "mcp-server.service"
    assert result["lines"] == ["line 195", "line 196", "line 197", "line 198", "line 199"]
    assert result["exit_code"] == 0


def test_logs_never_runs_unbounded(monkeypatch):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = list(argv)
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(websites.subprocess, "run", fake_run)

    for lines in (1, 7, 100, 5000):
        websites.logs("mem20cviz.service", lines=lines)
        argv = captured["argv"]
        assert argv[0] == "journalctl"
        assert argv[argv.index("-n") + 1] == str(lines)
        assert "--no-pager" in argv
        assert argv[argv.index("-u") + 1] == "mem20cviz.service"
        assert isinstance(captured["kwargs"].get("timeout"), (int, float))
        assert 0 < captured["kwargs"]["timeout"] < 120
        assert captured["kwargs"]["timeout"] is not None


def test_logs_reports_the_journalctl_exit_code(monkeypatch):
    monkeypatch.setattr(
        websites.subprocess,
        "run",
        lambda argv, **kw: subprocess.CompletedProcess(argv, 1, stdout="a\nb", stderr=""),
    )

    result = websites.logs("gone.service", lines=10)
    assert result["exit_code"] == 1
    assert result["lines"] == ["a", "b"]


def test_logs_clamps_output_fewer_lines_than_requested(monkeypatch):
    monkeypatch.setattr(
        websites.subprocess,
        "run",
        lambda argv, **kw: subprocess.CompletedProcess(argv, 0, stdout="only\n", stderr=""),
    )

    assert websites.logs("unit.service", lines=100)["lines"] == ["only"]


def test_health_derives_active_from_active_state(monkeypatch):
    monkeypatch.setattr(
        runtime,
        "service_status",
        lambda unit, user=False: {
            "unit": unit,
            "scope": "user" if user else "system",
            "load_state": "loaded",
            "exists": True,
            "active_state": "active",
            "main_pid": 42,
        },
    )

    result = websites.health("mcp-server.service")
    assert result["active"] is True
    assert result["main_pid"] == 42
    assert result["exists"] is True


def test_health_is_false_for_any_non_active_state(monkeypatch):
    for state in ("failed", "inactive", "activating", None):
        monkeypatch.setattr(
            runtime,
            "service_status",
            lambda unit, user=False, s=state: {
                "unit": unit,
                "load_state": "loaded",
                "exists": True,
                "active_state": s,
            },
        )
        assert websites.health("u.service")["active"] is False


def test_missing_unit_is_not_reported_as_inactive(monkeypatch):
    """A unit that does not exist must not look like a failed service."""
    monkeypatch.setattr(
        runtime,
        "service_status",
        lambda unit, user=False: {
            "unit": unit,
            "load_state": "not-found",
            "exists": False,
            "active_state": "inactive",
            "sub_state": "dead",
        },
    )

    result = websites.health("ghost.service")
    assert result["exists"] is False
    assert result["active"] is False
    assert result["load_state"] == "not-found"


def test_health_asks_for_the_right_systemd_scope(monkeypatch):
    """A user unit must be queried against the user manager.

    The system manager cannot see user units and reports them inactive/dead,
    which would invent a failure that never happened.
    """
    seen = []

    def record(unit, user=False):
        seen.append((unit, user))
        return {"unit": unit, "load_state": "loaded", "exists": True, "active_state": "active"}

    monkeypatch.setattr(runtime, "service_status", record)

    websites.health("mem20cviz.service", user=True)
    websites.health("mcp-server.service", user=False)

    assert ("mem20cviz.service", True) in seen
    assert ("mcp-server.service", False) in seen


def test_user_units_are_monitored_at_the_right_scope(monkeypatch):
    """mem20cviz/mem20ucgz are user units and must be listed as such."""
    names = {unit for unit, _ in websites.UNIT_CANDIDATES}
    assert {"mem20cviz.service", "mem20ucgz.service"} <= names
    scopes = dict(websites.UNIT_CANDIDATES)
    assert scopes["mem20cviz.service"] is True
    assert scopes["mem20ucgz.service"] is True
    assert scopes["mcp-server.service"] is False


def test_replaced_senzen_unit_is_not_still_monitored():
    """The old unit name was replaced; the panel must not still watch it."""
    names = {unit for unit, _ in websites.UNIT_CANDIDATES}
    assert "mem20senzen.service" not in names
    assert "mem20sensorz.service" in names


def test_fleet_health_returns_one_entry_per_candidate_unit(monkeypatch):
    seen = []

    def fake_status(unit, user=False):
        seen.append((unit, user))
        return {
            "unit": unit,
            "load_state": "loaded",
            "exists": True,
            "active_state": "active",
        }

    monkeypatch.setattr(runtime, "service_status", fake_status)

    result = websites.fleet_health()

    assert seen == list(websites.UNIT_CANDIDATES)
    assert result["count"] == len(websites.UNIT_CANDIDATES)
    assert [u["unit"] for u in result["units"]] == [u for u, _ in websites.UNIT_CANDIDATES]
    assert all(u["active"] is True for u in result["units"])
    assert result["healthy"] == len(websites.UNIT_CANDIDATES)


def test_fleet_health_tolerates_a_raising_probe(monkeypatch):
    def fake_status(unit, user=False):
        if unit == websites.UNIT_CANDIDATES[1][0]:
            raise RuntimeError("systemctl missing")
        return {
            "unit": unit,
            "load_state": "loaded",
            "exists": True,
            "active_state": "active",
        }

    monkeypatch.setattr(runtime, "service_status", fake_status)

    result = websites.fleet_health()

    assert result["count"] == len(websites.UNIT_CANDIDATES)
    assert len(result["units"]) == len(websites.UNIT_CANDIDATES)
    broken = result["units"][1]
    assert broken["unit"] == websites.UNIT_CANDIDATES[1][0]
    assert "RuntimeError: systemctl missing" in broken["error"]
    assert [u["unit"] for u in result["units"]] == [u for u, _ in websites.UNIT_CANDIDATES]


def test_fleet_health_tolerates_every_probe_raising(monkeypatch):
    def fake_status(unit, user=False):
        raise OSError("no systemd here")

    monkeypatch.setattr(runtime, "service_status", fake_status)

    result = websites.fleet_health()
    assert result["count"] == len(websites.UNIT_CANDIDATES)
    assert all("OSError" in u["error"] for u in result["units"])


def test_site_inventory_reports_api_error_instead_of_raising(monkeypatch):
    monkeypatch.setattr(
        websites,
        "build_client",
        lambda *a, **k: FakeCloudflare(raises="dns_records"),
    )

    result = websites.site_inventory()

    assert result["api_error"] == "RuntimeError: cloudflare dns_records exploded"
    assert result["zone_id"] is None
    assert result["record_count"] == 0
    assert result["wildcards"] == []
    assert result["zone"] == websites.DEFAULT_ZONE
    assert len(result["sites"]) == len(websites.FLEET_SITES)
    assert all(site["dns_present"] is False for site in result["sites"])
    assert all(site["observed"] is False for site in result["sites"])


def test_site_inventory_survives_a_client_that_cannot_be_built(monkeypatch):
    def explode(*a, **k):
        raise RuntimeError("no credentials")

    monkeypatch.setattr(websites, "build_client", explode)

    result = websites.site_inventory()
    assert result["api_error"] == "RuntimeError: no credentials"
    assert result["record_count"] == 0
    assert [s["host"] for s in result["sites"]] == [
        s["host"] for s in websites.FLEET_SITES
    ]


def test_site_inventory_marks_present_and_missing_hosts(monkeypatch):
    planned = websites.FLEET_SITES[1]["host"]
    live = next(s for s in websites.FLEET_SITES if s["state"] == "live")["host"]
    client = FakeCloudflare(
        records=[
            record(planned),
            record(live),
            record("*.jaysonai.online", rtype="CNAME", content="edge"),
        ],
        zone_id="zone-9",
    )
    monkeypatch.setattr(websites, "build_client", lambda *a, **k: client)

    result = websites.site_inventory()

    assert result["api_error"] is None
    assert result["zone_id"] == "zone-9"
    assert result["record_count"] == 3
    assert result["wildcards"] == ["*.jaysonai.online"]
    assert client.zone_lookups == [websites.DEFAULT_ZONE]

    by_host = {s["host"]: s for s in result["sites"]}
    assert by_host[planned]["dns_present"] is True
    assert by_host[planned]["observed"] is True
    assert by_host[live]["dns_present"] is True
    assert by_host[live]["observed"] is False
    assert by_host[websites.FLEET_SITES[0]["host"]]["dns_present"] is False


def test_site_inventory_host_matching_is_case_insensitive(monkeypatch):
    host = websites.FLEET_SITES[1]["host"]
    client = FakeCloudflare(records=[record(host.upper())])
    monkeypatch.setattr(websites, "build_client", lambda *a, **k: client)

    result = websites.site_inventory()
    by_host = {s["host"]: s for s in result["sites"]}
    assert by_host[host]["dns_present"] is True


def test_site_inventory_reads_are_non_mutating(monkeypatch):
    client = FakeCloudflare(records=[record(websites.FLEET_SITES[1]["host"])])
    monkeypatch.setattr(websites, "build_client", lambda *a, **k: client)

    websites.site_inventory()
    assert client.created == []
    assert client.deleted == []


def test_pages_reports_a_missing_account_without_touching_the_api(monkeypatch):
    def explode(*a, **k):
        raise RuntimeError("no account id")

    monkeypatch.setattr(websites, "resolve_account_id", explode)
    monkeypatch.setattr(
        audit,
        "inspect_pages",
        lambda **kw: pytest.fail("inspect_pages must not be called"),
    )

    result = websites.pages()
    assert result == {
        "error": "RuntimeError: no account id",
        "projects": [],
    }


def test_pages_lists_projects_without_live_fetching(monkeypatch):
    seen = {}

    def fake_inspect_pages(account_id=None, project=None, client=None, fetch_live=True):
        seen["account_id"] = account_id
        seen["fetch_live"] = fetch_live
        return {"projects": [{"name": "mem20"}], "total": 1}

    monkeypatch.setattr(websites, "resolve_account_id", lambda *a, **k: "acct-1")
    monkeypatch.setattr(audit, "inspect_pages", fake_inspect_pages)

    result = websites.pages()

    assert seen == {"account_id": "acct-1", "fetch_live": False}
    assert result == {
        "account_id": "acct-1",
        "projects": [{"name": "mem20"}],
        "total": 1,
    }
