import asyncio
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MCP = os.path.join(REPO, "mcp")
if MCP not in sys.path:
    sys.path.insert(0, MCP)

import server


def call(handler, args):
    s = server.Mem20MCPServer()
    return asyncio.new_event_loop().run_until_complete(getattr(s, handler)(args))


def test_predict_handles_non_threshold_query():
    """A query without 'will ... exceed N' has no final_value/threshold keys.
    The tool must render it instead of raising KeyError('final_value')."""
    out = call("_world_model_predict", {
        "query": "What is the current namespace read exposure and ACL enforcement?",
        "horizon": 3,
    })
    assert not out.startswith("Error"), out
    assert "World Model Prediction" in out, out
    assert "Query:" in out, out
    assert "Trajectory:" in out, out


def test_predict_still_reports_threshold_branch():
    from memory import world_model_add_variable, world_model_reset

    world_model_reset()
    world_model_add_variable("traffic", 0)
    out = call("_world_model_predict", {"query": "will traffic exceed 10", "horizon": 2})
    assert not out.startswith("Error"), out
    assert "Final value:" in out, out
    assert "threshold:" in out, out


def test_predict_requires_query():
    out = call("_world_model_predict", {"query": ""})
    assert out == "Error: query is required", out


def test_rule_effect_creates_derived_variable():
    """    A rule whose effect names an undeclared variable must produce that
    variable, not be silently dropped."""
    from memory import world_model_add_variable, world_model_reset, world_model_simulate

    world_model_reset()
    world_model_add_variable("stale_processes", 1)
    call("_world_model_add_rule", {
        "condition": "stale_processes > 0",
        "effect": {"exposure": "open", "enforcement_effective": 0},
        "probability": 1.0,
    })
    result = world_model_simulate(1)
    final = result["final_state"]
    assert final.get("exposure") == "open", final
    assert final.get("enforcement_effective") == 0, final


def test_numeric_effects_still_accumulate_additively():
    from memory import (
        world_model_add_rule,
        world_model_add_variable,
        world_model_reset,
        world_model_simulate,
    )

    world_model_reset()
    world_model_add_variable("population", 10)
    world_model_add_rule("population >= 0", {"population": 2}, 1.0)
    result = world_model_simulate(3)
    final = result["final_state"]
    assert final["population"] == 16, final


def test_string_effect_overwrites_rather_than_crashes():
    from memory import (
        world_model_add_rule,
        world_model_add_variable,
        world_model_reset,
        world_model_simulate,
    )

    world_model_reset()
    world_model_add_variable("mode", 0)
    world_model_add_rule("mode == 0", {"mode": "test_mode"}, 1.0)
    result = world_model_simulate(2)
    assert result["final_state"]["mode"] == "test_mode", result["final_state"]


def test_simulate_tool_renders_without_error():
    out = call("_world_model_simulate", {"steps": 2})
    assert not out.startswith("Error"), out
    assert "World Model Simulation" in out, out


def test_predict_does_not_mutate_state():
    from memory import WorldModel

    wm = WorldModel()
    wm.add_variable("pressure", 1.0)
    wm.add_transition_rule("pressure < 100", {"pressure": 1})
    before = wm.state_variables["pressure"]["value"]
    history_before = list(wm.state_variables["pressure"]["history"])

    result = wm.predict("describe the pressure outlook", horizon=5)

    assert result["trajectory"][-1]["pressure"] == 6.0, result["trajectory"]
    assert wm.state_variables["pressure"]["value"] == before, "predict mutated live value"
    assert wm.state_variables["pressure"]["history"] == history_before, "predict mutated history"


def test_predict_threshold_branch_also_non_mutating():
    from memory import WorldModel

    wm = WorldModel()
    wm.add_variable("traffic", 0)
    wm.add_transition_rule("traffic >= 0", {"traffic": 3})
    result = wm.predict("will traffic exceed 10", horizon=2)
    assert result["prediction"] is False, result
    assert result["final_value"] == 6, result
    assert wm.state_variables["traffic"]["value"] == 0, "threshold branch mutated state"


def test_counterfactual_does_not_pollute_history():
    from memory import WorldModel

    wm = WorldModel()
    wm.add_variable("pressure", 1.0)
    wm.add_transition_rule("pressure < 100", {"pressure": 1})
    history_before = list(wm.state_variables["pressure"]["history"])
    wm.counterfactual("pressure < 100", interventions={"pressure": 1}, steps=3)
    assert wm.state_variables["pressure"]["history"] == history_before, "counterfactual leaked history"


def test_rule_probability_zero_never_fires():
    from memory import WorldModel

    wm = WorldModel()
    wm.add_variable("counter", 0)
    wm.add_transition_rule("counter >= 0", {"counter": 1}, 0.0)
    traj = wm.simulate_step(5)
    assert traj[-1]["counter"] == 0, traj
    assert wm.state_variables["counter"]["value"] == 0


def test_rule_probability_one_always_fires():
    from memory import WorldModel

    wm = WorldModel()
    wm.add_variable("counter", 0)
    wm.add_transition_rule("counter >= 0", {"counter": 1}, 1.0)
    traj = wm.simulate_step(5)
    assert traj[-1]["counter"] == 5, traj


def test_rule_probability_fractional_is_bounded():
    from memory import WorldModel

    wm = WorldModel()
    wm.add_variable("coin", 0)
    wm.add_transition_rule("coin >= 0", {"coin": 1}, 0.5)
    traj = wm.simulate_step(200)
    fired = traj[-1]["coin"]
    assert 60 <= fired <= 140, f"p=0.5 fired {fired}/200 times, expected ~100"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
