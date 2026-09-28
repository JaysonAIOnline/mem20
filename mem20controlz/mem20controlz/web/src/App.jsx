import React, { useCallback, useEffect, useState } from "react";
import StatusPill from "./components/StatusPill.jsx";
import LoginGate from "./components/LoginGate.jsx";
import { ErrorBanner } from "./components/Banner.jsx";
import { KNOWN_STATUSES } from "./status.js";
import { useResource, formatClock } from "./hooks.js";
import { fetchAuthStatus, isUnauthorized } from "./auth.js";
import Overview from "./tabs/Overview.jsx";
import Subsystems from "./tabs/Subsystems.jsx";
import CliCoverage from "./tabs/CliCoverage.jsx";
import Websites from "./tabs/Websites.jsx";
import Dreams from "./tabs/Dreams.jsx";

const POLL_MS = 10000;

const NAV = [
  {
    group: "control",
    items: [
      { id: "overview", label: "Overview", hint: "service + registry census" },
      { id: "subsystems", label: "Subsystems", hint: "registry panels + probes" },
      { id: "cli", label: "CLI coverage", hint: "fleet CLI contract audit" },
    ],
  },
  {
    group: "fleet / web",
    items: [{ id: "websites", label: "Websites", hint: "sites · DNS · health · logs · pages" }],
  },
  {
    group: "imagination",
    items: [{ id: "dreams", label: "Dreams", hint: "review · keep · run" }],
  },
];

function NavBadge({ id, registry }) {
  const data = registry.data;
  if (id === "subsystems") {
    return data && Array.isArray(data.panels) ? <span className="nav-badge">{data.panels.length}</span> : null;
  }
  if (id === "overview" && data && data.counts && typeof data.counts === "object") {
    const degraded = KNOWN_STATUSES.filter((key) => key !== "ok" && data.counts[key] > 0).reduce(
      (sum, key) => sum + data.counts[key],
      0,
    );
    return degraded > 0 ? <span className="nav-badge nav-badge-warn">{degraded}</span> : null;
  }
  return null;
}

export default function App() {
  const [view, setView] = useState("overview");
  const [authStatus, setAuthStatus] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);

  const checkAuth = useCallback(async () => {
    try {
      const status = await fetchAuthStatus();
      setAuthStatus(status);
      return status;
    } catch {
      setAuthStatus(null);
      return null;
    } finally {
      setAuthChecked(true);
    }
  }, []);

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  // Two long-lived polls live at the top so switching tabs never restarts them.
  const health = useResource("/api/health", { pollMs: POLL_MS });
  const registry = useResource("/api/registry", { pollMs: POLL_MS });
  const manifest = useResource("/api/websites/manifest", { enabled: view === "websites" || view === "overview" });
  const coverage = useResource("/api/cli/coverage", { enabled: view === "cli" || view === "subsystems" });

  // A 401 on any protected route means the session lapsed, so show the gate
  // rather than leaving four red "unauthorized" banners on screen.
  const unauthorized = isUnauthorized(registry.error) || isUnauthorized(manifest.error) || isUnauthorized(coverage.error);
  const locked = authChecked && (unauthorized || authStatus?.authenticated === false);

  useEffect(() => {
    if (unauthorized) checkAuth();
  }, [unauthorized, checkAuth]);

  function refreshAll() {
    health.refresh();
    registry.refresh();
    manifest.refresh();
    coverage.refresh();
  }

  function handleAuthenticated() {
    checkAuth();
    refreshAll();
  }

  const healthData = health.data;

  if (locked) {
    return <LoginGate status={authStatus} onAuthenticated={handleAuthenticated} />;
  }

  return (
    <div className="shell">
      <aside className="nav">
        <div className="nav-brand">
          <span className="nav-brand-name">mem20</span>
          <span className="nav-brand-sub">control plane</span>
        </div>
        {NAV.map((section) => (
          <nav className="nav-group" key={section.group}>
            <span className="nav-group-title">{section.group}</span>
            {section.items.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`nav-item${view === item.id ? " nav-item-active" : ""}`}
                onClick={() => setView(item.id)}
                aria-current={view === item.id ? "page" : undefined}
              >
                <span className="nav-item-label">{item.label}</span>
                <NavBadge id={item.id} registry={registry} />
                <span className="nav-item-hint">{item.hint}</span>
              </button>
            ))}
          </nav>
        ))}
        <div className="nav-foot">
          <div className="nav-foot-row">
            <span>api</span>
            <span className="mono">same-origin /api</span>
          </div>
          <div className="nav-foot-row">
            <span>poll</span>
            <span className="mono">{POLL_MS / 1000}s · timeout 20s</span>
          </div>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div className="topbar-left">
            <h1>mem20 control plane</h1>
            <span className="topbar-sub">
              {view === "overview"
                ? "service + registry census"
                : view === "subsystems"
                  ? "registry panels, probes and CLI output"
                  : view === "cli"
                    ? "fleet CLI contract coverage"
                    : view === "dreams"
                      ? "review a dream, keep the good ones"
                      : "sites, DNS, systemd health, journals, Pages"}
            </span>
          </div>
          <div className="topbar-right">
            {healthData ? (
              <span className="topbar-service">
                <span className="mono">{healthData.service || "service not reported"}</span>
                <span className="mono muted">v{healthData.version || "?"}</span>
              </span>
            ) : null}
            <StatusPill
              status={healthData ? healthData.status : null}
              reason={health.error ? health.error.message : undefined}
              label={healthData ? undefined : health.error ? "api unreachable" : "not checked"}
            />
            <span className="topbar-clock mono" title="last /api/registry response">
              {formatClock(registry.updatedAt)}
            </span>
            <button type="button" className="btn btn-primary" onClick={refreshAll}>
              refresh
            </button>
          </div>
        </header>

        {health.error ? (
          <div className="strip">
            <ErrorBanner title="cannot reach the control plane API" error={health.error} onRetry={health.refresh} />
          </div>
        ) : null}
        {registry.error ? (
          <div className="strip">
            <ErrorBanner title="registry unavailable" error={registry.error} onRetry={registry.refresh} />
          </div>
        ) : null}

        <div className="content">
          {view === "overview" ? (
            <Overview health={health} registry={registry} manifest={manifest} onRefreshAll={refreshAll} />
          ) : null}
          {view === "subsystems" ? <Subsystems registry={registry} coverage={coverage} /> : null}
          {view === "cli" ? <CliCoverage coverage={coverage} /> : null}
          {view === "websites" ? <Websites manifest={manifest} /> : null}
          {view === "dreams" ? <Dreams /> : null}
        </div>
      </main>
    </div>
  );
}
