"""Detect credentials that have escaped the central mem20 secrets store.

Design rules:
  * Read-only. Nothing here writes, moves, redacts, or deletes.
  * Values are never printed, logged, or returned. Findings carry the variable
    name, location, and a short masked preview at most.
  * A value matching outside the store is not automatically a leak: long base
    URLs and gateway addresses are configuration, not credentials. Every hit is
    classified so the noise is separable from the real risk.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field

DEFAULT_STORE = "/opt/mem20/secrets"
DEFAULT_ROOT = "/opt/mem20"
MIN_VALUE_LEN = 12
MAX_FILE_BYTES = 8_000_000

SKIP_DIRS = {
    ".git", "secrets", ".venv", "venv", "node_modules", "__pycache__",
    "target", ".pytest_cache", ".ruff_cache", ".mypy_cache", "dist",
    "build", "site-packages", ".m2", "vendor", ".tox",
}
SKIP_EXT = {
    ".pyc", ".pyo", ".so", ".o", ".a", ".class", ".whl", ".zip", ".tar", ".gz",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf",
}

CREDENTIAL_HINTS = (
    "KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD", "CREDENTIAL", "PRIVATE",
    "AUTH", "SESSION", "COOKIE", "SALT", "CERT",
)
ENDPOINT_HINTS = (
    "URL", "URI", "ENDPOINT", "BASE", "HOST", "DOMAIN", "REGION", "PROJECT",
    "MODEL", "ORG", "BUCKET", "ACCOUNT_ID", "TENANT", "INDEX",
)

SECRET_CRIT = "critical"
SECRET_HIGH = "high"
SECRET_INFO = "info"


@dataclass(frozen=True)
class Finding:
    variable: str
    path: str
    line: int
    severity: str
    kind: str
    preview: str
    tracked: bool = False
    staged: bool = False
    ignored: bool = False

    @property
    def would_commit(self) -> bool:
        return self.tracked and not self.ignored

    def as_dict(self) -> dict:
        return {
            "variable": self.variable,
            "path": self.path,
            "line": self.line,
            "severity": self.severity,
            "kind": self.kind,
            "preview": self.preview,
            "tracked": self.tracked,
            "staged": self.staged,
            "ignored": self.ignored,
            "would_commit": self.would_commit,
        }


@dataclass
class SweepResult:
    root: str
    store: str
    values_hunted: int = 0
    files_scanned: int = 0
    findings: list[Finding] = field(default_factory=list)

    @property
    def critical(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == SECRET_CRIT]

    @property
    def high(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == SECRET_HIGH]

    @property
    def info(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == SECRET_INFO]

    @property
    def exposed(self) -> list[Finding]:
        return [f for f in self.findings if f.would_commit]

    def as_dict(self) -> dict:
        return {
            "root": self.root,
            "store": self.store,
            "values_hunted": self.values_hunted,
            "files_scanned": self.files_scanned,
            "counts": {
                "critical": len(self.critical),
                "high": len(self.high),
                "info": len(self.info),
                "would_commit": len(self.exposed),
            },
            "findings": [f.as_dict() for f in self.findings],
        }


def classify(name: str, value: str) -> tuple[str, str]:
    """Return (severity, kind) for a store entry.

    Credential-shaped names holding a high-entropy value are real leaks.
    Endpoint-shaped names are configuration duplication, reported as info so
    they never mask an actual credential.
    """
    upper = name.upper()
    looks_url = bool(re.match(r"^[a-z][a-z0-9+.\-]*://", value, re.I))
    if any(h in upper for h in ENDPOINT_HINTS) or looks_url:
        return SECRET_INFO, "config"
    if any(h in upper for h in CREDENTIAL_HINTS):
        return SECRET_CRIT, "credential"
    if len(value) >= 32 and re.search(r"[A-Za-z]", value) and re.search(r"\d", value):
        return SECRET_HIGH, "opaque"
    return SECRET_INFO, "unclassified"


def load_store(store_dir: str = DEFAULT_STORE) -> dict[str, str]:
    """Read the central store. Returns {name: value}; values stay in-process."""
    values: dict[str, str] = {}
    env = os.path.join(store_dir, ".env")
    if os.path.exists(env):
        with open(env, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                val = val.strip().strip('"').strip("'")
                if len(val) >= MIN_VALUE_LEN:
                    values[key.strip()] = val
    for extra in (".env.fallback", "bigpickle"):
        path = os.path.join(store_dir, extra)
        if os.path.exists(path):
            blob = open(path, encoding="utf-8", errors="replace").read().strip()
            if len(blob) >= MIN_VALUE_LEN:
                values[f"<{extra}>"] = blob
    return values


def _mask(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:3]}...{value[-2:]}"


def _git(root: str, args: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["git", "-C", root, *args],
            capture_output=True, text=True, timeout=20, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return subprocess.CompletedProcess(args, 1, "", "")


def _git_state(root: str, rel: str) -> tuple[bool, bool, bool]:
    """(tracked, staged, ignored) for a path, cached per sweep."""
    tracked = _git(root, ["ls-files", "--error-unmatch", "--", rel]).returncode == 0
    staged = rel in _git(root, ["diff", "--cached", "--name-only"]).stdout.split()
    ignored = _git(root, ["check-ignore", "-q", "--", rel]).returncode == 0
    return tracked, staged, ignored


def _iter_files(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for filename in filenames:
            if os.path.splitext(filename)[1].lower() in SKIP_EXT:
                continue
            yield os.path.join(dirpath, filename)


def sweep(
    root: str = DEFAULT_ROOT,
    store_dir: str = DEFAULT_STORE,
    include_info: bool = True,
    git_aware: bool = True,
) -> SweepResult:
    """Scan `root` for values from `store_dir` that appear outside the store.

    Pure inspection: the filesystem is only ever read.
    """
    result = SweepResult(root=root, store=store_dir)
    secrets = load_store(store_dir)
    result.values_hunted = len(secrets)
    if not secrets:
        return result

    git_cache: dict[str, tuple[bool, bool, bool]] = {}

    for path in _iter_files(root):
        try:
            if os.path.getsize(path) > MAX_FILE_BYTES:
                continue
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        result.files_scanned += 1
        rel = os.path.relpath(path, root)
        lines = text.splitlines()
        for name, value in secrets.items():
            if value not in text:
                continue
            severity, kind = classify(name, value)
            if severity == SECRET_INFO and not include_info:
                continue
            preview = _mask(value)
            for idx, line in enumerate(lines, 1):
                if value not in line:
                    continue
                tracked = staged = ignored = False
                if git_aware:
                    if rel not in git_cache:
                        git_cache[rel] = _git_state(root, rel)
                    tracked, staged, ignored = git_cache[rel]
                result.findings.append(Finding(
                    variable=name, path=rel, line=idx, severity=severity,
                    kind=kind, preview=preview, tracked=tracked,
                    staged=staged, ignored=ignored,
                ))

    order = {SECRET_CRIT: 0, SECRET_HIGH: 1, SECRET_INFO: 2}
    result.findings.sort(key=lambda f: (order[f.severity], f.variable, f.path, f.line))
    return result
