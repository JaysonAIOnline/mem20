"""Same-origin website mirror (stdlib only).

Fetches pages breadth-first from a start URL, stays on the origin host,
rewrites nothing, and stores raw bytes plus a manifest. Bounded by page
count, depth, bytes, and time so a runaway site cannot hang the caller.
"""

from __future__ import annotations

import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in ("a", "link"):
            for key, value in attrs:
                if key == "href" and value:
                    self.links.append(value)
        elif tag in ("img", "script"):
            for key, value in attrs:
                if key == "src" and value:
                    self.links.append(value)


def _safe_name(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    stem = (parsed.path.strip("/") or "index").replace("/", "_")
    if "." not in stem.rsplit("_", 1)[-1]:
        stem += ".html"
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in stem)


def mirror(start_url: str, out_dir: str | Path, *, max_pages: int = 20,
           max_depth: int = 2, max_bytes: int = 5_000_000,
           timeout: float = 15.0) -> dict:
    """Mirror same-origin pages breadth-first. Returns a manifest dict."""
    origin = urllib.parse.urlparse(start_url).netloc
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    queue: list[tuple[str, int]] = [(start_url, 0)]
    saved: list[dict] = []
    total = 0
    deadline = time.time() + max(1.0, timeout * max_pages)
    opener = urllib.request.build_opener()
    opener.addheaders = [("User-Agent", "mem20greenz/0.1 (mirror; local-first)")]
    while queue and len(saved) < max_pages:
        if time.time() > deadline:
            break
        url, depth = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            with opener.open(url, timeout=timeout) as resp:
                if resp.status != 200:
                    continue
                body = resp.read(max_bytes - total + 1)
        except Exception:
            continue
        total += len(body)
        if total > max_bytes:
            break
        name = _safe_name(url)
        (out / name).write_bytes(body)
        saved.append({"url": url, "file": name, "bytes": len(body)})
        if depth < max_depth and len(body) < max_bytes:
            try:
                parser = _Links()
                parser.feed(body.decode("utf-8", "replace"))
            except Exception:
                continue
            for link in parser.links:
                absolute = urllib.parse.urljoin(url, link.split("#")[0])
                parts = urllib.parse.urlparse(absolute)
                if parts.scheme not in ("http", "https"):
                    continue
                if parts.netloc != origin:
                    continue
                if absolute not in seen:
                    queue.append((absolute, depth + 1))
    manifest = {"start": start_url, "pages": len(saved), "bytes": total,
                "files": saved}
    (out / "manifest.json").write_text(
        __import__("json").dumps(manifest, indent=1), encoding="utf-8")
    return manifest
