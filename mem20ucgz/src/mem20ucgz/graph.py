from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from .models import Capability, CapabilityQuery, CapabilityState
from .signing import verify_manifest
from .state import StateStore


class CapabilityGraph:
    """Typed capability graph and lifecycle registry."""

    def __init__(self, store: StateStore, signing_key: str | None = None, enforce_signatures: bool = False) -> None:
        self.store = store
        self.signing_key = signing_key
        self.enforce_signatures = enforce_signatures

    def register(self, capability: Capability) -> Capability:
        capability.validate()
        if capability.signed:
            if not self.signing_key or not verify_manifest(capability.to_dict(), self.signing_key):
                raise ValueError("capability signature verification failed")
        elif self.enforce_signatures:
            raise ValueError("unsigned capability rejected by policy")
        self.store.put_capability(capability)
        self._refresh_edges_for(capability)
        return capability

    def _refresh_edges_for(self, cap: Capability) -> None:
        caps = {c.id: c for c in self.store.all_capabilities()}
        for req in cap.requires:
            if req in caps:
                self.store.put_edge(cap.id, req, "requires")
        for conflict in cap.conflicts:
            if conflict in caps:
                self.store.put_edge(cap.id, conflict, "conflicts")
        for other in caps.values():
            if other.id == cap.id:
                continue
            shared = sorted(set(cap.outputs) & set(other.inputs))
            if shared:
                self.store.put_edge(cap.id, other.id, "feeds", {"types": shared})
            reverse = sorted(set(other.outputs) & set(cap.inputs))
            if reverse:
                self.store.put_edge(other.id, cap.id, "feeds", {"types": reverse})

    def get(self, capability_id: str) -> Capability | None:
        return self.store.get_capability(capability_id)

    def update(self, capability: Capability) -> Capability:
        if not self.get(capability.id):
            raise KeyError(capability.id)
        return self.register(capability)

    def delete(self, capability_id: str) -> bool:
        return self.store.delete_capability(capability_id)

    def query(self, query: CapabilityQuery) -> list[Capability]:
        text = (query.text or "").lower().strip()
        out: list[Capability] = []
        for cap in self.store.all_capabilities():
            if query.active_only and cap.state != CapabilityState.ACTIVE:
                continue
            if query.signed_only and not cap.signed:
                continue
            if query.requires_platform and query.requires_platform not in cap.platforms:
                continue
            if query.provides and not set(query.provides).issubset(cap.outputs):
                continue
            if query.tags and not set(query.tags).issubset(cap.tags):
                continue
            if text:
                haystack = " ".join([cap.id, cap.name, cap.provider, *cap.tags, *cap.inputs, *cap.outputs]).lower()
                haystack = haystack.replace("-", " ").replace("/", " ").replace(".", " ")
                stop = {"who", "what", "which", "provides", "provide", "providing", "can", "any", "the", "a", "an", "i", "have", "need", "list", "me", "for", "of", "to", "on", "at", "is", "are"}
                tokens = [t.strip("?.!,;:'\"") for t in text.replace("-", " ").replace("/", " ").split() if t.strip("?.!,;:'\"") and t.strip("?.!,;:'\"") not in stop]
                if not all(t in haystack for t in tokens):
                    continue
            out.append(cap)
        return out

    def graph(self) -> dict[str, object]:
        return {
            "nodes": [c.to_dict() for c in self.store.all_capabilities()],
            "edges": self.store.edges(),
        }

    def providers_by_output(self) -> dict[str, list[Capability]]:
        idx: dict[str, list[Capability]] = defaultdict(list)
        for cap in self.store.all_capabilities():
            if cap.state == CapabilityState.ACTIVE:
                for out in cap.outputs:
                    idx[out].append(cap)
        return dict(idx)
