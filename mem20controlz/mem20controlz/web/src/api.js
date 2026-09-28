// Same-origin API client.
// The backend serves this bundle, so the default base is "" (same-origin).
// VITE_API_BASE is only for pointing a `vite dev` session at a remote backend.

const RAW_BASE = (import.meta.env && import.meta.env.VITE_API_BASE) || "";

export const API_BASE = RAW_BASE.replace(/\/+$/, "");

export const REQUEST_TIMEOUT_MS = 20000;

export class ApiError extends Error {
  constructor(message, details = {}) {
    super(message);
    this.name = "ApiError";
    this.status = details.status ?? null;
    this.body = details.body ?? null;
    this.url = details.url ?? null;
    this.method = details.method ?? null;
    this.timedOut = Boolean(details.timedOut);
  }
}

function detailFromBody(body) {
  if (body == null) return "";
  if (typeof body === "string") return body.trim().slice(0, 400);
  if (typeof body === "object") {
    for (const key of ["error", "detail", "message", "reason"]) {
      const value = body[key];
      if (typeof value === "string" && value.trim()) return value.trim().slice(0, 400);
    }
    try {
      return JSON.stringify(body).slice(0, 400);
    } catch {
      return "[unserialisable response body]";
    }
  }
  return String(body);
}

async function request(path, { method = "GET", body } = {}) {
  const url = `${API_BASE}${path}`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    const response = await fetch(url, {
      method,
      signal: controller.signal,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });

    const text = await response.text();
    let parsed = null;
    if (text) {
      try {
        parsed = JSON.parse(text);
      } catch {
        parsed = null;
      }
    }

    if (!response.ok) {
      const detail = detailFromBody(parsed ?? text);
      throw new ApiError(
        `HTTP ${response.status}${response.statusText ? ` ${response.statusText}` : ""} from ${method} ${path}` +
          (detail ? ` — ${detail}` : ""),
        { status: response.status, body: parsed ?? text, url, method },
      );
    }

    if (parsed === null) {
      throw new ApiError(
        `Empty or non-JSON response from ${method} ${path} (HTTP ${response.status})`,
        { status: response.status, body: text, url, method },
      );
    }

    return parsed;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    if (err && err.name === "AbortError") {
      throw new ApiError(
        `Request timed out after ${REQUEST_TIMEOUT_MS / 1000}s: ${method} ${path}`,
        { url, method, timedOut: true },
      );
    }
    throw new ApiError(
      `Network error calling ${method} ${path}: ${err && err.message ? err.message : String(err)}`,
      { url, method },
    );
  } finally {
    clearTimeout(timer);
  }
}

export function getJSON(path) {
  return request(path, { method: "GET" });
}

export function postJSON(path, body) {
  return request(path, { method: "POST", body });
}

export function deleteJSON(path) {
  return request(path, { method: "DELETE" });
}

export function qs(params) {
  const parts = [];
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`);
  }
  return parts.length ? `?${parts.join("&")}` : "";
}
