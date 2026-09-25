from mem20cviz.simulator import simulate


def test_sim_deterministic():
    a = simulate({"mode": "sim", "image_path": "x.png", "options": {"embed_dim": 32}})
    b = simulate({"mode": "sim", "image_path": "x.png", "options": {"embed_dim": 32}})
    assert a == b


def test_sim_clearly_marked_simulated():
    r = simulate({"mode": "sim"})
    assert r["metadata"]["simulated"] is True
    assert r["metadata"]["engine"] == "mem20cviz.simulator"


def test_sim_respects_embed_dim():
    r = simulate({"mode": "sim", "options": {"embed_dim": 16}})
    assert len(r["embedding"]) == 16


def test_sim_is_input_sensitive():
    r1 = simulate({"mode": "sim", "image_path": "a.png"})
    r2 = simulate({"mode": "sim", "image_path": "b.png"})
    assert r1 != r2