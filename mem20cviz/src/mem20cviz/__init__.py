"""mem20cviz — mem20 Computer-Vision-inference subsystem (imagined → built real).

Imagined by mem20 (imagination_dream, 3 iterations, 2026-09-20) as the
`cv.infer` capability-plane subsystem, then built here as a real, locally
executable package. Design that was imagined:

  * capability id `cv.infer`, typed I/O: image path or raw frame blob →
    detections / classifications / embedding
  * registered as a versioned descriptor in the mem20 UCG
  * a signed braid journal entry per inference
  * honest boundaries — the subsystem never pretends to see: it ships a REAL
    classical-CV feature engine (numpy/PIL: edges, colors, stats, embedding)
    plus a deterministic contract simulator, and an optional heavy-model
    provider hook that is only "real" when a model is actually configured.

Key integrity rule (from the imagination): no fabricated CV. mode="sim"
returns results explicitly marked simulated:true and derives deterministically
from the input hash; mode="real" performs actual pixel math on the real image.
"""