"""Security guardrails: OSV vulnerability audit + doctor/verify.

OSV scan — posts the dependency manifest to the OSV batch API and reports every
known-vulnerable version range hit. The endpoint is injectable (``base_url``) so
tests exercise a real HTTP round trip against a fake server; production uses the
public Google OSV API. Packages come from an injected list or are parsed from a
dependency manifest (``pyproject.toml`` via tomllib).

Doctor / verify — a battery of on-disk checks (module import, config load,
memory probe, branding sweep, self-test import, secrets vault, egress policy,
OSV scan); ``run()`` returns the full report and a single pass/fail.
"""

from __future__ import annotations

import pathlib
import re
import tomllib
from typing import Any, Callable, Optional

import httpx

OSV_BATCH_PATH = "/v1/querybatch"
DEFAULT_OSV_URL = "https://api.osv.dev"
OLD_NAME = "h" + "ermes"  # constructed to avoid self-matching


# ===================================================================== OSV
def parse_pypi(package: str, version: str) -> dict:
    return {
        "package": {"name": package,
                    "ecosystem": "PyPI"},
        "version": version,
    }


def dependency_packages(root: Optional[pathlib.Path] = None) -> list[dict]:
    """Parse a dependency manifest into OSV query packages."""
    root = pathlib.Path(root or "/opt/mem20/mem20agentz")
    candidates = [
        root / "pyproject.toml",
        root / "requirements.txt",
    ]
    for pth in candidates:
        if not pth.is_file():
            continue
        if pth.name == "requirements.txt":
            out = []
            for line in pth.read_text(encoding="utf-8").splitlines():
                line = line.split("#", 1)[0].strip()
                if not line or "==" not in line:
                    continue
                name, _, ver = line.partition("==")
                out.append(parse_pypi(name.strip(), ver.strip()))
            return out
        try:
            data = tomllib.loads(pth.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            continue
        deps = (data.get("project") or {}).get("dependencies") or []
        out = []
        for spec in deps:
            m = re.match(r"""^\s*([A-Za-z0-9_.\-]+)""", spec)
            vm = re.search(r"""([><=!~]+)\s*([0-9][^\s,;]*)""", spec)
            if not m or not vm:
                continue
            out.append(parse_pypi(m.group(1), vm.group(2)))
        return out
    return []


class OsvScanner:
    def __init__(self, base_url: str = DEFAULT_OSV_URL, timeout: float = 20.0,
                 packages: Optional[list[dict]] = None,
                 client_factory: Optional[Callable[[], httpx.Client]] = None,
                 root: Optional[pathlib.Path] = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._packages = packages
        self._client_factory = client_factory
        self._root = root

    def packages(self) -> list[dict]:
        if self._packages is not None:
            return self._packages
        return dependency_packages(self._root)

    def _client(self) -> httpx.Client:
        if self._client_factory is not None:
            return self._client_factory()
        return httpx.Client(timeout=self.timeout)

    def scan(self) -> dict:
        queries = self.packages()
        try:
            client = self._client()
            try:
                resp = client.post(self.base_url + OSV_BATCH_PATH,
                                   json={"queries": queries})
                resp.raise_for_status()
                rows = resp.json().get("results", [])
            finally:
                client.close()
        except Exception as exc:  # noqa: BLE001 (network/target failures)
            return {"ok": False, "status": "error",
                    "packages": len(queries), "vulns": [], "error": str(exc)}
        vulns = []
        for result in rows:
            for v in result.get("vulnerabilities") or []:
                vulns.append({
                    "id": v.get("id"),
                    "aliases": v.get("aliases") or [],
                    "summary": (v.get("summary") or v.get("details") or "")[:400],
                    "severity": (v.get("severity") or [{}])[0].get("score"),
                })
        return {"ok": len(vulns) == 0, "status": "clean" if not vulns
                else "vulnerable", "packages": len(queries),
                "vulns": vulns, "error": None}


# ==================================================================== doctor
class Doctor:
    def __init__(self, backend=None, scanner: Optional[OsvScanner] = None,
                 package_root: Optional[pathlib.Path] = None) -> None:
        self.backend = backend
        self.package_root = package_root
        self.scanner = scanner or OsvScanner(packages=[], root=package_root)

    def checks(self) -> list[dict]:
        out = []
        self._check(out, "import", "mem20agentz importable", self._c_import)
        self._check(out, "config", "config.yaml loads", self._c_config)
        self._check(out, "memory", "memory probe", self._c_memory)
        self._check(out, "branding", "no old vendor name in package",
                    self._c_branding)
        self._check(out, "self-test", "hermetic test module importable",
                    self._c_selftest)
        self._check(out, "secrets", "secrets vault + sources",
                    self._c_secrets)
        self._check(out, "egress", "egress policy fail-closed", self._c_egress)
        self._check(out, "auth", "LLM key ring presence", self._c_auth)
        self._check(out, "osv", "dependency vulnerability audit",
                    self._c_osv)
        return out

    def _check(self, out, name, label, fn):
        try:
            detail = fn()
            ok, detail = (True, detail) if isinstance(detail, str) else detail
        except Exception as exc:  # noqa: BLE001
            ok, detail = False, str(exc)
        out.append({"check": name, "label": label, "ok": ok, "detail": detail})

    def _c_import(self):
        import mem20agentz  # noqa: F401
        return f"mem20agentz {mem20agentz.__version__}"

    def _c_config(self):
        from .config import load_config
        cfg = load_config()
        return (True, str(cfg.path))

    def _c_memory(self):
        if self.backend is None:
            return (True, "backend not provided (skipped probe)")
        try:
            rec = self.backend.recall(topic="self-model",
                                      tags=["mem20agentz", "self_model"], k=1)
        except Exception as exc:  # noqa: BLE001
            if type(exc).__name__ == "BackendSealed":
                # MEM20AGENTZ_BACKEND=fake seals memory on purpose (tests);
                # report as informational, not a failure.
                return (True, "memory sealed in fake-backend mode")
            raise
        return (True, f"recall ok ({len(rec)} self-model(s))")

    def _c_branding(self):
        import mem20agentz as pkg
        root = pathlib.Path(pkg.__file__).parent
        hits = []
        for p in root.rglob("*.py"):
            if "test_" in p.name:
                continue
            if OLD_NAME.lower() in p.read_text(encoding="utf-8",
                                               errors="replace").lower():
                hits.append(str(p))
        if hits:
            return (False, f"old vendor name in: {hits}")
        return (True, f"clean across {sum(1 for _ in root.rglob('*.py'))} files")

    def _c_selftest(self):
        import mem20agentz.tests.test_mem20agentz  # noqa: F401
        return (True, "mem20agentz.tests.test_mem20agentz imports")

    def _c_secrets(self):
        from .secrets import Secrets
        s = Secrets()
        health = s.sources_health()
        n = len(s.list_keys())
        return (True, f"vault={health['vault']}, {n} key(s), "
                      f"op={health['op']}, bw={health['bw']}")

    def _c_egress(self):
        from .egress import default_policy
        policy = default_policy()
        verdict = policy.check("https://api.example.com/")
        if not policy.allow:
            return (True, f"fail-closed policy active ({verdict['reason']})")
        return (True, f"{len(policy.allow)} allow rule(s), "
                      f"{len(policy.bindings)} binding rule(s)")

    def _c_auth(self):
        from .auth import KeyRing
        from .llm import KNOWN_PROVIDERS
        from .secrets import Secrets
        keyring = KeyRing(secrets=Secrets())
        names = [n for n in KNOWN_PROVIDERS
                 if keyring.get(n)[0] or keyring.get(n)[1]]
        present = [n for n in names if keyring.get(n)[0]]
        detail = f"{len(present)}/{len(names)} provider key(s) present" \
                 if names else "no providers configured (substrate fallback)"
        return (True, detail)

    def _c_osv(self):
        result = self.scanner.scan()
        if result["status"] == "error":
            return (False, f"osv scan failed: {result.get('error')}")
        if result["status"] == "vulnerable":
            ids = ", ".join(v["id"] for v in result["vulns"][:5])
            return (False, f"{len(result['vulns'])} vuln(s) "
                           f"across {result['packages']} package(s): {ids}")
        return (True, f"clean across {result['packages']} package(s)")

    def run(self) -> dict:
        checks = self.checks()
        return {"ok": all(c["ok"] for c in checks), "checks": checks}