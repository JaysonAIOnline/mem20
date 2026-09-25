# Cloud Assembly — Best Practices for AI + Jayson

**Standing goal #2.** Plan for multi-cloud storage/compute so Jayson and heavy engines can run.

Your accounts (as stated): **OCI ×2 · Azure ×2 · AWS · Cloudflare · Tencent**

---

## 1. Critical truth: you cannot merge free tiers into one block disk

| Idea | Reality |
|------|---------|
| Glue OCI+Azure+AWS free disks into **one** EBS-like volume | **Impossible.** Block storage is local to a VM in one cloud/region |
| “Cluster” free object buckets into one filesystem | Only via **software overlay** (rclone, s3fs, LakeFS, custom index) — high latency, not suitable for Unreal editor DDC |
| Use Cloudflare as the Unreal drive | **No.** R2 is object storage; great for artifacts, not live engine installs |

**Rule for AI/game engines:**  
- **Hot path** (editor, compile, DerivedDataCache) = **one** paid/serious block volume next to **one** VM  
- **Cold path** (exports, backups, datasets, model weights) = object storage across clouds  

Free tiers are for **bootstrap and cold data**, not a live Unreal editor + DDC workspace.

---

## 2. Approximate free-tier storage inventory

*Verify in each console — offers change. Numbers are typical published ceilings, not a guarantee.*

| Cloud | Free-ish storage (ballpark) | Type | Unreal-capable? |
|-------|----------------------------|------|-----------------|
| **OCI ×2** | ~**200 GB block** per tenancy Always Free (home region); small object free tiers | Block + object | **Tight** — 200 GB can fit a **trimmed binary editor**, not a fat source build |
| **Azure ×2** | Trial **credits** + ~**2×64 GB** managed disks (12‑mo popular free style offers vary) | Block (with VM) | Small disks only |
| **AWS** | Often ~**30 GB EBS** class free-tier eligible (12 mo / credit programs vary post‑2025) + S3 free allowances | Block + object | Boot/dev only |
| **Cloudflare** | **R2 ~10 GB**/mo free storage + free egress | **Object only** | Artifacts/CDN only |
| **Tencent** | **COS/CBS/CVM/CDM/DNS** free tier (COS object, CBS block, CVM VMs) | Block + object + compute | **Distributed** — CBS/CVM for hot overflow, COS for cold, CDM/DNS via bridge |

### Rough “combined free” math (optimistic)
```
OCI block:     200 + 200 = 400 GB
Azure disks:   ~64–128 GB ×2 accounts (if offers apply) ≈ 128–256 GB
AWS EBS:       ~30 GB
Cloudflare R2: ~10 GB object
--------------------------------
Block-ish sum: ~560–700 GB scattered, NOT one filesystem
Object free:   tens of GB
```

**Still not one filesystem.** Combined free ≠ one mount. Cross-cloud I/O will be slow and fragile.

A **trimmed Unreal binary editor** (~40–70 GB installed, ~100–130 GB during install) *could* fit on **one OCI 200 GB** volume. A **source build** (~160–350 GB) or multi-version workstation will not. Plan **256–512 GB SSD** for a comfortable 4.0 slice; **~1 TB** only for source + multiple versions + DDC + fat projects.

---

## 2.1 Unreal disk size (measured, not folklore)

| Setup | Typical disk |
|-------|----------------|
| Binary editor, Windows-only, extra platforms **off** | **40–70 GB** installed |
| Default Epic Launcher install | **~100–130 GB** (download + extract overlap; editor ends smaller) |
| Several versions side by side | **150–250+ GB** |
| **Source build** of one version | **~160–350 GB** (Intermediate + `.git` dominate) |
| One project + DDC / Intermediate / Saved | Tens of GB, grows with content |
| Full workstation (2–3 versions + samples + DDC + projects) | Can approach **~1 TB** |

Epic does **not** publish “1 TB required.” The installer reports the size of **checked components**. Community guidance: a **256–512 GB SSD** for the editor.

---

## 3. Best practices for AI workloads on multi-cloud

1. **One home region for compute** — pick primary cloud for the GPU/CPU build box  
2. **Block disk same AZ as VM** — never “remote block” across clouds  
3. **Object for everything portable** — builds, datasets, LoRA weights, `release/installer/`  
4. **Immutable releases** — versioned buckets (`s3://…/releases/v1.2.3/`)  
5. **Secrets never in buckets as plaintext** — use each cloud’s secret manager  
6. **Egress awareness** — Cloudflare R2 wins for free egress; AWS/Azure/OCI charge egress  
7. **Snapshots before engine upgrades**  
8. **Separate “brain” from “muscle”** — Jayson control plane can stay small; heavy jobs on the build VM  

---

## 4. Recommended architecture (interwoven, not fake-one-disk)

```
                    ┌─────────────────────────┐
                    │  Jayson control plane     │
                    │  (Open WebUI + LiteLLM    │
                    │   + Resource Bridge)      │
                    └───────────┬───────────────┘
                                │ API
          ┌─────────────────────┼─────────────────────┐
          ▼                     ▼                     ▼
   ┌──────────────┐     ┌──────────────┐      ┌──────────────┐
   │ HOT block     │     │ COLD object   │      │ COLD object  │
   │ Primary cloud │     │ R2 / S3 /     │      │ OCI / Azure  │
   │ VM + 256–512GB │     │ Azure blob    │      │ secondary    │
   │ SSD (1TB later │     │ builds, packs │      │ backups      │
   │ if fat Unreal) │     │               │      │              │
   └──────────────┘     └──────────────┘      └──────────────┘
```

### Role assignment (suggested)

