import React from "react";
import { Panel, Section, Row, Grid, Json, Chips } from "../components/ui.jsx";
import StatusPill, { TonePill } from "../components/StatusPill.jsx";
import { ErrorBanner } from "../components/Banner.jsx";
import { KNOWN_STATUSES, TONE_DESCRIPTIONS } from "../status.js";
import { formatClock } from "../hooks.js";

function CountCell({ status, counts, panels }) {
  const present = counts && Object.prototype.hasOwnProperty.call(counts, status);
  return (
    <div className="cell">
      <span className="cell-label">
        <StatusPill status={status} small />
      </span>
      <span className={`cell-value big tone-${status}`}>{present ? counts[status] : "—"}</span>
      <span className="cell-hint">
        {present ? TONE_DESCRIPTIONS[status] : "key absent from the counts object"}
        {Array.isArray(panels) ? ` · ${panels.filter((p) => p && p.status === status).length} panel(s) match` : ""}
      </span>
    </div>
  );
}

export default function Overview({ health, registry, manifest, onRefreshAll }) {
  const registryData = registry.data;
  const panels = registryData && Array.isArray(registryData.panels) ? registryData.panels : null;
  const counts = registryData && registryData.counts && typeof registryData.counts === "object" ? registryData.counts : null;
  const contract = registryData && registryData.contract ? registryData.contract : null;
  const totals = registryData && registryData.total;
  const timeouts = registryData && registryData.probe_timeouts ? registryData.probe_timeouts : null;

  const healthData = health.data;
  const healthOk = healthData && healthData.status === "ok";

  return (
    <div className="tab-pane">
      <Panel
        title="Control plane service"
        subtitle={`/api/health · polled every 10s · last response ${formatClock(health.updatedAt)}`}
        actions={
          <button type="button" className="btn" onClick={onRefreshAll}>
            refresh all
          </button>
        }
      >
        <ErrorBanner title="/api/health failed" error={health.error} onRetry={health.refresh} />
        {healthData ? (
          <Grid
            columns={4}
            items={[
              { label: "status", value: <StatusPill status={healthData.status} />, hint: TONE_DESCRIPTIONS.ok },
              { label: "service", value: healthData.service ?? <span className="muted">not reported</span> },
              { label: "version", value: healthData.version ?? <span className="muted">not reported</span> },
              {
                label: "verdict",
                value: healthOk ? "API reported ok" : "API did not report ok",
                tone: healthOk ? "ok" : "degraded",
              },
            ]}
          />
        ) : null}
        {!healthData && !health.error && health.loading ? <div className="table-empty">loading…</div> : null}
        {!healthData && !health.error && !health.loading ? <div className="table-empty">no /api/health response captured yet</div> : null}
      </Panel>

      <Panel
        title="Registry status census"
        subtitle={`/api/registry · polled every 10s · last response ${formatClock(registry.updatedAt)}`}
        actions={
          <button type="button" className="btn" onClick={registry.refresh}>
            refresh registry
          </button>
        }
      >
        <ErrorBanner title="/api/registry failed" error={registry.error} onRetry={registry.refresh} />
        {counts ? (
          <>
            <div className="grid grid-4">
              {KNOWN_STATUSES.map((status) => (
                <CountCell key={status} status={status} counts={counts} panels={panels} />
              ))}
            </div>
            <div className="block">
              <Row label="total panels">{totals ?? <span className="muted">not reported</span>}</Row>
              <Row label="panels received">{panels ? panels.length : <span className="muted">not reported</span>}</Row>
              {timeouts ? (
                <Row label="probe timeouts" mono>
                  {Object.entries(timeouts)
                    .map(([key, value]) => `${key}=${value}`)
                    .join("  ")}
                </Row>
              ) : null}
            </div>
            <Section title="Honesty contract reported by the API">
              {contract ? (
                Object.entries(contract).map(([key, value]) => (
                  <Row key={key} label={key}>
                    {String(value)}
                  </Row>
                ))
              ) : (
                <div className="table-empty">the API returned no contract object</div>
              )}
            </Section>
            <Section title="Raw counts object">
              <Json value={counts} />
            </Section>
          </>
        ) : null}
        {!counts && !registry.error ? (
          <div className="table-empty">{registry.loading ? "loading…" : "no registry payload captured yet"}</div>
        ) : null}
      </Panel>

      <Panel title="Websites manager manifest" subtitle="/api/websites/manifest">
        <ErrorBanner
          title="/api/websites/manifest failed"
          error={manifest.error}
          onRetry={manifest.refresh}
        />
        {manifest.data ? (
          <>
            <Row label="zone" mono>
              {manifest.data.zone ?? <span className="muted">not reported</span>}
            </Row>
            <Section title="capabilities">
              <Chips values={manifest.data.capabilities} empty="no capabilities reported" />
            </Section>
            {manifest.data.writes_require ? (
              <Row label="writes require">{String(manifest.data.writes_require)}</Row>
            ) : null}
            {manifest.data.reuses ? <Row label="reuses">{String(manifest.data.reuses)}</Row> : null}
            <Section title="fleet sites declared by the manager">
              <div className="chips">
                {(manifest.data.fleet_sites || []).map((site) => (
                  <span className="chip chip-site" key={site.host}>
                    <span className="mono">{site.host}</span>
                    <TonePill
                      tone={site.state === "live" ? "ok" : site.state === "planned" ? "unknown" : "degraded"}
                      text={site.state || "state not reported"}
                      small
                    />
                    <span className="muted">{site.role || "role not reported"}</span>
                  </span>
                ))}
                {(!manifest.data.fleet_sites || manifest.data.fleet_sites.length === 0) && (
                  <span className="muted">no fleet sites reported</span>
                )}
              </div>
            </Section>
          </>
        ) : null}
        {!manifest.data && !manifest.error ? <div className="table-empty">loading…</div> : null}
      </Panel>
    </div>
  );
}
