import base64
import io
import json
import threading
import numpy as np
from PIL import Image

from mem20cviz.api import _Handler, main
from mem20cviz.descriptor import CAPABILITY_ID


def make_blob() -> str:
    arr = np.zeros((24, 32, 3), dtype=np.uint8)
    arr[:, :] = (30, 200, 90)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


class Dummy:
    pass


def test_card_descriptor():
    import urllib.request
    from http.server import ThreadingHTTPServer

    class T:
        pass

    # exercise the handler directly via a small in-process server
    import socket
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/.well-known/card") as r:
            card = json.loads(r.read())
        assert card["id"] == CAPABILITY_ID
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health") as r:
            health = json.loads(r.read())
        assert health["ok"] is True
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/infer",
            data=json.dumps({"mode": "real", "frame_blob_b64": make_blob()}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as r:
            result = json.loads(r.read())
        assert result["metadata"]["simulated"] is False
        assert result["features"]["width"] == 32
    finally:
        srv.shutdown()