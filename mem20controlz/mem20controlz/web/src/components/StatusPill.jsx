import React from "react";
import { toneForStatus, statusLabel } from "../status.js";

export default function StatusPill({ status, reason, small = false, label = null }) {
  const tone = toneForStatus(status);
  const text = label ?? statusLabel(status);
  return (
    <span className={`pill pill-${tone}${small ? " pill-small" : ""}`} title={reason || undefined}>
      <span className="pill-dot" aria-hidden="true" />
      {text}
    </span>
  );
}

export function TonePill({ tone, text, title, small = false }) {
  return (
    <span className={`pill pill-${tone}${small ? " pill-small" : ""}`} title={title || undefined}>
      <span className="pill-dot" aria-hidden="true" />
      {text}
    </span>
  );
}
