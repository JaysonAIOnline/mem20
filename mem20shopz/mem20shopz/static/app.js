// mem20 shop — live storefront.
//
// The page updates itself. No reload button, because a page that needs one is
// telling the visitor it does not trust its own data.
//
// Three things matter for honesty here:
//   * A product the server would refuse to sell is never rendered as buyable.
//   * A price is shown only when a real Stripe Price is behind it.
//   * "Live" means live: if readiness changes while you are reading, you are told,
//     rather than quietly being shown a stale state.

const POLL_MS = 10000;

const el = {
  dot: document.getElementById("dot"),
  liveText: document.getElementById("live-text"),
  modePill: document.getElementById("mode-pill"),
  statusBody: document.getElementById("status-body"),
  statusLink: document.getElementById("status-link"),
  notice: document.getElementById("notice"),
  groups: document.getElementById("groups"),
  catalogNote: document.getElementById("catalog-note"),
  activity: document.getElementById("activity"),
  activityList: document.getElementById("activity-list"),
  activityTotal: document.getElementById("activity-total"),
};

// What we last showed, so we can announce real changes instead of noise.
let lastReadiness = null;
let lastEventCount = null;
let lastSuccess = null;
let failures = 0;

async function getJSON(path) {
  const res = await fetch(path, { headers: { accept: "application/json" } });
  const text = await res.text();
  let body = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = null;
  }
  if (!res.ok) throw new Error((body && (body.error || body.detail)) || `HTTP ${res.status}`);
  return body;
}

