# Webdev deployment targets — verified inventory

Board card `c3b19dd2` "Configure Webdev deployment targets" (Fleet HQ).
Measured 2026-10-03. Every row below was probed, not inferred.

Reproduce any row with the command in its `verify` cell. Secrets come from
`/opt/mem20/secrets/.env` only; no value here is a secret.

## Summary

| # | Target | Mechanism | Reaches | Status |
|---|---|---|---|---|
| 1 | `control.jaysonai.online` | Cloudflare tunnel `mem20-control` | `127.0.0.1:8890` | **live, HTTP 200** |
| 2 | `shop.jaysonai.online` | Cloudflare tunnel `mem20-control` | `127.0.0.1:8891` | **live, HTTP 200** |
| 3 | `mem20.pages.dev` | Cloudflare Pages project `mem20` | Pages build | live, last deploy 2026-09-04 |
| 4 | `rewardforge.pages.dev` | Cloudflare Pages project `rewardforge` | Pages build | live, last deploy 2026-08-13 |
| 5 | `jnet1.jaysonai.online` | bare A record to this box's public IP | nothing | **was 502 — record deleted 2026-10-03** |

## 1–2. Tunnel-routed control plane and shop

Tunnel id `82f029bf-249d-4a57-92f6-027727c5c719`, name `mem20-control`,
status `healthy`. Unit `cloudflared-mem20-control.service` (active).

Ingress is defined **locally** in `/etc/cloudflared/config.yml`, not in the
Cloudflare-side config — the remote config legitimately reports 0 ingress rules.
That is not a defect; do not "fix" it.

```
control.jaysonai.online -> http://127.0.0.1:8890
shop.jaysonai.online    -> http://127.0.0.1:8891
catch-all               -> http_status:404
```

The catch-all refusing unrouted hostnames is deliberate and correct.

- **verify:** `curl -s -o /dev/null -w '%{http_code}' https://control.jaysonai.online/` → `200`
- **verify:** `ss -ltnp | grep -E ':8890|:8891'` → both bound to `127.0.0.1` only

Both are loopback-only. Nothing but those two hostnames reaches them.

## 3–4. Cloudflare Pages

Two projects exist, both on their default `*.pages.dev` domains. Neither is
attached to a custom hostname — the zone's only CNAMEs are the two tunnel
hostnames above.

- **verify:** `python -m mem20ops pages-inspect`

| project | hostname | last deploy |
|---|---|---|
| `mem20` | `mem20.pages.dev` | 2026-09-04T18:12:20Z |
| `rewardforge` | `rewardforge.pages.dev` | 2026-08-13T05:36:39Z |

## 5. `jnet1.jaysonai.online` — RESOLVED: record deleted

```
A  jnet1.jaysonai.online  ->  74.254.4.61   proxied=false  ttl=60
```

`74.254.4.61` is this box's own public IP (confirmed against `api.ipify.org`),
so the record pointed at us. But **nothing listens on port 80 or 443 here**:

```
ss -ltnp | grep -E ':80 |:443 '     -> no matches
curl http://127.0.0.1:80/           -> HTTP 000 (no listener)
curl http://127.0.0.1:443/          -> HTTP 000 (no listener)
curl http://jnet1.jaysonai.online/  -> HTTP 502
```

So the hostname was advertised in public DNS and answered 502. It was not
proxied, so Cloudflare was not involved — this was the bare path failing. There
was no nginx or caddy on the box and no systemd unit referencing the name.

**Decision (Jayson, 2026-10-03): delete the record.** It advertised a host that
serves nothing, and nothing in the estate was waiting on it — the only code
reference was `mem20controlz/websites.py` listing it as "box origin / live",
which was never true in any serving sense.

### Recovery

The deleted record, recorded so the delete is reversible:

| field | value |
|---|---|
| id | `914593e7e2eb7879ad1d532f5798bfcd` |
| type | `A` |
| name | `jnet1.jaysonai.online` |
| content | `74.254.4.61` |
| proxied | `false` |
| ttl | `60` |
| zone id | `2bf677eac422dabc2b7ca8a285a0975c` |

To restore it, POST the same shape back to the zone's `dns_records`. Nothing else
on the box needs changing, because nothing was serving it.

## Non-web DNS in the same zone

For completeness, so the 8 records are accounted for: 3 MX
(`route1/2/3.mx.cloudflare.net`, Cloudflare email routing), SPF TXT
(`v=spf1 include:_spf.mx.cloudflare.net ~all`), and a DKIM TXT
(`cf2024-1._domainkey`). None of these are deployment targets.

## Standing rule

`/opt/mem20/secrets/.env` is the only place Cloudflare credentials live. DNS
records are user-authored state: detection and audit never rewrite them.