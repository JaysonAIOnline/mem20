import React, { useMemo, useState } from "react";
import { Panel, Section, Row, Json, Chips, Table } from "../components/ui.jsx";
import StatusPill, { TonePill } from "../components/StatusPill.jsx";
import { ErrorBanner } from "../components/Banner.jsx";
import Stdout from "../components/Stdout.jsx";
import { KNOWN_STATUSES } from "../status.js";
import { formatClock } from "../hooks.js";

const KINDS = ["all", "subsystem", "core", "manager"];

function coverageRowFor(coverage, panel) {
  if (!coverage || !Array.isArray(coverage.results) || !panel) return null;
  const wanted = [panel.binary, panel.name, panel.id].filter(Boolean).map((v) => String(v));
  return coverage.results.find((row) => row && wanted.includes(String(row.name))) || null;
}

function Detail({ panel, coverageRow }) {
  if (!panel) {
    return (
      <div className="table-empty detail-empty">
        select a panel on the left. nothing is displayed until the API has returned a panel.
      </div>
    );
  }

  const rest = panel.rest || null;
  const cli = panel.cli || null;
  const surface = panel.http_surface || null;
  const verbs = Array.isArray(cli && cli.verbs)
    ? cli.verbs
    : Array.isArray(coverageRow && coverageRow.verbs)
      ? coverageRow.verbs
      : null;
  const gaps = coverageRow && Array.isArray(coverageRow.gaps) ? coverageRow.gaps : null;

  return (
    <div className="detail">
      <div className="detail-head">
        <h3 className="mono">{panel.name || panel.id || "unnamed panel"}</h3>
        <div className="detail-head-pills">
          <StatusPill status={panel.status} reason={panel.status_reason} />
          <span className="tag">{panel.kind ? panel.kind : "kind not reported"}</span>
        </div>
      </div>

      <div className={`reason reason-${panel.status === "ok" ? "ok" : "attention"}`}>
        <span className="reason-label">status_reason</span>
        <span className="reason-text">
          {panel.status_reason ? String(panel.status_reason) : "the API reported no status_reason for this panel"}
        </span>
      </div>

      {panel.description ? <p className="detail-desc">{String(panel.description)}</p> : null}

      <Section title="Identity">
        <Row label="id" mono>
          {panel.id ?? <span className="muted">not reported</span>}
        </Row>
        <Row label="kind">{panel.kind ?? <span className="muted">not reported</span>}</Row>
        <Row label="binary" mono>
          {panel.binary ?? <span className="muted">not reported</span>}
        </Row>
        <Row label="naming">{panel.naming ?? <span className="muted">not reported</span>}</Row>
      </Section>

      <Section title="HTTP surface (as declared by the registry)">
        {surface ? (
          <Json value={surface} />
        ) : (
          <div className="table-empty">no HTTP surface declared for this panel</div>
        )}
      </Section>

      <Section title="REST probe result">
        {rest ? (
          <>
            <Row label="reachable">
              {rest.reachable === true ? (
                <span className="tone-ok">true</span>
              ) : rest.reachable === false ? (
                <span className="tone-unreachable">false</span>
              ) : (
                <span className="muted">not reported</span>
              )}
            </Row>
            <Row label="http status" mono>
              {rest.status ?? <span className="muted">not reported</span>}
            </Row>
            <Row label="url" mono>
              {rest.url ?? <span className="muted">not reported</span>}
            </Row>
            {rest.http_error ? <Row label="http_error">true (server answered with an error status)</Row> : null}
            {rest.error ? (
              <Row label="error">
                <span className="tone-unreachable">{String(rest.error)}</span>
              </Row>
            ) : null}
            {rest.body ? (
              <>
                <div className="sub-label">body (first 2048 bytes, exactly as returned)</div>
                <pre className="stdout">{String(rest.body)}</pre>
              </>
            ) : null}
          </>
        ) : (
          <div className="table-empty">the API returned no rest result for this panel</div>
        )}
      </Section>

      <Section title="CLI probe result">
        {cli ? (
          <>
            <Row label="ok">
              {cli.ok === true ? (
                <span className="tone-ok">true</span>
              ) : cli.ok === false ? (
                <span className="tone-degraded">false</span>
              ) : (
                <span className="muted">not reported</span>
              )}
            </Row>
            <Row label="exit code" mono>
              {cli.exit_code === undefined || cli.exit_code === null ? (
                <span className="muted">not reported</span>
              ) : (
                String(cli.exit_code)
              )}
            </Row>
            <Row label="timed_out">
              {cli.timed_out === true ? (
                <span className="tone-unreachable">true</span>
              ) : cli.timed_out === false ? (
                <span className="bool">false</span>
              ) : (
                <span className="muted">not reported</span>
              )}
            </Row>
            {cli.detail ? <Row label="detail">{String(cli.detail)}</Row> : null}
            {cli.stderr ? (
              <>
                <div className="sub-label">stderr</div>
                <pre className="stdout stderr">{String(cli.stderr)}</pre>
              </>
            ) : null}
          </>
        ) : (
          <div className="table-empty">the API returned no cli probe result for this panel</div>
        )}
      </Section>

      <Section title="CLI verbs">
        {verbs && verbs.length > 0 ? (
          <Chips values={verbs} />
        ) : (
          <div className="table-empty">
            no verbs reported for this CLI
            {coverageRow ? " (the coverage report lists an empty verb list)" : " and no coverage row was matched"}
          </div>
        )}
        {gaps ? (
          <Row label="coverage gaps">
            <Chips values={gaps} empty="no gaps reported" />
          </Row>
        ) : null}
        {coverageRow ? (
          <Row label="coverage help_ok / has_json">
            <TonePill
              tone={coverageRow.help_ok === true ? "ok" : coverageRow.help_ok === false ? "degraded" : "unknown"}
              text={coverageRow.help_ok === undefined ? "not reported" : String(coverageRow.help_ok)}
              small
            />{" "}
            <TonePill
              tone={coverageRow.has_json === true ? "ok" : coverageRow.has_json === false ? "degraded" : "unknown"}
              text={coverageRow.has_json === undefined ? "not reported" : String(coverageRow.has_json)}
              small
            />
          </Row>
        ) : null}
      </Section>

      <Section title="cli.stdout (last 40 lines, read-only)">
        <Stdout text={cli ? cli.stdout : null} count={40} />
      </Section>

      <Section title="Raw panel object (exactly as returned)">
        <Json value={panel} />
      </Section>
    </div>
  );
}

