import React, { useState } from "react";
import { Panel, Row, Table, Mono, Json } from "../components/ui.jsx";
import { TonePill } from "../components/StatusPill.jsx";
import { ErrorBanner, NoticeBanner } from "../components/Banner.jsx";
import { TabBar } from "../components/ui.jsx";
import { useResource, formatClock } from "../hooks.js";

/**
 * The census of dreams that were never dreams.
 *
 * This view only reads. Marking a lineage and recording the correction in braid are
 * separate, explicit acts on the command line, because both write to a store that
 * other people read. A panel that quietly "fixed" thirty-nine lineages while you
 * were looking at a list would be indistinguishable from one that corrupted them.
 */
export default function DreamHollowView({ onOpenDream, refreshToken }) {
  const census = useResource("/api/dreams/hollow", { deps: [refreshToken] });
  const data = census.data;

  return (
    <div className="tab-pane">
      <Panel
        title="Hollow lineages"
        subtitle={`GET /api/dreams/hollow · last response ${formatClock(census.updatedAt)}`}
        actions={
          <button type="button" className="btn" onClick={census.refresh}>
            refresh
          </button>
        }
      >
        <ErrorBanner title="the hollow census failed" error={census.error} onRetry={census.refresh} />

        {data ? (
          <>
            <NoticeBanner tone="degraded" title={`${data.hollow_lineages} lineages recorded failures, not dreams`}>
              A provider outage once produced iterations with zero critiques and zero inventions. The engine stored the
              error honestly and still committed the node, so they are validly signed and sit in the ledger looking
              like dreams — which is the worst kind of wrong, because a reader cannot tell a real dream from a dead
              one.
            </NoticeBanner>

            <div className="block">
              <Row label="hollow lineages">{data.hollow_lineages}</Row>
              <Row label="hollow iterations">{data.hollow_iterations}</Row>
              <Row label="already marked">
                {data.already_marked} · unmarked: {data.unmarked}
              </Row>
              <Row label="this view">
                <span className="tone-ok">read-only</span> — {data.note}
              </Row>
            </div>

            <Table
              rows={data.entries}
              rowKey={(row) => row.dream_id}
              onRowClick={onOpenDream ? (row) => onOpenDream(row.dream_id) : undefined}
              empty="no hollow lineages found — every iteration on this host recorded real panel work"
              columns={[
                { key: "dream_id", label: "dream", render: (row) => <span className="mono strong">{row.dream_id}</span> },
                { key: "kind", label: "kind" },
                {
                  key: "iterations",
                  label: "hollow iterations",
                  render: (row) => <Mono value={Array.isArray(row.iterations) ? row.iterations.join(", ") : null} />,
                },
                {
                  key: "already_marked",
                  label: "marked",
                  render: (row) =>
                    row.already_marked ? (
                      <TonePill tone="ok" text="marked" small />
                    ) : (
                      <TonePill tone="degraded" text="unmarked" small title="promotion refuses it either way" />
                    ),
                },
              ]}
            />

            <details className="disclosure">
              <summary>raw response</summary>
              <Json value={data} />
            </details>
          </>
        ) : null}

        {!data && !census.error ? (
          <div className="table-empty">{census.loading ? "reading the store…" : "no census taken yet"}</div>
        ) : null}
      </Panel>
    </div>
  );
}
