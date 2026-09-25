//! braid_wire HTTP surface for the three UIs.
//!
//! A single TCP listener decodes HTTP/1.1 request frames, hands each one to a
//! handler (the door's Router), and writes back the JSON response. This is the
//! ONE network-facing surface; every door consumes it through the same
//! `Frontdoor` router, and every request carries the braid session macaroon.
//!
//! m6/m7 web shells: a server may be armed with an optional [`Shell`] — a
//! keyless route table (static pages, server-side ops, a forge write, and a
//! static manifest). Tokens are held by the bridge and never reach the
//! browser: `GET /` serves the page, `GET /world` a `WireOp::World`,
//! `GET /witness`/`/structure` the door1 views, `POST /forge/…` a write.

use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::sync::Arc;

use crate::messages::{WireOp, WireRequest, WireResponse};
use crate::protocol::Frame;

/// A request handler. The bridge/router impl owns the engine + policy; the
/// server only knows it returns a braid response for a braid request.
pub type Handler = Arc<dyn Fn(WireRequest) -> WireResponse + Send + Sync>;

/// One keyless shell route: either a static page, a server-side op (issued
/// with a bridge-held token), a forge write (bridge-held write token, payload
/// from the request body), an escalated write (bridge-held write token PLUS
/// the bridge-held human escalation token, D2.3/D2.4), a policy eval (POSTs a
/// capability string and returns a real policy verdict, m8 tool-policy/console
/// surfaces), or a static JSON manifest. The browser only ever holds the page
/// HTML — every cap token stays on the bridge.
#[derive(Debug, Clone)]
pub enum ShellRoute {
    /// Serve `html` verbatim.
    Page(String),
    /// Issue `op` with a bridge-held token and return the braid envelope.
    Op { op: WireOp, token: braid_keys::SessionMacaroon },
    /// Build a `WireOp::Write` from the JSON body `{ "target", "content" }`
    /// using a bridge-held write token and the route's op. `forge(path, token)`
    /// keeps the classic `write:note`; `forge_op(path, token, op)` generalizes.
    Forge { token: braid_keys::SessionMacaroon, op: String },
    /// Build a `WireOp::Write` from `{ "target", "content" }` using BOTH the
    /// bridge-held write token and the bridge-held human escalation token —
    /// the destructive path (admin:destroy) commits only through esc key.
    Escalated { token: braid_keys::SessionMacaroon, human: braid_keys::SessionMacaroon, op: String },
    /// Build a `WireOp::Spatial` (door3 quest3d, m9) from `{ "target",
    /// "content" }` using a bridge-held write token. A spatial fact is a real
    /// braid node — the walk-in derives it as a PROVEN fact. `op` is the
    /// capability the bridge token must grant (creative: `write:world`).
    Spatial { token: braid_keys::SessionMacaroon, op: String },
    /// POST a real capability string `{ "cap" }` and return the frozen policy
    /// snapshot's verdict for it (m8 eval-tasks / tool-policy console).
    Eval { token: braid_keys::SessionMacaroon, snapshot: String },
    /// Serve a static JSON document (nav manifest / surface directory).
    Json(serde_json::Value),
    /// door3 quest3d (m11, D3.5) — SPOKEN RESONANCE: GET renders the last
    /// `depth` proven nodes of the ONE ledger as a real `audio/wav` stream,
    /// synthesized by the kokoro TTS container via a bridge-held read token.
    /// The browser only holds the `<audio>` URL; the token stays on the
    /// bridge. Unreachable TTS => the bridge denies honestly (no fake track).
    Sound { token: braid_keys::SessionMacaroon, voice: String, depth: u64 },
    /// door3 (m12) — the INTENT STRAND: GET returns the committed `write:intent`
    /// projection (open desires + their proven resolutions) via a bridge-held
    /// read token. Read-gated exactly like every read surface.
    IntentView { token: braid_keys::SessionMacaroon },
    /// door3 (m12) — INTENT SUBMIT: POST `{ "desire", "target", "context"?,
    /// "weight"? }` commits a `write:intent` node with a bridge-held write
    /// token (scope must grant `write:intent`). The browser never holds a key.
    IntentSubmit { token: braid_keys::SessionMacaroon },
    /// m13 — the TERMINAL DOOR's unified TAIL: GET streams the last `limit`
    /// committed nodes of the ONE ledger via a bridge-held read token.
    /// `?limit=` / `?since=<cid>` override the route default, so a terminal
    /// can paginate and `--follow` with no token of its own.
    Tail { token: braid_keys::SessionMacaroon, default_limit: u64 },
    /// m13 — the TERMINAL DOOR's unified READ VIEW: GET returns the single
    /// head + fork invariant, the current head/depth, and every registered
    /// door's view position via a bridge-held read token.
    Inspect { token: braid_keys::SessionMacaroon },
    /// m13 — prove real: GET `/prove?cid=…` returns the Merkle spine to
    /// genesis + the verified flag for any committed node (bridge-held read
    /// token). The witness door's proof surface, on the same wire.
    Prove { token: braid_keys::SessionMacaroon },
    /// m13 — policy: GET returns the FULL frozen policy snapshot (the rule
    /// list the engine binds into every write triplet) via a bridge-held read
    /// token. The CLI prints rules; the console keeps its POST eval verdict.
    Policy { token: braid_keys::SessionMacaroon, snapshot: String },
}

