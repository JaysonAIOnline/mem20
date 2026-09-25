//! Transport framing for braid_wire.
//!
//! The wire is transport-agnostic: a Frame is either an HTTPRequest or an
//! HTTPResponse (HTTP/1.1, chunk-conscious) or a WebSocket-style message
//! (length-prefixed). The bridge picks the transport; the ENVELOPE is the
//! same either way. This keeps the door a transport-adaptive surface without
//! a second protocol island.

use serde::{Deserialize, Serialize};

/// A wire frame, however it got here.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Frame {
    /// HTTP/1.1 request — method, path with query, optional body.
    HttpRequest {
        method: String,
        path: String,
        #[serde(default)]
        body: String,
    },
    /// HTTP/1.1 response — numeric status + body.
    HttpResponse { status: u16, body: String },
    /// WebSocket-style message (length-prefixed JSON in the demo transport).
    WsMessage { body: String },
}

impl Frame {
    /// Parse a byte buffer into the first HTTP request header + body.
    /// (A minimal std-only HTTP/1.1 decoder; keeps the wire dependency-free.)
    pub fn parse_http(buf: &[u8]) -> Result<Self, String> {
        let text = std::str::from_utf8(buf).map_err(|e| format!("utf8: {e}"))?;
        let mut lines = text.split("\r\n");
        let head = lines.next().ok_or("empty request")?;
        let mut parts = head.split_whitespace();
        let method = parts.next().ok_or("no method")?.to_uppercase();
        let path = parts.next().ok_or("no path")?.to_string();
        // find body after the blank line
        let body = text
            .split("\r\n\r\n")
            .nth(1)
            .unwrap_or("")
            .to_string();
        Ok(Frame::HttpRequest { method, path, body })
    }

    /// Render a Response frame as HTTP/1.1 bytes.
    pub fn to_http_bytes(&self) -> Vec<u8> {
        match self {
            Frame::HttpResponse { status, body } => {
                let reason = match *status {
                    200 => "OK",
                    400 => "Bad Request",
                    403 => "Forbidden",
                    404 => "Not Found",
                    500 => "Internal Server Error",
                    _ => "Unknown",
                };
                format!(
                    "HTTP/1.1 {status} {reason}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
                    body.len()
                )
                .into_bytes()
            }
            other => format!("{other:?}").into_bytes(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_http_request_round_trip() {
        let req = b"POST /v1/op HTTP/1.1\r\nHost: x\r\nContent-Length: 5\r\n\r\nhello";
        let frame = Frame::parse_http(req).unwrap();
        assert_eq!(
            frame,
            Frame::HttpRequest {
                method: "POST".into(),
                path: "/v1/op".into(),
                body: "hello".into(),
            }
        );
    }

    #[test]
    fn render_http_response() {
        let bytes = Frame::HttpResponse {
            status: 200,
            body: "{\"ok\":true}".into(),
        }
        .to_http_bytes();
        let s = String::from_utf8(bytes).unwrap();
        assert!(s.starts_with("HTTP/1.1 200 OK\r\n"));
        assert!(s.contains("Content-Length: 11"));
        assert!(s.ends_with("\r\n\r\n{\"ok\":true}"));
    }
}