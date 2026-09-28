import React, { useState } from "react";
import { TabBar } from "../components/ui.jsx";
import { ErrorBanner, NoticeBanner } from "../components/Banner.jsx";
import Sites from "../views/SitesView.jsx";
import DnsView from "../views/DnsView.jsx";
import HealthView from "../views/HealthView.jsx";
import LogsView from "../views/LogsView.jsx";
import PagesView from "../views/PagesView.jsx";
import { useResource } from "../hooks.js";

const SUBTABS = [
  { id: "sites", label: "Sites" },
  { id: "dns", label: "DNS" },
  { id: "health", label: "Health" },
  { id: "logs", label: "Logs" },
  { id: "pages", label: "Pages" },
];

const DOCUMENTED_DEFAULT_ZONE = "jaysonai.online";

export default function Websites({ manifest }) {
  const [sub, setSub] = useState("sites");
  const [zoneOverride, setZoneOverride] = useState("");

  // Only the active sub-view issues its request; nothing is fetched "just in case".
  const sites = useResource("/api/websites/sites", { enabled: sub === "sites" });
  const health = useResource("/api/websites/health", { enabled: sub === "health" });
  const pages = useResource("/api/websites/pages", { enabled: sub === "pages" });

  const manifestZone = manifest.data && manifest.data.zone ? String(manifest.data.zone) : null;
  const zone = zoneOverride || manifestZone || DOCUMENTED_DEFAULT_ZONE;

  return (
    <div className="tab-pane">
      <TabBar tabs={SUBTABS} active={sub} onChange={setSub} label="websites views" />

      {zoneOverride && manifestZone && zoneOverride !== manifestZone ? (
        <NoticeBanner tone="info" title="zone overridden locally">
          the manifest reports <strong className="mono">{manifestZone}</strong>; the DNS panel is pointed at{" "}
          <strong className="mono">{zoneOverride}</strong>.
        </NoticeBanner>
      ) : null}

      {sub === "sites" ? <Sites sites={sites} /> : null}
      {sub === "dns" ? <DnsView zone={zone} onZoneChange={setZoneOverride} /> : null}
      {sub === "health" ? <HealthView health={health} /> : null}
      {sub === "logs" ? <LogsView /> : null}
      {sub === "pages" ? <PagesView pages={pages} /> : null}

      {manifest.error ? (
        <ErrorBanner title="/api/websites/manifest failed" error={manifest.error} onRetry={manifest.refresh} />
      ) : null}
    </div>
  );
}