/// The keyless web surface. One bridge, many routes, all keys server-side.
#[derive(Debug, Clone)]
pub struct Shell {
    routes: Vec<(String, ShellRoute)>,
    /// Set by [`Shell::spatial`]: when a spatial-write route exists, the walk-in
    /// page renders the place-fact control (m9). Shells without a spatial
    /// surface serve the same page WITHOUT the control — the page never
    /// advertises a write it cannot perform.
    place_surface: bool,
    /// Set by [`Shell::sound`]: when a sound route exists, the walk-in page
    /// renders the `<audio>` resonance player (m11, D3.5). Shells without a
    /// sound surface drop the player the same honest way.
    sound_surface: bool,
    /// Set by [`Shell::intent`]: when an intent route pair exists, the walk-in
    /// page renders the intent strand panel (m12) — open desires + a keyless
    /// submit control. Shells without an intent surface drop the panel.
    intent_surface: bool,
    /// Set by [`Shell::inspect`]: when an inspect route exists, the walk-in
    /// page renders the m13 single-head/forks/depth readout (unified READ
    /// VIEW). Shells without the surface drop the readout.
    inspect_surface: bool,
}

impl Shell {
    /// A static walk-in page, served at `GET /`.
    pub fn from_html(html: impl Into<String>) -> Self {
        Self { routes: vec![("/".into(), ShellRoute::Page(html.into()))], place_surface: false, sound_surface: false, intent_surface: false, inspect_surface: false }
    }

    /// Arm `GET /world` with a read-scoped token held by the server.
    pub fn world_token(mut self, token: braid_keys::SessionMacaroon) -> Self {
        self.routes.push(("/world".into(), ShellRoute::Op { op: WireOp::World { snapshot: String::new() }, token }));
        self
    }

    /// Serve `html` at `path`.
    pub fn page(mut self, path: impl Into<String>, html: impl Into<String>) -> Self {
        self.routes.push((path.into(), ShellRoute::Page(html.into())));
        self
    }

    /// Serve a server-side op at `path` (bridge-held token, GET).
    pub fn op(mut self, path: impl Into<String>, op: WireOp, token: braid_keys::SessionMacaroon) -> Self {
        self.routes.push((path.into(), ShellRoute::Op { op, token }));
        self
    }

    /// Serve a keyless forge write at `path` (bridge-held write token, POST).
    /// The op defaults to `write:note` (m6/m7 behavior).
    pub fn forge(mut self, path: impl Into<String>, token: braid_keys::SessionMacaroon) -> Self {
        self.routes.push((path.into(), ShellRoute::Forge { token, op: "write:note".into() }));
        self
    }

    /// Serve a keyless forge write with an arbitrary op (m8 godmode canvas /
    /// playground creative writes). Bridge-held write token, POST.
    pub fn forge_op(mut self, path: impl Into<String>, token: braid_keys::SessionMacaroon, op: impl Into<String>) -> Self {
        self.routes.push((path.into(), ShellRoute::Forge { token, op: op.into() }));
        self
    }

    /// Serve a keyless ESCALATED write at `path`: the bridge holds BOTH the
    /// write token and the human escalation token (m8 playground reset /
    /// godmode destructive surface). POST, D2.3 boundary.
    pub fn escalated(mut self, path: impl Into<String>, token: braid_keys::SessionMacaroon, human: braid_keys::SessionMacaroon, op: impl Into<String>) -> Self {
        self.routes.push((path.into(), ShellRoute::Escalated { token, human, op: op.into() }));
        self
    }

