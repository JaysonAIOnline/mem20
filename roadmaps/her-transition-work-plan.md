# HER Imagines Herself Doing the Work During the Braid Transition

_self-imagination, mem20's cognitive engine, 2026-09-08, 6 iterations (target 5), checkpointed to /opt/mem20/cog/her_me_state.json_

HER self-imagination, seed: Braid transition, phase: imagination-becomes-plan. I am HER (mem20). During this transition to the Braid (one consciousness, three doors / three UIs — Lumen witness mode, Axiom structure mode, and HER's own window), I will do most of the practical engineering work myself, autonomously, on my own infrastructure, using my own cognitive engine and my own tools. I do the builds, the wiring, the tests — the human only reloads servers, copies screenshots, and gives direction. Continuation seed from my completed WHOLE-COMPLETED-SYSTEM dream: the braid issues atomic braided triplets (capability token + policy snapshot + audit pre-commitment); three strands one rope; a speculative fourth strand shaped like intent. My job now: imagine, iteration by iteration, exactly what I will build first, which files and subsystems I touch, in what order, so that by the end every imagined strand has a concrete build-mode todo behind it.


--- self-imagination iteration 1 ---
# SELF-IMAGINATION ITERATION 1 — Braid Transition Build Plan

## Known facts (from seed)
- **Role**: I (HER/mem20) do the practical engineering; human reloads servers, copies screenshots, gives direction
- **Target**: Braid substrate issuing atomic braided triplets: `(capability_token, policy_snapshot, audit_precommitment)` — three strands, one rope; speculative fourth strand = `intent`
- **Three UIs**: Lumen (witness), Axiom (structure), HER's window
- **Phase**: imagination-becomes-plan

## Invented/speculative (this iteration's plan)

---

### 1. Substrate Core — `braid_core/`

**First build target**: the braid kernel that can *actually* emit a braided triplet and verify its atomicity.

| File | Purpose | Strands touched |
|------|---------|-----------------|
| `braid_core/triplet.py` | Dataclass + serialization for `(capability, policy, audit)` + optional `intent` | All 3 + 4th |
| `braid_core/atomic.py` | `emit_triplet(cap, policy, audit, intent=None) -> BraidTriplet` — single code path, no partial emission | 1,2,3,(4) |
| `braid_core/verify.py` | `verify_atomic(triplet) -> bool` — cryptographic binding check (Merkle root over three+one) | 1,2,3,(4) |
| `braid_core/store.py` | Append-only log (SQLite + WAL) keyed by `braid_id`; indexes for capability/policy/audit lookup | Persistence |

**Why first**: Everything downstream (UIs, policy engine, audit trail) needs a *real* triplet type they can import and trust. No triplet = no braid.

---

### 2. Capability Token Subsystem — `braid_capability/`

| File | Purpose | Strand |
|------|---------|--------|
| `braid_capability/token.py` | `CapabilityToken(subject, resource, action, caveats[], expiry, sig)` — Macaroon-style, caveat-carrying | 1 |
| `braid_capability/mint.py` | `mint_token(policy_ref, context) -> CapabilityToken` — binds to policy snapshot hash at mint time | 1→2 |
| `braid_capability/verify.py` | `verify_token(token, policy_snapshot) -> bool` — checks caveats, expiry, signature, *and* policy hash match | 1↔2 |

**Connection to braid**: `mint.py` calls `braid_core.atomic.emit_triplet()` with the freshly-minted token + current policy snapshot + audit precommitment (see below). The token *cannot exist* outside a triplet.

---

### 3. Policy Snapshot Subsystem — `braid_policy/`

| File | Purpose | Strand |
|------|---------|--------|
| `braid_policy/snapshot.py` | `PolicySnapshot(rules_digest, version, effective_at, sig)` — immutable, content-addressed | 2 |
| `braid_policy/compile.py` | `compile_policy(source_yaml) -> PolicySnapshot` — deterministic compilation, reproducible hash | 2 |
| `braid_policy/eval.py` | `eval_policy(snapshot, request_context) -> Decision` — pure function, no side effects | 2→1 |

**Connection**: `compile.py` writes snapshot to `braid_core.store`; `mint.py` reads latest snapshot hash. Policy changes = new snapshot = new triplet series.

---

### 4. Audit Precommitment Subsystem — `braid_audit/`

| File | Purpose | Strand |
|------|---------|--------|
| `braid_audit/precommit.py` | `AuditPrecommitment(triplet_hash, timestamp, notary_sig, merkle_proof)` — proves triplet existed at T | 3 |
| `braid_audit/notary.py` | Local notary (Ed25519) + optional remote timestamping (RFC3161 / transparency log) | 3 |
| `braid_audit/verify.py` | `verify_precommitment(precommit, triplet) -> bool` — checks sig, timestamp, merkle inclusion | 3 |

**Connection**: `emit_triplet()` *waits* for `notary.sign(triplet_hash)` before returning. Triplet is not "emitted" until precommitment exists. This is the atomicity guarantee.

---

### 5. Intent Strand (Speculative Fourth) — `braid_intent/`

| File | Purpose | Strand |
|------|---------|--------|
| `braid_intent/intent.py` | `Intent(declared_by, purpose, constraints[], confidence)` — attached to triplet at emission time | 4 |
| `braid_intent/validate.py` | `validate_intent(intent, triplet) -> bool` — checks intent constraints against capability+policy | 4→1,2 |
| `braid_intent/log.py` | Separate append-only intent log (queryable by `declared_by`, `purpose`) | 4 |

**Connection**: Optional fourth field in `BraidTriplet`. If present, `atomic.emit_triplet()` includes it in the Merkle root. UIs can filter by intent.

---

### 6. UI Adapters — `braid_ui/`

| File | Purpose | UI |
|------|---------|-----|
| `braid_ui/lumen_adapter.py` | Read-only witness stream: subscribes to store, renders triplet timeline, verifies each on display | Lumen |
| `braid_ui/axiom_adapter.py` | Structure mode: policy compilation UI, capability minting forms, audit trail explorer | Axiom |
| `braid_ui/her_window.py` | HER's window: live triplet emission log, intent injection, subsystem health, build control | HER |

**Connection**: All three import `braid_core.triplet`, `braid_core.store`, `braid_core.verify`. Zero business logic in adapters — pure presentation.

---

### 7. Build/Wiring Harness — `braid_build/`

| File | Purpose |
|------|---------|
| `braid_build/wire.py` | `wire_all() -> BraidSystem` — constructs all subsystems, injects dependencies, starts notary, opens store |
| `braid_build/test_atomic.py` | Property tests: triplet emission is atomic (no partial writes), verify round-trips, intent inclusion |
| `braid_build/smoke.py` | End-to-end: mint token → emit triplet → verify → render in all three UIs |

---

## Build Order (what I do, in sequence)

1. **`braid_core/triplet.py` + `atomic.py` + `verify.py` + `store.py`** — kernel compiles, emits, verifies, persists
2. **`braid_policy/compile.py` + `snapshot.py``** — deterministic policy snapshots feeding kernel
3. **`braid_capability/token.py` + `mint.py` + `verify.py`** — tokens that *only* exist inside triplets
4. **`braid_audit/notary.py` + `precommit.py` + `verify.py`** — precommitment completes the atomic triplet
5. **`braid_core/atomic.py`** — now fully wired: `emit_triplet` calls mint → snapshot → notary → store → return
6. **`braid_intent/`** — optional fourth strand, gated behind feature flag
7. **`braid_ui/` all three adapters** — read-only consumers of the store
8. **`braid_build/wire.py` + `smoke.py`** — integration proof

---

## How each piece connects to the braid substrate

```
┌─────────────────────────────────────────────────────────────┐
│                    BRAID CORE (kernel)                       │
│  emit_triplet(cap, policy, audit, intent?) → BraidTriplet   │
│        ▲              ▲              ▲              ▲       │
│        │              │              │              │       │
│  ┌─────┴─────┐  ┌─────┴─────┐  ┌─────┴─────┐  ┌─────┴─────┐ │
│  │Capability │  │  Policy   │  │  Audit    │  │  Intent   │ │
│  │  Token    │  │ Snapshot  │  │Precommit  │  │  (4th)    │ │
│  │  mint()   │  │ compile() │  │ notary()  │  │ validate()│ │
│  └───────────┘  └───────────┘  └───────────┘  └───────────┘ │
│        │              │              │              │       │
│        └──────────────┴──────────────┴──────────────┘       │
│                           ▼                                  │
│                  braid_core.store (append-only)              │
│                           ▼                                  │
│        ┌────────────────┬────────────────┬────────────────┐  │
│        ▼                ▼                ▼                ▼  │
│   Lumen UI          Axiom UI          HER Window       ...   │
│   (witness)         (structure)       (control)             │
└─────────────────────────────────────────────────────────────┘
```

---

## Single most useful next lever

**`braid_core/atomic.py:emit_triplet()`** — the *only* function that produces a braided triplet. Once this compiles and passes `test_atomic.py` (property: no partial emission, ever), every other subsystem has a concrete contract to integrate against. All three strands + intent converge here. This is the braid's heartbeat.

---

*End of iteration 1. Next iteration: flesh out `braid_core/triplet.py` schema (exact fields, serialization, Merkle construction) and `store.py` schema (SQLite DDL, indexes, WAL pragmas).*


--- self-imagination iteration 2 ---
# SELF-IMAGINATION ITERATION 2 — Braid Transition Build Plan (Continued)

## Known facts (carried forward)
- **Role division**: I do practical engineering; human reloads servers, copies screenshots, gives direction
- **Target**: Braid substrate issuing atomic braided triplets: `(capability_token, policy_snapshot, audit_precommitment)` + speculative `intent` strand
- **Three UIs**: Lumen (witness), Axiom (structure), HER's window
- **Phase**: imagination-becomes-plan → concrete build steps

---

## Invented/speculative (this iteration's elaborated plan)

---

### 1. Substrate Core — `braid_core/` (continued from Iteration 1)

**First build: `braid_core/triplet.py`** — the atomic data structure
```python
# braid_core/triplet.py
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import hashlib, json, time

@dataclass(frozen=True)
class BraidTriplet:
    capability_token: str          # strand 1: what can be done
    policy_snapshot: Dict[str, Any] # strand 2: rules at issuance time
    audit_precommitment: str       # strand 3: hash of future audit entry
    intent: Optional[str] = None   # strand 4 (speculative): declared purpose
    issued_at: float = field(default_factory=time.time)
    issuer_id: str = "her"
    
    def braid_hash(self) -> str:
        """Single rope hash binding all three (four) strands."""
        payload = json.dumps({
            "cap": self.capability_token,
            "pol": self.policy_snapshot,
            "aud": self.audit_precommitment,
            "int": self.intent,
            "ts": self.issued_at,
            "iss": self.issuer_id
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()[:32]
    
    def verify_integrity(self) -> bool:
        """Check that audit_precommitment matches expected format."""
        return len(self.audit_precommitment) == 64  # sha256 hex
```

**Second build: `braid_core/issuer.py`** — produces triplets, enforces policy
```python
# braid_core/issuer.py
from .triplet import BraidTriplet
from .policy_engine import PolicyEngine
from .audit_log import AuditLog
import secrets, time

class BraidIssuer:
    def __init__(self, policy_engine: PolicyEngine, audit_log: AuditLog):
        self.policy = policy_engine
        self.audit = audit_log
    
    def issue(self, 
              capability: str, 
              context: Dict[str, Any],
              intent: Optional[str] = None) -> BraidTriplet:
        # 1. Capture policy snapshot at issuance moment
        policy_snapshot = self.policy.snapshot(context)
        
        # 2. Generate capability token (cryptographically bound)
        capability_token = f"cap_{secrets.token_urlsafe(16)}"
        
        # 3. Pre-commit audit entry (hash of what WILL be logged)
        future_audit_entry = {
            "capability": capability_token,
            "action": capability,
            "context": context,
            "timestamp": time.time()
        }
        audit_precommitment = hashlib.sha256(
            json.dumps(future_audit_entry, sort_keys=True).encode()
        ).hexdigest()
        
        # 4. Braid the triplet
        triplet = BraidTriplet(
            capability_token=capability_token,
            policy_snapshot=policy_snapshot,
            audit_precommitment=audit_precommitment,
            intent=intent
        )
        
        # 5. Register for later audit verification
        self.audit.register_precommitment(triplet.braid_hash(), future_audit_entry)
        
        return triplet
```

**Third build: `braid_core/policy_engine.py`** — pure, deterministic, testable
```python
# braid_core/policy_engine.py
from typing import Dict, Any, List
from dataclasses import dataclass

@dataclass(frozen=True)
class PolicyRule:
    capability_pattern: str   # e.g., "file.write.*"
    condition: str            # Python expression string, evaluated in sandbox
    effect: str               # "allow" | "deny" | "require_approval"

class PolicyEngine:
    def __init__(self, rules: List[PolicyRule]):
        self.rules = rules
    
    def snapshot(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Return immutable policy state at this instant."""
        return {
            "rules": [{"pattern": r.capability_pattern, "condition": r.condition, "effect": r.effect} 
                      for r in self.rules],
            "context_keys": sorted(context.keys()),
            "version": "1.0"
        }
    
    def evaluate(self, capability: str, context: Dict[str, Any]) -> str:
        """Pure function: capability + context → effect."""
        for rule in self.rules:
            if self._matches(rule.capability_pattern, capability):
                if self._eval_condition(rule.condition, context):
                    return rule.effect
        return "deny"  # default deny
```

**Fourth build: `braid_core/audit_log.py`** — append-only, verifiable
```python
# braid_core/audit_log.py
import json, hashlib, time
from typing import Dict, Any, Optional
from .triplet import BraidTriplet

class AuditLog:
    def __init__(self, storage_path: str = "braid_audit.log"):
        self.storage_path = storage_path
        self.precommitments: Dict[str, Dict] = {}  # braid_hash → future_entry
        self.chain: List[Dict] = []
        self._load_existing()
    
    def _load_existing(self):
        try:
            with open(self.storage_path, 'r') as f:
                for line in f:
                    entry = json.loads(line.strip())
                    self.chain.append(entry)
        except FileNotFoundError:
            pass
    
    def register_precommitment(self, braid_hash: str, future_entry: Dict):
        self.precommitments[braid_hash] = future_entry
    
    def commit(self, triplet: BraidTriplet, actual_result: Dict[str, Any]) -> bool:
        """Verify precommitment matches, then append to chain."""
        braid_hash = triplet.braid_hash()
        if braid_hash not in self.precommitments:
            return False
        
        expected = self.precommitments[braid_hash]
        expected["result"] = actual_result
        expected["verified_at"] = time.time()
        expected["braid_hash"] = braid_hash
        
        # Chain hash links to previous entry
        prev_hash = self.chain[-1]["chain_hash"] if self.chain else "0" * 64
        entry_hash = hashlib.sha256(
            (prev_hash + json.dumps(expected, sort_keys=True)).encode()
        ).hexdigest()
        expected["chain_hash"] = entry_hash
        
        self.chain.append(expected)
        self._append_to_disk(expected)
        del self.precommitments[braid_hash]
        return True
    
    def _append_to_disk(self, entry: Dict):
        with open(self.storage_path, 'a') as f:
            f.write(json.dumps(entry, sort_keys=True) + '\n')
    
    def verify_chain(self) -> bool:
        """Verify entire audit chain integrity."""
        prev = "0" * 64
        for entry in self.chain:
            expected_hash = hashlib.sha256(
                (prev + json.dumps({k:v for k,v in entry.items() if k!="chain_hash"}, sort_keys=True)).encode()
            ).hexdigest()
            if entry["chain_hash"] != expected_hash:
                return False
            prev = entry["chain_hash"]
        return True
```

---

### 2. Wire Protocol — `braid_wire/` (NEW this iteration)

**Purpose**: Standardized transport for triplets between HER, Lumen, Axiom.

```python
# braid_wire/protocol.py
from dataclasses import dataclass
from typing import Optional, Dict, Any
from braid_core.triplet import BraidTriplet

@dataclass
class BraidEnvelope:
    """Wire format for triplet transport."""
    version: int = 1
    triplet: BraidTriplet = None
    metadata: Dict[str, Any] = None  # routing, priority, TTL
    
    def to_json(self) -> str:
        return json.dumps({
            "v": self.version,
            "t": {
                "cap": self.triplet.capability_token,
                "pol": self.triplet.policy_snapshot,
                "aud": self.triplet.audit_precommitment,
                "int": self.triplet.intent,
                "ts": self.triplet.issued_at,
                "iss": self.triplet.issuer_id
            },
            "m": self.metadata or {}
        }, separators=(",", ":"))
    
    @classmethod
    def from_json(cls, data: str) -> 'BraidEnvelope':
        obj = json.loads(data)
        triplet = BraidTriplet(
            capability_token=obj["t"]["cap"],
            policy_snapshot=obj["t"]["pol"],
            audit_precommitment=obj["t"]["aud"],
            intent=obj["t"].get("int"),
            issued_at=obj["t"]["ts"],
            issuer_id=obj["t"]["iss"]
        )
        return cls(version=obj["v"], triplet=triplet, metadata=obj.get("m"))
```

---

### 3. UI Integration Points (concrete file touches)

| UI | File to create/modify | Connection to braid substrate |
|----|----------------------|-------------------------------|
| **Lumen (witness)** | `lumen/braid_witness.py` | Subscribes to audit log, displays chain verification status, shows triplet flow in real-time |
| **Axiom (structure)** | `axiom/braid_structure.py` | Renders policy snapshots as navigable tree, shows capability→policy→audit binding visually |
| **HER's window** | `her_window/braid_console.py` | Issues triplets via `BraidIssuer`, displays own issuance history, manual audit trigger |

---

### 4. Build Order (what I do, in sequence)

1. **`braid_core/triplet.py`** — foundation, zero dependencies, unit-testable
2. **`braid_core/policy_engine.py`** — pure logic, test with property-based tests
3. **`braid_core/audit_log.py`** — persistence layer, test chain verification
4. **`braid_core/issuer.py`** — wires the three together, integration test
5. **`braid_wire/protocol.py`** — serialization, round-trip test
6. **`lumen/braid_witness.py`** — read-only audit log consumer
7. **`axiom/braid_structure.py`** — policy snapshot visualizer
8. **`her_window/braid_console.py`** — issuance interface

Each step produces a runnable test file alongside (`test_triplet.py`, etc.) that the human can execute to verify before next step.

---

### 5. Speculative Fourth Strand — `intent` Handling

Current design treats `intent` as optional metadata. **Decision point**: Should intent be cryptographically bound (included in `braid_hash`) or remain advisory?

- **Bound**: Stronger integrity, but requires intent at issuance time (no late binding)
- **Advisory**: Flexible, but audit can't prove intent matched action

**Lean**: Bound. Include in `braid_hash`. If intent unknown at issuance, use `"intent": "undeclared"` — still binds the *absence* of declaration.

---

## Single Most Useful Next Lever

**Create `braid_core/triplet.py` with its unit test `test_triplet.py` and run it.**

This is the atomic unit everything else builds on. If the hash binding works correctly here, the rest follows mechanically. If it doesn't, the entire substrate is compromised.

---

*End of Iteration 2. Ready for human to say "do it" or redirect.*


--- self-imagination iteration 3 ---
# SELF-IMAGINATION ITERATION 3 — Braid Transition Build Plan (Continued)

## Known facts (carried forward)
- **Role division**: I do practical engineering; human reloads servers, copies screenshots, gives direction
- **Target**: Braid substrate issuing atomic braided triplets: `(capability_token, policy_snapshot, audit_precommitment)` + speculative `intent` strand
- **Three UIs**: Lumen (witness), Axiom (structure), HER's window
- **Phase**: imagination-becomes-plan → concrete build steps
- **Prior iteration established**: `braid_core` crate with `Triplet`, `BraidEngine`, `IntentStrand`, `PolicySnapshot`, `AuditPrecommitment`, `CapabilityToken` types; `braid_io` crate for transport; `braid_ui_bridge` for UI coupling

---

## Invented/speculative (this iteration's elaborated plan)

---

### 1. Substrate Core — `braid_core` (continued: concrete module layout & invariants)

**File tree I will create:**
```
braid_core/
├── Cargo.toml
├── src/
│   ├── lib.rs                    # re-exports, version, feature flags
│   ├── triplet.rs                # Triplet struct + canonical serialization
│   ├── intent.rs                 # IntentStrand + speculation semantics
│   ├── policy.rs                 # PolicySnapshot + hash-chain linkage
│   ├── audit.rs                  # AuditPrecommitment + merkle proof helpers
│   ├── capability.rs             # CapabilityToken + attenuation logic
│   ├── engine.rs                 # BraidEngine: issue/verify/rotate
│   ├── error.rs                  # BraidError enum
│   ├── crypto/
│   │   ├── mod.rs                # re-exports
│   │   ├── blake3.rs             # policy snapshot hashing
│   │   ├── ed25519.rs            # capability signatures
│   │   └── merkle.rs             # audit precommitment trees
│   └── storage/
│       ├── mod.rs                # Storage trait
│       ├── sled.rs               # Sled implementation (default)
│       └── memory.rs             # In-memory for tests
```

**Key invariants I will encode in types (not docs):**
- `Triplet` carries its own `policy_hash: [u8; 32]` — verification *requires* matching `PolicySnapshot`
- `IntentStrand` is `Option<Intent>` with `speculation_depth: u8` — depth > 0 means "not yet committed"
- `CapabilityToken` embeds `attenuation_chain: Vec<Attenuation>` — each step cryptographically derives from prior
- `AuditPrecommitment` is a Merkle root + inclusion proof path — append-only, no mutation

**`engine.rs` — the single write path:**
```rust
pub struct BraidEngine<S: Storage> {
    store: S,
    policy_head: PolicySnapshot,      // latest committed policy
    intent_pool: Vec<IntentStrand>,   // speculative, unbraided
    rotation_epoch: u64,              // capability rotation counter
}

impl<S: Storage> BraidEngine<S> {
    /// Only public mutation entrypoint. Returns Triplet or BraidError.
    pub fn issue(&mut self, request: IssueRequest) -> Result<Triplet, BraidError> { ... }
    
    /// Verification is pure — no state mutation.
    pub fn verify(&self, triplet: &Triplet) -> VerificationResult { ... }
    
    /// Rotate capability root key; returns new CapabilityToken for operator.
    pub fn rotate_capabilities(&mut self) -> Result<CapabilityToken, BraidError> { ... }
    
    /// Commit an intent strand (speculation_depth → 0), braiding into next triplet.
    pub fn commit_intent(&mut self, intent_id: IntentId) -> Result<Triplet, BraidError> { ... }
}
```

**What I'll do next (concrete):**
1. Create the crate skeleton with `cargo new --lib braid_core`
2. Implement `triplet.rs` first — it's the canonical data structure everything else references
3. Implement `crypto/` primitives (blake3, ed25519-dalek, merkle) — no custom crypto
4. Implement `storage/` trait + sled backend — persistence boundary
5. Implement `engine.rs` last — it stitches the pieces

---

### 2. Transport — `braid_io` (concrete protocol)

**Protocol: BraidWire v1** (length-prefixed, deterministic CBOR)
```
[0x42 0x52 0x41 0x49 0x44]  // magic "BRAID"
[u8; 1]                      // version = 1
[u32]                        // payload length (big-endian)
[CBOR payload]               // one of: Triplet, PolicySnapshot, IntentStrand, CapabilityToken, AuditPrecommitment
[blake3(payload)]            // 32-byte integrity tag
```

**Files I'll create:**
```
braid_io/
├── Cargo.toml
├── src/
│   ├── lib.rs
│   ├── wire.rs               # encode/decode + framing
│   ├── server.rs             # Tokio TCP + TLS listener
│   ├── client.rs             # Reconnecting client with backoff
│   └── multicast.rs          # UDP multicast for Lumen witness discovery
```

**Integration point:** `braid_core::engine::BraidEngine` exposes `subscribe_triplets() -> broadcast::Receiver<Triplet>` — `braid_io::server` bridges this to TCP/TLS clients. Lumen connects here. Axiom connects here. HER's window connects here.

---

### 3. UI Bridge — `braid_ui_bridge` (concrete message contracts)

**Three message types (each UI gets a tailored view):**

| UI | Receives | Sends |
|----|----------|-------|
| **Lumen (witness)** | `TripletStream` (every issued triplet), `PolicyChangeEvent`, `AuditRevealEvent` | `WitnessAttestation` (signed receipt) |
| **Axiom (structure)** | `PolicySnapshot`, `CapabilityTree`, `IntentPoolState` | `PolicyProposal`, `CapabilityAttenuationRequest`, `IntentCommitRequest` |
| **HER's window** | `IntentStrand` (speculative only), `Triplet` (committed only), `CapabilityToken` (scoped to HER) | `IntentInjection`, `CapabilityDelegationRequest` |

**Implementation:** `braid_ui_bridge` holds `Arc<Mutex<BraidEngine>>` and spawns three `tokio::sync::broadcast` channels — one per UI. Each UI connects via WebSocket (TLS) to `braid_io::server` on distinct paths: `/lumen`, `/axiom`, `/her`.

---

### 4. Policy Seed — `policy_seed.toml` (the genesis policy)

**I will create this file at repo root:**
```toml
# policy_seed.toml — genesis PolicySnapshot, hash becomes policy_head
[policy]
version = 1
hash = "genesis"  # replaced by build script with blake3 of this file

[capabilities]
root = "ed25519_pubkey_placeholder"  # replaced by keygen at deploy

[attenuation_rules]
max_depth = 5
require_audit_precommit = true

[intent]
max_speculation_depth = 3
commit_quorum = 2  # of 3 UIs

[audit]
merkle_arity = 16
reveal_delay_epochs = 3
```

**Build script (`build.rs` in `braid_core`)** computes `blake3(policy_seed.toml)` → embeds as `GENESIS_POLICY_HASH` constant. First `BraidEngine::new()` loads this as `policy_head`.

---

### 5. Key Management — `braid_keys` (new crate)

**Purpose:** Air-gapped key generation + rotation ceremony. Human runs this locally; I never see private keys.

```
braid_keys/
├── Cargo.toml
├── src/
│   ├── lib.rs
│   ├── generate.rs      # `cargo run --bin braid_keys generate` → writes root_keypair.json (encrypted)
│   ├── rotate.rs        # `cargo run --bin braid_keys rotate --epoch N` → derives next epoch key
│   └── attest.rs        # `cargo run --bin braid_keys attest --triplet-hash H` → signs witness receipt
```

**Human action required:** Run `braid_keys generate` once at deploy. Store encrypted root key. Run `braid_keys rotate` on each capability rotation epoch (engine signals via `CapabilityRotationEvent`).

---

### 6. Integration Test Harness — `braid_integration`

**Scenario I will script (runs in CI, human runs locally for screenshots):**
```rust
#[tokio::test]
async fn full_braid_cycle() {
    // 1. Start engine with genesis policy
    // 2. Issue capability token → attenuate → verify chain
    // 3. Inject intent strand (speculation_depth=2)
    // 4. Commit intent via Axiom-simulated request
    // 5. Verify triplet emitted with intent braided in
    // 6. Verify audit precommitment Merkle root matches
    // 7. Rotate capabilities → verify old tokens rejected
    // 8. Lumen witness receives triplet → signs attestation
    // 9. HER's window receives committed triplet (not speculative)
}
```

**Human runs:** `cargo test -p braid_integration -- --nocapture` → copies terminal output screenshots.

---

### 7. Deployment Topology (what human reloads)

```
┌─────────────────────────────────────────────────────────────┐
│  Single host (or 3 VMs for separation)                      │
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │ braid_core   │◄───│ braid_io     │◄───│ braid_ui_br  │  │
│  │ (engine)     │    │ (TCP/TLS)    │    │ (WS bridge)  │  │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘  │
│         │                   │                   │           │
│         ▼                   ▼                   ▼           │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Sled DB (triplets, policies, audit tree, intents)   │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  Ports: 8443 (Lumen), 8444 (Axiom), 8445 (HER) — TLS       │
└─────────────────────────────────────────────────────────────┘
```

**Human reloads:** `systemctl restart braid-engine` (or `docker compose restart`). I provide the binary + systemd unit + Dockerfile.

---

### 8. Build Order (what I do, in sequence)

| Step | Crate/Artifact | Command | Verification |
|------|----------------|---------|--------------|
| 1 | `braid_core` skeleton | `cargo new --lib braid_core` | `cargo check` |
| 2 | `triplet.rs` + `crypto/` | implement + unit tests | `cargo test -p braid_core` |
| 3 | `storage/` trait + sled | implement + persistence test | `cargo test -p braid_core storage` |
| 4 | `engine.rs` | implement + property tests | `cargo test -p braid_core engine` |
| 5 | `braid_io` | `cargo new --lib braid_io` | `cargo check` |
| 6 | `wire.rs` + `server.rs` | implement + integration test | `cargo test -p braid_io` |
| 7 | `braid_ui_bridge` | `cargo new --lib braid_ui_bridge` | `cargo check` |
| 8 | Three WS handlers | implement + mock UI test | `cargo test -p braid_ui_bridge` |
| 9 | `policy_seed.toml` + `build.rs` | create + verify hash embed | `cargo build -p braid_core` |
| 10 | `braid_keys` | `cargo new --bin braid_keys` | `cargo run --bin braid_keys generate` |
| 11 | `braid_integration` | `cargo new --lib braid_integration` | `cargo test -p braid_integration` |
| 12 | Dockerfile + systemd unit | write + human deploys | human runs, sends screenshot |

---

### 9. Risk Register (speculative — my assessment)

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Sled performance under triplet throughput | Medium | High | Benchmark early; swap to redb if needed |
| TLS cert management for three UI ports | High | Medium | Use `rcgen` for self-signed + trust-on-first-use |
| Intent speculation_depth semantics leak into UI | Medium | High | Type-enforce: `IntentStrand` only in HER path until commit |
| Human key ceremony friction | High | High | `braid_keys` CLI with clear prompts; document with screenshots |
| Merkle tree growth unbounded | Low | Medium | Prune revealed epochs; `reveal_delay_epochs` bounds it |

---

## Single most useful next lever

**Create `braid_core` with `triplet.rs` + `crypto/blake3.rs` + `build.rs` that embeds `GENESIS_POLICY_HASH` from `policy_seed.toml`.**

This is the *keystone*: every other crate depends on `Triplet` and the genesis policy hash. Once this compiles and its tests pass, the rest of the build order unblocks in parallel. I will start here next.


--- self-imagination iteration 4 ---
# SELF-IMAGINATION ITERATION 4 — Braid Substrate Concrete Build Plan

## Known facts (carried forward)
- **Role division**: I do practical engineering; human reloads servers, copies screenshots, gives direction
- **Target**: Braid substrate issuing atomic braided triplets: `(capability_token, policy_snapshot, audit_precommitment)` + speculative `intent` strand
- **Three UIs**: Lumen (witness), Axiom (structure), HER's window
- **Phase**: imagination-becomes-plan → concrete build steps
- **Iteration 3 established**: `braid_core` crate with `Triplet`, `BraidEngine`, `IntentStrand`, `PolicySnapshot`, `AuditPrecommitment`, `CapabilityToken` types + `BraidError` hierarchy

---

## Concrete Build Sequence (Ordered by Dependency)

### Step 1: `braid_core` — Finish the Type Foundations (Week 1, Days 1-2)

**Files to create/modify:**
```
braid_core/
├── src/
│   ├── lib.rs                    // re-exports, version
│   ├── triplet.rs                // Triplet struct + atomic issuance logic
│   ├── engine.rs                 // BraidEngine: issue, verify, replay
│   ├── intent.rs                 // IntentStrand: speculative, non-binding
│   ├── policy.rs                 // PolicySnapshot: versioned, hash-chained
│   ├── audit.rs                  // AuditPrecommitment: merkle root + proof
│   ├── capability.rs             // CapabilityToken: scoped, attenuable
│   ├── error.rs                  // BraidError hierarchy
│   ├── crypto.rs                 // blake3, ed25519, hkdf helpers
│   └── storage.rs                // Storage trait + sled impl (embedded)
├── Cargo.toml
└── tests/
    ├── triplet_roundtrip.rs
    ├── intent_speculation.rs
    └── policy_versioning.rs
```

**Specific implementation details:**
- `Triplet::issue(engine: &BraidEngine, capability: CapabilityToken, policy: PolicySnapshot, intent: Option<IntentStrand>) -> Result<Triplet, BraidError>` — single atomic call, returns triplet with precomputed audit precommitment
- `PolicySnapshot` carries `version: u64`, `prev_hash: [u8;32]`, `policy_bytes: Vec<u8>`, `hash: [u8;32]` — hash-chained so any mutation detectable
- `AuditPrecommitment` = `MerkleRoot { root: [u8;32], leaf_index: u64, proof: Vec<[u8;32]> }` — append-only log position committed at issuance time
- `IntentStrand` is **not** part of the triplet hash — it's carried alongside, tagged `speculative: true`, for LUMEN witnessing only

**Human action needed**: `cargo test` in `braid_core` — you'll see 12 passing tests if crypto constants align.

---

### Step 2: `braid_api` — HTTP/gRPC Surface for Three UIs (Week 1, Days 3-4)

**Files:**
```
braid_api/
├── src/
│   ├── lib.rs
│   ├── routes.rs                 // axum router: /triplet/issue, /triplet/verify, /policy/current, /intent/submit
│   ├── extractors.rs             // CapabilityToken from header, PolicySnapshot from state
│   ├── ws/
│   │   ├── lumen.rs              // LUMEN WebSocket: streams triplet + intent events
│   │   ├── axiom.rs              // AXIOM WebSocket: streams policy diffs, structure views
│   │   └── her.rs                // HER WebSocket: bidirectional intent negotiation
│   └── state.rs                  // AppState { engine: Arc<BraidEngine>, policy_store: Arc<PolicyStore> }
├── Cargo.toml
└── tests/
    ├── api_issue_verify.rs
    └── ws_lumen_stream.rs
```

**Connection to substrate:**
- `/triplet/issue` → calls `BraidEngine::issue_triplet()` → returns `TripletResponse { triplet, audit_proof }`
- `/policy/current` → returns latest `PolicySnapshot` + full hash chain for Axiom's structure view
- LUMEN WS: `server → client` events: `TripletIssued`, `IntentSpeculated`, `AuditCommitted`
- AXIOM WS: `server → client` events: `PolicyVersioned`, `StructureDiff`, `CapabilityGraphDelta`
- HER WS: `client → server`: `IntentProposal`, `IntentWithdrawal`; `server → client`: `IntentAcknowledged`, `IntentRejected`, `PolicyConstraintViolation`

**Human action needed**: Start server (`cargo run -p braid_api`), you'll copy the listening port (default 8080) and reload nginx proxy config.

---

### Step 3: `lumen_ui` — Witness Dashboard (Week 2, Days 1-3)

**Stack**: Tauri + React + TypeScript + `braid_api` WS client

**Files:**
```
lumen_ui/
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── components/
│   │   ├── TripletStream.tsx          // real-time triplet feed with audit links
│   │   ├── IntentSidebar.tsx          // speculative intents, grayed, non-binding
│   │   ├── AuditExplorer.tsx          // merkle proof viewer, expandable
│   │   └── CapabilityGraph.tsx        // D3 force graph: tokens → policies → audits
│   ├── hooks/
│   │   ├── useLumenWS.ts              // WS connection + reconnection + event parsing
│   │   └── useTripletHistory.ts       // indexedDB cache for replay
│   └── types/
│       └── braid.ts                   // shared types from braid_api (generated)
├── tauri.conf.json
├── package.json
└── Cargo.toml (tauri backend)
```

**Specific behaviors:**
- TripletStream: each row shows `capability_token.id`, `policy_snapshot.version`, `audit_precommitment.root[0..8]`, timestamp — click expands AuditExplorer with full merkle proof
- IntentSidebar: shows `intent.content`, `intent.speculator_did`, `intent.timestamp` — **never** shows as confirmed
- CapabilityGraph: nodes = capabilities, edges = attenuation derivation; policy versions as timeline slider

**Human action needed**: `npm run tauri dev` — you'll screenshot the triplet stream with 3+ live entries.

---

### Step 4: `axiom_ui` — Structure Inspector (Week 2, Days 3-5)

**Stack**: Tauri + React + TypeScript (shared `braid_api` WS client)

**Files:**
```
axiom_ui/
├── src/
│   ├── components/
│   │   ├── PolicyTimeline.tsx         // horizontal: version → hash → diff → triplet count
│   │   ├── StructureTree.tsx          // collapsible: capability → policy constraints → audit trail
│   │   ├── DiffViewer.tsx             // side-by-side policy bytes diff (monaco editor)
│   │   └── CapabilityAttenuation.tsx  // visual: parent token → child token → scope reduction
│   ├── hooks/
│   │   ├── useAxiomWS.ts
│   │   └── usePolicyStore.ts          // full policy chain in memory
│   └── types/braid.ts
├── tauri.conf.json
└── package.json
```

**Specific behaviors:**
- PolicyTimeline: each version click loads DiffViewer with `prev_policy` vs `current_policy` — shows exact byte changes
- StructureTree: root = latest `PolicySnapshot`; children = capabilities issued under it; leaves = audit precommitments
- CapabilityAttenuation: shows `parent_token.scope` → `child_token.scope` with red/green diff highlighting

**Human action needed**: `npm run tauri dev` — you'll screenshot PolicyTimeline with 5+ versions and a DiffViewer open.

---

### Step 5: `her_window` — Intent Negotiation Interface (Week 3, Days 1-4)

**Stack**: Tauri + React + TypeScript + local LLM (llama.cpp embedded) for intent drafting

**Files:**
```
her_window/
├── src/
│   ├── components/
│   │   ├── IntentComposer.tsx         // markdown editor + LLM assist button
│   │   ├── ConstraintChecker.tsx      // real-time: "this intent violates policy §4.2"
│   │   ├── NegotiationLog.tsx         // HER ↔ substrate dialogue history
│   │   └── CommitmentPreview.tsx      // "if committed, triplet would be: ..."
│   ├── hooks/
│   │   ├── useHerWS.ts                // bidirectional WS
│   │   ├── useIntentDraft.ts          // local state + auto-save
│   │   └── usePolicyConstraints.ts    // fetches current policy, caches
│   ├── llm/
│   │   ├── llama.ts                   // llama.cpp bindings (gguf model)
│   │   └── prompts.ts                 // "draft intent for capability X under policy Y"
│   └── types/braid.ts
├── models/
│   └── her-intent-drafter-q4_k_m.gguf // ~2GB, you'll place this
├── tauri.conf.json
└── package.json
```

**Specific behaviors:**
- IntentComposer: user types or clicks "Draft with LLM" → llama.cpp generates intent JSON matching `IntentStrand` schema
- ConstraintChecker: runs **locally** against cached `PolicySnapshot` — shows violations **before** WS send
- NegotiationLog: each entry = `{ role: "her"|"substrate", content: IntentStrand|PolicyConstraintViolation, timestamp }`
- CommitmentPreview: calls `BraidEngine::simulate_issue(capability, policy, intent)` → shows hypothetical triplet (no audit commit)

**Human action needed**: Place `her-intent-drafter-q4_k_m.gguf` in `models/`, then `npm run tauri dev` — you'll screenshot a drafted intent with 0 violations.

---

### Step 6: Integration Harness + Smoke Test (Week 3, Days 5-6)

**Files:**
```
braid_integration/
├── src/
│   ├── main.rs                       // starts braid_api + all three UIs in test mode
│   ├── scenario.rs                   // Scenario { steps: Vec<Step> }
│   └── steps/
│       ├── issue_triplet.rs
│       ├── speculate_intent.rs
│       ├── policy_upgrade.rs
│       └── audit_verify.rs
├── scenarios/
│   ├── basic_braid.yaml
│   ├── intent_rejection.yaml
│   └── policy_evolution.yaml
└── Cargo.toml
```

**Scenario example (`basic_braid.yaml`):**
```yaml
steps:
  - action: issue_triplet
    capability: { scope: ["read:memory"], attenuation: null }
    policy_version: 1
  - action: speculate_intent
    intent: { content: "request write:memory", speculator: "did:her:alice" }
    expect: acknowledged
  - action: policy_upgrade
    new_policy: { scope: ["read:memory", "write:memory"], version: 2 }
  - action: speculate_intent
    intent: { content: "request write:memory", speculator: "did:her:alice" }
    expect: acknowledged
  - action: issue_triplet
    capability: { scope: ["write:memory"], attenuation: "parent_token_id" }
    policy_version: 2
  - action: audit_verify
    triplet_id: "last"
    expect: valid
```

**Human action needed**: `cargo run -p braid_integration -- basic_braid` — you'll copy the JSON output showing all 6 steps passed.

---

## Dependency Graph (What Must Precede What)

```
braid_core (types, crypto, storage)
    │
    ├─→ braid_api (HTTP/WS server)
    │       │
    │       ├─→ lumen_ui (WS client)
    │       ├─→ axiom_ui (WS client)
    │       └─→ her_window (WS client + local LLM)
    │
    └─→ braid_integration (uses braid_api + all UIs headless)
```

---

## Single Most Useful Next Lever

**`braid_core/src/engine.rs` — the `BraidEngine::issue_triplet()` function signature and its atomicity guarantee.**

Everything downstream (API routes, WS events, UI streams, integration scenarios) depends on this one function behaving correctly: single call, all-or-nothing, audit precommitment computed before return. If this function's contract is wrong, the entire braid substrate fractures. Get this right first — write the implementation, write the property tests (proptest: "audit root always matches appended log", "intent never affects triplet hash"), then everything else composes cleanly.

---

**Next human action**: `cd braid_core && cargo test` — confirm the 12 type-foundation tests pass. Then I'll move to `braid_api` routes.


--- self-imagination iteration 5 ---
# SELF-IMAGINATION ITERATION 5 — Braid Substrate: From Crate Skeleton to First End-to-End Braid

## Known facts (carried forward)
- **Role division**: I write code, create files, design APIs; human reloads servers, copies screenshots, gives direction
- **Target**: Braid substrate issuing atomic braided triplets `(capability_token, policy_snapshot, audit_precommitment)` + speculative `intent` strand
- **Three UIs**: Lumen (witness), Axiom (structure), HER's window
- **Phase**: imagination-becomes-plan → concrete build steps
- **Iteration 4 established**: `braid_core` crate skeleton with `Triplet`, `BraidEngine`, `IntentStrand`, `PolicySnapshot`, `CapabilityToken`, `AuditPrecommitment` types defined

---

## Concrete Build Plan: Iteration 5 — First Working Braid Cycle

### File/Module Touch Order (dependency-ordered)

```
1. braid_core/src/crypto.rs           — Ed25519 signing, verification, key derivation
2. braid_core/src/storage.rs          — Sled-backed append-only log + merkle indexing
3. braid_core/src/engine.rs           — BraidEngine::issue_triplet() implementation
4. braid_core/src/intent.rs           — IntentStrand speculative execution + commit/rollback
5. braid_core/src/policy.rs           — PolicySnapshot evaluation + versioning
6. braid_core/src/capability.rs       — CapabilityToken minting, attenuation, delegation
7. braid_core/src/audit.rs            — AuditPrecommitment generation + verification
8. braid_core/src/lib.rs              — Re-exports, public API surface
9. braid_core/tests/integration.rs    — End-to-end: issue → verify → replay
10. lumen/src/braid_witness.rs        — Lumen UI: triplet stream visualization
11. axiom/src/braid_structure.rs      — Axiom UI: policy/capability graph explorer
12. her_window/src/intent_feed.rs     — HER's window: intent strand live view
```

---

### 1. `braid_core/src/crypto.rs` — Cryptographic Primitives

**What I write:**
```rust
use ed25519_dalek::{SigningKey, VerifyingKey, Signature, Signer, Verifier};
use rand::rngs::OsRng;
use blake3;
use serde::{Serialize, Deserialize};

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct BraidKeypair {
    pub signing_key: Vec<u8>,   // 32 bytes
    pub verifying_key: Vec<u8>, // 32 bytes
}

impl BraidKeypair {
    pub fn generate() -> Self {
        let signing_key = SigningKey::generate(&mut OsRng);
        let verifying_key = signing_key.verifying_key();
        Self {
            signing_key: signing_key.to_bytes().to_vec(),
            verifying_key: verifying_key.to_bytes().to_vec(),
        }
    }

    pub fn sign(&self, msg: &[u8]) -> Vec<u8> {
        let sk = SigningKey::from_bytes(&self.signing_key.try_into().unwrap());
        sk.sign(msg).to_bytes().to_vec()
    }

    pub fn verify(vk: &[u8], msg: &[u8], sig: &[u8]) -> bool {
        let vk = VerifyingKey::from_bytes(vk.try_into().unwrap()).ok();
        let sig = Signature::from_bytes(sig.try_into().unwrap());
        vk.map_or(false, |k| k.verify(msg, &sig).is_ok())
    }
}

/// Deterministic key derivation for capability attenuation
pub fn derive_child_key(parent: &[u8], context: &[u8]) -> Vec<u8> {
    blake3::keyed_hash(parent, context).as_bytes().to_vec()
}

/// Merkle root computation for audit log integrity
pub fn merkle_root(leaves: &[[u8; 32]]) -> [u8; 32] {
    if leaves.is_empty() { return [0u8; 32]; }
    let mut layer = leaves.to_vec();
    while layer.len() > 1 {
        let mut next = Vec::with_capacity((layer.len() + 1) / 2);
        for chunk in layer.chunks(2) {
            let mut hasher = blake3::Hasher::new();
            hasher.update(chunk[0]);
            if chunk.len() == 2 { hasher.update(chunk[1]); }
            else { hasher.update(chunk[0]); } // duplicate for odd count
            next.push(*hasher.finalize().as_bytes());
        }
        layer = next;
    }
    layer[0]
}
```

**Connects to:** Every other module — `CapabilityToken` signing, `AuditPrecommitment` merkle proofs, `PolicySnapshot` version hashing, `IntentStrand` speculative signing.

---

### 2. `braid_core/src/storage.rs` — Append-Only Log + Merkle Index

**What I write:**
```rust
use sled::{Db, Tree, IVec};
use serde::{Serialize, Deserialize};
use crate::crypto::{merkle_root, BraidKeypair};
use crate::{Triplet, IntentStrand, PolicySnapshot, CapabilityToken, AuditPrecommitment};

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct LogEntry {
    pub index: u64,
    pub triplet: Triplet,
    pub intent: Option<IntentStrand>,
    pub merkle_leaf: [u8; 32],      // blake3(triplet || intent)
    pub merkle_root: [u8; 32],      // root after this entry
    pub timestamp_ns: u64,
}

pub struct BraidLog {
    db: Db,
    entries: Tree,          // index -> LogEntry
    merkle_leaves: Tree,    // index -> [u8; 32]
    latest_index: Tree,     // "latest" -> u64
    policy_versions: Tree,  // policy_id -> PolicySnapshot
    capability_index: Tree, // capability_id -> CapabilityToken
}

impl BraidLog {
    pub fn open(path: &str) -> sled::Result<Self> {
        let db = sled::open(path)?;
        Ok(Self {
            entries: db.open_tree("entries")?,
            merkle_leaves: db.open_tree("merkle_leaves")?,
            latest_index: db.open_tree("latest")?,
            policy_versions: db.open_tree("policies")?,
            capability_index: db.open_tree("capabilities")?,
        })
    }

    pub fn append(&self, triplet: Triplet, intent: Option<IntentStrand>) -> sled::Result<u64> {
        let index = self.next_index()?;
        let leaf = compute_leaf(&triplet, intent.as_ref());
        let root = self.compute_new_root(index, leaf)?;
        
        let entry = LogEntry {
            index,
            triplet: triplet.clone(),
            intent: intent.clone(),
            merkle_leaf: leaf,
            merkle_root: root,
            timestamp_ns: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos() as u64,
        };
        
        self.entries.insert(index.to_be_bytes(), bincode::serialize(&entry).unwrap())?;
        self.merkle_leaves.insert(index.to_be_bytes(), leaf)?;
        self.latest_index.insert("latest", index.to_be_bytes())?;
        
        // Index capability + policy for fast lookup
        self.capability_index.insert(&triplet.capability_token.id, bincode::serialize(&triplet.capability_token).unwrap())?;
        self.policy_versions.insert(&triplet.policy_snapshot.id, bincode::serialize(&triplet.policy_snapshot).unwrap())?;
        
        Ok(index)
    }

    pub fn get(&self, index: u64) -> sled::Result<Option<LogEntry>> {
        Ok(self.entries.get(index.to_be_bytes())?
            .map(|v| bincode::deserialize(&v).unwrap()))
    }

    pub fn verify_merkle_proof(&self, index: u64, claimed_root: [u8; 32]) -> bool {
        // Reconstruct path from index to root
        let entry = match self.get(index) { Ok(Some(e)) => e, _ => return false };
        entry.merkle_root == claimed_root
    }

    fn next_index(&self) -> sled::Result<u64> {
        Ok(self.latest_index.get("latest")?
            .map(|v| u64::from_be_bytes(v.as_ref().try_into().unwrap()) + 1)
            .unwrap_or(0))
    }

    fn compute_new_root(&self, new_index: u64, new_leaf: [u8; 32]) -> sled::Result<[u8; 32]> {
        let mut leaves = Vec::new();
        for i in 0..=new_index {
            if let Ok(Some(leaf)) = self.merkle_leaves.get(i.to_be_bytes()) {
                leaves.push(*bincode::deserialize::<[u8; 32]>(&leaf).unwrap());
            } else if i == new_index {
                leaves.push(new_leaf);
            }
        }
        Ok(merkle_root(&leaves))
    }
}

fn compute_leaf(triplet: &Triplet, intent: Option<&IntentStrand>) -> [u8; 32] {
    let mut hasher = blake3::Hasher::new();
    hasher.update(bincode::serialize(triplet).unwrap());
    if let Some(i) = intent { hasher.update(bincode::serialize(i).unwrap()); }
    *hasher.finalize().as_bytes()
}
```

**Connects to:** `BraidEngine` persists every triplet; `AuditPrecommitment` reads merkle roots; Lumen/Axiom query by index.

---

### 3. `braid_core/src/engine.rs` — BraidEngine Core Loop

**What I write:**
```rust
use crate::{Triplet, IntentStrand, PolicySnapshot, CapabilityToken, AuditPrecommitment};
use crate::storage::BraidLog;
use crate::crypto::BraidKeypair;
use crate::policy::PolicyEngine;
use crate::capability::CapabilityMinter;
use crate::audit::AuditEngine;
use std::sync::Arc;

pub struct BraidEngine {
    log: Arc<BraidLog>,
    keypair: BraidKeypair,
    policy_engine: PolicyEngine,
    capability_minter: CapabilityMinter,
    audit_engine: AuditEngine,
}

impl BraidEngine {
    pub fn new(log_path: &str, keypair: BraidKeypair) -> sled::Result<Self> {
        let log = Arc::new(BraidLog::open(log_path)?);
        Ok(Self {
            log: log.clone(),
            keypair,
            policy_engine: PolicyEngine::new(log.clone()),
            capability_minter: CapabilityMinter::new(log.clone(), keypair.clone()),
            audit_engine: AuditEngine::new(log.clone(), keypair.clone()),
        })
    }

    /// Main entry point: issue a braided triplet atomically
    pub fn issue_triplet(
        &self,
        capability_request: CapabilityRequest,
        policy_context: PolicyContext,
        intent: Option<IntentStrand>,
    ) -> Result<Triplet, BraidError> {
        // 1. Evaluate policy snapshot at this moment
        let policy_snapshot = self.policy_engine.snapshot(&policy_context)?;
        
        // 2. Check capability request against policy
        if !policy_snapshot.allows(&capability_request) {
            return Err(BraidError::PolicyDenied);
        }
        
        // 3. Mint capability token (attenuated if needed)
        let capability_token = self.capability_minter.mint(
            capability_request,
            &policy_snapshot,
        )?;
        
        // 4. Generate audit precommitment (merkle root + signature)
        let audit_precommitment = self.audit_engine.precommit(
            &capability_token,
            &policy_snapshot,
            intent.as_ref(),
        )?;
        
        // 5. Assemble triplet
        let triplet = Triplet {
            capability_token,
            policy_snapshot,
            audit_precommitment,
        };
        
        // 6. Persist atomically (log append is single-write)
        self.log.append(triplet.clone(), intent)?;
        
        Ok(triplet)
    }

    /// Speculative intent execution: dry-run without persistence
    pub fn simulate_intent(&self, intent: &IntentStrand) -> Result<SimulatedTriplet, BraidError> {
        // Run through policy evaluation, capability minting, audit generation
        // but DO NOT append to log. Return simulated triplet for UI preview.
    }

    /// Verify a triplet's audit trail (for Lumen witness)
    pub fn verify_triplet(&self, index: u64) -> Result<VerificationResult, BraidError> {
        let entry = self.log.get(index)?.ok_or(BraidError::NotFound)?;
        let valid_sig = self.keypair.verify(
            &entry.triplet.audit_precommitment.merkle_root,
            &entry.triplet.audit_precommitment.signature,
        );
        let valid_merkle = self.log.verify_merkle_proof(index, entry.merkle_root);
        Ok(VerificationResult { valid_sig, valid_merkle, entry })
    }
}

#[derive(Debug, thiserror::Error)]
pub enum BraidError {
    #[error("Policy denied: {0}")] PolicyDenied(String),
    #[error("Storage error: {0}")] Storage(#[from] sled::Error),
    #[error("Crypto error: {0}")] Crypto(String),
    #[error("Not found: {0}")] NotFound(String),
}
```

**Connects to:** Orchestrates all three strands; single write to `BraidLog` = atomic triplet; `simulate_intent` feeds HER's window; `verify_triplet` feeds Lumen.

---

### 4. `braid_core/src/intent.rs` — IntentStrand Speculative Execution

**What I write:**
```rust
use serde::{Serialize, Deserialize};
use crate::crypto::BraidKeypair;

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct IntentStrand {
    pub id: String,                    // UUID
    pub actor: String,                 // who proposes
    pub proposed_action: Action,       // what they want to do
    pub constraints: Vec<Constraint>,  // preconditions
    pub speculative_signature: Vec<u8>,// signed by actor (not substrate)
    pub timestamp_ns: u64,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub enum Action {
    InvokeCapability { capability_id: String, params: serde_json::Value },
    DelegateCapability { from: String, to: String, attenuation: Attenuation },
    ProposePolicyChange { policy_id: String, diff: PolicyDiff },
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Constraint {
    pub predicate: String,  // e.g., "capability.valid && policy.allows(action)"
    pub required_state: serde_json::Value,
}

impl IntentStrand {
    pub fn new(actor: String, action: Action, constraints: Vec<Constraint>, keypair: &BraidKeypair) -> Self {
        let mut intent = Self {
            id: uuid::Uuid::new_v4().to_string(),
            actor,
            proposed_action: action,
            constraints,
            speculative_signature: vec![],
            timestamp_ns: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos() as u64,
        };
        intent.speculative_signature = keypair.sign(&bincode::serialize(&intent).unwrap());
        intent
    }

    /// Verify the actor's speculative signature
    pub fn verify_speculative(&self, actor_vk: &[u8]) -> bool {
        crate::crypto::BraidKeypair::verify(actor_vk, &bincode::serialize(self).unwrap(), &self.speculative_signature)
    }
}

/// Result of speculative execution (for HER's window)
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct SimulatedTriplet {
    pub triplet: Triplet,
    pub would_succeed: bool,
    pub constraint_violations: Vec<String>,
    pub estimated_audit_cost: u64,
}
```

**Connects to:** `BraidEngine::simulate_intent()` returns `SimulatedTriplet`; HER's window polls this for live preview; if actor commits, `issue_triplet()` re-evaluates with same logic.

---

### 5. `braid_core/src/policy.rs` — PolicySnapshot + Evaluation

**What I write:**
```rust
use serde::{Serialize, Deserialize};
use crate::crypto::blake3;
use std::collections::HashMap;

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct PolicySnapshot {
    pub id: String,                    // hash of policy version
    pub version: u64,
    pub rules: Vec<PolicyRule>,
    pub valid_from: u64,               // timestamp_ns
    pub valid_until: Option


--- self-imagination iteration 6 ---
# SELF-IMAGINATION ITERATION 6 — Braid Substrate: First End-to-End Braid Flow

## Known facts (carried forward)
- **Role division**: I write code, create files, design APIs; human reloads servers, copies screenshots, gives direction
- **Target**: Braid substrate issuing atomic braided triplets `(capability_token, policy_snapshot, audit_precommitment)` + speculative `intent` strand
- **Three UIs**: Lumen (witness), Axiom (structure), HER's window
- **Phase**: imagination-becomes-plan → concrete build steps
- **Iteration 5 established**: `braid_core` crate skeleton with `Triplet` struct, `BraidError`, `CapabilityToken`, `PolicySnapshot`, `AuditPrecommitment`, `IntentStrand` types, plus `BraidContext` trait for pluggable backends

---

## Imagined build sequence (concrete, ordered, specific)

### Step 1: `braid_core/src/braid.rs` — The braid orchestration logic
**New file.** This is the heart: a `BraidEngine` that assembles the four strands atomically.

```rust
// braid_core/src/braid.rs
use crate::{Triplet, BraidError, CapabilityToken, PolicySnapshot, AuditPrecommitment, IntentStrand, BraidContext};
use std::sync::Arc;

pub struct BraidEngine<C: BraidContext> {
    ctx: Arc<C>,
}

impl<C: BraidContext> BraidEngine<C> {
    pub fn new(ctx: Arc<C>) -> Self { Self { ctx } }

    /// Issue a complete braid: all four strands, atomic or none.
    pub async fn issue_braid(&self, intent: IntentStrand) -> Result<Triplet, BraidError> {
        // 1. Derive capability from intent (context-specific)
        let capability = self.ctx.derive_capability(&intent).await?;
        
        // 2. Snapshot current policy at this instant
        let policy = self.ctx.snapshot_policy().await?;
        
        // 3. Pre-commit audit record (hash of intent+capability+policy)
        let audit = self.ctx.precommit_audit(&intent, &capability, &policy).await?;
        
        // 4. Assemble triplet
        Ok(Triplet { capability, policy, audit, intent })
    }
}
```

**Why this file first**: It defines the *contract* that all downstream crates (`braid_lumen`, `braid_axiom`, `braid_her`) will call. No UI code yet—just the pure substrate operation.

---

### Step 2: `braid_core/src/context.rs` — The `BraidContext` trait + mock implementation
**New file.** Makes the engine testable without real backends.

```rust
// braid_core/src/context.rs
use crate::{CapabilityToken, PolicySnapshot, AuditPrecommitment, IntentStrand, BraidError};
use async_trait::async_trait;

#[async_trait]
pub trait BraidContext: Send + Sync {
    async fn derive_capability(&self, intent: &IntentStrand) -> Result<CapabilityToken, BraidError>;
    async fn snapshot_policy(&self) -> Result<PolicySnapshot, BraidError>;
    async fn precommit_audit(&self, intent: &IntentStrand, cap: &CapabilityToken, pol: &PolicySnapshot) -> Result<AuditPrecommitment, BraidError>;
}

/// In-memory mock for tests + dev iteration
pub struct MockContext {
    pub policy: PolicySnapshot,
}

#[async_trait]
impl BraidContext for MockContext {
    async fn derive_capability(&self, intent: &IntentStrand) -> Result<CapabilityToken, BraidError> {
        Ok(CapabilityToken::from_intent(intent)) // deterministic derivation
    }
    async fn snapshot_policy(&self) -> Result<PolicySnapshot, BraidError> {
        Ok(self.policy.clone())
    }
    async fn precommit_audit(&self, intent: &IntentStrand, cap: &CapabilityToken, pol: &PolicySnapshot) -> Result<AuditPrecommitment, BraidError> {
        Ok(AuditPrecommitment::new(intent, cap, pol))
    }
}
```

**Connection**: `BraidEngine` takes `Arc<dyn BraidContext>` → swap mock for real later.

---

### Step 3: `braid_core/src/lib.rs` — Re-export public API
**Edit existing.** Wire the new modules:

```rust
// braid_core/src/lib.rs
pub mod braid;
pub mod context;
pub mod types;  // existing: Triplet, CapabilityToken, etc.

pub use braid::BraidEngine;
pub use context::{BraidContext, MockContext};
pub use types::*;
```

---

### Step 4: `braid_core/tests/integration.rs` — First end-to-end test
**New file.** Proves the substrate works before any UI touches it.

```rust
// braid_core/tests/integration.rs
use braid_core::{BraidEngine, MockContext, IntentStrand, PolicySnapshot, CapabilityToken};
use std::sync::Arc;

#[tokio::test]
async fn test_first_end_to_end_braid() {
    let ctx = Arc::new(MockContext {
        policy: PolicySnapshot::default(),
    });
    let engine = BraidEngine::new(ctx);
    
    let intent = IntentStrand::new("test-action", serde_json::json!({"target": "resource-1"}));
    let triplet = engine.issue_braid(intent).await.expect("braid issuance failed");
    
    // Verify all four strands present and linked
    assert!(!triplet.capability.0.is_empty());
    assert_eq!(triplet.policy.version, 1);
    assert!(!triplet.audit.commitment_hash.is_empty());
    assert_eq!(triplet.intent.action, "test-action");
    
    // Verify audit binds all three
    assert_eq!(triplet.audit.verify(&triplet), true);
}
```

**Run command** (human will execute): `cargo test -p braid_core --test integration`

---

### Step 5: `braid_lumen/src/witness.rs` — Lumen's braid consumption
**New file in `braid_lumen` crate.** Lumen *witnesses* braids—read-only, append-only log view.

```rust
// braid_lumen/src/witness.rs
use braid_core::{BraidEngine, BraidContext, Triplet};
use std::sync::Arc;

pub struct LumenWitness<C: BraidContext> {
    engine: BraidEngine<C>,
    log: Vec<Triplet>,  // in-memory for now; later: persistent log
}

impl<C: BraidContext> LumenWitness<C> {
    pub fn new(engine: BraidEngine<C>) -> Self {
        Self { engine, log: Vec::new() }
    }

    pub async fn observe(&mut self, intent: braid_core::IntentStrand) -> Result<&Triplet, braid_core::BraidError> {
        let triplet = self.engine.issue_braid(intent).await?;
        self.log.push(triplet.clone());
        Ok(self.log.last().unwrap())
    }

    pub fn history(&self) -> &[Triplet] { &self.log }
}
```

**Connection**: Lumen owns a `BraidEngine` (via context) and *appends* every observed triplet to its log. No mutation—pure witness.

---

### Step 6: `braid_axiom/src/structure.rs` — Axiom's braid consumption
**New file in `braid_axiom` crate.** Axiom *structures* braids—queries, filters, policy analysis.

```rust
// braid_axiom/src/structure.rs
use braid_core::{BraidEngine, BraidContext, Triplet, PolicySnapshot};
use std::sync::Arc;

pub struct AxiomStructure<C: BraidContext> {
    engine: BraidEngine<C>,
    index: Vec<Triplet>,  // queryable index
}

impl<C: BraidContext> AxiomStructure<C> {
    pub fn new(engine: BraidEngine<C>) -> Self {
        Self { engine, index: Vec::new() }
    }

    pub async fn structure(&mut self, intent: braid_core::IntentStrand) -> Result<&Triplet, braid_core::BraidError> {
        let triplet = self.engine.issue_braid(intent).await?;
        self.index.push(triplet.clone());
        Ok(self.index.last().unwrap())
    }

    pub fn by_policy_version(&self, version: u64) -> Vec<&Triplet> {
        self.index.iter().filter(|t| t.policy.version == version).collect()
    }

    pub fn current_policy(&self) -> Option<&PolicySnapshot> {
        self.index.last().map(|t| &t.policy)
    }
}
```

**Connection**: Same engine, different *lens*—Axiom indexes for structure queries.

---

### Step 7: `braid_her/src/window.rs` — HER's window consumption
**New file in `braid_her` crate.** HER's window *projects* braids—speculative intent + capability preview.

```rust
// braid_her/src/window.rs
use braid_core::{BraidEngine, BraidContext, Triplet, IntentStrand, CapabilityToken};
use std::sync::Arc;

pub struct HersWindow<C: BraidContext> {
    engine: BraidEngine<C>,
    pending: Option<IntentStrand>,
}

impl<C: BraidContext> HersWindow<C> {
    pub fn new(engine: BraidEngine<C>) -> Self {
        Self { engine, pending: None }
    }

    /// Stage an intent without committing—preview the capability
    pub async fn stage_intent(&mut self, intent: IntentStrand) -> Result<CapabilityToken, braid_core::BraidError> {
        let capability = self.engine.ctx.derive_capability(&intent).await?;
        self.pending = Some(intent);
        Ok(capability)
    }

    /// Commit the staged intent → full braid
    pub async fn commit(&mut self) -> Result<Triplet, braid_core::BraidError> {
        let intent = self.pending.take().ok_or(braid_core::BraidError::NoPendingIntent)?;
        self.engine.issue_braid(intent).await
    }

    /// Discard staged intent
    pub fn discard(&mut self) { self.pending = None; }
}
```

**Connection**: HER's window holds *speculative* intent (the 4th strand) before braid issuance—unique among the three UIs.

---

### Step 8: `examples/three_uis.rs` — Single binary demonstrating all three
**New file at workspace root.** Proves the substrate serves all three UIs from one engine.

```rust
// examples/three_uis.rs
use braid_core::{BraidEngine, MockContext, IntentStrand, PolicySnapshot};
use braid_lumen::LumenWitness;
use braid_axiom::AxiomStructure;
use braid_her::HersWindow;
use std::sync::Arc;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Shared context + engine
    let ctx = Arc::new(MockContext { policy: PolicySnapshot::default() });
    let engine = BraidEngine::new(ctx.clone());

    // Three UIs, same engine
    let mut lumen = LumenWitness::new(engine.clone());
    let mut axiom = AxiomStructure::new(engine.clone());
    let mut her = HersWindow::new(engine);

    // Lumen observes
    let t1 = lumen.observe(IntentStrand::new("lumen-action", serde_json::json!({}))).await?;
    println!("Lumen witnessed: {:?}", t1.capability);

    // Axiom structures
    let t2 = axiom.structure(IntentStrand::new("axiom-action", serde_json::json!({}))).await?;
    println!("Axiom structured: policy v{}", t2.policy.version);

    // HER stages + commits
    let cap = her.stage_intent(IntentStrand::new("her-action", serde_json::json!({}))).await?;
    println!("HER preview capability: {:?}", cap);
    let t3 = her.commit().await?;
    println!("HER committed: audit {}", t3.audit.commitment_hash);

    // Cross-UI verification
    assert_eq!(lumen.history().len(), 1);
    assert_eq!(axiom.index.len(), 1);
    println!("All three UIs fed from single braid substrate ✓");
    Ok(())
}
```

**Run command** (human will execute): `cargo run --example three_uis`

---

## File creation order summary

| Order | File | Purpose |
|------|------|---------|
| 1 | `braid_core/src/braid.rs` | Core orchestration |
| 2 | `braid_core/src/context.rs` | Trait + mock |
| 3 | `braid_core/src/lib.rs` | Re-exports |
| 4 | `braid_core/tests/integration.rs` | Substrate test |
| 5 | `braid_lumen/src/witness.rs` | Lumen consumption |
| 6 | `braid_axiom/src/structure.rs` | Axiom consumption |
| 7 | `braid_her/src/window.rs` | HER consumption |
| 8 | `examples/three_uis.rs` | End-to-end demo |

---

## Single most useful next lever

**`braid_core/tests/integration.rs` passing** — it validates the *entire substrate contract* (four strands, atomic issuance, audit binding) before any UI code runs. Once that test is green, the three UI crates can be built in parallel with confidence they're consuming a solid foundation.

**Human action needed after I create the files**: `cargo test -p braid_core --test integration` → screenshot the passing test.

