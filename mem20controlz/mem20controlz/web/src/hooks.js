import { useCallback, useEffect, useRef, useState } from "react";
import { getJSON } from "./api.js";

const IDLE = {
  data: null,
  error: null,
  loading: false,
  updatedAt: null,
  everLoaded: false,
  requests: 0,
};

/**
 * Fetch `path` with an optional poll interval, keeping the last good data when a
 * refresh fails and exposing the failure as an error object (never a blank UI).
 *
 * `enabled: false` means "not requested yet": the hook stays idle and the caller
 * is expected to say so in the UI rather than showing invented data.
 */
export function useResource(path, { enabled = true, pollMs = 0, deps = [] } = {}) {
  const [state, setState] = useState(IDLE);
  const seqRef = useRef(0);
  const mountedRef = useRef(true);
  const pathRef = useRef(path);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // A new path means the old payload belongs to something else: drop it so we
  // never show the previous unit's data under a new label.
  useEffect(() => {
    if (pathRef.current !== path) {
      pathRef.current = path;
      seqRef.current += 1;
      setState(IDLE);
    }
  }, [path]);

  const load = useCallback(
    async ({ quiet = false } = {}) => {
      if (!enabled) return null;
      const seq = ++seqRef.current;
      if (!quiet) setState((prev) => ({ ...prev, loading: true }));
      try {
        const data = await getJSON(path);
        if (seq !== seqRef.current || !mountedRef.current) return null;
        setState((prev) => ({
          data,
          error: null,
          loading: false,
          updatedAt: Date.now(),
          everLoaded: true,
          requests: prev.requests + 1,
        }));
        return data;
      } catch (error) {
        if (seq !== seqRef.current || !mountedRef.current) return null;
        setState((prev) => ({
          ...prev,
          error,
          loading: false,
          updatedAt: Date.now(),
        }));
        return null;
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [path, enabled, ...deps],
  );

  useEffect(() => {
    if (!enabled) {
      setState((prev) => (prev.loading ? { ...prev, loading: false } : prev));
      return undefined;
    }
    load();
    if (!pollMs) return undefined;
    const id = setInterval(() => {
      load({ quiet: true });
    }, pollMs);
    return () => clearInterval(id);
  }, [enabled, load, pollMs]);

  return { ...state, refresh: load, path, enabled };
}

export function formatClock(ms) {
  if (!ms) return "never";
  const date = new Date(ms);
  return date.toLocaleTimeString(undefined, { hour12: false });
}

/**
 * Run a one-shot action (a POST) and expose pending/error/result.
 *
 * Separate from `useResource` because a write is not a poll: it is fired once, on
 * purpose, and its failure has to stay on screen until it is acknowledged. A write
 * that silently swallowed its error would report a promotion that never happened.
 */
export function useAction() {
  const [state, setState] = useState({ pending: false, error: null, result: null, at: null });
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const run = useCallback(async (fn) => {
    setState((prev) => ({ ...prev, pending: true, error: null }));
    try {
      const result = await fn();
      if (mountedRef.current) setState({ pending: false, error: null, result, at: Date.now() });
      return result;
    } catch (error) {
      if (mountedRef.current) setState({ pending: false, error, result: null, at: Date.now() });
      return null;
    }
  }, []);

  const reset = useCallback(
    () => setState({ pending: false, error: null, result: null, at: null }),
    [],
  );

  return { ...state, run, reset };
}
