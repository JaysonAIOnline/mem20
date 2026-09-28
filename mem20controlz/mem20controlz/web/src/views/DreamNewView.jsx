import React, { useState } from "react";
import { Panel, Row, Mono, Chips } from "../components/ui.jsx";
import { ErrorBanner, NoticeBanner } from "../components/Banner.jsx";
import { useAction } from "../hooks.js";
import { postJSON } from "../api.js";

/**
 * Start a new dream.
 *
 * The distinction that matters here: creating a dream is free. It writes one small
 * JSON file and calls no model. Running it is what costs money, and that is a
 * separate button on the detail view. Saying so up front is the difference between
 * a form that feels safe to use and one that does not.
 */
export default function DreamNewView({ manifest, onCreated }) {
  const [seed, setSeed] = useState("");
  const [foundation, setFoundation] = useState("");
  const [kind, setKind] = useState("active");
  const create = useAction();

  const kinds = manifest && Array.isArray(manifest.kinds) ? manifest.kinds : ["active"];

  async function submit(event) {
    event.preventDefault();
    const result = await create.run(() =>
      postJSON("/api/dreams", { seed: seed.trim(), foundation: foundation.trim(), kind }),
    );
    if (result) {
      setSeed("");
      setFoundation("");
      if (onCreated) onCreated(result.dream_id);
    }
  }

  return (
    <div className="tab-pane">
      <Panel title="New dream" subtitle="POST /api/dreams">
        <NoticeBanner tone="info" title="this costs nothing">
          creating a dream writes one small file and calls no model. Spending starts when you run it, on the dream's
          own page — one iteration is a full panel of models.
        </NoticeBanner>

        <form className="form-grid" onSubmit={submit}>
          <label className="field field-wide">
            <span>seed — the brief it starts from</span>
            <textarea
              className="input"
              rows={4}
              value={seed}
              onChange={(event) => setSeed(event.target.value)}
              placeholder="A storefront that explains its own pricing without being asked."
              maxLength={4000}
            />
          </label>
          <label className="field field-wide">
            <span>foundation — the premise it grows biased toward (optional)</span>
            <textarea
              className="input"
              rows={2}
              value={foundation}
              onChange={(event) => setFoundation(event.target.value)}
              placeholder="Make it trustworthy in one glance."
            />
          </label>
          <label className="field field-narrow">
            <span>kind</span>
            <select className="input" value={kind} onChange={(event) => setKind(event.target.value)}>
              {kinds.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
          <div className="field">
            <span>&nbsp;</span>
            <button type="submit" className="btn btn-primary" disabled={create.pending || !seed.trim()}>
              {create.pending ? "creating…" : "create dream"}
            </button>
          </div>
        </form>

        {create.error ? <ErrorBanner title="the dream was not created" error={create.error} /> : null}

        {create.result ? (
          <NoticeBanner tone="ok" title="created">
            <Mono value={create.result.dream_id} /> · {create.result.iterations} iteration(s) · {create.result.note}
          </NoticeBanner>
        ) : null}
      </Panel>

      {manifest ? (
        <Panel title="What kinds exist">
          <Row label="kinds">
            <Chips values={manifest.kinds} />
          </Row>
          <Row label="default">{manifest.default_kind}</Row>
          <Row label="why it matters">
            an alert bar is chosen per kind, and the idle timer draws only from the idle kinds — a dream given an
            unknown kind would match no filter and no alert
          </Row>
        </Panel>
      ) : null}
    </div>
  );
}