| Role | Provider | Why |
|------|----------|-----|
| **Primary compute + block** | AWS **or** Azure **or** OCI (pick one with best GPU/price for you) | **256–512 GB SSD** for Godot/Unity + one Unreal binary; 1 TB only if source/multi-version |
| **Public artifact distribution** | **Cloudflare R2** | Free egress, installers, patches |
| **Secondary backup** | Other OCI or Azure account | Cross-cloud disaster copy |
| **Jayson always-on** | Small VM or existing home lab + Docker | Control plane; doesn’t need a fat engine disk |

### Interweaving pattern
- Nightly: build VM → upload `builds/` + `release/` → R2  
- Weekly: snapshot block volume; copy critical project zips → second cloud object  
- Jayson Resource Bridge tracks **where** each dataset lives (see §6)

---

## 5. Provisioning plan (phases)

### Phase A — Inventory (this week)
- [ ] Log into each account; note **real** free quotas remaining  
- [ ] Pick **primary cloud** for the build VM  
- [ ] Estimate monthly $ for **256–512 GB SSD** (quote 1 TB only if you want source Unreal)  

### Phase B — Hot path (Godot/Unity now; Unreal at 4.0)
- [ ] Create VM in primary cloud (enough RAM/CPU; GPU later if needed)  
- [ ] Attach **256–512 GB** SSD block volume (1 TB optional later)  
- [ ] Mount e.g. `/mnt/engines`, `/mnt/projects`  
- [ ] Install Godot first (small); Unreal when disk ready  
- [ ] Snapshots on schedule  

### Phase C — Cold path (free tiers woven)
- [ ] Cloudflare R2 bucket: `jayson-releases`  
- [ ] AWS S3 or OCI object: `jayson-backups`  
- [ ] Azure blob on second account: `jayson-cold`  
- [ ] `rclone` remotes for each; documented in bridge config  

### Phase D — Jayson integration
- [ ] Deploy **Resource Bridge** (second bridge, §6)  
- [ ] Register backends (block path via SSH/agent, object via S3 API)  
- [ ] Production Run Stage 6 writes to `builds/` then bridge publishes to R2  

### Phase E — Hardening
- [ ] Budget alerts on all clouds  
- [ ] No public buckets without intentional policy  
- [ ] Test restore from secondary backup once  

---

## 6. Second bridge: Jayson Resource Bridge

LiteLLM = **model** bridge.  
Resource Bridge = **storage/compute** bridge so Jayson can address multi-cloud without pretending it’s one disk.

### Responsibilities
- Catalog backends: `hot-block`, `r2-releases`, `oci-backup`, …  
- List/upload/download artifacts by logical URI: `jayson://releases/mygame/1.0.0/`  
- Optional: trigger remote build scripts on the hot VM (SSH/CI webhook)  
- Quotas & health: free-tier headroom warnings  
- **Never** mount cross-cloud block as local for Unreal  

### Suggested API (OpenAI-tool style for Open WebUI)

| Tool | Purpose |
|------|---------|
| `storage_list(backend, prefix)` | List objects/paths |
| `storage_put(backend, key, source)` | Upload build/artifact |
| `storage_get(backend, key, dest)` | Download to workspace |
| `storage_publish_release(project, version)` | Copy from hot `release/` → R2 |
| `compute_status(host)` | Is build VM up? Disk free? |
| `compute_run(host, command)` | Optional guarded remote command |

### Implementation sketch (2.0 → 3.0 Resource Bridge; Unreal in 4.0)
1. Small FastAPI service next to LiteLLM in compose  
2. Config YAML of backends (S3-compatible endpoints + SSH host for hot)  
3. Open WebUI tool wrapping HTTP calls  
4. Later: auth tokens per backend  

Logical layout:
```
jayson://hot/projects/<game>/...
jayson://releases/<game>/<version>/...
jayson://backups/<game>/<date>/...
```

---

## 7. What free tiers *are* good for

- Storing **production packages**, manifests, small assets  
- **Release** zips/APKs on R2  
- Backup of `PRODUCTION_PACKAGE.md` + git mirrors  
- Not: live Unreal DerivedDataCache on object storage; not: merging disks across clouds  

---

## 8. Decision checklist

| Question | Answer |
|----------|--------|
| Can free tiers fund Unreal install? | **Maybe a trimmed binary on OCI 200 GB**; not a source/multi-version workstation |
| Best free multi-cloud use? | Object cold storage + R2 distribution; **OCI Always Free** for the chat UI |
| Path to Unreal? | Dedicated **256–512 GB SSD** on one primary cloud (1 TB if you go source-heavy) |
| Jayson role? | Control plane + Resource Bridge; jobs on hot VM |

---

## 9. Next actions when you say “provision”

1. Choose primary cloud (AWS / Azure / OCI)  
2. Size VM + **256–512 GB** disk quote (1 TB only if source Unreal)  
3. Stand up R2 release bucket  
4. Scaffold Resource Bridge service in 2.0 compose  
5. Wire Production Run Stage 6 → publish  

Until then: develop on **Godot/Unity** local or small cloud disks; keep Unreal on the **4.0** track after block storage exists.

---

## Account inventory (owner-confirmed)

| Provider | Keys / accounts | Notes |
|----------|-----------------|--------|
| **Azure** | **2** | Two separate credentials/subscriptions — usable for primary or secondary roles |
| **OCI** | **2** | Two tenancies/keys — Always Free block can stack *per tenancy* (still separate volumes) |
| AWS | 1 (as stated earlier) | |
| Cloudflare | 1 (as stated earlier) | R2 object / Workers |
| **Tencent** | **1** | TencentCloud MAAS + COS/CBS/CVM/CDM/DNS — hy4/hy3/GLM/DeepSeek/Kimi via `TENCENT_MAAS_API_KEY` |

Do not assume keys are interchangeable across the pair; treat each as its own quota and IAM boundary.
