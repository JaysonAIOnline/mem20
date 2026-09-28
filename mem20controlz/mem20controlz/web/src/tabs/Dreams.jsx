import React, { useState } from "react";
import { TabBar } from "../components/ui.jsx";
import { ErrorBanner } from "../components/Banner.jsx";
import { useResource } from "../hooks.js";
import DreamListView from "../views/DreamListView.jsx";
import DreamDetailView from "../views/DreamDetailView.jsx";
import DreamNewView from "../views/DreamNewView.jsx";
import DreamRunsView from "../views/DreamRunsView.jsx";
import DreamHollowView from "../views/DreamHollowView.jsx";

const SUBTABS = [
  { id: "review", label: "Review" },
  { id: "new", label: "New" },
  { id: "runs", label: "Runs" },
  { id: "hollow", label: "Hollow" },
];

/**
 * The dream review surface.
 *
 * Review is the default view and the reason this panel exists: find a dream, read
 * what it actually produced, and keep it or leave it. A single `bump` counter is
 * threaded through the sub-views rather than each one polling on its own timer, so
 * a promotion or a run refreshes everything that depends on it exactly once.
 */
export default function Dreams() {
  const [sub, setSub] = useState("review");
  const [selected, setSelected] = useState(null);
  const [bump, setBump] = useState(0);

  const manifest = useResource("/api/dreams/manifest", { enabled: sub === "new" });

  function openDream(dreamId) {
    setSelected(dreamId);
    setSub("review");
  }

  function changed() {
    setBump((n) => n + 1);
  }

  return (
    <div className="tab-pane">
      <TabBar tabs={SUBTABS} active={sub} onChange={setSub} label="dream views" />

      {sub === "review" ? (
        <div className="split">
          <div className="split-list">
            <DreamListView selected={selected} onSelect={setSelected} refreshToken={bump} />
          </div>
          <div className="split-detail">
            <DreamDetailView dreamId={selected} onChanged={changed} refreshToken={bump} />
          </div>
        </div>
      ) : null}

      {sub === "new" ? (
        <DreamNewView manifest={manifest.data} onCreated={(dreamId) => { changed(); openDream(dreamId); }} />
      ) : null}

      {sub === "runs" ? <DreamRunsView refreshToken={bump} onOpenDream={openDream} /> : null}

      {sub === "hollow" ? <DreamHollowView onOpenDream={openDream} refreshToken={bump} /> : null}

      {manifest.error ? (
        <ErrorBanner title="/api/dreams/manifest failed" error={manifest.error} onRetry={manifest.refresh} />
      ) : null}
    </div>
  );
}
