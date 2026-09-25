#!/usr/bin/env bash
# mem20cviz demo: build a real image, run REAL cv.infer, journal to braid, print receipt
set -euo pipefail
cd "$(dirname "$0")/.."

FS_CV="${FS_CV:-fs-cv}"
if ! command -v "$FS_CV" >/dev/null 2>&1 && [ -x /root/.venv/bin/fs-cv ]; then
    FS_CV=/root/.venv/bin/fs-cv
fi

python - <<'PY'
# generate a real test image: gradient + block (has real edges, colors)
import numpy as np
from PIL import Image
w, h = 160, 90
arr = np.zeros((h, w, 3), dtype=np.uint8)
yy, xx = np.mgrid[0:h, 0:w]
arr[:, :, 0] = (xx / w * 255).astype(np.uint8)
arr[:, :, 1] = (yy / h * 255).astype(np.uint8)
arr[:, :, 2] = ((xx + yy) / (w + h) * 255).astype(np.uint8)
arr[20:50, 40:90] = (255, 0, 0)
arr[55:80, 100:140] = (0, 0, 255)
Image.fromarray(arr).save("/tmp/opencode/mem30/cv_demo.png")
print("wrote /tmp/opencode/mem30/cv_demo.png")
PY

echo "== 1. REAL classical-CV inference (journal -> braid) =="
$FS_CV infer --image /tmp/opencode/mem30/cv_demo.png > /tmp/opencode/mem30/cv_demo_real.json
python - <<'PY'
import json
r = json.load(open("/tmp/opencode/mem30/cv_demo_real.json"))
md = r["metadata"]
print("simulated:", md["simulated"], "| engine:", md["engine"], "| runtime_ms:", md["runtime_ms"])
print("size:", md["width"], "x", md["height"])
print("mean rgb:", [round(v,1) for v in (r["features"]["mean_r"], r["features"]["mean_g"], r["features"]["mean_b"])])
print("edge energy:", r["features"]["edge_mean_energy"])
print("dominant colors:", r["features"]["dominant_colors"][:2])
print("embedding dim:", len(r["embedding"]))
print("braid:", md.get("_braid"))
PY

echo "== 2. sim contract (deterministic, simulated=true) =="
$FS_CV sim --payload '{"mode":"sim"}' | python -c "import json,sys; r=json.load(sys.stdin); print('simulated:', r['metadata']['simulated'], '| objects:', len(r['objects']), '| embed:', len(r['embedding']))"

echo "== 3. descriptor =="
$FS_CV descriptor | python -c "import json,sys; d=json.load(sys.stdin); print('id:', d['id'], '| version:', d['version'], '| outputs:', d['outputs'])"