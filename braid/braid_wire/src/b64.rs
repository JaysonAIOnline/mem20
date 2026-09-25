//! Minimal standard base64 (transport layer only).
//!
//! The wire-op responses carry binary WAV audio as base64 JSON strings, and
//! the shell `Sound` route decodes them back to raw `audio/wav` bytes. No
//! external dependency — 40 lines, standard alphabet, RFC 4648 padding.

const ALPHABET: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

/// Encode bytes to base64 (standard alphabet, padded).
pub fn encode(data: &[u8]) -> String {
    let mut out = String::with_capacity(data.len().div_ceil(3) * 4);
    for chunk in data.chunks(3) {
        let n = chunk.len();
        let b0 = chunk[0] as u32;
        let b1 = if n > 1 { chunk[1] as u32 } else { 0 };
        let b2 = if n > 2 { chunk[2] as u32 } else { 0 };
        let triple = (b0 << 16) | (b1 << 8) | b2;
        out.push(ALPHABET[((triple >> 18) & 63) as usize] as char);
        out.push(ALPHABET[((triple >> 12) & 63) as usize] as char);
        if n > 1 {
            out.push(ALPHABET[((triple >> 6) & 63) as usize] as char);
        } else {
            out.push('=');
        }
        if n > 2 {
            out.push(ALPHABET[(triple & 63) as usize] as char);
        } else {
            out.push('=');
        }
    }
    out
}

/// Decode a padded base64 string back to bytes.
pub fn decode(input: &str) -> Result<Vec<u8>, String> {
    fn val(c: u8) -> Option<u8> {
        match c {
            b'A'..=b'Z' => Some(c - b'A'),
            b'a'..=b'z' => Some(c - b'a' + 26),
            b'0'..=b'9' => Some(c - b'0' + 52),
            b'+' => Some(62),
            b'/' => Some(63),
            _ => None,
        }
    }
    let bytes = input.as_bytes();
    if !bytes.len().is_multiple_of(4) {
        return Err("invalid base64 length".into());
    }
    let mut out = Vec::with_capacity(bytes.len() / 4 * 3);
    let mut i = 0;
    while i < bytes.len() {
        let a = val(bytes[i]).ok_or("invalid char")?;
        let b = val(bytes[i + 1]).ok_or("invalid char")?;
        let c = if bytes[i + 2] == b'=' { 0 } else { val(bytes[i + 2]).ok_or("invalid char")? };
        let d = if bytes[i + 3] == b'=' { 0 } else { val(bytes[i + 3]).ok_or("invalid char")? };
        let combined = ((a as u32) << 18) | ((b as u32) << 12) | ((c as u32) << 6) | (d as u32);
        out.push((combined >> 16) as u8);
        if bytes[i + 2] != b'=' {
            out.push((combined >> 8) as u8);
        }
        if bytes[i + 3] != b'=' {
            out.push(combined as u8);
        }
        i += 4;
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn round_trip() {
        let cases = [b"".as_slice(), b"f".as_slice(), b"fo".as_slice(), b"foo".as_slice(), b"foob".as_slice(), b"fooba".as_slice(), b"foobar".as_slice(), &[0u8; 64]];
        for c in cases {
            let enc = encode(c);
            let dec = decode(&enc).expect("decode");
            assert_eq!(dec, c);
        }
    }

    #[test]
    fn known_vectors() {
        assert_eq!(encode(b"foobar"), "Zm9vYmFy");
        assert_eq!(decode("Zm9vYmFy").unwrap(), b"foobar");
        assert_eq!(encode(b"fo"), "Zm8=");
        assert_eq!(decode("Zm8=").unwrap(), b"fo");
        assert_eq!(encode(b"f"), "Zg==");
        assert_eq!(decode("Zg==").unwrap(), b"f");
    }
}