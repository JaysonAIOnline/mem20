import { useCallback, useEffect, useState } from "react";

async function api(path, body) {
  const res = await fetch(path, {
    method: body ? "POST" : "GET",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

function NodeRow({ node }) {
  return (
    <li className="node">
      <span className="label">{node.label}</span>
      <code>{node.name}</code>
    </li>
  );
}

function RelRow({ rel }) {
  return (
    <li className="rel">
      <strong>{rel.type}</strong>
      <span>
        {rel.from} {"->"} {rel.to}
      </span>
    </li>
  );
}

export default function App() {
  const [model, setModel] = useState(null);
  const [graph, setGraph] = useState(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [spoken, setSpoken] = useState("");
  const [error, setError] = useState("");
  const [skill, setSkill] = useState(null);

  const refresh = useCallback(async () => {
    const g = await api("/api/graph");
    setGraph(g);
    return g;
  }, []);

  useEffect(() => {
    (async () => {
      try {
        setModel(await api("/api/model"));
        await refresh();
      } catch (e) {
        setError(String(e.message || e));
      }
    })();
  }, [refresh]);

  async function act(kind) {
    setBusy(true);
    setError("");
    setSpoken("");
    setSkill(null);
    try {
      const out = await api(`/api/${kind}`, { text });
      setSpoken(out.spoken || out.skill?.executed ? "Applied." : "");
      if (out.skill) setSkill(out.skill);
      await refresh();
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <header>
        <h1>mem20 OREO build surface</h1>
        {model && (
          <p className="model">
            engine <code>{model.engine}</code> · build <code>{model.build}</code>
            {model.deterministic ? " · deterministic" : ""}
          </p>
        )}
      </header>

      {error && <p className="error">{error}</p>}

      <section className="control">
        <textarea
          rows={3}
          value={text}
          placeholder='e.g. "Connect the db to the dashboard with a secure auth."'
          onChange={(e) => setText(e.target.value)}
        />
        <div className="buttons">
          <button onClick={() => act("say")} disabled={busy || !text.trim()}>
            Say (NL edit)
          </button>
          <button
            className="assist"
            onClick={() => act("assist")}
            disabled={busy || !text.trim()}
          >
            Assist (agent round-trip)
          </button>
        </div>
      </section>

      {spoken && <p className="spoken">{spoken}</p>}
      {skill && (
        <p className="skill">
          skill <code>{`oreo_graph_edit`}</code> registered · executed{" "}
          {String(skill.executed)} · steps{" "}
          {Array.isArray(skill.steps) ? skill.steps.length : "n/a"}
        </p>
      )}

      <div className="panels">
        <section>
          <h2>Nodes ({graph?.graph?.nodes?.length ?? 0})</h2>
          <ul>
            {(graph?.graph?.nodes ?? []).map((n, i) => (
              <NodeRow key={i} node={n} />
            ))}
          </ul>
        </section>
        <section>
          <h2>Relationships ({graph?.graph?.relationships?.length ?? 0})</h2>
          <ul>
            {(graph?.graph?.relationships ?? []).map((r, i) => (
              <RelRow key={i} rel={r} />
            ))}
          </ul>
        </section>
      </div>

      {graph?.ascii && <pre className="ascii">{graph.ascii}</pre>}
    </main>
  );
}