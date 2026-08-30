import React, { useEffect, useState, useCallback } from "react";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

async function getJSON(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export default function App() {
  const [health, setHealth] = useState(null);
  const [ready, setReady] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [memory, setMemory] = useState([]);
  const [error, setError] = useState(null);
  const [recallQuery, setRecallQuery] = useState("");
  const [recallResult, setRecallResult] = useState(null);

  const refresh = useCallback(async () => {
    try {
      const [h, r, m, mem] = await Promise.all([
        getJSON("/api/health"),
        getJSON("/api/ready"),
        getJSON("/api/metrics"),
        getJSON("/api/memory?limit=50"),
      ]);
      setHealth(h);
      setReady(r);
      setMetrics(m);
      setMemory(mem.records || []);
      setError(null);
    } catch (e) {
      setError(String(e.message || e));
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
  }, [refresh]);

  async function runRecall(e) {
    e.preventDefault();
    try {
      const res = await fetch(`${API_BASE}/api/recall`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: recallQuery, k: 10 }),
      });
      const data = await res.json();
      setRecallResult(data.records || []);
    } catch (e) {
      setRecallResult({ error: String(e.message || e) });
    }
  }

  return (
    <div className="app">
      <header>
        <h1>mem20</h1>
        <span className="subtitle">memory + world-model dashboard</span>
        <button onClick={refresh}>refresh</button>
      </header>

      {error && (
        <div className="banner error">
          Cannot reach the bridge at <code>{API_BASE}</code>. Start it with
          <code>python bridge/server.py</code> (and the mem20 MCP server). {error}
        </div>
      )}

      <section className="cards">
        <Card title="/health" data={health} ok={health?.status === "ok"} />
        <Card title="/ready" data={ready} ok={ready?.ready === true} />
        <Card
          title="/metrics"
          data={metrics && {
            tools_registered: metrics.tools_registered,
            request_count: metrics.request_count,
            request_errors: metrics.request_errors,
            memory_system_available: metrics.memory_system_available,
            simulated_facts: metrics.simulated_facts,
          }}
        />
      </section>

      <section className="memory">
        <h2>Memory store ({memory.length})</h2>
        <table>
          <thead>
            <tr>
              <th>topic</th>
              <th>priority</th>
              <th>tags</th>
              <th>content</th>
            </tr>
          </thead>
          <tbody>
            {memory.map((r, i) => (
              <tr key={i}>
                <td>{r.topic}</td>
                <td>{r.priority}</td>
                <td>{(r.tags || []).join(", ")}</td>
                <td className="content">{(r.content || "").slice(0, 240)}</td>
              </tr>
            ))}
            {memory.length === 0 && (
              <tr>
                <td colSpan={4}>(empty or bridge offline)</td>
              </tr>
            )}
          </tbody>
        </table>
      </section>

      <section className="recall">
        <h2>Recall</h2>
        <form onSubmit={runRecall}>
          <input
            value={recallQuery}
            onChange={(e) => setRecallQuery(e.target.value)}
            placeholder="topic to recall…"
          />
          <button type="submit">recall</button>
        </form>
        {recallResult && (
          <ul>
            {Array.isArray(recallResult) ? (
              recallResult.map((r, i) => (
                <li key={i}>
                  <strong>{r.topic}</strong>: {(r.content || "").slice(0, 200)}
                </li>
              ))
            ) : (
              <li className="error">{JSON.stringify(recallResult)}</li>
            )}
          </ul>
        )}
      </section>
    </div>
  );
}

function Card({ title, data, ok }) {
  return (
    <div className={`card ${ok ? "ok" : ""}`}>
      <h3>
        {title} {ok === true ? "✓" : ok === false ? "✗" : ""}
      </h3>
      <pre>{data ? JSON.stringify(data, null, 2) : "loading…"}</pre>
    </div>
  );
}