    /// Serve a keyless spatial-write at `path` (door3 quest3d, m9): a spatial
    /// fact committed into the ONE ledger with a bridge-held write token.
    /// POST, creative surface (`write:world`); the response echoes the fresh
    /// WorldScene + resonance window so the walk-in updates immediately.
    pub fn spatial(mut self, path: impl Into<String>, token: braid_keys::SessionMacaroon, op: impl Into<String>) -> Self {
        self.place_surface = true;
        self.routes.push((path.into(), ShellRoute::Spatial { token, op: op.into() }));
        self
    }

    /// Serve a real policy-eval at `path`: POST `{ "cap": "..." }` and the
    /// bridge returns the frozen snapshot's verdict (m8 /evaluate,
    /// /tool-policy-console). Bridge-held read token, POST.
    pub fn eval(mut self, path: impl Into<String>, token: braid_keys::SessionMacaroon, snapshot: impl Into<String>) -> Self {
        self.routes.push((path.into(), ShellRoute::Eval { token, snapshot: snapshot.into() }));
        self
    }

    /// Serve a static JSON document at `path` (nav manifest / surface directory).
    pub fn json(mut self, path: impl Into<String>, value: serde_json::Value) -> Self {
        self.routes.push((path.into(), ShellRoute::Json(value)));
        self
    }

    /// Arm the SPOKEN-RESONANCE route (m11, D3.5): `GET {path}` streams the
    /// last `depth` proven nodes of the ONE ledger as a real `audio/wav`
    /// spine-audio, synthesized by the kokoro TTS container over a
    /// bridge-held READ token. `voice` is the deterministic kokoro voice.
    pub fn sound(mut self, path: impl Into<String>, token: braid_keys::SessionMacaroon, voice: impl Into<String>, depth: u64) -> Self {
        self.sound_surface = true;
        self.routes.push((path.into(), ShellRoute::Sound { token, voice: voice.into(), depth }));
        self
    }

    /// Arm the INTENT STRAND route pair (m12): `GET {path}` streams the
    /// committed `write:intent` projection (open desires + resolutions) over a
    /// bridge-held READ token; `POST {path}` commits a new intent
    /// (`{ "desire", "target" }`) over a bridge-held WRITE token licensed for
    /// `write:intent`. The browser only ever holds the page.
    pub fn intent(mut self, path: impl Into<String>, read_token: braid_keys::SessionMacaroon, write_token: braid_keys::SessionMacaroon) -> Self {
        self.intent_surface = true;
        let path = path.into();
        self.routes.push((path.clone(), ShellRoute::IntentView { token: read_token }));
        self.routes.push((path, ShellRoute::IntentSubmit { token: write_token }));
        self
    }

    /// Arm the TERMINAL DOOR's unified TAIL (m13): `GET {path}` streams the
    /// last `default_limit` committed nodes of the ONE ledger over a
    /// bridge-held READ token. `?limit=` / `?since=<cid>` override at request
    /// time, so a terminal can paginate and `--follow` with no token of its own.
    pub fn tail(mut self, path: impl Into<String>, token: braid_keys::SessionMacaroon, default_limit: u64) -> Self {
        self.routes.push((path.into(), ShellRoute::Tail { token, default_limit }));
        self
    }

    /// Arm the TERMINAL DOOR's unified READ VIEW (m13): `GET {path}` returns
    /// the real single-head/forks invariant, current head/depth, and every
    /// registered door's view position over a bridge-held READ token. Also
    /// lights the single-head readout in the walk-in page header.
    pub fn inspect(mut self, path: impl Into<String>, token: braid_keys::SessionMacaroon) -> Self {
        self.inspect_surface = true;
        self.routes.push((path.into(), ShellRoute::Inspect { token }));
        self
    }

    /// Arm a real proof surface (m13): `GET {path}?cid=…` returns the Merkle
    /// spine to genesis + the verified flag for any committed node, over a
    /// bridge-held READ token (the witness driver, keyless at the shell).
    pub fn prove(mut self, path: impl Into<String>, token: braid_keys::SessionMacaroon) -> Self {
        self.routes.push((path.into(), ShellRoute::Prove { token }));
        self
    }

