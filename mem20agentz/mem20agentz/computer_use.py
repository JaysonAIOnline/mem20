"""Computer-use primitives (sub-phase 2.6).

Real, seat-of-the-pants desktop/shell capabilities exposed as tool-shaped
operations: run a shell command (timed, captured), snapshot the primary
display (honest error when no screenshot backend / headless), read and
write text files. Outputs are truncated so the agent can never be
drowned by a runaway command. Hermetic tests drive `run`/`read`/`write`
for real and exercise the honest no-backend error on `shot`.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import time

MAX_OUT = 4000

_DANGEROUS = re.compile(r"^\s*(rm\s+-rf\s+/|mkfs\.|dd\s+if=/dev/zero)"
                        r"|:(){:|fork\s*bomb", re.I)


class ComputerError(RuntimeError):
    pass


def _cut(text: str, limit: int = MAX_OUT) -> str:
    text = str(text)
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[truncated {len(text) - limit} chars]"


class ComputerUse:
    """Small, honest computer-use surface (run/shot/read/write)."""

    def tools(self) -> list[dict]:
        return [
            {"name": "computer.run",
             "description": f"run a shell command (max {MAX_OUT} chars out)"},
            {"name": "computer.shot",
             "description": "capture the primary display to a PNG"},
            {"name": "computer.read",
             "description": "read a text file"},
            {"name": "computer.write",
             "description": "write a text file"},
        ]

    # --------------------------------------------------------------- run
    def run(self, command: str, timeout: float = 30.0) -> dict:
        command = str(command or "").strip()
        if not command:
            return {"ok": False, "error": "empty command"}
        if _DANGEROUS.match(command):
            return {"ok": False, "error": "destructive command refused"}
        try:
            proc = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                timeout=timeout, check=False)
            out = proc.stdout or ""
            err = proc.stderr or ""
            return {"ok": proc.returncode == 0,
                    "rc": proc.returncode,
                    "output": _cut(out or err or f"(exit {proc.returncode})")}
        except subprocess.TimeoutExpired as exc:
            return {"ok": False, "rc": -1,
                    "error": f"timeout after {timeout}s",
                    "output": _cut(exc.output or "")}
        except OSError as exc:
            return {"ok": False, "error": str(exc)}

    # --------------------------------------------------------------- shot
    def shot(self, path: Optional[str] = None,
             display: bool = True) -> dict:
        try:
            import mss  # noqa: F401  (screenshot backend)
            from PIL import Image  # noqa: F401  (encoding backend)
        except ImportError as exc:
            return {"ok": False,
                    "error": f"no screenshot backend ({exc}); "
                             "install mss and Pillow"}
        if not display:
            return {"ok": False, "error": "no display available (headless)"}
        out = path or f"shot-{int(time.time())}.png"
        try:
            import mss as _mss
            with _mss.mss() as sct:
                primary = sct.monitors[1]
                raw = sct.grab(primary)
            import PIL.Image as _Image
            img = _Image.frombytes("RGB", raw.size, raw.rgb)
            img.save(out)
            return {"ok": True, "path": str(out),
                    "size": img.size, "bytes": pathlib.Path(out).stat().st_size}
        except Exception as exc:  # noqa: BLE001 (driver errors vary)
            return {"ok": False, "error": str(exc)}

    # ---------------------------------------------------------- read/write
    def read(self, path: str, limit: int = 100_000) -> dict:
        p = pathlib.Path(path).expanduser()
        if not p.exists():
            return {"ok": False, "error": f"no such file: {path}"}
        if not p.is_file():
            return {"ok": False, "error": f"not a file: {path}"}
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "path": str(p), "chars": len(text),
                "content": _cut(text, limit)}

    def write(self, path: str, text: str) -> dict:
        p = pathlib.Path(path).expanduser()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(str(text), encoding="utf-8")
        except OSError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "path": str(p), "bytes": p.stat().st_size}