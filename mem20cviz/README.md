# mem20cviz — computer-vision-inference subsystem

Imagined by mem20 (imagination_dream, 3 iterations, 2026-09-20) as the
`cv.infer` capability-plane subsystem, then **built real** here as a locally
executable package. Designed to fit the mem20 pattern: a versioned capability
descriptor registered in the UCG, typed I/O, signed braid journal per inference,
honest boundaries — no fabricated CV.

## What it does

| mode   | engine                              | real? | meaning                                     |
|--------|-------------------------------------|-------|---------------------------------------------|
| `real` | `mem20cviz.classical` (numpy/PIL)   | yes   | actual pixel math: edges, colors, stats, fixed-dim embedding |
| `sim`  | `mem20cviz.simulator`               | no    | deterministic contract proof, `simulated:true`, hash-derived |

The subsystem **never pretends to see**. `sim` explicitly marks itself
simulated. `real` computes actual statistics of the actual image. A heavy NN
provider is an optional future hook — it is reported unavailable unless
actually configured, never faked.

## Install

```bash
pip install -e /opt/mem20/mem20cviz
```

## Usage

```bash
# real inference on a real image
fs-cv infer --image photo.png

# real inference from a base64 raw frame
fs-cv infer --frame-blob "$(base64 -w0 frame.rgb)"

# contract simulator
fs-cv sim --payload '{"mode":"sim"}'

# UCG descriptor
fs-cv descriptor

# HTTP server (GET /health, /.well-known/card, POST /infer)
fs-cv serve --port 8783
```

## Capability descriptor

- id: `cap.cv-inference.v1`
- version: `0.1.0`
- provider: `mem30.cv.inference`
- inputs: `image_path`, `frame_blob_b64`, `mode`, `options`
- outputs: `cv/features`, `cv/objects`, `cv/classifications`, `cv/embedding`
- tags: vision, inference, local, deterministic, classical