//! m6 — door3 shell routing over ONE wire. The same listener serves the
//! keyless walk-in page (`GET /`), the server-side world (`GET /world`, token
//! held by the bridge — never in the page), and the braid envelope
//! (`POST /v1/op`) that every door already uses.

use std::sync::Arc;
use std::thread;
use std::time::Duration;

use braid_core::crypto::new_signing_key;
use braid_keys::did_key;
use braid_wire::{
    http_get_raw, http_post_raw, BraidWireServer, Shell, WireOp, WireRequest, WireResponse,
};
use ed25519_dalek::{SigningKey, VerifyingKey};

fn mac(loc: &str, sk: &SigningKey, caps: &[&str]) -> braid_keys::SessionMacaroon {
    braid_keys::SessionMacaroon::issue(loc, &did_key(&VerifyingKey::from(sk)), caps, sk)
}

/// Boot a server behind the given shell (or none) and return its address.
fn boot(shell: Option<Shell>) -> String {
    let handler: braid_wire::Handler = Arc::new(|req: WireRequest| match req.op {
        WireOp::World { .. } => WireResponse::ok(
            serde_json::json!({ "door": "door3", "kind": "world", "echo": "handler got world" }),
            None,
        ),
        WireOp::Health => WireResponse::ok(serde_json::json!({ "status": "ok" }), None),
        _ => WireResponse::ok(serde_json::json!({ "echo": true }), None),
    });
    let server = match shell {
        Some(s) => BraidWireServer::new("127.0.0.1:0", handler)
            .expect("bind")
            .with_shell(s),
        None => BraidWireServer::new("127.0.0.1:0", handler).expect("bind"),
    };
    let addr = server.local_addr();
    thread::spawn(move || {
        let _ = server.run();
    });
    thread::sleep(Duration::from_millis(120));
    addr
}

#[test]
fn shell_serves_page_world_and_op_on_one_wire() {
    let sk = new_signing_key();
    let shell = Shell::from_html("<html><body data-door3=\"walk-in\">door3 walk-in</body></html>")
        .world_token(mac("door3", &sk, &["read:*:*"]));
    let addr = boot(Some(shell));

    // GET / → the keyless page, content-type text/html.
    let (status, raw) = http_get_raw(&addr, "/").expect("get /");
    assert_eq!(status, 200, "GET / status");
    assert!(raw.to_lowercase().contains("text/html"), "html content-type: {raw}");
    assert!(raw.contains("door3 walk-in"), "page body: {raw}");

    // GET /world → the handler saw a real WireOp::World (server-side token).
    let (status, raw) = http_get_raw(&addr, "/world").expect("get /world");
    assert_eq!(status, 200, "GET /world status");
    let world: WireResponse = serde_json::from_str(raw.split("\r\n\r\n").nth(1).unwrap()).unwrap();
    assert!(world.ok, "world op ok: {:?}", world.error);
    assert_eq!(world.data["door"], "door3");
    assert_eq!(world.data["echo"], "handler got world");

    // POST /v1/op → every door's existing path still works on the SAME port.
    let op = WireRequest::new(
        "http",
        mac("door3", &sk, &["write:note:*"]),
        WireOp::Read { snapshot: String::new(), op_filter: None },
    );
    let body = serde_json::to_string(&op).unwrap();
    let r = http_post_raw(&addr, "/v1/op", &body).expect("post /v1/op");
    assert!(r.ok, "op ok: {:?}", r.error);
    assert!(r.data["echo"].as_bool().unwrap_or(false));
}

#[test]
fn no_shell_means_no_page_but_op_unchanged() {
    let addr = boot(None);

    let (status, _) = http_get_raw(&addr, "/").expect("get /");
    assert_eq!(status, 403, "no shell ⇒ no page");

    let (status, _) = http_get_raw(&addr, "/world").expect("get /world");
    assert_eq!(status, 403, "no shell ⇒ no world route");
}

#[test]
fn route_table_serves_pages_ops_forge_and_manifest() {
    let sk = new_signing_key();
    let shell = Shell::from_html("<html>door1 nav</html>")
        .page("/about", "<html>about door1</html>")
        .op(
            "/witness",
            WireOp::Read { snapshot: String::new(), op_filter: None },
            mac("door1", &sk, &["read:*:*"]),
        )
        .forge("/forge", mac("door1", &sk, &["write:note:*"]))
        .json("/manifest", serde_json::json!({ "surfaces": ["witness", "forge"] }));
    let addr = boot(Some(shell));

    // GET / → the nav page; GET /about → the extra page.
    let (status, raw) = http_get_raw(&addr, "/").expect("get /");
    assert_eq!(status, 200);
    assert!(raw.contains("door1 nav"));
    let (status, raw) = http_get_raw(&addr, "/about").expect("get /about");
    assert_eq!(status, 200);
    assert!(raw.contains("about door1"));

    // GET /witness → a server-side WireOp::Read reached the handler (token server-side).
    let (status, raw) = http_get_raw(&addr, "/witness").expect("get /witness");
    assert_eq!(status, 200);
    let r: WireResponse = serde_json::from_str(raw.split("\r\n\r\n").nth(1).unwrap()).unwrap();
    assert!(r.ok, "witness op ok: {:?}", r.error);
    assert_eq!(r.data["echo"], true, "handler saw the read op");

    // GET /manifest → static JSON.
    let (status, raw) = http_get_raw(&addr, "/manifest").expect("get /manifest");
    assert_eq!(status, 200);
    let r: WireResponse = serde_json::from_str(raw.split("\r\n\r\n").nth(1).unwrap()).unwrap();
    assert!(r.ok);
    assert_eq!(r.data["surfaces"][0], "witness");

    // POST /forge → the handler received a real write:note built from the body.
    let forge = serde_json::json!({ "target": "place/room", "content": "forged note" });
    let r = http_post_raw(&addr, "/forge", &forge.to_string()).expect("post /forge");
    assert!(r.ok, "forge ok: {:?}", r.error);

    // Unknown shell paths fall through to the base router (403), never a page.
    let (status, _) = http_get_raw(&addr, "/nope").expect("get /nope");
    assert_eq!(status, 403, "unknown path is not a shell route");

    // POST /forge with a malformed body is refused by the shell (no target).
    let r = http_post_raw(&addr, "/forge", "{}").expect("post /forge bad body");
    assert!(!r.ok);
    assert!(r.error.as_deref().unwrap_or("").contains("target"));
}