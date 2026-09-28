import React, { useState } from "react";
import { Panel, Section, Json, YesNo, Table } from "../components/ui.jsx";
import { ErrorBanner, NoticeBanner } from "../components/Banner.jsx";
import { deleteJSON, postJSON, qs } from "../api.js";
import { useResource, formatClock } from "../hooks.js";

const RECORD_TYPES = ["A", "AAAA", "CNAME", "TXT", "MX", "NS", "SRV", "CAA", "PTR"];

const EMPTY_FORM = { type: "A", name: "", content: "", proxied: false, ttl: 1 };

export default function DnsView({ zone, onZoneChange }) {
  const [pattern, setPattern] = useState("");
  const [appliedPattern, setAppliedPattern] = useState("");
  const [form, setForm] = useState(EMPTY_FORM);
  const [confirmCreate, setConfirmCreate] = useState(false);
  const [pendingDelete, setPendingDelete] = useState(null);
  const [write, setWrite] = useState(null);
  const [busy, setBusy] = useState(false);

  const path = `/api/websites/dns${qs({ zone, pattern: appliedPattern })}`;
  const dns = useResource(path);

  const data = dns.data;
  const records = data && Array.isArray(data.records) ? data.records : null;
  const typeCounts = data && data.type_counts && typeof data.type_counts === "object" ? data.type_counts : null;

  function setField(key, value) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function submitCreate() {
    setBusy(true);
    setWrite(null);
    try {
      const payload = await postJSON("/api/websites/dns", {
        zone,
        type: form.type,
        name: form.name.trim(),
        content: form.content.trim(),
        proxied: Boolean(form.proxied),
        ttl: Number(form.ttl),
      });
      setWrite({ verb: "create", ok: true, payload });
      setForm(EMPTY_FORM);
      setConfirmCreate(false);
      dns.refresh();
    } catch (error) {
      setWrite({ verb: "create", ok: false, error });
    } finally {
      setBusy(false);
    }
  }

  async function submitDelete(record) {
    setBusy(true);
    setWrite(null);
    try {
      const payload = await deleteJSON(
        `/api/websites/dns/${encodeURIComponent(record.id)}${qs({ zone })}`,
      );
      setWrite({ verb: "delete", ok: true, payload, record });
      setPendingDelete(null);
      dns.refresh();
    } catch (error) {
      setWrite({ verb: "delete", ok: false, error, record });
      setPendingDelete(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="tab-pane">
      <Panel
        title="DNS records"
        subtitle={`GET ${path} · last response ${formatClock(dns.updatedAt)}`}
        actions={
          <>
            <input
              className="input input-zone"
              value={zone}
              onChange={(event) => onZoneChange(event.target.value)}
              aria-label="zone"
              placeholder="zone"
            />
            <input
              className="input"
              value={pattern}
              placeholder="regex filter…"
              onChange={(event) => setPattern(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") setAppliedPattern(pattern.trim());
              }}
              aria-label="record pattern"
            />
            <button type="button" className="btn" onClick={() => setAppliedPattern(pattern.trim())}>
              apply filter
            </button>
            <button type="button" className="btn" onClick={dns.refresh}>
              refresh
            </button>
          </>
        }
      >
        <ErrorBanner title="DNS read failed" error={dns.error} onRetry={dns.refresh} />

        {appliedPattern ? (
          <NoticeBanner tone="info" title="server-side filter applied">
            regex <code className="chip">{appliedPattern}</code> is evaluated by the backend; the table shows exactly what
            it returned as matched records.
          </NoticeBanner>
        ) : null}

        {data ? (
          <div className="kv-inline">
            <span>
              zone <strong className="mono">{data.zone ?? "not reported"}</strong>
            </span>
            <span>
              total_records <strong>{data.total_records === undefined ? "not reported" : data.total_records}</strong>
            </span>
            <span>
              matched_records{" "}
              <strong>{data.matched_records === undefined ? "not reported" : data.matched_records}</strong>
            </span>
            <span>
              type_counts{" "}
              {typeCounts ? (
                <span className="chips">
                  {Object.keys(typeCounts)
                    .sort()
                    .map((key) => (
                      <code className="chip" key={key}>
                        {key}: {String(typeCounts[key])}
                      </code>
                    ))}
                </span>
              ) : (
                <strong className="muted">not reported</strong>
              )}
            </span>
          </div>
        ) : null}

        {data && data.findings ? (
          <Section title="findings reported by the DNS audit">
            <Json value={data.findings} />
          </Section>
        ) : null}

        <Table
          rows={records || []}
          rowKey={(row, index) => row.id || `${row.name}-${row.type}-${index}`}
          empty={records ? "the API returned no records for this filter" : "DNS inventory not loaded"}
          columns={[
            { key: "type", label: "type", render: (row) => <span className="tag">{row.type ?? "—"}</span> },
            { key: "name", label: "name", render: (row) => <span className="mono strong">{row.name}</span> },
            { key: "content", label: "content", render: (row) => <span className="mono">{row.content}</span> },
            { key: "proxied", label: "proxied", render: (row) => <YesNo value={row.proxied} /> },
            {
              key: "ttl",
              label: "ttl",
              render: (row) => (row.ttl === undefined ? <span className="muted">not reported</span> : String(row.ttl)),
            },
            {
              key: "id",
              label: "action",
              render: (row) => {
                if (!row.id) return <span className="muted">no record id reported</span>;
                if (pendingDelete !== row.id) {
                  return (
                    <button
                      type="button"
                      className="btn btn-danger btn-small"
                      disabled={busy}
                      onClick={(event) => {
                        event.stopPropagation();
                        setWrite(null);
                        setPendingDelete(row.id);
                      }}
                    >
                      delete…
                    </button>
                  );
                }
                return (
                  <span className="confirm">
                    <span className="confirm-text">
                      delete <strong className="mono">{row.name}</strong>?
                    </span>
                    <button type="button" className="btn btn-danger btn-small" disabled={busy} onClick={() => submitDelete(row)}>
                      confirm
                    </button>
                    <button type="button" className="btn btn-small" onClick={() => setPendingDelete(null)}>
                      cancel
                    </button>
                  </span>
                );
              },
            },
          ]}
        />

        {!dns.everLoaded && !dns.error ? (
          <div className="table-empty">{dns.loading ? "loading DNS inventory…" : "no DNS response captured yet"}</div>
        ) : null}

        {data ? (
          <details className="disclosure">
            <summary>raw response</summary>
            <Json value={data} />
          </details>
        ) : null}
      </Panel>

      <Panel
        title="Create DNS record"
        subtitle={`POST /api/websites/dns · zone ${zone} · write endpoint, confirmed before it fires`}
      >
        {write && !write.ok ? (
          <ErrorBanner title={`${write.verb} rejected by the API`} error={write.error} onDismiss={() => setWrite(null)} />
        ) : null}
        {write && write.ok ? (
          <NoticeBanner tone="ok" title={`${write.verb} accepted by the API`} onDismiss={() => setWrite(null)}>
            <Json value={write.payload} />
          </NoticeBanner>
        ) : null}

        <div className="form-grid">
          <label className="field">
            <span>type</span>
            <select className="input" value={form.type} onChange={(event) => setField("type", event.target.value)}>
              {RECORD_TYPES.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>name</span>
            <input
              className="input"
              value={form.name}
              onChange={(event) => setField("name", event.target.value)}
              placeholder="host.subdomain (no scheme)"
            />
          </label>
          <label className="field field-wide">
            <span>content</span>
            <input
              className="input"
              value={form.content}
              onChange={(event) => setField("content", event.target.value)}
              placeholder="203.0.113.10 / cname target / txt value"
            />
          </label>
          <label className="field field-narrow">
            <span>ttl</span>
            <input
              className="input"
              type="number"
              min="1"
              value={form.ttl}
              onChange={(event) => setField("ttl", event.target.value)}
            />
          </label>
          <label className="checkline">
            <input type="checkbox" checked={form.proxied} onChange={(event) => setField("proxied", event.target.checked)} />
            proxied
          </label>
        </div>

        <div className="form-actions">
          {confirmCreate ? (
            <>
              <span className="confirm-text">
                create <strong className="mono">{form.name || "(no name)"}</strong>{" "}
                <strong className="mono">{form.type}</strong> →{" "}
                <strong className="mono">{form.content || "(no content)"}</strong> in{" "}
                <strong className="mono">{zone}</strong>?
              </span>
              <button type="button" className="btn btn-danger" disabled={busy} onClick={submitCreate}>
                confirm create
              </button>
              <button type="button" className="btn" onClick={() => setConfirmCreate(false)}>
                cancel
              </button>
            </>
          ) : (
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => {
                setWrite(null);
                setConfirmCreate(true);
              }}
            >
              create record…
            </button>
          )}
          <span className="muted">no write happens until the confirm step is accepted.</span>
        </div>
      </Panel>
    </div>
  );
}