    /// Arm a full-policy surface (m13): `GET {path}` returns the frozen
    /// `snapshot`'s rule list (the same authority bound into every write
    /// triplet) over a bridge-held READ token. `snapshot == ""` uses the
    /// bridge's default snapshot.
    pub fn policy(mut self, path: impl Into<String>, token: braid_keys::SessionMacaroon, snapshot: impl Into<String>) -> Self {
        self.routes.push((path.into(), ShellRoute::Policy { token, snapshot: snapshot.into() }));
        self
    }

    /// True if this shell owns the (method, path).
    pub fn has(&self, method: &str, path: &str) -> bool {
        self.routes.iter().any(|(p, r)| {
            p == path
                && match r {
                    ShellRoute::Forge { .. } | ShellRoute::Escalated { .. } | ShellRoute::Spatial { .. } | ShellRoute::Eval { .. } | ShellRoute::IntentSubmit { .. } => {
                        method == "POST"
                    }
                    _ => method == "GET",
                }
        })
    }

    /// Respond to a shell-owned request. Returns `None` when the route is not
    /// owned by this shell (caller falls through to the base router).
    fn respond(&self, method: &str, path: &str, query: &str, body: &str, handler: &Handler) -> Option<Reply> {
        // A route pair like GET /canvas + POST /canvas (or GET /evaluate +
        // POST /evaluate) shares one path — scan ALL routes at the path and
        // take the first whose method guard fires.
        self.routes
            .iter()
            .filter(|(p, _)| p == path)
            .find_map(|route| match &route.1 {
            ShellRoute::Page(html) if method == "GET" => {
                let html = if self.place_surface {
                    html.replace(
                        "<!--PLACE_SURFACE-->",
                        r#"<span id="place">
    <input id="placeTarget" placeholder="object (write:world)" spellcheck="false">
    <button id="placeBtn" title="commit a spatial fact into the one ledger (keyless over the bridge token)">place fact</button>
  </span>"#,
                    )
                } else {
                    html.replacen("<!--PLACE_SURFACE-->", "", 1)
                };
                let html = if self.sound_surface {
                    html.replace(
                        "<!--SOUND_SURFACE-->",
                        r#"<section id="sound">
    <p class="label">resonance — the spine speaks its last echoes (audio/wav)</p>
    <audio id="spineAudio" controls preload="metadata"><source src="/sound" type="audio/wav"></audio>
    <p id="audioStatus" class="status"></p>
  </section>"#,
                    )
                } else {
                    html.replacen("<!--SOUND_SURFACE-->", "", 1)
                };
                let html = if self.intent_surface {
                    let html = html.replace(
                        "<!--INTENT_SURFACE-->",
                        r#"<span class="stat">intent <b id="intentOpen">–</b> open · <b id="intentResolved">–</b> resolved</span>"#,
                    );
                    html.replace(
                        "<!--INTENT_PANEL-->",
                        r#"<section id="intentPanel" class="intent">
    <h2>intent strand <span class="dim">— committed write:intent nodes, open until proven work fulfills them</span></h2>
    <form id="intentForm">
      <input id="intentDesire" placeholder="desire" spellcheck="false">
      <input id="intentTarget" placeholder="target (write:intent)" spellcheck="false">
      <button type="submit">submit intent</button>
    </form>
    <ul id="intentList"><li class="stat">no intents yet — the walk-in is satisfied until a desire is committed.</li></ul>
  </section>"#,
                    )
                } else {
                    let html = html.replacen("<!--INTENT_SURFACE-->", "", 1);
                    html.replacen("<!--INTENT_PANEL-->", "", 1)
                };
                let html = if self.inspect_surface {
                    html.replace("<!--INSPECT_SURFACE-->", INSPECT_PANEL)
                } else {
                    html.replacen("<!--INSPECT_SURFACE-->", "", 1)
                };
                Some(Reply::Html(html))
            }
            ShellRoute::Json(v) if method == "GET" => {
                Some(Reply::Json(WireResponse::ok(v.clone(), None)))
            }
            ShellRoute::Op { op, token } if method == "GET" => {
                let req = WireRequest::new("http", token.clone(), op.clone());
                Some(Reply::Json((handler)(req)))
            }
            ShellRoute::Forge { token, op } if method == "POST" => {
                let body: serde_json::Value = serde_json::from_str(body).unwrap_or_default();
                let target = body.get("target").and_then(|v| v.as_str());
                let content = body.get("content").and_then(|v| v.as_str());
                let Some(target) = target else {
                    return Some(Reply::Json(WireResponse::err("forge body needs `target` (string)")));
                };
                let Some(content) = content else {
                    return Some(Reply::Json(WireResponse::err("forge body needs `content` (string)")));
                };
                let req = WireRequest::new(
                    "http",
                    token.clone(),
                    WireOp::Write {
                        snapshot: String::new(),
                        op: op.clone(),
                        target: target.into(),
                        payload: serde_json::json!({ "content": content }),
                    },
                );
                Some(Reply::Json((handler)(req)))
            }
            ShellRoute::Escalated { token, human, op } if method == "POST" => {
                let body: serde_json::Value = serde_json::from_str(body).unwrap_or_default();
                let target = body.get("target").and_then(|v| v.as_str());
                let content = body.get("content").and_then(|v| v.as_str());
                let Some(target) = target else {
                    return Some(Reply::Json(WireResponse::err("escalated body needs `target` (string)")));
                };
                let Some(content) = content else {
                    return Some(Reply::Json(WireResponse::err("escalated body needs `content` (string)")));
                };
                let mut req = WireRequest::new(
                    "http",
                    token.clone(),
                    WireOp::Write {
                        snapshot: String::new(),
                        op: op.clone(),
                        target: target.into(),
                        payload: serde_json::json!({ "content": content }),
                    },
                );
                req.escalation = Some(human.clone());
                Some(Reply::Json((handler)(req)))
            }
            ShellRoute::Spatial { token, op } if method == "POST" => {
                let body: serde_json::Value = serde_json::from_str(body).unwrap_or_default();
                let target = body.get("target").and_then(|v| v.as_str());
                let content = body.get("content").and_then(|v| v.as_str());
                let Some(target) = target else {
                    return Some(Reply::Json(WireResponse::err("spatial body needs `target` (string)")));
                };
                let Some(content) = content else {
                    return Some(Reply::Json(WireResponse::err("spatial body needs `content` (string)")));
                };
                let req = WireRequest::new(
                    "http",
                    token.clone(),
                    WireOp::Spatial {
                        snapshot: String::new(),
                        op: op.clone(),
                        target: target.into(),
                        payload: serde_json::json!({ "content": content }),
                    },
                );
                Some(Reply::Json((handler)(req)))
            }
            ShellRoute::Eval { token, snapshot } if method == "POST" => {
                let body: serde_json::Value = serde_json::from_str(body).unwrap_or_default();
                let cap = body.get("cap").and_then(|v| v.as_str());
                let Some(cap) = cap else {
                    return Some(Reply::Json(WireResponse::err("eval body needs `cap` (string)")));
                };
                let req = WireRequest::new(
                    "http",
                    token.clone(),
                    WireOp::Policy { snapshot: snapshot.clone(), cap: Some(cap.into()) },
                );
                Some(Reply::Json((handler)(req)))
            }
            ShellRoute::Sound { token, voice: _, depth } if method == "GET" => {
                let req = WireRequest::new(
                    "http",
                    token.clone(),
                    WireOp::Audio { snapshot: String::new(), depth: *depth },
                );
                let resp = (handler)(req);
                if resp.ok {
                    // The op response ships the wav base64; the shell re-serves
                    // it as RAW audio/wav so the browser <audio> element can
                    // stream the spine without ever touching a token.
                    let resp = resp.clone();
                    let wav_b64 = resp
                        .data
                        .get("wav_b64")
                        .and_then(|v| v.as_str());
                    match wav_b64.map(crate::b64::decode) {
                        Some(Ok(wav)) => Some(Reply::Audio(wav)),
                        _ => Some(Reply::Json(WireResponse::err("sound route: missing or corrupt wav_b64 in op response"))),
                    }
                } else {
                    Some(Reply::Json(resp))
                }
            }
            ShellRoute::IntentView { token } if method == "GET" => {
                let req = WireRequest::new(
                    "http",
                    token.clone(),
                    WireOp::Intent { snapshot: String::new() },
                );
                Some(Reply::Json((handler)(req)))
            }
            ShellRoute::IntentSubmit { token } if method == "POST" => {
                let body: serde_json::Value = serde_json::from_str(body).unwrap_or_default();
                let desire = body.get("desire").and_then(|v| v.as_str());
                let target = body.get("target").and_then(|v| v.as_str());
                let Some(desire) = desire else {
                    return Some(Reply::Json(WireResponse::err("intent body needs `desire` (string)")));
                };
                let Some(target) = target else {
                    return Some(Reply::Json(WireResponse::err("intent body needs `target` (string)")));
                };
                let context = body.get("context").cloned().unwrap_or(serde_json::Value::Null);
                let weight = body.get("weight").and_then(serde_json::Value::as_u64).unwrap_or(1);
                let req = WireRequest::new(
                    "http",
                    token.clone(),
                    WireOp::Write {
                        snapshot: String::new(),
                        op: braid_core::intent::INTENT_OP.into(),
                        target: target.into(),
                        payload: braid_core::intent::IntentStrand::carrying(desire, target, context, weight),
                    },
                );
                Some(Reply::Json((handler)(req)))
            }
            ShellRoute::Tail { token, default_limit } if method == "GET" => {
                // Terminal doors are cursor-driven: `?since=<cid>` resumes just
                // AFTER a committed node, `?limit=` overrides the route default.
                let limit = q_param(query, "limit")
                    .and_then(|s| s.parse::<u64>().ok())
                    .filter(|l| *l > 0)
                    .unwrap_or(*default_limit);
                let since = q_param(query, "since");
                let req = WireRequest::new(
                    "http",
                    token.clone(),
                    WireOp::Tail { snapshot: String::new(), since_cid: since, limit },
                );
                Some(Reply::Json((handler)(req)))
            }
            ShellRoute::Inspect { token } if method == "GET" => {
                let req = WireRequest::new("http", token.clone(), WireOp::Inspect);
                Some(Reply::Json((handler)(req)))
            }
            ShellRoute::Prove { token } if method == "GET" => {
                let cid = q_param(query, "cid").unwrap_or_default();
                if cid.is_empty() {
                    return Some(Reply::Json(WireResponse::err("prove needs `?cid=<cid>` on the query string")));
                }
                let req = WireRequest::new("http", token.clone(), WireOp::Prove { cid });
                Some(Reply::Json((handler)(req)))
            }
            ShellRoute::Policy { token, snapshot } if method == "GET" => {
                let req = WireRequest::new(
                    "http",
                    token.clone(),
                    WireOp::Policy { snapshot: snapshot.clone(), cap: None },
                );
                Some(Reply::Json((handler)(req)))
            }
            _ => None,
        })
    }
}

