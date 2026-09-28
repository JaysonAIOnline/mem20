import React, { useState } from "react";
import { Panel, Row } from "../components/ui.jsx";
import { TonePill } from "../components/StatusPill.jsx";
import { ErrorBanner, NoticeBanner } from "../components/Banner.jsx";
import { qs } from "../api.js";
import { useResource, formatClock } from "../hooks.js";

export default function LogsView() {
  const [unit, setUnit] = useState("mcp-server.service");
  const [lines, setLines] = useState(100);
  const [applied, setApplied] = useState({ unit: "mcp-server.service", lines: 100 });

  const path = `/api/websites/logs${qs({ unit: applied.unit, lines: applied.lines })}`;
  const logs = useResource(path);

  const data = logs.data;
  const output = data && Array.isArray(data.lines) ? data.lines : null;
  const exitCode = data ? data.exit_code : null;
  const exitOk = exitCode === 0;

  return (
    <div className="tab-pane">
      <Panel
        title="Journal tail"
        subtitle={`GET ${path} · last response ${formatClock(logs.updatedAt)}`}
      >
        <form
          className="form-grid"
          onSubmit={(event) => {
            event.preventDefault();
            setApplied({ unit: unit.trim(), lines: Number(lines) || 100 });
          }}
        >
          <label className="field field-wide">
            <span>unit</span>
            <input
              className="input"
              value={unit}
              onChange={(event) => setUnit(event.target.value)}
              placeholder="mcp-server.service"
            />
          </label>
          <label className="field field-narrow">
            <span>lines</span>
            <input
              className="input"
              type="number"
              min="1"
              max="2000"
              value={lines}
              onChange={(event) => setLines(event.target.value)}
            />
          </label>
          <div className="field">
            <span>&nbsp;</span>
            <button type="submit" className="btn btn-primary">
              fetch journal
            </button>
          </div>
        </form>

        <ErrorBanner title="journal fetch failed" error={logs.error} onRetry={logs.refresh} />

        {data ? (
          <>
            <div className="kv-inline">
              <span>
                unit <strong className="mono">{data.unit ?? "not reported"}</strong>
              </span>
              <span>
                exit_code{" "}
                <TonePill
                  tone={exitOk ? "ok" : "error"}
                  text={exitCode === undefined || exitCode === null ? "not reported" : String(exitCode)}
                  small
                />
              </span>
              <span>
                lines returned <strong>{output ? output.length : "not reported"}</strong>
              </span>
            </div>

            {exitCode !== null && exitCode !== 0 ? (
              <NoticeBanner tone="degraded" title="journalctl reported a non-zero exit code">
                the output below is whatever the backend captured from a failing journalctl invocation.
              </NoticeBanner>
            ) : null}

            {output && output.length > 0 ? (
              <pre className="stdout journal">{output.join("\n")}</pre>
            ) : (
              <div className="table-empty">
                {logs.loading ? "loading journal…" : "the API returned no log lines for this unit"}
              </div>
            )}
          </>
        ) : null}

        {!logs.everLoaded && !logs.error ? <div className="table-empty">no journal request made yet</div> : null}
      </Panel>

      <Panel title="Notes">
        <Row label="read-only">this view only reads; it never mutates a service.</Row>
        <Row label="bounded">line count is capped by the backend at the value you send.</Row>
      </Panel>
    </div>
  );
}
