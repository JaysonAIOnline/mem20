"""Evaluator — real model evaluation on real predictions and real timings.

Accuracy, per-class precision/recall/F1, perplexity and (when requested)
latency/throughput are all computed by actually running the model: loading the
real weight file, predicting on real evaluation text, and timing real forward
passes. No canned values.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .mlp import CharMLP, make_corpus


class EvaluationMetric(str, Enum):
    """Evaluation metric."""
    ACCURACY = "accuracy"
    PRECISION = "precision"
    RECALL = "recall"
    F1 = "f1"
    PERPLEXITY = "perplexity"
    LATENCY = "latency"
    THROUGHPUT = "throughput"
    MEMORY = "memory"


@dataclass
class EvaluationConfig:
    """Evaluation configuration."""
    model_path: str
    metrics: List[EvaluationMetric] = field(default_factory=lambda: [
        EvaluationMetric.ACCURACY, EvaluationMetric.LATENCY])
    num_samples: int = 1000
    warmup_runs: int = 2
    benchmark_runs: int = 30
    device: str = "cpu"
    compare_with: Optional[str] = None


@dataclass
class EvaluationResult:
    """Real evaluation result."""
    model_path: str
    metrics: Dict[str, float]
    latency_stats: Dict[str, float]
    throughput: float
    memory_mb: float
    passed: bool
    comparison: Optional[Dict[str, Any]] = None


def _eval_text() -> str:
    c = make_corpus()
    split = int(len(c) * 0.85)
    return c[split:]


class Evaluator:
    """Model evaluator — real metrics over real model execution."""

    def __init__(self):
        self.supported_metrics = [m.value for m in EvaluationMetric]

    def evaluate(
        self,
        config: EvaluationConfig,
        test_data: Optional[List[str]] = None,
    ) -> EvaluationResult:
        """Evaluate a real model file: load, predict, measure. All real."""
        model = CharMLP.load(config.model_path)
        text = (test_data[0] if test_data else None) or _eval_text()

        metrics: Dict[str, float] = {}
        latency_stats: Dict[str, float] = {}
        throughput = 0.0
        memory_mb = Path(config.model_path).stat().st_size / (1024 ** 2)

        if EvaluationMetric.ACCURACY in config.metrics:
            metrics["accuracy"] = model.accuracy(text)
        if EvaluationMetric.PRECISION in config.metrics:
            p, _, _ = model.precision_recall_f1(text)
            metrics["precision"] = p
        if EvaluationMetric.RECALL in config.metrics:
            _, r, _ = model.precision_recall_f1(text)
            metrics["recall"] = r
        if EvaluationMetric.F1 in config.metrics:
            _, _, f1 = model.precision_recall_f1(text)
            metrics["f1"] = f1
        if EvaluationMetric.PERPLEXITY in config.metrics:
            metrics["perplexity"] = model.perplexity(text)

        sample_metrics = config.metrics
        needs_latency = (EvaluationMetric.LATENCY in sample_metrics) or \
            (EvaluationMetric.THROUGHPUT in sample_metrics)

        if needs_latency:
            contexts = _latency_contexts(model, text, min(config.num_samples, 200))
            for _ in range(config.warmup_runs):
                for c in contexts:
                    model.predict_distribution(c)
            timings = []
            n_runs = max(config.benchmark_runs, 1)
            for _ in range(n_runs):
                t0 = time.perf_counter()
                for c in contexts:
                    model.predict_distribution(c)
                timings.append((time.perf_counter() - t0) / len(contexts) * 1000.0)
            timings = np.asarray(timings)
            latency_stats = {
                "p50": float(np.percentile(timings, 50)),
                "p95": float(np.percentile(timings, 95)),
                "p99": float(np.percentile(timings, 99)),
                "mean": float(timings.mean()),
            }
            throughput = float(len(contexts) * n_runs / max(sum(timings) / 1000.0, 1e-9))
            if EvaluationMetric.LATENCY in sample_metrics:
                metrics["latency_p50"] = latency_stats["p50"]
                metrics["latency_p95"] = latency_stats["p95"]
                metrics["latency_p99"] = latency_stats["p99"]
            if EvaluationMetric.THROUGHPUT in sample_metrics:
                metrics["throughput"] = throughput
        if EvaluationMetric.MEMORY in sample_metrics:
            metrics["memory_mb"] = memory_mb

        comparison = None
        if config.compare_with:
            other = CharMLP.load(config.compare_with)
            acc_other = other.accuracy(text)
            comparison = {
                "other_accuracy": acc_other,
                "accuracy_diff": metrics.get("accuracy", 0.0) - acc_other,
                "model_params": model.param_count(),
                "other_params": other.param_count(),
                "param_ratio": other.param_count() / max(model.param_count(), 1),
            }

        passed = metrics.get("accuracy", 1.0) > (1.0 / model.vocab_size)
        return EvaluationResult(
            model_path=config.model_path,
            metrics=metrics,
            latency_stats=latency_stats,
            throughput=throughput,
            memory_mb=memory_mb,
            passed=bool(passed),
            comparison=comparison,
        )

    def benchmark(
        self,
        model_path: str,
        num_runs: int = 30,
        warmup: int = 2,
    ) -> Dict[str, Any]:
        """Real latency/throughput benchmark of a model file."""
        model = CharMLP.load(model_path)
        contexts = _latency_contexts(model, _eval_text(), 100)
        for _ in range(warmup):
            for c in contexts:
                model.predict_distribution(c)
        timings = []
        for _ in range(num_runs):
            t0 = time.perf_counter()
            for c in contexts:
                model.predict_distribution(c)
            timings.append((time.perf_counter() - t0) / len(contexts) * 1000.0)
        timings = np.asarray(timings)
        return {
            "latency_p50_ms": float(np.percentile(timings, 50)),
            "latency_p95_ms": float(np.percentile(timings, 95)),
            "latency_p99_ms": float(np.percentile(timings, 99)),
            "mean_latency_ms": float(timings.mean()),
            "throughput_rps": float(len(contexts) * num_runs / max(timings.sum() / 1000.0, 1e-9)),
            "memory_mb": Path(model_path).stat().st_size / (1024 ** 2),
            "params": float(model.param_count()),
            "device": "cpu",
            "evaluations": float(len(contexts) * num_runs),
        }

    def compare_models(
        self,
        model_a: str,
        model_b: str,
        test_data: Optional[List[str]] = None,
        metrics: Optional[List[EvaluationMetric]] = None,
    ) -> Dict[str, Any]:
        """Real head-to-head comparison of two model files."""
        text = (test_data[0] if test_data else None) or _eval_text()
        a = CharMLP.load(model_a)
        b = CharMLP.load(model_b)
        acc_a = a.accuracy(text)
        acc_b = b.accuracy(text)
        ppl_a = a.perplexity(text)
        ppl_b = b.perplexity(text)
        winner = "model_a" if acc_a >= acc_b else "model_b"
        return {
            "model_a": model_a,
            "model_b": model_b,
            "accuracy_a": acc_a,
            "accuracy_b": acc_b,
            "perplexity_a": ppl_a,
            "perplexity_b": ppl_b,
            "winner": winner,
            "accuracy_diff": acc_b - acc_a,
            "params_a": a.param_count(),
            "params_b": b.param_count(),
        }

    def profile_model(self, model_path: str, input_data: Any = None) -> Dict[str, Any]:
        """Real model profile from the actual weight file on disk."""
        model = CharMLP.load(model_path)
        return {
            "total_params": model.param_count(),
            "trainable_params": model.param_count(),
            "weight_bytes": model.model_bytes(),
            "file_bytes": Path(model_path).stat().st_size,
            "memory_mb": Path(model_path).stat().st_size / (1024 ** 2),
            "layers": 2,
            "layer_units": {"W1_hidden": model.W1.shape[1], "W2_vocab": model.W2.shape[1]},
            "vocab_size": model.vocab_size,
            "context_len": model.context_len,
            "dtype": str(model.W1.dtype),
        }


def _latency_contexts(model: CharMLP, text: str, limit: int) -> List[str]:
    ids = model.encode(text)
    contexts = []
    for i in range(model.context_len, len(ids), 5):
        chunk = ids[i - model.context_len: i]
        contexts.append(model.decode(chunk))
        if len(contexts) >= limit:
            break
    if not contexts:
        contexts = ["the quick brown fox"]
    return contexts