/// A decoded response: JSON (the braid envelope), a raw HTML page, or raw
/// audio bytes (the m11 sound surface streams `audio/wav`, never the envelope).
enum Reply {
    Json(WireResponse),
    Html(String),
    Audio(Vec<u8>),
}

/// m13: the walk-in's single-head readout — lives only when an inspect route
/// is armed (the page never advertises a surface it cannot serve). Polls
/// `GET /inspect` (keyless, bridge-held token) and shows heads/forks/depth.
const INSPECT_PANEL: &str = r#"<span class="stat">heads <b id="inspectHeads">–</b> · forks <b id="inspectForks">–</b> · depth <b id="inspectDepth">–</b></span>
<script>
(function () {
  var keys = { heads: "inspectHeads", forks: "inspectForks", depth: "inspectDepth" };
  async function pull() {
    try {
      var r = await fetch("/inspect");
      var j = await r.json();
      if (j.ok && j.data) {
        document.getElementById(keys.heads).textContent = j.data.heads;
        document.getElementById(keys.forks).textContent = j.data.forks;
        document.getElementById(keys.depth).textContent = j.data.head_depth;
      }
    } catch (e) {}
  }
  pull();
  setInterval(pull, 4000);
})();
</script>"#;

/// Fetch one query parameter from a raw query string (`?a=1&b=2` → `a`, `b`).
fn q_param(query: &str, key: &str) -> Option<String> {
    query.split('&').find_map(|kv| {
        let (k, v) = kv.split_once('=')?;
        (k == key).then(|| v.to_string())
    })
}

