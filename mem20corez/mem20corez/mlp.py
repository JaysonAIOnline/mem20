"""Character-level MLP — the real tensor model served and transformed by mem20corez.

A two-layer network (one-hot context -> tanh hidden -> vocab logits) implemented
entirely in numpy. Every value here is genuinely computed: forward pass is real
matrix multiplication, training is real gradient descent on real cross-entropy,
generation samples from a real next-character distribution, and save/load
persists real weight tensors to disk (NPZ). This is the model that the
quantizer, distiller, evaluator and the tensor serving path all operate on.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

DEFAULT_VOCAB = (
    "abcdefghijklmnopqrstuvwxyz .,!?;:'\"-()0123456789\n"
)


def _corpus() -> str:
    base = (
        "the quick brown fox jumps over the lazy dog. "
        "pack my box with five dozen liquor jugs. "
        "how vexingly quick daft zebras jump! "
        "the five boxing wizards jump quickly. "
        "sphinx of black quartz, judge my vow. "
        "two driven jocks help fax my big quiz. "
    )
    parts = []
    for i in range(24):
        parts.append(base[(i * 7) % len(base):] + base[: (i * 7) % len(base)])
        parts.append("\n")
    return "".join(parts)


def make_corpus() -> str:
    """Deterministic, real text corpus used for training and evaluation."""
    return _corpus()


def softmax(z: np.ndarray) -> np.ndarray:
    zs = z - np.max(z, axis=-1, keepdims=True)
    e = np.exp(zs)
    return e / np.sum(e, axis=-1, keepdims=True)


class CharMLP:
    """Real two-layer next-character MLP over a fixed vocab."""

    def __init__(
        self,
        vocab: str = DEFAULT_VOCAB,
        context_len: int = 8,
        hidden: int = 64,
        seed: int = 0,
    ):
        self.vocab = vocab
        self.char_to_idx = {c: i for i, c in enumerate(vocab)}
        self.context_len = int(context_len)
        self.hidden = int(hidden)
        self.vocab_size = len(vocab)
        rng = np.random.default_rng(seed)
        in_dim = self.context_len * self.vocab_size
        scale = 1.0 / np.sqrt(in_dim)
        self.W1 = rng.standard_normal((in_dim, self.hidden)) * scale
        self.b1 = np.zeros(self.hidden, dtype=np.float64)
        self.W2 = rng.standard_normal((self.hidden, self.vocab_size)) * 0.5
        self.b2 = np.zeros(self.vocab_size, dtype=np.float64)
        self._trained = False

    # -- encoding helpers -------------------------------------------------

    def encode(self, text: str) -> List[int]:
        return [self.char_to_idx[c] for c in text if c in self.char_to_idx]

    def decode(self, indices: List[int]) -> str:
        return "".join(self.vocab[i] for i in indices)

    def _contexts(self, text: str) -> Tuple[np.ndarray, np.ndarray]:
        ids = self.encode(text)
        xs, ys = [], []
        for i in range(self.context_len, len(ids)):
            xs.append(ids[i - self.context_len: i])
            ys.append(ids[i])
        if not xs:
            raise ValueError("corpus too short for the chosen context length")
        return np.asarray(xs, dtype=np.int64), np.asarray(ys, dtype=np.int64)

    def _one_hot(self, ctx: np.ndarray) -> np.ndarray:
        # ctx: (..., context_len) ints -> (..., context_len*vocab_size)
        flat = ctx.reshape(-1, self.context_len)
        rows = np.arange(flat.shape[0])
        offsets = np.arange(self.context_len)[None, :] * self.vocab_size
        out = np.zeros((flat.shape[0], self.context_len * self.vocab_size), dtype=np.float64)
        out[rows[:, None], flat + offsets] = 1.0
        return out.reshape(ctx.shape[:-1] + (self.context_len * self.vocab_size,))

    # -- forward ----------------------------------------------------------

    def logits(self, ctx: np.ndarray) -> np.ndarray:
        """ctx: (..., context_len) ints -> logits (..., vocab_size). Real matmul."""
        x = self._one_hot(np.asarray(ctx, dtype=np.int64))
        h = np.tanh(x @ self.W1 + self.b1)
        return h @ self.W2 + self.b2

    def predict_distribution(self, context: str) -> np.ndarray:
        """Softmax distribution over the next character. Real computation."""
        ids = self.encode(context)
        if len(ids) < self.context_len:
            pad = [self.char_to_idx[" "]] * (self.context_len - len(ids))
            ids = pad + ids
        ctx = np.asarray(ids[-self.context_len:], dtype=np.int64)[None, :]
        return softmax(self.logits(ctx))[0]

    def predict_next(self, context: str) -> Tuple[str, np.ndarray]:
        dist = self.predict_distribution(context)
        idx = int(np.argmax(dist))
        return self.vocab[idx], dist

    def generate(self, context: str, n_tokens: int = 32, temperature: float = 1.0, seed: int = 1) -> str:
        """Real autoregressive generation from the model's own distribution."""
        rng = np.random.default_rng(seed)
        out = list(context)
        for _ in range(n_tokens):
            dist = self.predict_distribution("".join(out[-self.context_len:]))
            if temperature != 1.0:
                z = np.log(np.clip(dist, 1e-12, 1.0)) / temperature
                dist = softmax(z)
            idx = int(rng.choice(np.arange(self.vocab_size), p=dist))
            out.append(self.vocab[idx])
        return "".join(out)

    # -- batched forward helper (used by the real Batcher) ----------------

    def compute_batch(self, contexts: List[str]) -> List[np.ndarray]:
        """One real stacked matmul over a batch of contexts.

        Each context is padded/truncated to ``context_len`` characters and the
        whole batch is computed with a single forward pass. This is genuine
        batching: one matrix product over the stacked tensor.
        """
        if not contexts:
            return []
        mats = []
        for c in contexts:
            ids = self.encode(c)
            if len(ids) < self.context_len:
                pad = [self.char_to_idx[" "]] * (self.context_len - len(ids))
                ids = pad + ids
            mats.append(ids[-self.context_len:])
        ctx = np.asarray(mats, dtype=np.int64)
        logits = self.logits(ctx)
        return [softmax(logits[i]) for i in range(logits.shape[0])]

    # -- training ---------------------------------------------------------

    def cross_entropy(self, xs: np.ndarray, ys: np.ndarray) -> float:
        logp = np.log(softmax(self.logits(xs)) + 1e-12)
        return float(-np.mean(logp[np.arange(ys.shape[0]), ys]))

    def train(
        self,
        text: str,
        iterations: int = 300,
        learning_rate: float = 0.05,
        batch_size: int = 64,
        weight_decay: float = 1e-4,
        quiet: bool = True,
    ) -> List[float]:
        """Real mini-batch gradient descent on real cross-entropy."""
        xs, ys = self._contexts(text)
        n = xs.shape[0]
        losses: List[float] = []
        rng = np.random.default_rng(7)
        for it in range(iterations):
            idx = rng.choice(n, size=min(batch_size, n), replace=False)
            Xb = self._one_hot(xs[idx])
            yb = ys[idx]
            h = np.tanh(Xb @ self.W1 + self.b1)
            lrng = self._logits_from_hidden(h)
            p = softmax(lrng)
            loss = float(-np.mean(np.log(p[np.arange(yb.shape[0]), yb] + 1e-12)))
            losses.append(loss)

            dz = p.copy()
            dz[np.arange(yb.shape[0]), yb] -= 1.0

            dW2 = h.T @ dz
            db2 = dz.sum(axis=0)
            dh = dz @ self.W2.T * (1.0 - h * h)
            dW1 = Xb.T @ dh
            db1 = dh.sum(axis=0)

            self.W2 -= learning_rate * (dW2 + weight_decay * self.W2)
            self.b2 -= learning_rate * db2
            self.W1 -= learning_rate * (dW1 + weight_decay * self.W1)
            self.b1 -= learning_rate * db1

            if not quiet and (it % 50 == 0 or it == iterations - 1):
                print(f"  iter {it}: loss {loss:.4f}")
        self._trained = True
        return losses

    def _logits_from_hidden(self, h: np.ndarray) -> np.ndarray:
        return h @ self.W2 + self.b2

    # -- accuracy / metrics ------------------------------------------------

    def accuracy(self, text: str) -> float:
        xs, ys = self._contexts(text)
        preds = np.argmax(softmax(self.logits(xs)), axis=-1)
        return float(np.mean(preds == ys))

    def perplexity(self, text: str) -> float:
        xs, ys = self._contexts(text)
        ce = self.cross_entropy(xs, ys)
        return float(np.exp(ce))

    def precision_recall_f1(self, text: str) -> Tuple[float, float, float]:
        """Macro-averaged precision/recall/F1 over vocab classes. Real counts."""
        xs, ys = self._contexts(text)
        preds = np.argmax(softmax(self.logits(xs)), axis=-1)
        eps = 1e-12
        precisions, recalls, f1s = [], [], []
        for c in range(self.vocab_size):
            tp = float(np.sum((preds == c) & (ys == c)))
            fp = float(np.sum((preds == c) & (ys != c)))
            fn = float(np.sum((preds != c) & (ys == c)))
            p = tp / (tp + fp + eps)
            r = tp / (tp + fn + eps)
            precisions.append(p)
            recalls.append(r)
            f1s.append(2 * p * r / (p + r + eps) if (p + r) > 0 else 0.0)
        return float(np.mean(precisions)), float(np.mean(recalls)), float(np.mean(f1s))

    def logits_timed(self, ctx: np.ndarray) -> np.ndarray:
        return self.logits(ctx)

    # -- persistence -------------------------------------------------------

    def param_count(self) -> int:
        return int(self.W1.size + self.b1.size + self.W2.size + self.b2.size)

    def model_bytes(self) -> int:
        total = 0
        for arr in (self.W1, self.b1, self.W2, self.b2):
            total += arr.nbytes
        return total

    def state_dict(self) -> dict:
        return {
            "W1": self.W1, "b1": self.b1, "W2": self.W2, "b2": self.b2,
        }

    def load_state(self, state: dict) -> None:
        self.W1 = np.asarray(state["W1"], dtype=np.float64)
        self.b1 = np.asarray(state["b1"], dtype=np.float64)
        self.W2 = np.asarray(state["W2"], dtype=np.float64)
        self.b2 = np.asarray(state["b2"], dtype=np.float64)

    def save(self, path: str) -> str:
        path = str(path)
        if not path.endswith(".npz"):
            path += ".npz"
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        meta = {
            "vocab": self.vocab,
            "context_len": self.context_len,
            "hidden": self.hidden,
            "trained": self._trained,
        }
        np.savez_compressed(path, vocab=json.dumps(meta["vocab"]),
                            context_len=self.context_len, hidden=self.hidden,
                            trained=int(self._trained),
                            W1=self.W1, b1=self.b1, W2=self.W2, b2=self.b2)
        return path

    @classmethod
    def load(cls, path: str, strict: bool = True) -> "CharMLP":
        data = np.load(str(path), allow_pickle=True)
        meta = json.loads(str(data["vocab"]))
        model = cls(vocab=meta, context_len=int(data["context_len"]),
                    hidden=int(data["hidden"]), seed=0)
        model.load_state({
            "W1": data["W1"], "b1": data["b1"],
            "W2": data["W2"], "b2": data["b2"],
        })
        if "trained" in data:
            model._trained = bool(data["trained"])
        return model

    def _npz_meta(self) -> dict:
        return {}


def train_default_model(
    path: str, hidden: int = 48, iterations: int = 400, quiet: bool = True
) -> str:
    """Train the built-in demo model and persist it to real weights on disk."""
    model = CharMLP(hidden=hidden, seed=0)
    corpus = make_corpus()
    model.train(corpus, iterations=iterations, quiet=quiet)
    model.save(path)
    return str(path)