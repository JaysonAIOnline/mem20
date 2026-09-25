# Runtime Profile Architecture

> Forward-looking runtime model for Claw3D after the mem20 claw plugin + Mem20 adapter work landed on `main`.

## Goal

Claw3D should treat runtime connection targets as profiles, not as ad hoc
gateway URLs tied to one backend assumption.

That means the app should model:

- provider
- runtime profile
- floor binding

instead of making the user think in terms of:

- one hard-coded backend
- one port
- one global gateway selection

## Recommendation

Use one gateway contract in the UI, with different backend providers
behind it.

Default path:

- `mem20 claw plugin` is the default runtime profile

Optional paths:

- `Mem20 Adapter`
- `Custom Runtime(s)`

The important rule is:

- the UI keeps speaking one Claw3D gateway contract
- the backend behind that contract may be native mem20 claw plugin, Mem20 through
  the adapter, or a custom runtime/provider

## Core Terms

### Provider

A provider identifies the backend family behind a runtime profile.

Initial provider set:

- `mem20 claw plugin`
- `mem20`
- `custom`
- `demo`

Provider answers questions like:

- what backend is this?
- what capabilities should the UI expect?
- which default labels or help copy apply?

### Runtime Profile

A runtime profile is a named connection target.

Examples:

- `mem20 claw plugin Default`
- `Mem20 Adapter`
- `Custom Staging Runtime`
- `Custom Prod Runtime`

Suggested shape:

```ts
export type RuntimeProfileId = string;

export type RuntimeProfile = {
  id: RuntimeProfileId;
  label: string;
  provider: "mem20 claw plugin" | "mem20" | "custom" | "demo";
  gatewayUrl: string;
  token?: string | null;
  adapterType?: "mem20 claw plugin" | "mem20" | "custom" | "demo" | null;
  enabled: boolean;
  defaultProfile: boolean;
  notes?: string | null;
};
```

Runtime profile answers:

- where does Claw3D connect?
- what provider is behind this connection?
- which auth/token should be used?
- which profile should be the default?

### Floor Binding

A floor binding maps an office floor to a runtime profile.

Examples:

- `mem20 claw plugin Floor -> mem20 claw plugin-default`
- `Mem20 Floor -> mem20-default`
- `Custom Floor -> custom-default`
- `Lobby -> null`
- `Campus -> null`

Suggested shape:

```ts
export type FloorRuntimeBinding = {
  floorId: FloorId;
  runtimeProfileId: RuntimeProfileId | null;
};
```

Floor binding answers:

- which runtime powers this floor?
- is this floor provider-backed, function-backed, or a destination?

## Runtime Model

The recommended mental model is:

```text
Provider -> Runtime Profile -> Floor Binding
```

Examples:

- provider: `mem20 claw plugin`
  - profile: `mem20 claw plugin-default`
  - bound floor: `mem20 claw plugin-ground`

- provider: `mem20`
  - profile: `mem20-default`
  - bound floor: `mem20-first`

- provider: `custom`
  - profiles:
    - `custom-default`
    - `custom-staging`
    - `custom-prod`
  - one or more custom floors may bind to them later

## Default Behavior

Initial default behavior should be:

- if nothing else is configured, Claw3D prefers `mem20 claw plugin`
- Mem20 remains optional and adapter-backed
- custom runtimes remain optional and profile-driven

That means:

- mem20 claw plugin is the safe baseline
- Mem20 should not destabilize the default path
- custom runtimes should not require special-case UI logic

## Mem20 Adapter Position

Right now Mem20 works through the adapter path, and that is acceptable as
the near-term production path.

Architecture implication:

- Mem20 should be represented as a provider/profile combination
- not as a special global mode

So the app should think:

- provider: `mem20`
- profile: `mem20-default`
- gateway URL: adapter endpoint

This keeps the runtime selection model uniform even though Mem20 is still
adapter-backed today.

## Custom Runtime Position

Custom runtimes should fit the same profile model:

- provider: `custom`
- one or more named profiles
- floor binding selects which profile powers which floor

This avoids making the "Custom Floor" logic one-off and lets Claw3D grow
to multiple custom environments without another architecture pass.

## One Gateway Contract, Different Backends

The UI should not branch everywhere on backend family.

Instead:

- the browser talks one Claw3D gateway contract
- Studio/settings select the runtime profile
- profile/provider metadata informs capability checks and defaults

This keeps the frontend stable while backends differ behind the scenes.

## Office Systems Implications

This model supports the current Office Systems direction cleanly.

### Floor Zones

- `Building`
- `Outside`

### Floor Types

- provider-backed
- function-backed
- destination/outside

### Examples

- `Lobby`
  - function-backed
  - no runtime binding required

- `mem20 claw plugin Floor`
  - provider-backed
  - bound to `mem20 claw plugin-default`

- `Mem20 Floor`
  - provider-backed
  - bound to `mem20-default`

- `Custom Floor`
  - provider-backed
  - bound to `custom-default`

- `Training Floor`
  - function-backed
  - may later bind to a chosen provider profile

- `Trader's Floor`
  - function-backed
  - may later bind to a chosen provider profile

- `Campus` / `Stadium`
  - outside destinations
  - not required to behave like numbered floors

## Branch Sequence

Recommended next branches:

- `docs/runtime-profiles`
- `feat/claw3doctor`
- `refactor/office-shell`
- later:
  - `docs/floor-builder-schema`
  - `feat/floor-builder`

## Next Sequence

### 1. `docs: runtime profile architecture`

Define:

- provider vs profile vs floor binding
- `mem20 claw plugin` default
- `Mem20 Adapter` optional
- `Custom Runtime(s)` optional
- one gateway contract, different backends

### 2. `feat: claw3doctor`

First pass should check:

- Claw3D settings/env
- gateway reachability
- mem20 claw plugin version
- Mem20 adapter/API availability
- auth/token issues
- common websocket/origin/secure-context failures

### 3. `refactor: office shell modularization`

Next extractions:

- `OfficeShell`
- `OfficeFloorController`
- `OfficePanelsController`

### 4. `docs: floor schema and builder plan`

Define the schema before building the editor.

### 5. `feat: admin floor builder`

Only after floor metadata/schema stabilizes.

## Why This Comes First

The runtime-profile document should land before more implementation work
because it informs both:

- multi-runtime support
- `claw3doctor`

Without this, diagnostics and floor binding will keep being designed
against moving assumptions.

## Summary

Claw3D should move to a runtime profile model where:

- providers describe the backend family
- profiles describe named connection targets
- floors bind to profiles

mem20 claw plugin remains the default.
Mem20 adapter remains optional.
Custom runtimes become first-class without special-case UI debt.