/// BraidWireServer — ONE listener, decoding HTTP frames to WireRequests.
pub struct BraidWireServer {
    listener: TcpListener,
    handler: Handler,
    shell: Option<Shell>,
}

impl BraidWireServer {
    pub fn new(addr: &str, handler: Handler) -> Result<Self, String> {
        let listener = TcpListener::bind(addr).map_err(|e| format!("bind {addr}: {e}"))?;
        Ok(Self { listener, handler, shell: None })
    }

    /// Arm the optional keyless web surface (m6 door3 shell, m7 door1 shell —
    /// static pages, server-side ops, forge writes, manifest). The base
    /// envelope routes (`POST /v1/op`, `/health`) are untouched.
    pub fn with_shell(mut self, shell: Shell) -> Self {
        self.shell = Some(shell);
        self
    }

    /// The bound local address (useful for tests binding :0).
    pub fn local_addr(&self) -> String {
        self.listener
            .local_addr()
            .map(|a| a.to_string())
            .unwrap_or_else(|_| "unknown".into())
    }

    /// Serve one connection request (parse frame → handler → reply).
    pub fn handle(&self, mut stream: TcpStream) -> Result<(), String> {
        let mut buf = Vec::with_capacity(4096);
        let mut chunk = [0u8; 4096];
        loop {
            let n = stream
                .read(&mut chunk)
                .map_err(|e| format!("read: {e}"))?;
            if n == 0 {
                break;
            }
            buf.extend_from_slice(&chunk[..n]);
            if buf.windows(4).any(|w| w == b"\r\n\r\n") {
                break;
            }
        }

        let frame = Frame::parse_http(&buf)?;
        let bytes = route(frame, &self.handler, &self.shell)?;
        stream
            .write_all(&bytes)
            .map_err(|e| format!("write: {e}"))?;
        let _ = stream.flush();
        Ok(())
    }

