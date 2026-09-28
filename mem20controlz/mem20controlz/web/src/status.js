// Status vocabulary. Nothing is ever mapped to the "ok" tone unless the API
// literally reported the ok status.

export const KNOWN_STATUSES = ["ok", "degraded", "unreachable", "no-health", "unknown"];

export const TONE_DESCRIPTIONS = {
  ok: "API reported status ok (verified surface answered).",
  degraded: "reachable but failing / not verified against the contract.",
  unreachable: "probe could not reach the surface at all.",
  "no-health": "the CLI runs, but exposes no health verb — a probe gap, not a fault.",
  unknown: "no verified surface — the API could not confirm anything.",
  error: "the request itself failed.",
};

export function toneForStatus(status) {
  if (status === "ok") return "ok";
  if (status === "degraded") return "degraded";
  if (status === "unreachable") return "unreachable";
  if (status === "no-health") return "no-health";
  if (status === "unknown") return "unknown";
  // Unrecognised or absent status: never green.
  return "unknown";
}

export function statusLabel(status) {
  if (status === null || status === undefined || status === "") return "not reported";
  return String(status);
}

export function isCounted(panels, status) {
  if (!Array.isArray(panels)) return 0;
  return panels.filter((panel) => panel && panel.status === status).length;
}
