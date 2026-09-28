import React, { useMemo, useState } from "react";
import { Panel, Table, Mono, Chips } from "../components/ui.jsx";
import { TonePill } from "../components/StatusPill.jsx";
import { ErrorBanner, NoticeBanner } from "../components/Banner.jsx";
import { useResource, formatClock } from "../hooks.js";
import { qs } from "../api.js";

/**
 * The review queue.
 *
 * Two things this list is careful about. It shows no artifact text - the rows are
 * polled, and a lineage's artifact runs to hundreds of kilobytes - and it never
 * hides a hollow dream without saying how many it hid. Thirty-nine of the lineages
 * on this host are failed provider calls that look like dreams unless they are
 * labelled, so they are flagged rather than quietly dropped.
 */
export default function DreamListView({ selected, onSelect, refreshToken }) {
  const [kind, setKind] = useState("");
  const [showHollow, setShowHollow] = useState(true);
  const [onlyUnpromoted, setOnlyUnpromoted] = useState(false);
  const [query, setQuery] = useState("");

  const path = `/api/dreams${qs({
    kind,
    include_hollow: showHollow,
    only_unpromoted: onlyUnpromoted,
  })}`;
  const list = useResource(path, { deps: [refreshToken] });
  const data = list.data;

  const rows = useMemo(() => {
    const all = data && Array.isArray(data.dreams) ? data.dreams : [];
    const needle = query.trim().toLowerCase();
    if (!needle) return all;
    return all.filter((row) => String(row.dream_id || "").toLowerCase().includes(needle));
  }, [data, query]);

  const hollowCount = useMemo(
    () => (data && Array.isArray(data.dreams) ? data.dreams.filter((r) => r.hollow).length : 0),
    [data],
  );
  const keptCount = useMemo(
    () => (data && Array.isArray(data.dreams) ? data.dreams.filter((r) => r.promoted).length : 0),
    [data],
  );

  return (
    <div className="tab-pane">
      <Panel
        title="Dreams"
        subtitle={`GET ${path} · ${rows.length} shown · last response ${formatClock(list.updatedAt)}`}
        actions={
          <button type="button" className="btn" onClick={list.refresh}>
            refresh
          </button>
        }
      >
        <ErrorBanner title="the dream list failed to load" error={list.error} onRetry={list.refresh} />

        <div className="form-grid">
          <label className="field field-narrow">
            <span>kind</span>
            <select className="input" value={kind} onChange={(event) => setKind(event.target.value)}>
              <option value="">all kinds</option>
              <option value="active">active</option>
              <option value="idle_prototype">idle_prototype</option>
              <option value="idle_proposal">idle_proposal</option>
              <option value="idle_idea">idle_idea</option>
            </select>
          </label>
          <label className="field field-narrow">
            <span>find</span>
            <input
              className="input"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="dream id"
            />
          </label>
          <div className="field">
            <span>filters</span>
            <span className="chips">
              <button
                type="button"
                className={`btn btn-small${showHollow ? " btn-primary" : ""}`}
                onClick={() => setShowHollow((v) => !v)}
                title="Hollow lineages recorded provider errors rather than a dream."
              >
                {showHollow ? "showing" : "hiding"} hollow ({hollowCount})
              </button>
              <button
                type="button"
                className={`btn btn-small${onlyUnpromoted ? " btn-primary" : ""}`}
                onClick={() => setOnlyUnpromoted((v) => !v)}
                title="Only dreams with no promotion pack on disk yet."
              >
                {onlyUnpromoted ? "only unkept" : "kept too"} ({keptCount} kept)
              </button>
            </span>
          </div>
        </div>

        {data && data.hidden_hollow > 0 ? (
          <NoticeBanner tone="degraded" title="hollow lineages are hidden">
            {data.hidden_hollow} lineages recorded provider errors instead of a dream and are not shown.
            They are still on disk, still in the store, and still refuse promotion.
          </NoticeBanner>
        ) : null}

        {data && hollowCount > 0 && showHollow ? (
          <NoticeBanner tone="info" title={`${hollowCount} of these are not dreams`}>
            A hollow lineage recorded a failed provider call where a panel result should be. Its braid
            signature may well verify — a signature proves the bytes are intact, not that a dream happened.
          </NoticeBanner>
        ) : null}

        <Table
          rows={rows}
          rowKey={(row) => row.dream_id}
          onRowClick={(row) => onSelect(row.dream_id)}
          selectedKey={selected}
          empty={
            list.loading
              ? "loading dreams…"
              : "no dreams matched these filters — the store may be empty, or the filters may be too narrow"
          }
          columns={[
            {
              key: "dream_id",
              label: "dream",
              render: (row) => <span className="mono strong">{row.dream_id}</span>,
            },
            { key: "kind", label: "kind", render: (row) => <Mono value={row.kind} /> },
            {
              key: "iterations",
              label: "iters",
              render: (row) => (row.iterations === 0 ? <span className="muted">0</span> : String(row.iterations)),
            },
            { key: "inventions", label: "inventions" },
            {
              key: "fidelity",
              label: "fidelity",
              render: (row) => <Mono value={row.fidelity === null || row.fidelity === undefined ? null : row.fidelity} />,
            },
            {
              key: "omission",
              label: "omission",
              render: (row) => <Mono value={row.omission === null || row.omission === undefined ? null : row.omission} />,
            },
            {
              key: "hollow",
              label: "hollow",
              render: (row) =>
                row.hollow ? (
                  <TonePill tone="degraded" text="hollow" small title={row.hollow_why} />
                ) : (
                  <span className="muted">—</span>
                ),
            },
            {
              key: "promoted",
              label: "kept",
              render: (row) =>
                row.promoted ? (
                  <TonePill tone="ok" text="kept" small title={`pack: ${row.path}`} />
                ) : (
                  <span className="muted">—</span>
                ),
            },
            {
              key: "state",
              label: "state",
              render: (row) => {
                if (row.paused) return <TonePill tone="degraded" text="paused" small title={row.pause_reason} />;
                if (row.done) return <TonePill tone="ok" text="done" small />;
                if (!row.iterations) return <span className="muted">not run</span>;
                return <span className="muted">idle</span>;
              },
            },
          ]}
        />

        {data ? (
          <details className="disclosure">
            <summary>what this list does and does not contain</summary>
            <div className="kv-inline">
              <span>
                total <strong>{data.total}</strong>
              </span>
              <span>
                shown <strong>{data.returned}</strong>
              </span>
              <span>
                read took <strong className="mono">{data.read_s}s</strong>
              </span>
            </div>
            <div className="row">
              <span className="row-label">artifacts</span>
              <span className="row-value">
                {data.artifacts_included ? "included" : "not included"} — {data.artifacts_note}
              </span>
            </div>
            <div className="row">
              <span className="row-label">kept means</span>
              <span className="row-value">
                a pack directory exists under <Mono value={data.promotions_root} />
              </span>
            </div>
          </details>
        ) : null}
      </Panel>
    </div>
  );
}
