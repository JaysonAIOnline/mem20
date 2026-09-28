import React from "react";

/** Last `count` lines of a text blob, read-only, as returned by the API. */
export function tailLines(text, count = 40) {
  if (text === null || text === undefined || text === "") return null;
  const cleaned = String(text).replace(/\r\n/g, "\n").replace(/\n+$/, "");
  if (cleaned === "") return null;
  const lines = cleaned.split("\n");
  return lines.slice(Math.max(0, lines.length - count)).join("\n");
}

export default function Stdout({ text, count = 40, label = "stdout" }) {
  const tail = tailLines(text, count);
  if (tail === null) {
    return <div className="table-empty">no {label} reported by the API for this panel</div>;
  }
  const total = String(text).replace(/\r\n/g, "\n").replace(/\n+$/, "").split("\n").length;
  return (
    <>
      <div className="stdout-meta">
        showing last {Math.min(count, total)} of {total} {label} line{total === 1 ? "" : "s"} (read-only)
      </div>
      <pre className="stdout">{tail}</pre>
    </>
  );
}