    /// Accept loop — runs forever, one thread per connection (three doors can
    /// interleave without blocking each other; the engine serializes writes).
    pub fn run(&self) -> Result<(), String> {
        for stream in self.listener.incoming() {
            match stream {
                Ok(mut s) => {
                    s.set_nodelay(true).ok();
                    let handler = self.handler.clone();
                    let shell = self.shell.clone();
                    std::thread::spawn(move || {
                        let _ = serve_stream(&mut s, handler.clone(), shell);
                    });
                }
                Err(e) => eprintln!("[braid_wire] accept error: {e}"),
            }
        }
        Ok(())
    }
}

/// Decode one frame into response bytes (JSON envelope or raw HTML page).
fn route(frame: Frame, handler: &Handler, shell: &Option<Shell>) -> Result<Vec<u8>, String> {
    let response = match frame {
        Frame::HttpRequest { method, path, body } => {
            let (path, query) = match path.split_once('?') {
                Some((p, q)) => (p.to_string(), q.to_string()),
                None => (path.to_string(), String::new()),
            };
            let method = method.to_uppercase();
            let shell_owned = shell
                .as_ref()
                .map(|s| s.has(&method, &path))
                .unwrap_or(false);
            let response = if shell_owned {
                shell.as_ref().and_then(|s| s.respond(&method, &path, &query, &body, handler))
            } else {
                None
            };
            match response {
                Some(r) => r,
                None => match (method.as_str(), path.as_str()) {
                    (_, "/v1/op") => match serde_json::from_str::<WireRequest>(&body) {
                        Ok(req) => Reply::Json((handler)(req)),
                        Err(e) => Reply::Json(WireResponse::err(format!("bad envelope: {e}"))),
                    },
                    (_, "/health") => {
                        Reply::Json(WireResponse::ok(serde_json::json!({ "status": "ok" }), None))
                    }
                    (m, p) => Reply::Json(WireResponse::err(format!("no route: {m} {p}"))),
                },
            }
        }
        _ => return Err("only HTTP requests are served on this socket".into()),
    };

    let bytes = match response {
        Reply::Json(r) => {
            let json = serde_json::to_string(&r).map_err(|e| format!("serialize: {e}"))?;
            Frame::HttpResponse {
                status: if r.ok { 200 } else { 403 },
                body: json,
            }
            .to_http_bytes()
        }
        Reply::Html(html) => format!(
            "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{html}",
            html.len()
        )
        .into_bytes(),
        Reply::Audio(wav) => Vec::from(
            format!(
                "HTTP/1.1 200 OK\r\nContent-Type: audio/wav\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                wav.len()
            )
            .as_bytes(),
        )
        .into_iter()
        .chain(wav)
        .collect(),
    };
    Ok(bytes)
}

