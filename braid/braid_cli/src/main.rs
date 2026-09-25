//! braid_cli binary — stateless terminal door for the ONE ledger.

use std::env;
use std::process;

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() < 2 {
        eprintln!(
            "braid_cli — terminal door: inspect | tail | query <cap> | policy | prove <cid> (--base url, --since cid, --limit n)"
        );
        process::exit(1);
    }

    let mut base = env::var("BRAID_BASE").unwrap_or_else(|_| braid_cli::DEFAULT_BASE.to_string());
    let mut since: Option<String> = None;
    let mut limit: Option<u64> = None;
    let mut positional: Vec<String> = Vec::new();

    let mut it = args.iter().skip(1);
    while let Some(a) = it.next() {
        match a.as_str() {
            "--base" => {
                if let Some(v) = it.next() {
                    base = v.clone();
                }
            }
            "--since" => {
                if let Some(v) = it.next() {
                    since = Some(v.clone());
                }
            }
            "--limit" => {
                if let Some(v) = it.next() {
                    limit = v.parse().ok();
                }
            }
            _ if a.starts_with("--base=") => base = a[7..].to_string(),
            _ if a.starts_with("--since=") => since = Some(a[8..].to_string()),
            _ if a.starts_with("--limit=") => limit = a[8..].parse().ok(),
            _ => positional.push(a.clone()),
        }
    }

    let res = match positional.first().map(String::as_str) {
        Some("inspect") => braid_cli::run_inspect(&base),
        Some("tail") => braid_cli::run_tail(&base, since.as_deref(), limit),
        Some("query") => positional
            .get(1)
            .map(String::as_str)
            .ok_or_else(|| "query needs a capability (e.g. query write:note:*)".to_string())
            .and_then(|c| braid_cli::run_query(&base, c)),
        Some("policy") => braid_cli::run_policy(&base),
        Some("prove") => positional
            .get(1)
            .map(String::as_str)
            .ok_or_else(|| "prove needs a cid".to_string())
            .and_then(|c| braid_cli::run_prove(&base, c)),
        Some(other) => Err(format!(
            "unknown subcommand `{other}` (inspect | tail | query <cap> | policy | prove <cid>)"
        )),
        None => Err(
            "braid_cli — terminal door: inspect | tail | query <cap> | policy | prove <cid> (--base url, --since cid, --limit n)".into(),
        ),
    };

    match res {
        Ok(env) => {
            println!("{}", serde_json::to_string_pretty(&env).unwrap());
        }
        Err(e) => {
            eprintln!("error: {e}");
            process::exit(1);
        }
    }
}