"""Make the harness guide findable however you arrive at the harness.

Three doors, because people arrive differently:

* ``mem20gamez build-harness docs``  - terminal
* ``GET /guide`` and ``GET /api/docs`` - browser / API
* :func:`docs_pointer`                 - printed by ``surface()`` and the CLI, so the
  guide is advertised by the thing itself rather than hidden in a file

The guide itself is the README next to this module, so there is exactly one copy
to keep true.
"""

from __future__ import annotations

from pathlib import Path

README = Path(__file__).resolve().parent / "README.md"


def read() -> str:
    """The full guide as markdown."""
    return README.read_text(encoding="utf-8")


def pointer() -> dict:
    """Where the guide is, for anything that wants to advertise it."""
    return {
        "guide": "mem20gamez build harness",
        "readme": str(README),
        "exists": README.is_file(),
        "terminal": "mem20gamez build-harness docs",
        "http": "/guide  (and /api/docs)",
        "live_status": "/api/projects/<id>/run/status",
        "one_line": (
            "Nothing counts as done unless a vision/audio model actually looked at "
            "a real in-engine render and said it matches the production pack."
        ),
    }


def as_html(markdown_text: str | None = None) -> str:
    """Minimal markdown-to-HTML for the /docs route.

    Deliberately dependency-free: the harness already depends on FastAPI, and
    pulling in a markdown library to render one page would be a new failure mode
    in a tool whose whole point is not failing quietly.

    Supports exactly what the guide uses: headings, pipe tables, lists, fenced
    code, blockquotes, rules, and inline bold/code.
    """
    import html
    import re

    text = markdown_text if markdown_text is not None else read()
    out: list[str] = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        "<title>mem20gamez build harness</title>",
        "<style>",
        "body{font:16px/1.65 system-ui,sans-serif;max-width:56rem;margin:2rem auto;",
        "padding:0 1.25rem;color:#e8ecf5;background:#0b0d12}",
        "h1,h2{line-height:1.2}h2{margin-top:2.4rem;border-bottom:1px solid #262c3d;padding-bottom:.3rem}",
        "code{background:#1a1f2e;padding:.15rem .35rem;border-radius:4px;font-size:.9em}",
        "pre{background:#141824;border:1px solid #262c3d;border-radius:8px;padding:1rem;overflow:auto}",
        "pre code{background:none;padding:0}",
        "table{border-collapse:collapse;width:100%;margin:1rem 0;font-size:.95rem}",
        "td,th{border:1px solid #262c3d;padding:.45rem .6rem;text-align:left;vertical-align:top}",
        "th{background:#141824;color:#9aa4bd;font-weight:600}",
        "blockquote{border-left:3px solid #6ea8fe;margin:1rem 0;",
        "padding:.5rem 1rem;color:#c3cbe0;background:#11141c}",
        "a{color:#6ea8fe}hr{border:0;border-top:1px solid #262c3d;margin:2rem 0}",
        "li{margin:.15rem 0}",
        "</style></head><body>",
    ]

    def esc(value: str) -> str:
        return _inline(html.escape(value))

    in_list = False
    in_code = False
    quote: list[str] = []
    lines = text.splitlines()
    index = 0

    def flush_quote() -> None:
        if quote:
            out.append(f"<blockquote>{esc(' '.join(quote))}</blockquote>")
            quote.clear()

    def flush_list() -> None:
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    while index < len(lines):
        line = lines[index].rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            flush_quote()
            flush_list()
            out.append("</code></pre>" if in_code else "<pre><code>")
            in_code = not in_code
            index += 1
            continue
        if in_code:
            out.append(html.escape(line) or "&nbsp;")
            index += 1
            continue

        if stripped.startswith(">"):
            quote.append(stripped.lstrip(">").strip())
            index += 1
            continue
        flush_quote()

        if not stripped:
            flush_list()
            index += 1
            continue

        # A pipe table is a header row, a separator row, then body rows.
        if stripped.startswith("|") and index + 1 < len(lines) and re.match(
            r"^\|[\s:|-]+\|$", lines[index + 1].strip()
        ):
            flush_list()
            header = _row(stripped)
            index += 2
            body_rows = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                body_rows.append(_row(lines[index].strip()))
                index += 1
            out.append("<table><thead><tr>")
            out.extend(f"<th>{esc(cell)}</th>" for cell in header)
            out.append("</tr></thead><tbody>")
            for row in body_rows:
                out.append("<tr>")
                out.extend(f"<td>{esc(cell)}</td>" for cell in row)
                out.append("</tr>")
            out.append("</tbody></table>")
            continue

        if stripped.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{esc(stripped[2:])}</li>")
            index += 1
            continue
        flush_list()

        if stripped.startswith("### "):
            out.append(f"<h3>{esc(stripped[4:])}</h3>")
        elif stripped.startswith("## "):
            out.append(f"<h2>{esc(stripped[3:])}</h2>")
        elif stripped.startswith("# "):
            out.append(f"<h1>{esc(stripped[2:])}</h1>")
        elif stripped.startswith("---"):
            out.append("<hr>")
        else:
            out.append(f"<p>{esc(stripped)}</p>")
        index += 1

    flush_quote()
    flush_list()
    if in_code:
        out.append("</code></pre>")
    out.append("</body></html>")
    return "\n".join(out)


def _row(line: str) -> list[str]:
    """Split a markdown table row into cells."""
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _inline(text: str) -> str:
    """Bold and inline code, the only two inline forms the guide uses."""
    import re

    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    return text