export default function Subsystems({ registry, coverage }) {
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState("all");
  const [status, setStatus] = useState("all");
  const [selectedId, setSelectedId] = useState(null);

  const registryData = registry.data;
  const panels = registryData && Array.isArray(registryData.panels) ? registryData.panels : null;

  const filtered = useMemo(() => {
    if (!panels) return null;
    const needle = query.trim().toLowerCase();
    return panels.filter((panel) => {
      if (!panel) return false;
      if (kind !== "all" && panel.kind !== kind) return false;
      if (status !== "all" && panel.status !== status) return false;
      if (!needle) return true;
      return [panel.id, panel.name, panel.binary, panel.description, panel.status_reason]
        .filter(Boolean)
        .some((field) => String(field).toLowerCase().includes(needle));
    });
  }, [panels, query, kind, status]);

  const selected = filtered ? filtered.find((panel) => panel.id === selectedId) || filtered[0] || null : null;
  const coverageRow = coverage.data ? coverageRowFor(coverage.data, selected) : null;

  const counts = registryData && registryData.counts && typeof registryData.counts === "object" ? registryData.counts : null;

  return (
    <div className="tab-pane">
      <Panel
        title="Subsystem registry"
        subtitle={`/api/registry · last response ${formatClock(registry.updatedAt)} · auto-refresh every 10s`}
        actions={
          <>
            <input
              className="input"
              type="search"
              placeholder="filter panels…"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            <select className="input" value={kind} onChange={(event) => setKind(event.target.value)} aria-label="kind filter">
              {KINDS.map((value) => (
                <option key={value} value={value}>
                  kind: {value}
                </option>
              ))}
            </select>
            <select className="input" value={status} onChange={(event) => setStatus(event.target.value)} aria-label="status filter">
              <option value="all">status: all</option>
              {KNOWN_STATUSES.map((value) => (
                <option key={value} value={value}>
                  status: {value}
                </option>
              ))}
            </select>
            <button type="button" className="btn" onClick={registry.refresh}>
              refresh
            </button>
          </>
        }
      >
        <ErrorBanner title="/api/registry failed" error={registry.error} onRetry={registry.refresh} />
        <div className="split">
          <div className="split-list">
            <div className="filter-summary">
              {panels ? (
                <>
                  showing <strong>{filtered.length}</strong> of <strong>{panels.length}</strong> panels
                  {counts
                    ? KNOWN_STATUSES.map((key) => (
                        <span key={key} className="filter-chip">
                          {key} {Object.prototype.hasOwnProperty.call(counts, key) ? counts[key] : "—"}
                        </span>
                      ))
                    : null}
                </>
              ) : (
                <span className="muted">
                  {registry.loading ? "loading registry…" : "no registry payload yet — press refresh"}
                </span>
              )}
            </div>
            <Table
              rows={filtered || []}
              rowKey={(row) => row.id || row.name}
              onRowClick={(row) => setSelectedId(row.id)}
              selectedKey={selected ? selected.id : undefined}
              empty={panels ? "no panel matches the current filters" : "registry not loaded"}
              columns={[
                { key: "name", label: "panel", render: (row) => <span className="mono strong">{row.name || row.id}</span> },
                { key: "kind", label: "kind", render: (row) => <span className="tag">{row.kind || "—"}</span> },
                { key: "status", label: "status", render: (row) => <StatusPill status={row.status} reason={row.status_reason} small /> },
              ]}
            />
          </div>
          <div className="split-detail">
            <Detail panel={selected} coverageRow={coverageRow} />
          </div>
        </div>
      </Panel>
    </div>
  );
}
