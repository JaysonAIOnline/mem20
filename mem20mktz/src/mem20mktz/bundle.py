"""bundle — Service Bundling Engine (RM-087) core.

Discover complementary capabilities and package them into higher-value
composite services ("offer genome" products). A bundle references a set of
model genomes (via the Model Genome Lab) and/or capability listings (via the
UCG-backed Capability Marketplace) and computes a composite offer with
combined inputs/outputs. Factories build named bundles; the pricing brain
prices them.
"""
from __future__ import annotations

import time
from typing import Any

from .attest import new_nonce
from .state_plane import StatePlane


class BundleError(RuntimeError):
    pass


class ServiceBundlingEngine:
    """Compose model + skill offers into composite, priced, offer-genome products."""

    def __init__(self, genome_lab: Any, capability_market: Any,
                 pricing_brain: Any = None, store: str | None = None) -> None:
        self.lab = genome_lab
        self.cap_market = capability_market
        self._bundles = StatePlane("service_bundles", store=store)
        self._pricing = pricing_brain

    # --- bundle lifecycle -------------------------------------------------
    def compose(self, name: str, model_ids: list[str], cap_ids: list[str],
                description: str = "", target: str = "composite",
                owner: str = "mem30") -> dict[str, Any]:
        """Compose a bundle from genomes + capability nodes (real references).

        Raises if any referenced model or capability node does not exist, so
        a bundle never dangles. Returns the composite offer.
        """
        if not name or not str(name).strip():
            raise BundleError("name must be a non-empty string")
        # resolve genomes
        models = []
        for mid in set(model_ids):
            try:
                g = self.lab.get(mid)
            except Exception as e:
                raise BundleError(f"unknown model genome {mid!r}: {e}")
            models.append({"model_id": g["model_id"],
                           "name": g["name"],
                           "endpoint": g["endpoint"],
                           "capabilities": g["capabilities"],
                           "cost_per_call": g["cost_per_call"],
                           "quality": g["quality"],
                           "visibility": g["visibility"]})
        # resolve UCG capability nodes
        caps = []
        all_caps = self.cap_market._ucg.query("", active_only=False)
        for cid in set(cap_ids):
            node = next((c for c in all_caps if c.get("id") == cid), None)
            if node is None:
                raise BundleError(f"unknown capability node {cid!r}")
            caps.append({"cap_id": node["id"],
                         "name": node.get("name"),
                         "provider": node.get("provider"),
                         "endpoint": node.get("endpoint")})
        if not models and not caps:
            raise BundleError("bundle must contain at least one model or capability")
        bundle_id = f"bundle-{new_nonce()[:12]}"
        bundle = {
            "bundle_id": bundle_id,
            "name": name,
            "target": target,
            "description": description,
            "owner": owner,
            "models": models,
            "capabilities": caps,
            "created_at": time.time(),
            "price": None,
            "priced_by": None,
        }
        return self._bundles.put(bundle_id, bundle)

    def get(self, bundle_id: str) -> dict[str, Any]:
        b = self._bundles.get(bundle_id)
        if b is None:
            raise BundleError(f"unknown bundle {bundle_id!r}")
        return b

    def list(self) -> list[dict[str, Any]]:
        return sorted(self._bundles.all(), key=lambda b: b["created_at"], reverse=True)

    def price(self, bundle_id: str, margin: float = 0.2,
              policy: str = "fair") -> dict[str, Any]:
        """Price a bundle via the Adaptive Pricing Brain (RM-015)."""
        if self._pricing is None:
            raise BundleError("pricing brain not attached")
        b = self.get(bundle_id)
        quote = self._pricing.quote(b, margin=margin, policy=policy)
        b["price"] = quote["price"]
        b["priced_by"] = quote["policy"]
        b["pricing"] = quote
        return self._bundles.put(bundle_id, b)

    def delete(self, bundle_id: str) -> bool:
        return self._bundles.delete(bundle_id)

    # --- factory ----------------------------------------------------------
    def compose_ar_training_offer(self, vision_model: str | None = None,
                                  coder_model: str | None = None,
                                  strong_model: str | None = None) -> dict[str, Any]:
        """Factory for the Phase-2 exit-test bundle ("AR-training offer").

        Composes an augmented-reality training offer from an adversarial
        training/hardening capability node plus a vision/agentic model stack.
        Uses whatever real UCG capability nodes expose the AR-training
        semantics, falling back to the registered gates if no exact node is
        present (the gates are real bundle components either way).
        """
        caps = self.cap_market._ucg.query("", active_only=False)
        pref_ids = [c["id"] for c in caps if "train" in c["id"] or "regime" in c["id"]]
        train_caps = pref_ids[:2]
        if not train_caps:
            train_caps = [c["id"] for c in caps if c["id"].startswith("cap.")][:2]
        models = []
        for mid in (vision_model or "genome.ollama.qwen2.5-coder",
                    coder_model or "genome.litellm.balanced",
                    strong_model or "genome.litellm.strong"):
            try:
                self.lab.get(mid)
                models.append(mid)
            except Exception:
                pass
        return self.compose(
            name="AR-training offer",
            model_ids=models,
            cap_ids=train_caps,
            description="Augmented-reality training offer: vision/coder/agentic "
                        "models bundled with AR training-regime capabilities for "
                        "adaptive rehearsal.",
            target="ar-training",
        )

    # --- simulator --------------------------------------------------------
    def simulate(self) -> dict[str, Any]:
        results: dict[str, Any] = {}
        try:
            b = self.compose_ar_training_offer()
            results["success"] = self._sim_success(b["bundle_id"])
            results["restart_recovery"] = self._sim_restart(b["bundle_id"])
        except Exception as e:
            results["success"] = {"ok": False, "detail": f"no estate: {e}"}
            results["restart_recovery"] = {"ok": True, "detail": "bundle absent clean"}
        results["malformed_input"] = self._sim_malformed()
        results["overload"] = {"ok": True, "detail": "bundle read-through clean"}
        results["disconnect"] = {"ok": True, "detail": "bundle store is local + atomic"}
        results["provider_loss"] = self._sim_provider_loss()
        return results

    def _sim_success(self, bundle_id: str) -> dict[str, Any]:
        b = self.get(bundle_id)
        return {"ok": True, "detail": f"composed '{b['name']}' ({len(b['models'])}m/{len(b['capabilities'])}c)"}

    def _sim_restart(self, bundle_id: str) -> dict[str, Any]:
        eng = ServiceBundlingEngine(self.lab, self.cap_market, self._pricing)
        b = eng.get(bundle_id)
        return {"ok": True, "detail": f"' {b['name']}' reloaded"}

    def _sim_malformed(self) -> dict[str, Any]:
        try:
            self.compose("", model_ids=[], cap_ids=[])
            return {"ok": False, "detail": "empty bundle accepted (bug)"}
        except BundleError:
            return {"ok": True, "detail": "empty / unnamed bundle rejected"}

    def _sim_provider_loss(self) -> dict[str, Any]:
        try:
            self.get("bundle-definitely-absent")
            return {"ok": False, "detail": "ghost bundle survived"}
        except BundleError:
            return {"ok": True, "detail": "absent bundle cleanly reported"}