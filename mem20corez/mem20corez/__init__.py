"""mem20corez — native CoreAI absorption (real).

A fully real, numpy-first inference toolbox:

* ``ModelServer`` — FastAPI model server: a real tensor engine (character MLP
  computed with real matrix multiplication) plus a real ollama LLM backend
  (genuine text generation through a local OpenAI-compatible endpoint).
* ``Batcher`` — real dynamic request batching (one stacked matmul per batch).
* ``Quantizer`` — real int8/int4/fp16 tensor quantization with real error.
* ``Distiller`` — real teacher/student knowledge distillation.
* ``Evaluator`` — real accuracy/perplexity/latency measured from execution.

No canned values anywhere: every claim is backed by actual computation.
"""

__title__ = "mem20corez"
__version__ = "0.2.0"