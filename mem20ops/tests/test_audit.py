import json

import pytest

from mem20ops import audit
from mem20ops.cloudflare import (
    CredentialError,
    load_env_file,
    resolve_token,
)


class FakeClient:
    def __init__(self, records=None, projects=None, project=None, deployments=None):
        self._records = records or []
        self._projects = projects or []
        self._project = project or {}
        self._deployments = deployments or []
        self.deleted = []

    def get_zone_id(self, zone_name):
        return "zone-123"

    def dns_records(self, zone_id, per_page=200):
        return list(self._records)

    def pages_projects(self, account_id):
        return list(self._projects)

    def pages_project(self, account_id, project):
        return dict(self._project)

    def pages_deployments(self, account_id, project):
        return list(self._deployments)

    def delete_pages_project(self, account_id, project):
        self.deleted.append(project)
        return {"id": project}


def _record(name, rtype="A", content="1.2.3.4", proxied=False):
    return {"id": f"id-{name}", "name": name, "type": rtype, "content": content,
            "proxied": proxied, "ttl": 1}


def test_audit_dns_counts_types_and_groups_origins():
    records = [
        _record("a.example.com", "A", "10.0.0.1", True),
        _record("b.example.com", "A", "10.0.0.1", True),
        _record("example.com", "MX", "mx.provider.com"),
        _record("example.com", "TXT", "v=spf1"),
    ]
    result = audit.audit_dns("example.com", client=FakeClient(records))
    assert result["total_records"] == 4
    assert result["type_counts"] == {"A": 2, "MX": 1, "TXT": 1}
    assert result["findings"]["email_routing_records"] == 2
    assert result["findings"]["wildcard_shadows_unlisted_hosts"] is False
    assert len(result["findings"]["origin_groups"]["10.0.0.1"]) == 2


def test_audit_dns_flags_wildcard_shadowing():
    records = [_record("*.example.com", "A", "10.0.0.1", True), _record("a.example.com")]
    result = audit.audit_dns("example.com", client=FakeClient(records))
    assert result["findings"]["wildcard_shadows_unlisted_hosts"] is True
    assert result["findings"]["wildcards"][0]["name"] == "*.example.com"


def test_audit_dns_pattern_filters_records():
    records = [_record("keep.example.com"), _record("drop.other.net")]
    result = audit.audit_dns("example.com", pattern="keep", client=FakeClient(records))
    assert result["total_records"] == 2
    assert result["matched_records"] == 1
    assert result["records"][0]["name"] == "keep.example.com"


def test_audit_dns_sorting_is_type_then_name():
    records = [_record("z.example.com", "A"), _record("a.example.com", "CNAME", "target")]
    result = audit.audit_dns("example.com", client=FakeClient(records))
    assert [r["type"] for r in result["records"]] == ["A", "CNAME"]


def test_pages_delete_requires_confirm():
    with pytest.raises(ValueError):
        audit.delete_pages_project("proj", confirm=False)


def test_pages_delete_reports_remaining():
    client = FakeClient(projects=[{"name": "other"}], project={"name": "proj", "subdomain": "p.pages.dev"})
    result = audit.delete_pages_project("proj", account_id="acct", confirm=True, client=client)
    assert client.deleted == ["proj"]
    assert result["still_present"] is False
    assert result["remaining_projects"] == ["other"]


def test_pages_inspect_lists_projects():
    projects = [{"name": "a", "subdomain": "a.pages.dev", "domains": [],
                 "created_on": "x", "production_branch": "main",
                 "latest_deployment": {"created_on": "y"}}]
    result = audit.inspect_pages(account_id="acct", client=FakeClient(projects=projects))
    assert result["total"] == 1
    assert result["projects"][0]["name"] == "a"


def test_pages_inspect_project_without_network():
    detail = {"name": "p", "subdomain": None, "domains": [], "created_on": "x",
              "production_branch": "main", "latest_deployment": {"created_on": "z"}}
    result = audit.inspect_pages(account_id="acct", project="p", client=FakeClient(project=detail))
    assert result["name"] == "p"
    assert "live" not in result


def test_env_file_parsing(tmp_path):
    env = tmp_path / ".env"
    env.write_text('A=1\nexport B="two"\n# comment\nC=\'three\'\nBAD\n', encoding="utf-8")
    values = load_env_file(str(env))
    assert values == {"A": "1", "B": "two", "C": "three"}


def test_missing_env_file_returns_empty(tmp_path):
    assert load_env_file(str(tmp_path / "nope.env")) == {}


def test_resolve_token_raises_without_credentials(tmp_path, monkeypatch):
    for key in ("CLOUDFLARE_API_TOKEN", "CF_API_TOKEN", "CLOUDFLARE_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(CredentialError):
        resolve_token(str(tmp_path / "missing.env"))


def test_resolve_token_prefers_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "env-token")
    assert resolve_token(str(tmp_path / "missing.env")) == "env-token"


def test_resolve_token_falls_back_to_file(tmp_path, monkeypatch):
    for key in ("CLOUDFLARE_API_TOKEN", "CF_API_TOKEN", "CLOUDFLARE_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    env = tmp_path / ".env"
    env.write_text("CF_API_TOKEN=file-token\n", encoding="utf-8")
    assert resolve_token(str(env)) == "file-token"


def test_json_serialisable_output():
    records = [_record("a.example.com")]
    payload = audit.audit_dns("example.com", client=FakeClient(records))
    json.dumps(payload)
