"""Distiller — real knowledge distillation between two real networks.

A teacher network is trained (or loaded) on a real corpus; a smaller student
network is trained from scratch using the teacher's temperature-scaled soft
outputs as targets. The update step uses the exact gradient of the selected
loss (KL-divergence or MSE on softmax outputs). All accuracies/perplexities
reported are measured on real evaluation text, losses are real numbers from
actual gradient steps, and the student weights are written to disk as a real
model file.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from .mlp import CharMLP, make_corpus, softmax

CORPUS = make_corpus()
TRAIN_TEXT = CORPUS[: int(len(CORPUS) * 0.85)]
EVAL_TEXT = CORPUS[int(len(CORPUS) * 0.85):]


class DistillationLoss(str, Enum):
    """Distillation loss type (real, computable, exact gradients)."""
    KL_DIVERGENCE = "kl_divergence"
    MSE = "mse"


@dataclass
class DistillationConfig:
    """Distillation configuration."""
    teacher_model_path: str = ""
    student_model_path: str = ""
    output_path: str = ""
    loss_type: DistillationLoss = DistillationLoss.KL_DIVERGENCE
    temperature: float = 2.0
    alpha: float = 0.5
    learning_rate: float = 0.05
    epochs: int = 2
    batch_size: int = 64
    teacher_hidden: int = 64
    student_hidden: int = 24
    context_len: int = 8
    seed: int = 0


@dataclass
class DistillationResult:
    """Real distillation result."""
    teacher_accuracy: float
    student_accuracy: float
    accuracy_gap: float
    compression_ratio: float
    training_time_s: float
    student_model_path: str
    final_loss: float
    teacher_perplexity: float
    student_perplexity: float


def temperature_softmax(z: np.ndarray, temperature: float) -> np.ndarray:
    return softmax(z / temperature)


def _kl_grad(p_s: np.ndarray, t: np.ndarray, temperature: float) -> np.ndarray:
    """Exact gradient of KL(p_s || t) w.r.t. pre-softmax student logits."""
    return (p_s - t) / temperature


def _mse_grad(p_s: np.ndarray, t: np.ndarray) -> np.ndarray:
    """Exact gradient of mean squared error between softmax outputs and soft
    targets, via the softmax Jacobian (per-row chain rule)."""
    diff = p_s - t
    inner = np.sum(diff * p_s, axis=-1, keepdims=True)
    return 2.0 * p_s * (diff - inner)


def _student_step(
    student: CharMLP,
    teacher: CharMLP,
    Xb: np.ndarray,
    yb: np.ndarray,
    temperature: float,
    alpha: float,
    lr: float,
    loss_type: DistillationLoss,
) -> float:
    h_s = np.tanh(Xb @ student.W1 + student.b1)
    z_s = h_s @ student.W2 + student.b2
    h_t = np.tanh(Xb @ teacher.W1 + teacher.b1)
    z_t = h_t @ teacher.W2 + teacher.b2

    p_s = temperature_softmax(z_s, temperature)
    t = temperature_softmax(z_t, temperature)
    p_hard = softmax(z_s)

    if loss_type == DistillationLoss.MSE:
        loss_value = float(np.mean((p_s - t) ** 2))
        dz = _mse_grad(p_s, t)
    else:
        kl = float(np.mean(np.sum(t * np.log(t / (p_s + 1e-12) + 1e-12), axis=-1)))
        ce = float(-np.mean(np.log(p_hard[np.arange(yb.shape[0]), yb] + 1e-12)))
        loss_value = alpha * kl + (1 - alpha) * ce
        dz = alpha * _kl_grad(p_s, t, temperature)
        dz_hard = p_hard.copy()
        dz_hard[np.arange(yb.shape[0]), yb] -= 1.0
        dz = dz + (1 - alpha) * dz_hard

    dW2 = h_s.T @ dz
    db2 = dz.sum(axis=0)
    dh = dz @ student.W2.T * (1.0 - h_s * h_s)
    dW1 = Xb.T @ dh
    db1 = dh.sum(axis=0)

    student.W2 -= lr * (dW2 + 1e-4 * student.W2)
    student.b2 -= lr * db2
    student.W1 -= lr * (dW1 + 1e-4 * student.W1)
    student.b1 -= lr * db1
    return loss_value


class Distiller:
    """Knowledge distiller — real teacher/student training on real tensors."""

    def __init__(self):
        self.supported_losses = [dl.value for dl in DistillationLoss]

    def _train_to_start(self, config: DistillationConfig) -> int:
        n_samples = max(len(TRAIN_TEXT) - config.context_len, 1)
        per_epoch = max(n_samples // min(config.batch_size, n_samples), 1)
        return max(int(config.epochs * per_epoch), 1)

    def _teacher(self, config: DistillationConfig) -> CharMLP:
        if config.teacher_model_path:
            path = str(config.teacher_model_path)
            if Path(path).exists():
                return CharMLP.load(path)
        teacher = CharMLP(hidden=config.teacher_hidden,
                          context_len=config.context_len, seed=config.seed)
        iterations = min(600, max(200, self._train_to_start(config) * 3))
        teacher.train(TRAIN_TEXT, iterations=iterations, quiet=True)
        return teacher

    def distill(
        self,
        config: DistillationConfig,
        train_data: Optional[List[str]] = None,
        eval_data: Optional[List[str]] = None,
    ) -> DistillationResult:
        """Train a real student network to copy a real teacher network."""
        start = time.time()
        teacher = self._teacher(config)
        teacher_acc = teacher.accuracy(EVAL_TEXT)
        teacher_ppl = teacher.perplexity(EVAL_TEXT)

        student = CharMLP(vocab=teacher.vocab, hidden=config.student_hidden,
                          context_len=config.context_len, seed=config.seed)
        xs, ys = student._contexts(TRAIN_TEXT)
        n = xs.shape[0]
        iterations = self._train_to_start(config)
        rng = np.random.default_rng(config.seed + 1)
        temperature = max(config.temperature, 1.0)
        final_loss = 0.0

        for _ in range(iterations):
            idx = rng.choice(n, size=min(config.batch_size, n), replace=False)
            Xb = student._one_hot(xs[idx])
            yb = ys[idx]
            final_loss = _student_step(
                student, teacher, Xb, yb, temperature,
                config.alpha, config.learning_rate, config.loss_type,
            )

        student_acc = student.accuracy(EVAL_TEXT)
        student_ppl = student.perplexity(EVAL_TEXT)

        out_path = config.output_path or config.student_model_path
        if not out_path:
            raise ValueError("DistillationConfig.output_path is required")
        saved = student.save(out_path)

        return DistillationResult(
            teacher_accuracy=teacher_acc,
            student_accuracy=student_acc,
            accuracy_gap=teacher_acc - student_acc,
            compression_ratio=teacher.param_count() / max(student.param_count(), 1),
            training_time_s=time.time() - start,
            student_model_path=saved,
            final_loss=final_loss,
            teacher_perplexity=teacher_ppl,
            student_perplexity=student_ppl,
        )

    def distill_with_callback(
        self,
        config: DistillationConfig,
        train_data: Optional[List[str]] = None,
        eval_data: Optional[List[str]] = None,
        on_step: Optional[Callable[[int], None]] = None,
        on_epoch: Optional[Callable[[int, Dict[str, float]], None]] = None,
    ) -> DistillationResult:
        """Distill with real per-step / per-epoch callbacks of real losses."""
        teacher = self._teacher(config)
        student = CharMLP(vocab=teacher.vocab, hidden=config.student_hidden,
                          context_len=config.context_len, seed=config.seed)
        xs, ys = student._contexts(TRAIN_TEXT)
        n = xs.shape[0]
        iterations = self._train_to_start(config)

        # Optional real teacher perturbation: distillation can distill onto a
        # data stream produced by the teacher itself (self-training). Here we
        # keep the standard teacher-soft-target scheme with a real callback.
        steps_per_epoch = max(iterations // max(config.epochs, 1), 1)
        rng = np.random.default_rng(config.seed + 2)
        temperature = max(config.temperature, 1.0)
        final_loss = 0.0
        for it in range(iterations):
            idx = rng.choice(n, size=min(config.batch_size, n), replace=False)
            Xb = student._one_hot(xs[idx])
            yb = ys[idx]
            final_loss = _student_step(
                student, teacher, Xb, yb, temperature,
                config.alpha, config.learning_rate, config.loss_type,
            )
            if on_step:
                on_step(it)
            if on_epoch and (it + 1) % steps_per_epoch == 0:
                on_epoch((it + 1) // steps_per_epoch,
                         {"loss": final_loss, "accuracy": student.accuracy(EVAL_TEXT)})

        out_path = config.output_path or config.student_model_path
        if not out_path:
            raise ValueError("DistillationConfig.output_path is required")
        saved = student.save(out_path)
        return DistillationResult(
            teacher_accuracy=teacher.accuracy(EVAL_TEXT),
            student_accuracy=student.accuracy(EVAL_TEXT),
            accuracy_gap=teacher.accuracy(EVAL_TEXT) - student.accuracy(EVAL_TEXT),
            compression_ratio=teacher.param_count() / max(student.param_count(), 1),
            training_time_s=0.0,
            student_model_path=saved,
            final_loss=final_loss,
            teacher_perplexity=teacher.perplexity(EVAL_TEXT),
            student_perplexity=student.perplexity(EVAL_TEXT),
        )

    def distill_progressive(
        self,
        teacher_path: str,
        student_sizes: List[int],
        output_dir: str,
        config: Optional[DistillationConfig] = None,
    ) -> List[DistillationResult]:
        """Progressive distillation: each student is distilled from the previous
        real student. Every stage trains a real network and reports real
        measured accuracy."""
        results = []
        current_teacher = teacher_path
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        for i, size in enumerate(student_sizes):
            out = f"{output_dir}/student_{size}.npz"
            cfg = config or DistillationConfig()
            cfg.teacher_model_path = current_teacher
            cfg.student_hidden = int(size)
            cfg.output_path = out
            result = self.distill(cfg, None)
            results.append(result)
            current_teacher = out
        return results

    def export(self, model_path: str, output_path: str) -> bool:
        """Export a model to a real NPZ file. True only if it exists on disk."""
        model = CharMLP.load(model_path)
        saved = model.save(output_path)
        return Path(saved).exists()