import React, { useMemo, useState } from "react";
import { Panel, Section, Row, Json, Chips, Table } from "../components/ui.jsx";
import { TonePill } from "../components/StatusPill.jsx";
import { ErrorBanner } from "../components/Banner.jsx";
import { formatClock } from "../hooks.js";

const NAMING = ["all", "fs-standard", "mem20-native", "other"];

function boolTone(value) {
  if (value === true) return "ok";
  if (value === false) return "degraded";
  return "unknown";
}

function renderScalar(value) {
  if (value === null || value === undefined) return <span className="muted">not reported</span>;
  if (typeof value === "boolean") return <TonePill tone={boolTone(value)} text={String(value)} small />;
  if (typeof value === "number" || typeof value === "string") return <span className="mono">{String(value)}</span>;
  return <Json value={value} />;
}

function Extra({ label, value }) {
  if (value === null || value === undefined) return null;
  return (
    <Section title={label}>
      {Array.isArray(value) ? (
        <Chips values={value} empty="empty list reported" />
      ) : typeof value === "object" ? (
        <Json value={value} />
      ) : (
        <Row label={label}>{renderScalar(value)}</Row>
      )}
    </Section>
  );
}

export default function CliCoverage({ coverage }) {
  const [query, setQuery] = useState("");
  const [naming, setNaming] = useState("all");
  const [onlyGaps, setOnlyGaps] = useState(false);
  const [selectedName, setSelectedName] = useState(null);

  const data = coverage.data;
  const results = data && Array.isArray(data.results) ? data.results : null;
  const totals = data && data.totals && typeof data.totals === "object" ? data.totals : null;

  const filtered = useMemo(() => {
    if (!results) return null;
    const needle = query.trim().toLowerCase();
    return results.filter((row) => {
      if (!row) return false;
      if (naming !== "all" && row.naming !== naming) return false;
      if (onlyGaps && !(Array.isArray(row.gaps) && row.gaps.length > 0)) return false;
      if (!needle) return true;
      return [row.name, row.naming, ...(Array.isArray(row.gaps) ? row.gaps : [])]
        .filter(Boolean)
        .some((field) => String(field).toLowerCase().includes(needle));
    });
  }, [results, query, naming, onlyGaps]);

  const selected = filtered ? filtered.find((row) => row.name === selectedName) || filtered[0] || null : null;
  const extras = data
    ? Object.entries(data).filter(([key]) => key !== "totals" && key !== "results")
    : [];

  return (
    <div className="tab-pane">
      <Panel
        title="Fleet CLI coverage"
        subtitle={`/api/cli/coverage · last response ${formatClock(coverage.updatedAt)}`}
        actions={
          <>
            <input
              className="input"
              type="search"
              placeholder="filter binaries…"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            <select className="input" value={naming} onChange={(event) => setNaming(event.target.value)} aria-label="naming filter">
              {NAMING.map((value) => (
                <option key={value} value={value}>
                  naming: {value}
                </option>
              ))}
            </select>
            <label className="checkline">
              <input type="checkbox" checked={onlyGaps} onChange={(event) => setOnlyGaps(event.target.checked)} />
              only gaps
            </label>
            <button type="button" className="btn" onClick={coverage.refresh}>
              refresh
            </button>
          </>
        }
      >
        <ErrorBanner title="/api/cli/coverage failed" error={coverage.error} onRetry={coverage.refresh} />

        <Section title="Totals reported by the API">
          {totals ? (
            <div className="grid grid-auto">
              {Object.keys(totals)
                .sort()
                .map((key) => (
                  <div className="cell" key={key}>
                    <span className="cell-label mono">{key}</span>
                    <span className="cell-value">{renderScalar(totals[key])}</span>
                  </div>
                ))}
            </div>
          ) : (
            <div className="table-empty">{data ? "the API returned no totals object" : "coverage not loaded"}</div>
          )}
        </Section>

        <div className="split">
          <div className="split-list">
            <div className="filter-summary">
              {results ? (
                <>
                  showing <strong>{filtered.length}</strong> of <strong>{results.length}</strong> CLIs
                </>
              ) : (
                <span className="muted">{coverage.loading ? "loading coverage…" : "no coverage payload yet"}</span>
              )}
            </div>
            <Table
              rows={filtered || []}
              rowKey={(row) => row.name}
              onRowClick={(row) => setSelectedName(row.name)}
              selectedKey={selected ? selected.name : undefined}
              empty={results ? "no CLI matches the current filters" : "coverage not loaded"}
              columns={[
                { key: "name", label: "binary", render: (row) => <span className="mono strong">{row.name}</span> },
                { key: "naming", label: "naming", render: (row) => <span className="tag">{row.naming || "—"}</span> },
                {
                  key: "help_ok",
                  label: "help",
                  render: (row) => <TonePill tone={boolTone(row.help_ok)} text={row.help_ok === undefined ? "not reported" : String(row.help_ok)} small />,
                },
                {
                  key: "has_json",
                  label: "--json",
                  render: (row) => <TonePill tone={boolTone(row.has_json)} text={row.has_json === undefined ? "not reported" : String(row.has_json)} small />,
                },
                {
                  key: "gaps",
                  label: "gaps",
                  render: (row) => (
                    <Chips values={Array.isArray(row.gaps) ? row.gaps : null} empty="—" />
                  ),
                },
              ]}
            />
          </div>
          <div className="split-detail">
            {selected ? (
              <div className="detail">
                <div className="detail-head">
                  <h3 className="mono">{selected.name}</h3>
                  <div className="detail-head-pills">
                    <span className="tag">{selected.naming || "naming not reported"}</span>
                    <TonePill tone={boolTone(selected.help_ok)} text={`help_ok=${selected.help_ok === undefined ? "not reported" : selected.help_ok}`} small />
                    <TonePill tone={boolTone(selected.has_json)} text={`has_json=${selected.has_json === undefined ? "not reported" : selected.has_json}`} small />
                  </div>
                </div>
                <Section title="identity">
                  <Row label="path" mono>
                    {selected.path ?? <span className="muted">not reported</span>}
                  </Row>
                  <Row label="symlink">{selected.symlink === undefined ? <span className="muted">not reported</span> : String(selected.symlink)}</Row>
                  <Row label="declared_in">{selected.declared_in ?? <span className="muted">not reported</span>}</Row>
                  <Row label="timed_out">{selected.timed_out === undefined ? <span className="muted">not reported</span> : String(selected.timed_out)}</Row>
                  <Row label="help_exit" mono>
                    {selected.help_exit === undefined ? <span className="muted">not reported</span> : String(selected.help_exit)}
                  </Row>
                  {selected.detail ? <Row label="detail">{String(selected.detail)}</Row> : null}
                </Section>
                <Section title="verbs">
                  <Chips values={Array.isArray(selected.verbs) ? selected.verbs : null} empty="no verbs reported" />
                </Section>
                <Section title="gaps">
                  <Chips values={Array.isArray(selected.gaps) ? selected.gaps : null} empty="no gaps reported" />
                </Section>
                <Section title="raw row">
                  <Json value={selected} />
                </Section>
              </div>
            ) : (
              <div className="table-empty detail-empty">select a CLI to inspect it.</div>
            )}
          </div>
        </div>

        {extras.length > 0 ? (
          <>
            {extras.map(([key, value]) => (
              <Extra key={key} label={key} value={value} />
            ))}
          </>
        ) : null}
      </Panel>
    </div>
  );
}