function ago(seconds) {
  if (seconds < 2) return "just now";
  if (seconds < 60) return `${Math.floor(seconds)}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  return `${Math.floor(seconds / 3600)}h ago`;
}

function setLive(kind, text) {
  el.dot.className = `dot ${kind}`;
  el.liveText.textContent = text;
}

function markPill(pill, kind, text) {
  pill.className = `pill ${kind}`;
  pill.textContent = text;
}

function check(label, on, note) {
  const node = document.createElement("span");
  node.className = `check ${on ? "on" : "off"}`;
  const b = document.createElement("b");
  b.textContent = on ? "yes" : "no";
  node.append(`${label} `, b);
  if (note) {
    const small = document.createElement("span");
    small.className = "muted small";
    small.textContent = note;
    node.append(" ", small);
  }
  return node;
}

function renderReadiness(r) {
  const canSell = Boolean(r.can_sell);
  markPill(
    el.modePill,
    canSell ? "ok" : "warn",
    `${r.mode || "unknown"} mode${canSell ? " · selling" : " · not selling"}`
  );
  if (el.statusLink) {
    el.statusLink.textContent = canSell ? "What you get when you buy" : "Why can I not buy yet?";
    el.statusLink.href = canSell ? "#catalog" : "#status";
  }

  const body = el.statusBody;
  body.replaceChildren();

  const checks = document.createElement("div");
  checks.className = "checks";
  const cat = r.catalog || {};
  checks.append(
    check("Payments", Boolean(r.secret_present && r.publishable_present)),
    check("Webhook", Boolean(r.webhook_present)),
    check("Prices", Boolean(cat.configured), `${cat.configured || 0}/${cat.skus || 0} set`),
    check("Provisioning", Boolean(r.can_provision), r.can_provision ? "" : "dry-run")
  );
  body.append(checks);

  const reasons = r.blocking_reasons || [];
  if (reasons.length) {
    const list = document.createElement("ul");
    list.className = "reasons";
    for (const reason of reasons) {
      const li = document.createElement("li");
      li.textContent = reason;
      list.append(li);
    }
    body.append(list);
  } else {
    const p = document.createElement("p");
    p.className = "muted";
    p.textContent = "Nothing is blocking a purchase. Prices below are real and live.";
    body.append(p);
  }

  // Announce a genuine change, once, and only when it matters.
  if (lastReadiness !== null && lastReadiness.can_sell !== r.can_sell) {
    showNotice(
      r.can_sell ? "The shop is open" : "The shop is closed for now",
      r.can_sell
        ? "Payments, prices and provisioning are all configured. Products below are buyable."
        : `A requirement went away: ${(r.blocking_reasons || []).join("; ")}`
    );
  }
  lastReadiness = r;
}

function showNotice(title, body) {
  const box = el.notice;
  box.replaceChildren();
  const h = document.createElement("h3");
  h.textContent = title;
  const p = document.createElement("p");
  p.textContent = body;
  box.append(h, p);
  box.hidden = false;
}

function money(cents, currency) {
  if (cents === null || cents === undefined) return null;
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency: (currency || "usd").toUpperCase(),
      maximumFractionDigits: 2,
    }).format(cents / 100);
  } catch {
    return `${(cents / 100).toFixed(2)} ${(currency || "usd").toUpperCase()}`;
  }
}

function skuCard(sku, canSell) {
  const card = document.createElement("article");
  card.className = "card";

  const kind = document.createElement("span");
  kind.className = "kind";
  kind.textContent = (sku.kind || "product").replace(/_/g, " ");

  const name = document.createElement("h4");
  name.textContent = sku.name || sku.id;

  const desc = document.createElement("p");
  desc.className = "desc";
  desc.textContent = sku.description || "";

  card.append(kind, name, desc);

  // The reason goes above the price row, not under it: it explains the price, and
  // leaving it last pushed it against the card edge and broke button alignment.
  if (!sku.configured && sku.unconfigured_reason) {
    const why = document.createElement("span");
    why.className = "why";
    why.textContent = sku.unconfigured_reason;
    card.append(why);
  }

  const foot = document.createElement("div");
  foot.className = "card-foot";

  const buyable = Boolean(sku.configured) && canSell;
  const price = document.createElement("span");
  if (buyable) {
    const amount = money(sku.amount_cents, sku.currency);
    price.className = "price";
    price.textContent = amount || sku.price_label || "See checkout";
  } else {
    price.className = "price none";
    price.textContent = sku.configured ? "checkout unavailable right now" : "price not set";
  }

  const btn = document.createElement("button");
  btn.className = `btn ${buyable ? "btn-primary" : "is-off"}`;
  btn.textContent = buyable ? "Buy" : "Unavailable";
  btn.disabled = !buyable;
  if (buyable) {
    btn.addEventListener("click", () => startCheckout(sku, btn));
  } else if (sku.unconfigured_reason) {
    btn.title = sku.unconfigured_reason;
  }

  foot.append(price, btn);
  card.append(foot);
  return card;
}

async function startCheckout(sku, btn) {
  btn.disabled = true;
  const original = btn.textContent;
  btn.textContent = "Starting…";
  try {
    const body = await getJSON("/api/checkout");
    const url = body && (body.url || body.checkout_url);
    if (url) {
      window.location.assign(url);
      return;
    }
    throw new Error((body && body.reason) || "checkout did not return a URL");
  } catch (err) {
    btn.disabled = false;
    btn.textContent = "Try again";
    showNotice("Checkout could not start", String(err.message || err));
    setTimeout(() => {
      btn.textContent = original;
    }, 4000);
  }
}

function renderCatalog(catalog) {
  const groups = catalog.groups || [];
  const skus = groups.flatMap((g) => g.skus || []);
  const configured = skus.filter((s) => s.configured).length;
  const canSell = Boolean(lastReadiness && lastReadiness.can_sell);

  el.catalogNote.textContent = skus.length
    ? `${skus.length} products across ${groups.length} groups · ${configured} priced and buyable`
    : "No products are published yet.";

  const root = el.groups;
  root.replaceChildren();
  if (!groups.length) {
    const p = document.createElement("p");
    p.className = "muted";
    p.textContent = "The catalog is empty right now.";
    root.append(p);
    return;
  }

  for (const group of groups) {
    const section = document.createElement("div");
    section.className = "group";
    const head = document.createElement("div");
    head.className = "group-head";
    const h3 = document.createElement("h3");
    h3.textContent = group.title || group.id;
    const blurb = document.createElement("p");
    blurb.textContent = group.blurb || "";
    head.append(h3, blurb);

    const cards = document.createElement("div");
    cards.className = "cards";
    for (const sku of group.skus || []) cards.append(skuCard(sku, canSell));

    section.append(head, cards);
    root.append(section);
  }
}

function renderEvents(status) {
  const total = (status && status.events_recorded) || 0;
  el.activityTotal.textContent = total ? `${total} events processed` : "no events yet";
  if (!total) {
    el.activity.hidden = true;
    return;
  }
  el.activity.hidden = false;
  const outcomes = (status && status.outcomes) || {};
  const list = el.activityList;
  list.replaceChildren();
  for (const [outcome, count] of Object.entries(outcomes)) {
    const li = document.createElement("li");
    const name = document.createElement("span");
    name.textContent = outcome;
    const n = document.createElement("span");
    n.className = `when ${outcome === "ok" || outcome === "provisioned" ? "outcome-ok" : "outcome-bad"}`;
    n.textContent = `×${count}`;
    li.append(name, n);
    list.append(li);
  }
  if (lastEventCount !== null && total > lastEventCount) {
    showNotice("New payment activity", `${total - lastEventCount} new event(s) processed just now.`);
  }
  lastEventCount = total;
}

async function tick() {
  try {
    const [readiness, catalog, events] = await Promise.all([
      getJSON("/api/readiness"),
      getJSON("/api/catalog"),
      getJSON("/api/webhooks/status"),
    ]);
    failures = 0;
    lastSuccess = Date.now();
    renderReadiness(readiness);
    renderCatalog(catalog);
    renderEvents(events);
    const blocking = (readiness.blocking_reasons || []).length;
    setLive(
      readiness.can_sell ? "ok" : blocking ? "warn" : "ok",
      `live · updated ${ago(0)}`
    );
  } catch (err) {
    failures += 1;
    setLive("bad", `reconnecting… (${failures})`);
    if (failures === 1) {
      showNotice("Lost contact with the server", "Retrying automatically. No need to reload.");
    }
  }
}

// Keep the "updated Ns ago" honest between polls.
setInterval(() => {
  if (lastSuccess === null || failures > 0) return;
  const secs = Math.round((Date.now() - lastSuccess) / 1000);
  const kind = lastReadiness && lastReadiness.can_sell ? "ok" : "warn";
  setLive(kind, `live · updated ${ago(secs)}`);
}, 1000);

function start() {
  tick();
  // Polling continues in the background; the tab being hidden only skips the work,
  // and coming back refreshes immediately rather than waiting out the interval.
  setInterval(() => {
    if (!document.hidden) tick();
  }, POLL_MS);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) tick();
  });
  window.addEventListener("focus", tick);
}

start();
