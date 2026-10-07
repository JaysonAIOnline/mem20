"""Cloudflare API access for mem20 ops tooling.

Credentials are read from the consolidated environment file; token values are
never returned, logged, or included in any command output.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Protocol

DEFAULT_ENV_FILE = "/opt/mem20/secrets/.env"
TOKEN_KEYS = ("CLOUDFLARE_API_TOKEN", "CF_API_TOKEN", "CLOUDFLARE_TOKEN")
ACCOUNT_KEYS = ("CLOUDFLARE_ACCOUNT_ID", "CF_ACCOUNT_ID")
DEFAULT_API = "https://api.cloudflare.com/client/v4"


class CredentialError(RuntimeError):
    """Raised when required Cloudflare credentials are absent."""


def load_env_file(path: str = DEFAULT_ENV_FILE) -> dict[str, str]:
    """Parse a dotenv file into a dict without mutating the process environment."""
    values: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as handle:
            raw = handle.read()
    except FileNotFoundError:
        return values
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        if stripped.lower().startswith("export "):
            stripped = stripped[len("export "):]
        key, _, value = stripped.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def resolve_token(env_file: str = DEFAULT_ENV_FILE) -> str:
    """Return a Cloudflare API token from the environment or the env file."""
    for key in TOKEN_KEYS:
        value = os.environ.get(key)
        if value:
            return value
    file_values = load_env_file(env_file)
    for key in TOKEN_KEYS:
        value = file_values.get(key)
        if value:
            return value
    raise CredentialError(
        "no Cloudflare API token found; set one of " + ", ".join(TOKEN_KEYS)
        + f" or place it in {env_file}"
    )


def resolve_account_id(env_file: str = DEFAULT_ENV_FILE) -> str:
    """Return the Cloudflare account id from the environment or the env file."""
    for key in ACCOUNT_KEYS:
        value = os.environ.get(key)
        if value:
            return value
    file_values = load_env_file(env_file)
    for key in ACCOUNT_KEYS:
        value = file_values.get(key)
        if value:
            return value
    raise CredentialError(
        "no Cloudflare account id found; set one of " + ", ".join(ACCOUNT_KEYS)
        + f" or place it in {env_file}"
    )


class CloudflareError(RuntimeError):
    """Raised when the Cloudflare API returns a failure response."""


class CloudflareClient:
    """Minimal Cloudflare v4 client covering the endpoints this package needs."""

    def __init__(self, token: str, timeout: float = 30.0, api_base: str = DEFAULT_API) -> None:
        self._token = token
        self._timeout = timeout
        self._api_base = api_base.rstrip("/")

    def _request(self, method: str, path: str, params: dict | None = None) -> Any:
        url = f"{self._api_base}{path}"
        if params:
            clean = {k: v for k, v in params.items() if v is not None}
            if clean:
                url = f"{url}?{urllib.parse.urlencode(clean)}"
        request = urllib.request.Request(url, method=method)
        request.add_header("Authorization", f"Bearer {self._token}")
        request.add_header("Accept", "application/json")
        with urllib.request.urlopen(request, timeout=self._timeout) as response:
            body = response.read().decode("utf-8")
        payload = json.loads(body)
        if not payload.get("success"):
            errors = payload.get("errors") or []
            detail = "; ".join(
                f"{e.get('code')}: {e.get('message')}" for e in errors if isinstance(e, dict)
            )
            raise CloudflareError(detail or f"Cloudflare API error on {method} {path}")
        return payload.get("result")

    def get_zone_id(self, zone_name: str) -> str:
        result = self._request("GET", "/zones", {"name": zone_name, "per_page": 1})
        if not result:
            raise CloudflareError(f"zone not found: {zone_name}")
        return result[0]["id"]

    def dns_records(self, zone_id: str, per_page: int = 200) -> list[dict]:
        return self._request(
            "GET", f"/zones/{zone_id}/dns_records", {"per_page": per_page}
        ) or []

    def delete_dns_record(self, zone_id: str, record_id: str) -> dict:
        return self._request("DELETE", f"/zones/{zone_id}/dns_records/{record_id}") or {}

    def create_dns_record(self, zone_id: str, payload: dict) -> dict:
        return self._post_json(f"/zones/{zone_id}/dns_records", payload)

    def _post_json(self, path: str, payload: dict) -> Any:
        url = f"{self._api_base}{path}"
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=data, method="POST")
        request.add_header("Authorization", f"Bearer {self._token}")
        request.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(request, timeout=self._timeout) as response:
            body = response.read().decode("utf-8")
        parsed = json.loads(body)
        if not parsed.get("success"):
            raise CloudflareError(f"Cloudflare API error on POST {path}")
        return parsed.get("result")

    def pages_projects(self, account_id: str) -> list[dict]:
        return self._request("GET", f"/accounts/{account_id}/pages/projects") or []

    def pages_project(self, account_id: str, project: str) -> dict:
        return self._request("GET", f"/accounts/{account_id}/pages/projects/{project}") or {}

    def pages_deployments(self, account_id: str, project: str) -> list[dict]:
        return self._request(
            "GET", f"/accounts/{account_id}/pages/projects/{project}/deployments"
        ) or []

    def pages_deployments_preview(self, account_id: str, project: str) -> list[dict]:
        return self._request(
            "GET", f"/accounts/{account_id}/pages/projects/{project}/deployments/preview"
        ) or []

    def delete_pages_project(self, account_id: str, project: str) -> dict:
        return self._request(
            "DELETE", f"/accounts/{account_id}/pages/projects/{project}"
        ) or {}


class CloudflareAPI(Protocol):
    """The subset of the Cloudflare API this package depends on.

    Declared as a Protocol so test doubles and alternative transports can be
    substituted without inheriting from the HTTP client.
    """

    def get_zone_id(self, zone_name: str) -> str: ...

    def dns_records(self, zone_id: str, per_page: int = 200) -> list[dict]: ...

    def delete_dns_record(self, zone_id: str, record_id: str) -> dict: ...

    def create_dns_record(self, zone_id: str, payload: dict) -> dict: ...

    def pages_projects(self, account_id: str) -> list[dict]: ...

    def pages_project(self, account_id: str, project: str) -> dict: ...

    def pages_deployments(self, account_id: str, project: str) -> list[dict]: ...

    def delete_pages_project(self, account_id: str, project: str) -> dict: ...


def build_client(env_file: str = DEFAULT_ENV_FILE) -> CloudflareClient:
    """Construct a client using credentials from the environment or env file."""
    return CloudflareClient(resolve_token(env_file))


def fetch_text(url: str, timeout: float = 20.0) -> tuple[int, str]:
    """Fetch a URL and return (status, body); HTTP errors return the status code."""
    request = urllib.request.Request(url, method="GET")
    request.add_header("User-Agent", "mem20ops/0.1")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
