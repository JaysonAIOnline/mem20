"""Checkpoint persistence for NumPy and optional Torch policies."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

try:
    import torch

    TORCH_AVAILABLE = True
except ImportError:
    torch = None
    TORCH_AVAILABLE = False


@dataclass
class ModelCheckpoint:
    step: int
    trainer_type: str
    settings: dict[str, Any]
    metrics: dict[str, float]
    path: str


class ModelSaver:
    """Save complete policy parameters and retain a bounded checkpoint history."""

    def __init__(self, save_dir: str, max_checkpoints: int = 5) -> None:
        if int(max_checkpoints) < 1:
            raise ValueError("max_checkpoints must be positive")
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.max_checkpoints = int(max_checkpoints)
        self.checkpoints: list[ModelCheckpoint] = []

    def save(
        self,
        policy: Any,
        optimizer: Any = None,
        step: int = 0,
        metrics: dict[str, float] | None = None,
        trainer_type: str = "ppo",
        settings: dict[str, Any] | None = None,
    ) -> str:
        """Persist real parameters; metadata-only checkpoints are rejected."""
        if policy is None or not hasattr(policy, "state_dict"):
            raise TypeError("policy must expose a state_dict method")
        metric_values = {key: float(value) for key, value in (metrics or {}).items()}
        setting_values = dict(settings or {})
        metadata = {
            "step": int(step),
            "trainer_type": str(trainer_type),
            "settings": setting_values,
            "metrics": metric_values,
        }
        state = policy.state_dict()
        if TORCH_AVAILABLE and isinstance(policy, torch.nn.Module):
            path = self.save_dir / f"checkpoint_{int(step)}.pt"
            torch.save(
                {
                    **metadata,
                    "policy_state_dict": state,
                    "optimizer_state_dict": optimizer.state_dict() if optimizer else None,
                },
                path,
            )
        else:
            if not isinstance(state, dict) or not state:
                raise TypeError("policy state_dict must contain parameter arrays")
            path = self.save_dir / f"checkpoint_{int(step)}.npz"
            np.savez(
                path,
                metadata=np.asarray(json.dumps(metadata, sort_keys=True)),
                **{key: np.asarray(value) for key, value in state.items()},
            )
        checkpoint = ModelCheckpoint(
            step=int(step),
            trainer_type=str(trainer_type),
            settings=setting_values,
            metrics=metric_values,
            path=str(path),
        )
        self.checkpoints.append(checkpoint)
        self._cleanup()
        return str(path)

    def load(self, path: str, policy: Any = None, optimizer: Any = None) -> dict[str, Any]:
        """Load a checkpoint and optionally restore policy and optimizer state."""
        source = Path(path)
        if not source.exists():
            raise FileNotFoundError(source)
        if source.suffix == ".npz":
            with np.load(source, allow_pickle=False) as archive:
                metadata = json.loads(str(archive["metadata"].item()))
                state = {key: archive[key].copy() for key in archive.files if key != "metadata"}
        elif source.suffix == ".pt":
            if not TORCH_AVAILABLE:
                raise RuntimeError("PyTorch is required to load a .pt checkpoint")
            checkpoint = torch.load(source, map_location="cpu")
            metadata = {key: checkpoint[key] for key in ("step", "trainer_type", "settings", "metrics")}
            state = checkpoint["policy_state_dict"]
            if optimizer is not None and checkpoint.get("optimizer_state_dict") is not None:
                optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        elif source.suffix == ".json":
            with source.open("r", encoding="utf-8") as handle:
                metadata = json.load(handle)
            state = metadata.pop("policy_state", None)
            if not isinstance(state, dict):
                raise ValueError("JSON checkpoint does not contain policy parameters")
        else:
            raise ValueError(f"unsupported checkpoint format: {source.suffix}")
        if policy is not None:
            if not hasattr(policy, "load_state_dict"):
                raise TypeError("policy must expose load_state_dict")
            policy.load_state_dict(state)
        result = dict(metadata)
        result["policy_state"] = state
        return result

    def _cleanup(self) -> None:
        self.checkpoints.sort(key=lambda item: item.step)
        while len(self.checkpoints) > self.max_checkpoints:
            old = self.checkpoints.pop(0)
            old_path = Path(old.path)
            if old_path.exists():
                old_path.unlink()

    def get_latest_checkpoint(self) -> ModelCheckpoint | None:
        if not self.checkpoints:
            return None
        return max(self.checkpoints, key=lambda item: item.step)

    def list_checkpoints(self) -> list[ModelCheckpoint]:
        return sorted(self.checkpoints, key=lambda item: item.step)
