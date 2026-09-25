"""Execution ordering for mem20orcaz.

Stable topological reordering of the agent queue honoring ``depends_on``.
Faithful to OrKa semantics: only ``depends_on`` entries referencing agents
within the top-level agent list constrain ordering; fork branch targets are
excluded; the sort is stable so unconstrained configs keep their declared order.
"""

from __future__ import annotations

from typing import Any, Dict, List


def _deps_of(cfg: Dict[str, Any]) -> List[str]:
    raw = cfg.get("depends_on") or []
    if isinstance(raw, str):
        raw = [raw]
    return [d for d in raw if isinstance(d, str)]


def topological_queue(agent_ids: List[str], cfg_by_id: Dict[str, Dict[str, Any]]) -> List[str]:
    """Return ``agent_ids`` reordered to honor ``depends_on``.

    Args:
        agent_ids: The orchestrator's ordered list of agent ids.
        cfg_by_id: Map of agent id -> its config dict (carrying ``depends_on``).

    Returns:
        A list containing exactly the same ids, reordered so each agent follows
        the agents it depends on. Stable w.r.t. the input order.

    Raises:
        ValueError: if ``depends_on`` forms a cycle among the listed agents.
    """
    id_set = set(agent_ids)
    index = {aid: i for i, aid in enumerate(agent_ids)}

    deps: Dict[str, List[str]] = {}
    for aid in agent_ids:
        cfg = cfg_by_id.get(aid, {})
        deps[aid] = [d for d in _deps_of(cfg) if d in id_set and d != aid]

    if not any(deps.values()):
        return list(agent_ids)

    remaining = set(agent_ids)
    satisfied: set[str] = set()
    result: List[str] = []

    while remaining:
        ready = sorted(
            (aid for aid in remaining if all(d in satisfied for d in deps[aid])),
            key=lambda a: index[a],
        )
        if not ready:
            cycle = sorted(remaining, key=lambda a: index[a])
            raise ValueError(
                f"depends_on cycle detected among agents: {cycle}. "
                "Remove the circular dependency or list these agents without depends_on."
            )
        nxt = ready[0]
        result.append(nxt)
        satisfied.add(nxt)
        remaining.discard(nxt)

    return result


def ordered_initial_queue(agent_ids: List[Any], agent_cfgs: Any) -> List[Any]:
    """Reorder an initial queue by ``depends_on`` safely for edge cases.

    Leaves the list untouched if it contains non-string entries (e.g. nested
    decision-tree branches), since ordering only applies to a flat agent list.
    """
    if not agent_ids:
        return list(agent_ids)
    if not all(isinstance(aid, str) for aid in agent_ids):
        return list(agent_ids)

    cfg_by_id: Dict[str, Dict[str, Any]] = {}
    if isinstance(agent_cfgs, dict):
        for aid in agent_ids:
            cfg_by_id[aid] = agent_cfgs.get(aid, {})
    elif isinstance(agent_cfgs, list):
        for cfg in agent_cfgs:
            if isinstance(cfg, dict) and isinstance(cfg.get("id"), str):
                cfg_by_id[cfg["id"]] = cfg

    try:
        return topological_queue(list(agent_ids), cfg_by_id)
    except ValueError:
        return list(agent_ids)