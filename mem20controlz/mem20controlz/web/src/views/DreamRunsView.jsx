import React, { useState } from "react";
import { Panel, Row, Mono, Json } from "../components/ui.jsx";
import { TonePill } from "../components/StatusPill.jsx";
import { ErrorBanner, NoticeBanner } from "../components/Banner.jsx";
import { useResource, formatClock } from "../hooks.js";

const POLL_WHILE_RUNNING = 5000;

/**
 * Background runs, and who holds the run lock.
 *
 * A run takes minutes, so this polls while one is live and stops when none is. The
 * statuses are deliberately distinct: `paused` is not `failed`. Exit code 2 means
 * the provider dropped and everything that landed was kept, and an operator told
 * "failed" would reasonably throw away a run that is mostly intact.
 */
function toneForRun(status) {
  if (status === "done") return "ok";
  if (status === "running") return "unknown";
  if (status === "paused") return "degraded";
  return "degraded";
}

/** Whether a job is still running, read from the list already in hand. */
function jobIsRunning(jobId, jobs) {
  const job = jobs.find((j) => j.job_id === jobId);
  return Boolean(job && job.status === "running");
}

export default function DreamRunsView({ refreshToken, onOpenDream }) {
  const [openJob, setOpenJob] = useState(null);
  const runs = useResource("/api/dreams/runs", { deps: [refreshToken] });
  const stats = useResource("/api/dreams/idle-stats", { deps: [refreshToken] });

  const data = runs.data;
  const jobs = data && Array.isArray(data.jobs) ? data.jobs : [];
  // Poll only while the open job is actually running, so a control plane nobody is
  // waiting on does not re-fetch forever.
  const detail = useResource(openJob ? `/api/dreams/runs/${openJob}` : "/api/dreams/runs", {
    enabled: Boolean(openJob),
    pollMs: openJob && jobIsRunning(openJob, jobs) ? POLL_WHILE_RUNNING : 0,
  });

  return (
    <div className="tab-pane">
      <Panel
        title="Runs"
        subtitle={`GET /api/dreams/runs · last response ${formatClock(runs.updatedAt)}`}
        actions={
          <button type="button" className="btn" onClick={runs.refresh}>
            refresh
          </button>
        }
      >
        <ErrorBanner title="the run list failed to load" error={runs.error} onRetry={runs.refresh} />

        {data && data.total === 0 ? (
          <div className="table-empty">
            no run has been started from this panel yet. A run started with <Mono value="mem20-dream run" /> on the
            command line is not listed here.
          </div>
        ) : null}

        {jobs.length ? (
          <div className="block">
            {jobs.map((job) => (
              <div key={job.job_id} className="block">
                <div className="block-head">
                  <h3>
                    <Mono value={job.dream_id} />{" "}
                    <span className="muted">
                      · {job.iterations} iteration(s) · pid {job.pid} · {job.duration_note}
                    </span>
                  </h3>
                  <div className="block-actions">
                    <TonePill tone={toneForRun(job.status)} text={job.status} small title={job.note} />
                    {onOpenDream ? (
                      <button type="button" className="btn btn-small" onClick={() => onOpenDream(job.dream_id)}>
                        open dream
                      </button>
                    ) : null}
                    <button
                      type="button"
                      className="btn btn-small"
                      onClick={() => setOpenJob(openJob === job.job_id ? null : job.job_id)}
                    >
                      {openJob === job.job_id ? "hide log" : "log"}
                    </button>
                  </div>
                </div>
                <div className="reason reason-ok">
                  <span className="reason-label">{job.status}</span>
                  <span className="reason-text">{job.note}</span>
                </div>
                {job.exit_code !== null && job.exit_code !== undefined ? (
                  <div className="kv-inline">
                    <span>
                      exit_code <strong className="mono">{job.exit_code}</strong>
                    </span>
                    {job.timed_out ? <span className="tone-degraded">killed past the ceiling</span> : null}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        ) : null}

        {data && data.in_memory_only ? (
          <NoticeBanner tone="info" title="run records live in this process">
            {data.note}
          </NoticeBanner>
        ) : null}
      </Panel>

      {openJob && detail.data && detail.data.job_id === openJob ? (
        <Panel title="Run log" subtitle={`${detail.data.log_lines} line(s) · tail of ${detail.data.log_path}`}>
          {Array.isArray(detail.data.log) && detail.data.log.length ? (
            <pre className="stdout">{detail.data.log.join("\n")}</pre>
          ) : (
            <div className="table-empty">the run has written nothing to its log yet</div>
          )}
          <details className="disclosure">
            <summary>job record</summary>
            <Json value={{ ...detail.data, log: undefined }} />
          </details>
        </Panel>
      ) : null}

      {stats.data ? (
        <Panel title="Idle dreaming" subtitle="GET /api/dreams/idle-stats">
          <div className="block">
            <Row label="idle dreams">{stats.data.idle_dreams}</Row>
            <Row label="active dreams">{stats.data.active_dreams}</Row>
            <Row label="iterations per turn">{stats.data.iterations_per_turn}</Row>
            <Row label="run lock">
              {stats.data.run_lock ? (
                <>
                  <TonePill tone="degraded" text="held" small />{" "}
                  <Mono value={stats.data.run_lock.dream_id || "unidentified"} /> for{" "}
                  {stats.data.run_lock.age_s}s
                  {stats.data.run_lock.unreadable ? (
                    <span className="tone-degraded"> · unreadable claim: {stats.data.run_lock.parse_error}</span>
                  ) : null}
                </>
              ) : (
                <span className="tone-ok">free — a run may start</span>
              )}
            </Row>
          </div>

          {stats.data.state ? (
            <div className="block">
              <div className="block-head">
                <h3>last idle turn</h3>
              </div>
              <Row label="dream">
                <Mono value={stats.data.state.dream_id} />
              </Row>
              <Row label="iterations">
                {stats.data.state.iterations_run} of {stats.data.state.iterations_planned}
              </Row>
              <Row label="committed">
                {stats.data.state.committed} · {stats.data.state.uncommitted} never committed
              </Row>
              <Row label="paused">
                {stats.data.state.paused ? (
                  <span className="tone-degraded">{stats.data.state.pause_reason}</span>
                ) : (
                  <span className="muted">no</span>
                )}
              </Row>
              <Row label="alerted">
                {stats.data.state.alerted ? "yes" : "no"} · delivered:{" "}
                {stats.data.state.alert_delivered === null || stats.data.state.alert_delivered === undefined
                  ? "not attempted"
                  : String(stats.data.state.alert_delivered)}
              </Row>
            </div>
          ) : (
            <div className="table-empty">idle dreaming has not run a turn yet</div>
          )}
        </Panel>
      ) : null}
    </div>
  );
}
