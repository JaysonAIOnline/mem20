import base64
import io
import numpy as np
from PIL import Image

from mem20cviz.service import run_inference, InferenceError


def make_blob(rgb=(255, 0, 0), size=(32, 24)) -> str:
    arr = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    arr[:, :] = rgb
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def test_real_mode_returns_features():
    r = run_inference({"mode": "real", "frame_blob_b64": make_blob()}, journal=False)
    assert r["metadata"]["simulated"] is False
    assert r["metadata"]["engine"] == "mem20cviz.classical"
    assert r["features"]["width"] == 32
    assert len(r["embedding"]) == 128


def test_sim_mode_returns_simulated():
    r = run_inference({"mode": "sim", "image_path": "nope.png"}, journal=False)
    assert r["metadata"]["simulated"] is True


def test_invalid_mode_rejected():
    try:
        run_inference({"mode": "banana"})
        assert False, "should raise"
    except InferenceError:
        pass


def test_real_requires_image():
    try:
        run_inference({"mode": "real"}, journal=False)
        assert False, "should raise"
    except InferenceError:
        pass


def test_missing_image_file_errors():
    try:
        run_inference({"mode": "real", "image_path": "/no/such/file.png"}, journal=False)
        assert False, "should raise"
    except InferenceError:
        pass


def test_contract_outputs_present():
    r = run_inference({"mode": "real", "frame_blob_b64": make_blob((0, 128, 200))}, journal=False)
    for key in ("objects", "classifications", "embedding", "features", "metadata"):
        assert key in r