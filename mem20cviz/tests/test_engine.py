import io
import numpy as np
from PIL import Image

from mem20cviz.engine import compute_features, load_image, CvEngineError


def make_image(rgb=(255, 0, 0), size=(64, 48), mode="RGB") -> bytes:
    arr = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    arr[:, :] = rgb
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return buf.getvalue()


def test_load_image_png_bytes():
    blob = make_image()
    arr = load_image(frame_blob_b64=__import__("base64").b64encode(blob).decode())
    assert arr.shape == (48, 64, 3)
    assert int(arr[0, 0, 0]) == 255


def test_load_image_requires_exactly_one_source():
    try:
        load_image()
        assert False, "should raise"
    except CvEngineError:
        pass
    try:
        load_image(image_path="x.png")
        assert False, "should raise"
    except CvEngineError:
        pass


def test_compute_features_solid_red():
    blob = make_image((255, 0, 0))
    feats = compute_features(frame_blob_b64=__import__("base64").b64encode(blob).decode())
    assert feats.width == 64 and feats.height == 48
    assert feats.channels == 3
    assert abs(feats.mean_r - 255.0) < 1.0
    assert abs(feats.mean_g) < 1.0
    assert abs(feats.mean_b) < 1.0
    assert feats.luminance_mean > 60.0  # red luminance ~76
    assert feats.edge_mean_energy < 0.05  # no edges in solid image
    assert len(feats.edge_energy_histogram) == 16
    assert len(feats.embedding) >= 128
    assert len(feats.dominant_colors) >= 1


def test_compute_features_deterministic():
    blob = make_image((0, 128, 200))
    a = compute_features(frame_blob_b64=__import__("base64").b64encode(blob).decode())
    b = compute_features(frame_blob_b64=__import__("base64").b64encode(blob).decode())
    assert a.to_dict() == b.to_dict()


def test_compute_features_detects_edges():
    # checkerboard: many edges
    sx, sy = 64, 48
    arr = np.zeros((sy, sx, 3), dtype=np.uint8)
    period = 4
    for y in range(sy):
        for x in range(sx):
            if ((x // period) + (y // period)) % 2 == 0:
                arr[y, x] = 255
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    feats = compute_features(frame_blob_b64=__import__("base64").b64encode(buf.getvalue()).decode())
    assert feats.edge_mean_energy > 0.2


def test_embedding_len_actually_128():
    blob = make_image((10, 200, 30))
    feats = compute_features(frame_blob_b64=__import__("base64").b64encode(blob).decode())
    assert len(feats.embedding) == 128