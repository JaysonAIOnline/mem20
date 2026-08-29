"""Engine-level tests for Phase 8.1 (causal world model + self model).

These exercise the engine directly (no MCP layer) against an isolated temp store
set up by the ``fresh_store`` fixture in conftest.py.
"""
import json

import pytest


def test_world_model_do_intervention(fresh_store):
    M = fresh_store
    wm = M.WorldModel()
    wm.add_variable("temperature", 20.0)
    rec = wm.do("temperature", 25.0, label="test")
    assert rec["variable"] == "temperature"
    assert rec["value"] == 25.0
    assert wm.state_variables["temperature"]["value"] == 25.0


def test_world_model_counterfactual_is_non_mutating(fresh_store):
    M = fresh_store
    wm = M.WorldModel()
    wm.add_variable("temperature", 20.0)
    cf = wm.counterfactual("temperature > 23", {"temperature": 30}, steps=1)
    assert cf["condition_holds"] is True
    # counterfactual must NOT mutate the live state
    assert wm.state_variables["temperature"]["value"] == 20.0


def test_world_model_transition_rule_simulate(fresh_store):
    M = fresh_store
    wm = M.WorldModel()
    wm.add_variable("pressure", 1.0)
    wm.add_transition_rule("pressure < 100", {"pressure": 1})
    traj = wm.simulate_step(steps=3)
    assert len(traj) == 3
    assert traj[-1]["pressure"] == 3.0
    assert wm.state_variables["pressure"]["value"] == 4.0


def test_world_model_prediction_persistence(fresh_store):
    M = fresh_store
    rid = M.world_model_record_prediction("will it rain?", "yes")["prediction_id"]
    assert rid
    M.world_model_resolve_prediction(rid, "no", True)
    import os

    assert os.path.exists(M.PREDICTIONS_LEDGER)
    with open(M.PREDICTIONS_LEDGER, encoding="utf-8") as f:
        lines = [l for l in f if l.strip()]
    assert any(rid in l and "no" in l for l in lines)


def test_self_model_continuity(fresh_store):
    M = fresh_store
    sm = M.SelfModel()
    sm.create(["reason", "recall"], ["honesty"])
    sm.create(["reason", "recall"], ["honesty"])
    r = sm.continuity()
    assert r["score"] == 1.0
    assert r["drift"] is False
    sm.create(["reason"], ["expediency"])
    r2 = sm.continuity()
    assert 0.0 <= r2["score"] <= 1.0
    assert isinstance(r2["drift"], bool)
