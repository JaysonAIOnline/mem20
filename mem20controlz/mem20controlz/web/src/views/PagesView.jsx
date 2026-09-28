import React from "react";
import { Panel, Table, Json } from "../components/ui.jsx";
import { ErrorBanner, NoticeBanner } from "../components/Banner.jsx";
import { formatClock } from "../hooks.js";

function renderDomains(domains) {
  if (domains === undefined || domains === null) return <span className="muted">not reported</span>;
  if (Array.isArray(domains)) {
    if (domains.length === 0) return <span className="muted">empty list reported</span>;
    return (
      <span className="chips">
        {domains.map((domain, index) => (
          <code className="chip" key={`${String(domain)}-${index}`}>
            {typeof domain === "object" ? JSON.stringify(domain) : String(domain)}
          </code>
        ))}
      </span>
    );
  }
  return <span className="mono">{String(domains)}</span>;
}

function renderDeployment(latest) {
  if (latest === undefined || latest === null) return <span className="muted">not reported</span>;
  if (typeof latest === "object") {
    if (Object.keys(latest).length === 0) return <span className="muted">empty object reported</span>;
    return <pre className="json inline">{JSON.stringify(latest, null, 2)}</pre>;
  }
  return <span className="mono">{String(latest)}</span>;
}

export default function PagesView({ pages }) {
  const data = pages.data;
  const projects = data && Array.isArray(data.projects) ? data.projects : null;

  return (
    <div className="tab-pane">
      <Panel
        title="Cloudflare Pages projects"
        subtitle={`/api/websites/pages · last response ${formatClock(pages.updatedAt)}`}
        actions={
          <button type="button" className="btn" onClick={pages.refresh}>
            refresh
          </button>
        }
      >
        <ErrorBanner title="/api/websites/pages failed" error={pages.error} onRetry={pages.refresh} />

        {data && data.error ? (
          <NoticeBanner tone="degraded" title="the backend could not list the account">
            {String(data.error)} — the project list below may be incomplete.
          </NoticeBanner>
        ) : null}

        {data ? (
          <div className="kv-inline">
            <span>
              total <strong>{data.total === undefined ? "not reported" : data.total}</strong>
            </span>
            <span>
              projects received <strong>{projects ? projects.length : "not reported"}</strong>
            </span>
            {data.account_id ? (
              <span>
                account_id <strong className="mono">{String(data.account_id)}</strong>
              </span>
            ) : null}
          </div>
        ) : null}

        <Table
          rows={projects || []}
          rowKey={(row, index) => row.name || index}
          empty={projects ? "the API returned no Pages projects" : "pages list not loaded"}
          columns={[
            { key: "name", label: "project", render: (row) => <span className="mono strong">{row.name}</span> },
            {
              key: "subdomain",
              label: "subdomain",
              render: (row) =>
                row.subdomain ? <span className="mono">{String(row.subdomain)}</span> : <span className="muted">not reported</span>,
            },
            { key: "domains", label: "domains", render: (row) => renderDomains(row.domains) },
            { key: "latest_deployment", label: "latest_deployment", render: (row) => renderDeployment(row.latest_deployment) },
          ]}
        />

        {!pages.everLoaded && !pages.error ? (
          <div className="table-empty">{pages.loading ? "loading pages…" : "no Pages response captured yet"}</div>
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
