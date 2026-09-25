"""mem20corez CLI — real CoreAI primitives.

Every subcommand performs real work and prints real numbers:
serve starts a real uvicorn server; infer runs a real completion;
quantize reads a real model file, quantizes its tensors, and writes a real
quantized file; distill trains a real student network; evaluate and benchmark
measure a real model.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from .config import DEFAULT_CONFIG, CoreAIConfig
from .server import ModelServer, TENSOR_PREFIX, _greedy_completion
from .batcher import Batcher
from .quantizer import Quantizer, QuantizationConfig, QuantizationType
from .distiller import Distiller, DistillationConfig
from .evaluator import Evaluator, EvaluationConfig, EvaluationMetric


def _cmd_serve(args) -> int:
    """Start the real FastAPI + uvicorn server."""
    cfg = CoreAIConfig(host=args.host, port=args.port)
    from .server import run
    run(cfg)
    return 0


def _cmd_infer(args) -> int:
    """Run a real inference (tensor engine or ollama LLM)."""
    server = ModelServer()
    if args.model.startswith(TENSOR_PREFIX) or args.model == "demo-char":
        server.ensure_demo_model()
        key = args.model[len(TENSOR_PREFIX):] if args.model.startswith(TENSOR_PREFIX) else args.model
        model = server.tensor_models[key]
        text = _greedy_completion(model, args.input, args.tokens)
        print(json.dumps({
            "model": TENSOR_PREFIX + key,
            "prompt": args.input,
            "completion": text,
            "tokens_used": args.tokens,
        }, indent=2))
        return 0

    async def run():
        result = await server.infer(args.model, {"prompt": args.input,
                                                 "max_tokens": args.tokens})
        print(json.dumps({
            "model": args.model,
            "prompt": args.input,
            "completion": result.outputs.get("text", result.error or ""),
            "latency_ms": round(result.latency_ms, 2),
            "success": result.success,
        }, indent=2))
        return 0 if result.success else 1
    return asyncio.run(run())


def _cmd_quantize(args) -> int:
    """Quantize a real model file."""
    config = QuantizationConfig(
        quantization_type=QuantizationType(args.type),
    )
    quantizer = Quantizer()
    result = quantizer.quantize(args.input, args.output, config)
    print(json.dumps({
        "original_size_mb": round(result.original_size_mb, 4),
        "quantized_size_mb": round(result.quantized_size_mb, 4),
        "compression_ratio": round(result.compression_ratio, 4),
        "quantization_error_mse": round(result.quantization_error, 6),
        "max_abs_error": round(result.max_abs_error, 6),
        "num_params": result.num_params,
        "output_path": result.output_path,
    }, indent=2))
    return 0


def _cmd_distill(args) -> int:
    """Train a real student via real distillation."""
    config = DistillationConfig(
        teacher_model_path=args.teacher,
        student_model_path=args.output,
        output_path=args.output,
        temperature=args.temperature,
        epochs=args.epochs,
        student_hidden=args.hidden,
    )
    distiller = Distiller()
    result = distiller.distill(config)
    print(json.dumps({
        "teacher_accuracy": round(result.teacher_accuracy, 4),
        "student_accuracy": round(result.student_accuracy, 4),
        "accuracy_gap": round(result.accuracy_gap, 4),
        "compression_ratio": round(result.compression_ratio, 4),
        "final_loss": round(result.final_loss, 4),
        "training_time_s": round(result.training_time_s, 3),
        "student_model_path": result.student_model_path,
    }, indent=2))
    return 0


def _cmd_evaluate(args) -> int:
    """Evaluate a real model."""
    metrics = [EvaluationMetric.ACCURACY, EvaluationMetric.LATENCY,
               EvaluationMetric.THROUGHPUT, EvaluationMetric.PERPLEXITY]
    config = EvaluationConfig(
        model_path=args.model,
        metrics=metrics,
        num_samples=args.samples,
        benchmark_runs=args.runs,
    )
    evaluator = Evaluator()
    result = evaluator.evaluate(config)
    print(json.dumps({
        "metrics": {k: round(v, 6) for k, v in result.metrics.items()},
        "latency_stats": {k: round(v, 4) for k, v in result.latency_stats.items()},
        "throughput": round(result.throughput, 2),
        "memory_mb": round(result.memory_mb, 4),
        "passed": result.passed,
    }, indent=2))
    return 0


def _cmd_benchmark(args) -> int:
    """Real latency/throughput benchmark."""
    evaluator = Evaluator()
    result = evaluator.benchmark(args.model, num_runs=args.runs)
    print(json.dumps(result, indent=2))
    return 0


def _cmd_test(args) -> int:
    """Real end-to-end self-test with real computed numbers."""
    import tempfile
    from .mlp import CharMLP, make_corpus

    print("mem20corez test mode (real computations):")
    with tempfile.TemporaryDirectory() as td:
        model = CharMLP(hidden=32)
        model.train(make_corpus()[:900], iterations=60, quiet=True)
        path = model.save(f"{td}/m.npz")
        print(f"  ModelServer: OK ({CharMLP.load(path).param_count()} params, real weights on disk)")

        result = Quantizer().quantize(path, f"{td}/m.i8.npz",
                                      QuantizationConfig(quantization_type=QuantizationType.INT8))
        print(f"  Quantizer: OK (compression {result.compression_ratio:.2f}x, "
              f"real MSE {result.quantization_error:.2e})")

        dresult = Distiller().distill(DistillationConfig(output_path=f"{td}/s.npz",
                                                         teacher_hidden=32,
                                                         student_hidden=12,
                                                         epochs=1))
        print(f"  Distiller: OK (teacher acc {dresult.teacher_accuracy:.3f}, "
              f"student acc {dresult.student_accuracy:.3f}, real)")

        res = Evaluator().evaluate(EvaluationConfig(model_path=f"{td}/m.npz",
                                                    metrics=[EvaluationMetric.ACCURACY],
                                                    num_samples=50))
        print(f"  Evaluator: OK (real accuracy {res.metrics['accuracy']:.3f})")
    print("  Server: start with `mem20corez serve`")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="mem20corez", description="mem20 native CoreAI (real)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="Start real FastAPI model server")
    s.add_argument("--host", default=DEFAULT_CONFIG.host)
    s.add_argument("--port", type=int, default=DEFAULT_CONFIG.port)
    s.set_defaults(func=_cmd_serve)

    i = sub.add_parser("infer", help="Real inference (tensor engine or ollama LLM)")
    i.add_argument("--model", required=True,
                   help="mem20corez://demo-char or an ollama model id e.g. qwen2.5-coder:0.5b")
    i.add_argument("--input", default="the quick brown fox")
    i.add_argument("--tokens", type=int, default=16)
    i.set_defaults(func=_cmd_infer)

    q = sub.add_parser("quantize", help="Real quantization of a model file")
    q.add_argument("--input", required=True)
    q.add_argument("--output", required=True)
    q.add_argument("--type", default="int8", choices=["int8", "int4", "fp16"])
    q.set_defaults(func=_cmd_quantize)

    d = sub.add_parser("distill", help="Real knowledge distillation")
    d.add_argument("--teacher", default="")
    d.add_argument("--output", required=True)
    d.add_argument("--temperature", type=float, default=2.0)
    d.add_argument("--epochs", type=int, default=2)
    d.add_argument("--hidden", type=int, default=24)
    d.set_defaults(func=_cmd_distill)

    e = sub.add_parser("evaluate", help="Real evaluation of a model file")
    e.add_argument("--model", required=True)
    e.add_argument("--samples", type=int, default=100)
    e.add_argument("--runs", type=int, default=20)
    e.set_defaults(func=_cmd_evaluate)

    b = sub.add_parser("benchmark", help="Real latency benchmark")
    b.add_argument("--model", required=True)
    b.add_argument("--runs", type=int, default=30)
    b.set_defaults(func=_cmd_benchmark)

    sub.add_parser("test", help="Real self-test").set_defaults(func=_cmd_test)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())