"""Secrets store: local vault + external sources, values never printed.

Resolution order for ``Secrets.get(name)``:
  1. environment      ``MEM20AGENTZ_<NAME>`` (NAME uppercased, ``.`` → ``_``)
  2. local vault      ``<root>/<name>``            (file content, stripped)
  3. local vault      ``<root>/<name>.json``       (``{"value": ...}``)
  4. external source  name prefix ``op://vault/item/field`` → 1Password CLI
                      name prefix ``bw://<item-id>/<field>`` → Bitwarden CLI

External CLI sources are only consulted when the binary is installed; a missing
binary is reported as ``unavailable`` (never failed with a stack trace). Every
surface that could reach a log — ``get``, ``describe``, ``redact`` — is built so
no secret value is ever printed.

``redact(text)`` masks all currently-known secret values so transcripts and log
lines written by other modules stay safe.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
from typing import Callable, Optional

DEFAULT_SECRETS_DIR = pathlib.Path("/opt/mem20/secrets")
SECRETS_ENV = "MEM20AGENTZ_SECRETS"


class SecretsError(RuntimeError):
    pass


class MissingSecret(KeyError):
    pass


def secrets_root() -> pathlib.Path:
    return pathlib.Path(
        os.environ.get(SECRETS_ENV) or DEFAULT_SECRETS_DIR).expanduser()


class Secrets:
    def __init__(self, root: Optional[pathlib.Path] = None,
                 env: Optional[dict] = None,
                 cli_bin: Optional[dict] = None) -> None:
        self.root = pathlib.Path(root or secrets_root()).expanduser()
        self._env = env if env is not None else os.environ
        self._cli_bin = cli_bin

    # ------------------------------------------------------------ helpers
    def _env_name(self, name: str) -> str:
        return "MEM20AGENTZ_" + name.upper().replace(".", "_").replace("-", "_")

    def _cli(self, tool: str) -> Optional[str]:
        if self._cli_bin is not None:
            return self._cli_bin.get(tool)
        return shutil.which(tool)

    def _external(self, name: str) -> Optional[str]:
        if name.startswith("op://"):
            bin = self._cli("op")
            if not bin:
                raise SecretsError("1Password CLI (op) not installed")
            out = subprocess.run([bin, "read", name], capture_output=True,
                                 text=True, check=False)
            if out.returncode != 0:
                raise SecretsError(f"op read failed: "
                                   f"{out.stderr.strip() or 'no output'}")
            return out.stdout.strip()
        if name.startswith("bw://"):
            bin = self._cli("bw")
            if not bin:
                raise SecretsError("Bitwarden CLI (bw) not installed")
            item = name[len("bw://"):]
            out = subprocess.run([bin, "get", "password", item],
                                 capture_output=True, text=True, check=False)
            if out.returncode != 0:
                raise SecretsError(f"bw get failed: "
                                   f"{out.stderr.strip() or 'no output'}")
            return out.stdout.strip()
        return None

    # -------------------------------------------------------------- local
    def _paths(self, name: str) -> list[pathlib.Path]:
        return [self.root / name, self.root / f"{name}.json"]

    def _local(self, name: str) -> Optional[str]:
        for p in self._paths(name):
            if not p.is_file():
                continue
            if p.suffix == ".json":
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if isinstance(data, dict) and isinstance(data.get("value"), str):
                    return data["value"]
                continue
            return p.read_text(encoding="utf-8").strip()
        return None

    # -------------------------------------------------------------- public
    def list_keys(self) -> list[str]:
        """All key names across env + vault. Never returns values."""
        keys = set()
        for k in self._env:
            up = k.upper()
            if up.startswith("MEM20AGENTZ_"):
                keys.add(up[len("MEM20AGENTZ_"):])
        if self.root.is_dir():
            for p in sorted(self.root.iterdir()):
                if p.is_file():
                    keys.add(p.stem)
        return sorted(keys)

    def get(self, name: str, default: Optional[str] = None) -> Optional[str]:
        """Resolve a secret; returns None (or default) when absent."""
        env_val = self._env.get(self._env_name(name))
        if env_val:
            return env_val
        local = self._local(name)
        if local is not None:
            return local
        try:
            return self._external(name)
        except SecretsError:
            return default

    def has(self, name: str) -> bool:
        return self.get(name) is not None

    def write(self, name: str, value: str) -> dict:
        """Persist into the local vault with owner-only permissions."""
        if not value:
            raise SecretsError("refusing to store an empty secret")
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            self.root.chmod(0o700)
        except OSError:
            pass
        path = self.root / name
        path.write_text(value, encoding="utf-8")
        path.chmod(0o600)
        return {"stored": name, "path": str(path), "bytes": len(value)}

    def delete(self, name: str) -> dict:
        removed = []
        for p in self._paths(name):
            if p.is_file():
                p.unlink()
                removed.append(str(p))
        return {"removed": removed}

    def source_of(self, name: str) -> dict:
        """Where a key resolves from — always value-free."""
        if self._env.get(self._env_name(name)):
            return {"key": name, "present": True, "source": "env"}
        if self._local(name) is not None:
            p = self._paths(name)[0]
            return {"key": name, "present": True,
                    "source": f"vault:{p}"}
        if name.startswith("op://") or name.startswith("bw://"):
            tool = "op" if name.startswith("op://") else "bw"
            return {"key": name, "present": False,
                    "source": f"{tool}-cli",
                    "available": self._cli(tool) is not None}
        return {"key": name, "present": False, "source": None}

    def describe(self) -> list[dict]:
        """One value-free line per key (env+vault+external prefixes)."""
        out = []
        for key in self.list_keys():
            out.append(self.source_of(key))
        for key in ("op://vault/item/field", "bw://item/field"):
            out.append(self.source_of(key))
        return out

    def sources_health(self) -> dict:
        """CLI source availability, not values."""
        return {
            "op": self._cli("op") is not None,
            "bw": self._cli("bw") is not None,
            "vault": str(self.root),
        }

    # ---------------------------------------------------------- redaction
    def _known(self) -> list[str]:
        out = []
        for key in self.list_keys():
            try:
                val = self.get(key)
            except (SecretsError, OSError):
                continue
            if val and len(val) >= 4:
                out.append(val)
        if self._env.get("MEM20AGENTZ_ACP_TOKEN"):
            out.append(self._env["MEM20AGENTZ_ACP_TOKEN"])
        return out

    def redact(self, text: str) -> str:
        known = [v for v in dict.fromkeys(self._known()) if v in text]
        if not known:
            return text
        pattern = re.compile("|".join(re.escape(v) for v in known))
        return pattern.sub("••••", text)


def redact(text: str) -> str:
    """Module-level convenience that never raises on fetch errors."""
    try:
        return Secrets().redact(text)
    except Exception:  # noqa: BLE001
        return text