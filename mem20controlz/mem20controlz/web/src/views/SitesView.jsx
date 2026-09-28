import React from "react";
import { Panel, Row, Table, YesNo, Json } from "../components/ui.jsx";
import { TonePill } from "../components/StatusPill.jsx";
import { ErrorBanner, NoticeBanner } from "../components/Banner.jsx";
import { formatClock } from "../hooks.js";

function siteTone(site) {
  if (site && site.api_error) return "degraded";
  if (site && site.state === "live" && site.dns_present === true) return "ok";
  if (site && site.state === "live" && site.dns_present === false) return "unreachable";
  if (site && site.state === "planned") return "unknown";
  return "unknown";
}

export default function Sites({ sites }) {
  const data = sites.data;

  return (
    <div className="tab-pane">
      <Panel
        title="Site inventory"
        subtitle={`GET /api/websites/sites · last response ${formatClock(sites.updatedAt)}`}
        actions={
          <button type="button" className="btn" onClick={sites.refresh}>
            refresh
          </button>
        }
      >
        <ErrorBanner title="/api/websites/sites failed" error={sites.error} onRetry={sites.refresh} />

        {data && data.api_error ? (
          <NoticeBanner tone="degraded" title="Cloudflare API error reported by the backend">
            {String(data.api_error)} — the inventory below is what the backend could still determine, and it may be
            incomplete.
          </NoticeBanner>
        ) : null}

        {data ? (
          <>
            <div className="block">
              <Row label="zone">{data.zone ?? <span className="muted">not reported</span>}</Row>
              <Row label="zone_id" mono>
                {data.zone_id ?? <span className="muted">not reported</span>}
              </Row>
              <Row label="record_count">
                {data.record_count === undefined ? <span className="muted">not reported</span> : String(data.record_count)}
              </Row>
              <Row label="wildcards">
                {Array.isArray(data.wildcards) && data.wildcards.length > 0 ? (
                  <span className="chips">
                    {data.wildcards.map((name) => (
                      <code className="chip" key={String(name)}>
                        {String(name)}
                      </code>
                    ))}
                  </span>
                ) : (
                  <span className="muted">no wildcard records reported</span>
                )}
              </Row>
              <Row label="api_error">
                {data.api_error === null || data.api_error === undefined ? (
                  <span className="tone-ok">none reported</span>
                ) : (
                  <span className="tone-degraded">{String(data.api_error)}</span>
                )}
              </Row>
            </div>

            <Table
              rows={Array.isArray(data.sites) ? data.sites : []}
              rowKey={(row, index) => row.host || index}
              empty="the API returned an empty site list"
              columns={[
                { key: "host", label: "host", render: (row) => <span className="mono strong">{row.host}</span> },
                { key: "role", label: "role", render: (row) => row.role ?? <span className="muted">not reported</span> },
                {
                  key: "state",
                  label: "state",
                  render: (row) => (
                    <TonePill tone={siteTone(row)} text={row.state ?? "not reported"} small />
                  ),
                },
                { key: "dns_present", label: "dns_present", render: (row) => <YesNo value={row.dns_present} /> },
                { key: "observed", label: "observed", render: (row) => <YesNo value={row.observed} /> },
              ]}
            />
            <details className="disclosure">
              <summary>raw response</summary>
              <Json value={data} />
            </details>
          </>
        ) : null}

        {!data && !sites.error ? (
          <div className="table-empty">{sites.loading ? "loading…" : "no site inventory captured yet"}</div>
        ) : null}
      </Panel>
    </div>
  );
}
