import React from "react";
import { Panel, Table, Json } from "../components/ui.jsx";
import { TonePill } from "../components/StatusPill.jsx";
import { ErrorBanner } from "../components/Banner.jsx";
import { formatClock } from "../hooks.js";

function unitTone(unit) {
  if (!unit) return "unknown";
  if (unit.error) return "error";
  // A unit that does not exist is not a failed service, and painting it red
  // would invent an outage. systemd's own load_state decides that.
  if (unit.exists === false || unit.load_state === "not-found") return "unknown";
  const state = unit.active_state;
  if (state === "active") return "ok";
  if (state === "failed" || state === "inactive" || state === "deactivating" || state === "activating") {
    return "unreachable";
  }
  return "unknown";
}

function unitLabel(unit) {
  if (!unit) return "not reported";
  if (unit.error) return "error";
  if (unit.exists === false || unit.load_state === "not-found") return "no such unit";
  return unit.active_state === undefined || unit.active_state === null ? "not reported" : String(unit.active_state);
}

export default function HealthView({ health }) {
  const data = health.data;
  const units = data && Array.isArray(data.units) ? data.units : null;

  return (
    <div className="tab-pane">
      <Panel
        title="Fleet service health"
        subtitle={`/api/websites/health · last response ${formatClock(health.updatedAt)}`}
        actions={
          <button type="button" className="btn" onClick={health.refresh}>
            refresh
          </button>
        }
      >
        <ErrorBanner title="/api/websites/health failed" error={health.error} onRetry={health.refresh} />

        {data ? (
          <div className="kv-inline">
            <span>
              count <strong>{data.count === undefined ? "not reported" : data.count}</strong>
            </span>
            <span>
              units received <strong>{units ? units.length : "not reported"}</strong>
            </span>
          </div>
        ) : null}

        <Table
          rows={units || []}
          rowKey={(row, index) => row.unit || index}
          empty={units ? "the API returned an empty unit list" : "health not loaded"}
          columns={[
            { key: "unit", label: "unit", render: (row) => <span className="mono strong">{row.unit}</span> },
            {
              key: "scope",
              label: "scope",
              render: (row) => (
                <span className="mono muted">{row.scope === undefined ? "not reported" : row.scope}</span>
              ),
            },
            {
              key: "active_state",
              label: "active_state",
              render: (row) => <TonePill tone={unitTone(row)} text={unitLabel(row)} small />,
            },
            {
              key: "sub_state",
              label: "sub_state",
              render: (row) => (row.sub_state === undefined || row.sub_state === null ? <span className="muted">not reported</span> : <span className="mono">{row.sub_state}</span>),
            },
            {
              key: "main_pid",
              label: "main_pid",
              render: (row) => (row.main_pid === undefined || row.main_pid === null ? <span className="muted">not reported</span> : <span className="mono">{String(row.main_pid)}</span>),
            },
            {
              key: "active_enter",
              label: "active_enter",
              render: (row) => (row.active_enter === undefined || row.active_enter === null ? <span className="muted">not reported</span> : <span className="mono">{String(row.active_enter)}</span>),
            },
            {
              key: "error",
              label: "error",
              render: (row) =>
                row.error ? <span className="tone-error mono">{String(row.error)}</span> : <span className="muted">—</span>,
            },
          ]}
        />

        {!health.everLoaded && !health.error ? (
          <div className="table-empty">{health.loading ? "loading health…" : "no health response captured yet"}</div>
        ) : null}

        {data ? (
          <details className="disclosure">
            <summary>raw response</summary>
            <Json value={data} />
          </details>
        ) : null}
      </Panel>
    </div>
  );
}
