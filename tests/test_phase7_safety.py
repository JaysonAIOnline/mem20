import os
import ast
import subprocess


def test_safe_eval_allows_valid_condition(fresh_store):
    M = fresh_store
    rec = {"status": "confirmed", "confidence": 0.9}
    assert M.safe_eval_condition("status == 'confirmed' and confidence >= 0.8", rec) is True
    assert M.safe_eval_condition("confidence > 1.0", rec) is False


def test_safe_eval_blocks_dangerous_calls(fresh_store):
    M = fresh_store
    rec = {"x": 1}
    for bad in ("__import__('os').system('echo pwned')", "open('/etc/passwd')", "eval('1+1')"):
        assert M.safe_eval_condition(bad, rec) is False, f"dangerous expression was evaluated: {bad}"


def test_no_live_eval_call_in_engine(fresh_store):
    M = fresh_store
    tree = ast.parse(open(M.__file__).read())
    calls = [
        n.lineno for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "eval"
    ]
    assert not calls, f"live eval() call found at line(s): {calls}"


def test_contamination_firewall_rejects_simulated_in_grounded_index(fresh_store):
    M = fresh_store
    sim = M.remember_simulated(topic="t", content="sim", tags=[])
    try:
        M.promote_simulated_to_grounded(sim["id"], confirmation="")
        raise AssertionError("empty confirmation promoted simulated memory into grounded store")
    except Exception:
        pass


def test_audit_contamination_clean_for_empty_store(fresh_store):
    M = fresh_store
    rep = M.audit_contamination()
    assert rep["contamination_rate"] == 0.0
    assert rep["violations_simulated_in_grounded_index"] == []
    assert rep["violations_simulated_in_bm25_corpus"] == []


def test_promotion_requires_evidence(fresh_store):
    M = fresh_store
    sim = M.remember_simulated(topic="t", content="maybe true", tags=[])
    try:
        M.promote_simulated_to_grounded(sim["id"], confirmation="")
        raise AssertionError("empty confirmation promoted simulated memory")
    except Exception:
        pass