fn serve_stream(stream: &mut TcpStream, handler: Handler, shell: Option<Shell>) -> Result<(), String> {
    let mut buf = Vec::with_capacity(4096);
    let mut chunk = [0u8; 4096];
    loop {
        let n = stream.read(&mut chunk).map_err(|e| format!("read: {e}"))?;
        if n == 0 {
            return Ok(());
        }
        buf.extend_from_slice(&chunk[..n]);
        if buf.windows(4).any(|w| w == b"\r\n\r\n") {
            break;
        }
    }
    let frame = Frame::parse_http(&buf)?;
    let bytes = route(frame, &handler, &shell)?;
    stream.write_all(&bytes).map_err(|e| format!("write: {e}"))?;
    let _ = stream.flush();
    Ok(())
}

/// Tiny client helper for tests and the smoke harness: POST a braid request
/// to /v1/op and get back the JSON response.
pub fn http_post_raw(addr: &str, path: &str, body: &str) -> Result<WireResponse, String> {
    let mut stream = TcpStream::connect(addr).map_err(|e| format!("connect: {e}"))?;
    let req = format!(
        "POST {path} HTTP/1.1\r\nHost: {addr}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
        body.len()
    );
    stream.write_all(req.as_bytes()).map_err(|e| format!("write: {e}"))?;

    let mut resp_buf = Vec::new();
    stream.read_to_end(&mut resp_buf).map_err(|e| format!("read: {e}"))?;
    let text = std::str::from_utf8(&resp_buf).map_err(|e| format!("utf8: {e}"))?;
    let body = text.split("\r\n\r\n").nth(1).unwrap_or("");
    serde_json::from_str(body).map_err(|e| format!("decode body: {e}"))
}

/// Tiny client helper for the door3 shell: GET a page and return the status
/// code plus the full raw response (headers + body) so callers can check
/// content-type and content.
pub fn http_get_raw(addr: &str, path: &str) -> Result<(u16, String), String> {
    let mut stream = TcpStream::connect(addr).map_err(|e| format!("connect: {e}"))?;
    let req = format!("GET {path} HTTP/1.1\r\nHost: {addr}\r\nConnection: close\r\n\r\n");
    stream.write_all(req.as_bytes()).map_err(|e| format!("write: {e}"))?;
    let mut resp_buf = Vec::new();
    stream.read_to_end(&mut resp_buf).map_err(|e| format!("read: {e}"))?;
    let text = std::str::from_utf8(&resp_buf).map_err(|e| format!("utf8: {e}"))?;
    let status = text
        .lines()
        .next()
        .and_then(|l| l.split_whitespace().nth(1))
        .and_then(|s| s.parse::<u16>().ok())
        .ok_or("no status line")?;
    Ok((status, text.to_string()))
}

/// Tiny client helper for the audio strand: GET a page and return the status
/// code, declared content-type, and the RAW body bytes (WAV audio is binary,
/// so this variant never forces UTF-8).
pub fn http_get_bytes(addr: &str, path: &str) -> Result<(u16, String, Vec<u8>), String> {
    let mut stream = TcpStream::connect(addr).map_err(|e| format!("connect: {e}"))?;
    let req = format!("GET {path} HTTP/1.1\r\nHost: {addr}\r\nConnection: close\r\n\r\n");
    stream.write_all(req.as_bytes()).map_err(|e| format!("write: {e}"))?;
    let mut resp_buf = Vec::new();
    stream.read_to_end(&mut resp_buf).map_err(|e| format!("read: {e}"))?;
    let head = resp_buf
        .windows(4)
        .position(|w| w == b"\r\n\r\n")
        .map(|i| i + 4)
        .ok_or("no response headers")?;
    let head_text = String::from_utf8_lossy(&resp_buf[..head]).to_string();
    let status = head_text
        .lines()
        .next()
        .and_then(|l| l.split_whitespace().nth(1))
        .and_then(|s| s.parse::<u16>().ok())
        .ok_or("no status line")?;
    let content_type = head_text
        .lines()
        .find(|l| l.to_ascii_lowercase().starts_with("content-type:"))
        .map(|l| l.split_once(':').map(|(_, v)| v.trim().to_string()).unwrap_or_default())
        .unwrap_or_default();
    Ok((status, content_type, resp_buf[head..].to_vec()))
}