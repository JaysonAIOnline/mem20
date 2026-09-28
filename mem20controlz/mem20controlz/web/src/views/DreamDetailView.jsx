import React, { useState } from "react";
import { Panel, Row, Grid, Chips, Mono, Json, Table } from "../components/ui.jsx";
import { TonePill } from "../components/StatusPill.jsx";
import { ErrorBanner, NoticeBanner } from "../components/Banner.jsx";
import { useResource, useAction, formatClock } from "../hooks.js";
import { postJSON } from "../api.js";

/**
 * One dream, in full, with the three things a person might want to do to it.
 *
 * The controls are separated by what they cost. Reading is free. Verifying spends
 * a little work re-proving every node. Promoting writes a pack to disk *and* a
 * record to the ledger, so it asks first and says exactly what it will do.
 * Running spends real money — a full panel of models per iteration — so it is
 * behind its own confirmation and states the cost before you press it.
 */
export default function DreamDetailView({ dreamId, onChanged, refreshToken }) {
  const [confirmPromote, setConfirmPromote] = useState(false);
  const [confirmRun, setConfirmRun] = useState(false);
  const [iterations, setIterations] = useState(1);
  const [showCritiques, setShowCritiques] = useState(false);

  const path = `/api/dreams/${encodeURIComponent(dreamId)}`;
  // Not requested until a dream is chosen. Without this the panel asks for
  // `/api/dreams/null` on arrival and gets a 409 it has no use for.
  const detail = useResource(path, { enabled: Boolean(dreamId), deps: [dreamId, refreshToken] });
  const chain = useResource(`/api/dreams/${encodeURIComponent(dreamId)}/chain`, {
    enabled: Boolean(dreamId),
    deps: [dreamId],
  });

  const verify = useAction();
  const promote = useAction();
  const run = useAction();

  const data = detail.data;
  if (!dreamId) {
    return (
      <div className="tab-pane">
        <Panel title="Dream">
          <div className="table-empty">choose a dream from the list to review it</div>
        </Panel>
      </div>
    );
  }

  const hollow = Boolean(data && data.hollow);
  const promoted = Boolean(data && data.promotion && data.promotion.promoted);
  const iterationsRun = data && Array.isArray(data.iterations) ? data.iterations.length : 0;
  const inventions = data && data.inventions && Array.isArray(data.inventions.entries) ? data.inventions.entries : [];
  const history = data && Array.isArray(data.score_history) ? data.score_history : [];

  async function doVerify() {
    const result = await verify.run(() => postJSON(`/api/dreams/${encodeURIComponent(dreamId)}/verify`));
    if (result) detail.refresh();
  }

  async function doPromote(force) {
    const result = await promote.run(() =>
      postJSON(`/api/dreams/${encodeURIComponent(dreamId)}/promote`, { force }),
    );
    setConfirmPromote(false);
    if (result) {
      detail.refresh();
      chain.refresh();
      if (onChanged) onChanged();
    }
  }

  async function doRun() {
    const result = await run.run(() =>
      postJSON("/api/dreams/runs", { dream_id: dreamId, iterations: Number(iterations) || 1 }),
    );
    setConfirmRun(false);
    if (result) {
      detail.refresh();
      if (onChanged) onChanged();
    }
  }

  return (
    <div className="tab-pane">
      <Panel
        title={dreamId}
        subtitle={`GET ${path} · last response ${formatClock(detail.updatedAt)}`}
        actions={
          <>
            <button type="button" className="btn btn-small" onClick={detail.refresh} disabled={detail.loading}>
              refresh
            </button>
            <button type="button" className="btn btn-small" onClick={doVerify} disabled={verify.pending}>
              {verify.pending ? "proving…" : "verify chain"}
            </button>
          </>
        }
      >
        <ErrorBanner title="this dream failed to load" error={detail.error} onRetry={detail.refresh} />

        {hollow ? (
          <NoticeBanner tone="degraded" title="this lineage is hollow">
            {data.hollow.why} — iterations {Array.isArray(data.hollow.iterations) ? data.hollow.iterations.join(", ") : "?"}{" "}
            recorded provider errors instead of a panel result. Its signature can be perfectly valid; a signature proves the
            bytes are intact, not that a dream happened. Promotion and running are both refused.
          </NoticeBanner>
        ) : null}

        {data && data.paused ? (
          <NoticeBanner tone="degraded" title="this lineage is paused">
            {data.pause_reason} — everything that landed was kept. Run it again to resume.
          </NoticeBanner>
        ) : null}

        {verify.result ? (
          <NoticeBanner
            tone={verify.result.healthy ? "ok" : "degraded"}
            title={verify.result.healthy ? "the chain re-proved" : "the chain does not verify"}
          >
            {verify.result.checked} node(s) checked, {verify.result.verified} verified
            {Array.isArray(verify.result.broken) && verify.result.broken.length
              ? `; broken: ${verify.result.broken.map((b) => b.cid || b).join(", ")}`
              : ""}
            {verify.result.note ? ` — ${verify.result.note}` : ""}
          </NoticeBanner>
        ) : null}
        <ErrorBanner title="verify failed" error={verify.error} onRetry={doVerify} />

        {data ? (
          <>
            <Grid
              columns={4}
              items={[
                { label: "iterations", value: iterationsRun },
                { label: "artifact chars", value: data.artifact_chars },
                { label: "inventions", value: inventions.length },
                { label: "critiques", value: data.critique_count },
              ]}
            />

            <div className="block">
              <Row label="kind">{data.kind}</Row>
              <Row label="seed">{data.seed || <span className="muted">not reported</span>}</Row>
              <Row label="foundation">{data.foundation || <span className="muted">not reported</span>}</Row>
              <Row label="braid nodes">
                {data.provenance.braid_cids} committed
                {data.provenance.uncommitted ? (
                  <span className="tone-degraded"> · {data.provenance.uncommitted} never committed</span>
                ) : null}
              </Row>
              <Row label="provenance">
                {data.provenance.verified === null ? (
                  <span className="muted">not verified yet — use “verify chain”</span>
                ) : data.provenance.verified ? (
                  <span className="tone-ok">verified</span>
                ) : (
                  <span className="tone-degraded">failed verification</span>
                )}
              </Row>
              <Row label="kept" mono>
                {promoted ? (
                  <span className="tone-ok">
                    yes — {data.promotion.files.join(", ")} in {data.promotion.path}
                  </span>
                ) : (
                  <span className="muted">no pack on disk</span>
                )}
              </Row>
            </div>

            {Array.isArray(data.provenance.uncommitted_detail) && data.provenance.uncommitted_detail.length ? (
              <NoticeBanner tone="degraded" title="some iterations were never written to the ledger">
                {data.provenance.uncommitted_detail
                  .map((u) => `iteration ${u.n}: ${u.reason}`)
                  .join(" · ")}
              </NoticeBanner>
            ) : null}
          </>
        ) : null}

        {!data && !detail.error ? (
          <div className="table-empty">{detail.loading ? "loading dream…" : "nothing loaded yet"}</div>
        ) : null}
      </Panel>

      {data ? (
        <Panel
          title="The artifact"
          subtitle="the text this dream arrived at — the thing being reviewed"
          className="artifact-panel"
        >
          {data.artifact ? (
            <pre className="artifact">{data.artifact}</pre>
          ) : (
            <div className="table-empty">
              no artifact yet — this dream has not been run, so there is nothing to review
            </div>
          )}
        </Panel>
      ) : null}

      {data && inventions.length ? (
        <Panel title="Inventions" subtitle="things imagined that do not exist yet">
          <Table
            rows={inventions}
            rowKey={(row, index) => `${row.name}-${index}`}
            columns={[
              { key: "name", label: "name", render: (row) => <span className="strong">{row.name}</span> },
              { key: "description", label: "what it would be" },
              {
                key: "smallest_real_version",
                label: "smallest real version",
                render: (row) => <Mono value={row.smallest_real_version} />,
              },
              { key: "source_iteration", label: "found at" },
            ]}
          />
        </Panel>
      ) : null}

      {data && history.length ? (
        <Panel title="Score history" subtitle="panel judgements, not measurements">
          <Table
            rows={history}
            rowKey={(row) => row.n}
            columns={[
              { key: "n", label: "#" },
              { key: "fidelity", label: "fidelity" },
              { key: "omission", label: "omission" },
              { key: "artifact_chars", label: "chars" },
              {
                key: "accepted",
                label: "accepted",
                render: (row) => (
                  <TonePill tone={row.accepted ? "ok" : "degraded"} text={row.accepted ? "adopted" : "rejected"} small />
                ),
              },
            ]}
          />
        </Panel>
      ) : null}

      {iterationsRun ? (
        <Panel
          title="Panel critiques"
          subtitle={`${data.critique_count} across ${iterationsRun} iteration(s)`}
          actions={
            <button type="button" className="btn btn-small" onClick={() => setShowCritiques((v) => !v)}>
              {showCritiques ? "hide" : "show"}
            </button>
          }
        >
          {showCritiques ? (
            <div className="block">
              {data.iterations.map((iteration) => (
                <div key={iteration.n} className="block">
                  <div className="block-head">
                    <h3>iteration {iteration.n}</h3>
                    <div className="block-actions">
                      {iteration.accepted ? (
                        <TonePill tone="ok" text="adopted" small />
                      ) : (
                        <TonePill
                          tone="degraded"
                          text="rejected"
                          small
                          title={iteration.rejection_reason || undefined}
                        />
                      )}
                    </div>
                  </div>
                  {iteration.rejection_reason ? (
                    <div className="reason reason-attention">
                      <span className="reason-label">why it was rejected</span>
                      <span className="reason-text">{iteration.rejection_reason}</span>
                    </div>
                  ) : null}
                  {Array.isArray(iteration.critiques) && iteration.critiques.length ? (
                    <ul className="critique-list">
                      {iteration.critiques.map((critique, index) => (
                        <li key={`${iteration.n}-${index}`}>
                          <span className="filter-chip">{critique.role || critique.kind || "?"}</span>{" "}
                          <span className="reason-text">{critique.text}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <div className="muted">no critiques recorded for this iteration</div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="table-empty">critiques hidden — they are long, and there are {data.critique_count} of them</div>
          )}
        </Panel>
      ) : null}

      <Panel title="Keep it" subtitle="promotion writes a portable pack and records the promotion in braid">
        {promote.error ? (
          <ErrorBanner title="promotion was refused" error={promote.error} onRetry={() => doPromote(false)} />
        ) : null}

        {promote.result && promote.result.promoted ? (
          <NoticeBanner tone="ok" title="promoted">
            wrote {promote.result.files.join(" and ")} to <Mono value={promote.result.out_dir} /> ·{" "}
            {promote.result.skills} skill(s), {promote.result.inventions} invention(s) · ledger:{" "}
            {promote.result.braid && promote.result.braid.committed
              ? `committed as ${promote.result.braid.cid}`
              : `NOT committed — ${(promote.result.braid && promote.result.braid.reason) || "no reason reported"}`}
            {promote.result.recovered_stranded_pack
              ? ` · recovered a pack stranded by an earlier interrupted promotion`
              : ""}
          </NoticeBanner>
        ) : null}

        {promote.result && !promote.result.promoted ? (
          <NoticeBanner tone="degraded" title="the engine refused">
            {promote.result.reason}
            {promote.result.provenance && Array.isArray(promote.result.provenance.broken) && promote.result.provenance.broken.length
              ? ` — broken nodes: ${promote.result.provenance.broken.map((b) => b.cid || b).join(", ")}`
              : ""}
          </NoticeBanner>
        ) : null}

        {hollow ? (
          <div className="table-empty">
            promotion is unavailable for a hollow lineage — the engine refuses it, and the button is not offered
          </div>
        ) : confirmPromote ? (
          <span className="confirm">
            <span className="confirm-text">
              write a pack for <strong className="mono">{dreamId}</strong>
              {promoted ? ", replacing the existing one" : ""}?
            </span>
            <button type="button" className="btn btn-danger btn-small" disabled={promote.pending} onClick={() => doPromote(promoted)}>
              {promote.pending ? "writing…" : promoted ? "replace pack" : "confirm"}
            </button>
            <button type="button" className="btn btn-small" onClick={() => setConfirmPromote(false)}>
              cancel
            </button>
          </span>
        ) : (
          <div className="form-actions">
            <button type="button" className="btn btn-primary" onClick={() => setConfirmPromote(true)}>
              {promoted ? "replace pack" : "promote this dream"}
            </button>
            <span className="muted">
              writes {dreamId}.json and {dreamId}.md, and one braid record. Skills in the pack are learned observations,
              not verified procedures.
            </span>
          </div>
        )}
      </Panel>

      <Panel title="Run it" subtitle="one iteration is a full panel of models — this spends real money">
        {run.error ? <ErrorBanner title="the run was refused" error={run.error} onRetry={doRun} /> : null}
        {run.result ? (
          <NoticeBanner tone="info" title="run started">
            job <Mono value={run.result.job_id} /> · pid {run.result.pid} · {run.result.iterations} iteration(s) · log{" "}
            <Mono value={run.result.log_path} />
          </NoticeBanner>
        ) : null}

        {hollow || data && data.done ? (
          <div className="table-empty">
            {hollow ? "a hollow lineage is never run" : "this dream is already done — start a new one to keep going"}
          </div>
        ) : confirmRun ? (
          <span className="confirm">
            <span className="confirm-text">
              run <strong>{iterations}</strong> iteration(s) of <strong className="mono">{dreamId}</strong>? this
              calls models and costs money.
            </span>
            <button type="button" className="btn btn-danger btn-small" disabled={run.pending} onClick={doRun}>
              {run.pending ? "starting…" : "confirm"}
            </button>
            <button type="button" className="btn btn-small" onClick={() => setConfirmRun(false)}>
              cancel
            </button>
          </span>
        ) : (
          <div className="form-actions">
            <label className="field field-narrow">
              <span>iterations</span>
              <input
                className="input"
                type="number"
                min="1"
                max="20"
                value={iterations}
                onChange={(event) => setIterations(event.target.value)}
              />
            </label>
            <button type="button" className="btn" onClick={() => setConfirmRun(true)}>
              start a run
            </button>
            <span className="muted">
              runs in the background; the Runs tab follows it. A run that hits a provider error pauses and keeps
              everything that landed.
            </span>
          </div>
        )}
      </Panel>

      {chain.data ? (
        <Panel title="Braid chain" subtitle={`GET /api/dreams/${dreamId}/chain`}>
          <Row label="committed" mono>
            {chain.data.braid_committed}
          </Row>
          <Row label="uncommitted" mono>
            {chain.data.uncommitted && chain.data.uncommitted.length ? (
              <Chips values={chain.data.uncommitted.map((u) => `${u.n}: ${u.reason}`)} />
            ) : (
              <span className="muted">none</span>
            )}
          </Row>
          {Array.isArray(chain.data.chain) && chain.data.chain.length ? (
            <details className="disclosure">
              <summary>{chain.data.chain.length} node(s)</summary>
              <Json value={chain.data.chain} />
            </details>
          ) : (
            <div className="table-empty">no braid nodes recorded for this dream</div>
          )}
        </Panel>
      ) : null}
    </div>
  );
}
