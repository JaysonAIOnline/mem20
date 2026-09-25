"""Real classical-computer-vision feature engine (numpy + PIL).

This is the "real" inference path. Every number here is computed from actual
pixels of the input image: dimensions, channels, per-channel statistics,
luminance histogram, edge energy (via discrete gradient), and a fixed-size
feature embedding. It is deterministic and honest — it genuinely analyzes the
image; it just does not claim object semantics it cannot know.
"""
from __future__ import annotations

import base64
import io
import os
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from PIL import Image

EDGE_ENERGY_BINS = 16
FEATURE_EMBED_DIM = 128


class CvEngineError(RuntimeError):
    pass


def load_image(image_path: str | None = None, frame_blob_b64: str | None = None) -> np.ndarray:
    """Load an image from path or base64 raw blob into an HxWx3 uint8 array.

    Accepts PNG/JPEG and raw RGB frames. Raises CvEngineError on failure.
    """
    if image_path and frame_blob_b64:
        raise CvEngineError("provide exactly one of image_path / frame_blob")
    if frame_blob_b64:
        try:
            raw = base64.b64decode(frame_blob_b64, validate=True)
        except Exception as e:  # noqa: BLE001
            raise CvEngineError(f"invalid base64 frame blob: {e}") from e
        try:
            img = Image.open(io.BytesIO(raw))
            arr = np.asarray(img)
        except Exception as e:  # noqa: BLE001
            raise CvEngineError(f"unable to decode frame blob: {e}") from e
    elif image_path:
        if not os.path.isfile(image_path):
            raise CvEngineError(f"image file not found: {image_path}")
        try:
            with Image.open(image_path) as img:
                arr = np.asarray(img)
        except Exception as e:  # noqa: BLE001
            raise CvEngineError(f"unable to open image {image_path}: {e}") from e
    else:
        raise CvEngineError("image_path or frame_blob required")
    return _to_uint8_rgb(arr)


def _to_uint8_rgb(arr: np.ndarray) -> np.ndarray:
    if arr.dtype != np.uint8:
        arr = np.clip(arr, 0, 255).astype(np.uint8)
    if arr.ndim == 2:  # grayscale -> RGB
        arr = np.stack([arr] * 3, axis=-1)
    elif arr.ndim == 3:
        if arr.shape[2] == 1:
            arr = np.repeat(arr, 3, axis=2)
        elif arr.shape[2] == 4:  # RGBA -> RGB
            arr = arr[:, :, :3]
        elif arr.shape[2] != 3:
            raise CvEngineError(f"unsupported channel count: {arr.shape[2]}")
    else:
        raise CvEngineError(f"unsupported image rank: {arr.ndim}")
    return np.ascontiguousarray(arr)


def _edge_energy(gray: np.ndarray) -> tuple[float, np.ndarray]:
    """Edge energy via finite-difference gradient magnitude, in [0..1].

    Returns (mean_edge_energy, histogram over EDGE_ENERGY_BINS).
    """
    gy, gx = np.gradient(gray.astype(np.float32) / 255.0)
    mag = np.sqrt(gx * gx + gy * gy)
    mean = float(np.mean(mag) / np.sqrt(2.0))  # normalize by max possible
    hist, _ = np.histogram(mag, bins=EDGE_ENERGY_BINS, range=(0.0, np.sqrt(2.0)))
    total = hist.sum()
    hist = hist.astype(np.float64)
    if total > 0:
        hist = hist / total
    return mean, hist


def _luminance_histogram(gray: np.ndarray, bins: int = 32) -> np.ndarray:
    hist, _ = np.histogram(gray, bins=bins, range=(0, 256))
    total = hist.sum()
    if total > 0:
        hist = hist.astype(np.float64) / total
    return hist


def _dominant_colors(rgb: np.ndarray, k: int = 6) -> list[dict[str, Any]]:
    """Dominant colors by coarse quantization + mode.

    Real computation: bucket each pixel to a 16x16x16 color cube, take the top-k
    most frequent cubes, and return their centroid color + fraction.
    """
    small = rgb[:: max(1, rgb.shape[0] // 96), :: max(1, rgb.shape[1] // 96)]
    px = small.reshape(-1, 3).astype(np.int32)
    n = len(px)
    if n == 0:
        return []
    bucket = (px // 16)
    key = bucket[:, 0] * 256 + bucket[:, 1] * 16 + bucket[:, 2]
    unique, counts = np.unique(key, return_counts=True)
    order = np.argsort(-counts)[:k]
    out = []
    for idx in order:
        u = unique[idx]
        b, g, r = u // 256, (u // 16) % 16, u % 16
        mask = key == u
        centroid = px[mask].mean(axis=0)
        out.append({
            "r": int(round(centroid[0])),
            "g": int(round(centroid[1])),
            "b": int(round(centroid[2])),
            "fraction": round(float(counts[idx]) / n, 5),
        })
    return out


@dataclass(slots=True)
class FeatureResult:
    width: int
    height: int
    channels: int
    mean_r: float
    mean_g: float
    mean_b: float
    std_r: float
    std_g: float
    std_b: float
    luminance_mean: float
    luminance_std: float
    edge_mean_energy: float
    edge_energy_histogram: list[float] = field(default_factory=list)
    luminance_histogram: list[float] = field(default_factory=list)
    dominant_colors: list[dict[str, Any]] = field(default_factory=list)
    embedding: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict
        d = dict(asdict(self))
        d["edge_energy_histogram"] = [round(float(x), 6) for x in d["edge_energy_histogram"]]
        d["luminance_histogram"] = [round(float(x), 6) for x in d["luminance_histogram"]]
        d["embedding"] = [round(float(x), 6) for x in d["embedding"]]
        return d


def compute_features(
    image_path: str | None = None,
    frame_blob_b64: str | None = None,
    array: np.ndarray | None = None,
    embed_dim: int = FEATURE_EMBED_DIM,
) -> FeatureResult:
    """Run the real classical-CV pipeline on an image. Deterministic."""
    if array is None:
        array = load_image(image_path, frame_blob_b64)
    rgb = _to_uint8_rgb(array)
    h, w, c = rgb.shape
    gray = rgb[:, :, 0] * 0.299 + rgb[:, :, 1] * 0.587 + rgb[:, :, 2] * 0.114

    edge_mean, edge_hist = _edge_energy(gray)
    lum_hist = _luminance_histogram(gray)
    dominant = _dominant_colors(rgb)

    feats = {
        "width": w, "height": h, "channels": 3,
        "mean_r": float(rgb[:, :, 0].mean()), "mean_g": float(rgb[:, :, 1].mean()),
        "mean_b": float(rgb[:, :, 2].mean()),
        "std_r": float(rgb[:, :, 0].std()), "std_g": float(rgb[:, :, 1].std()),
        "std_b": float(rgb[:, :, 2].std()),
        "luminance_mean": float(gray.mean()), "luminance_std": float(gray.std()),
        "edge_mean_energy": edge_mean,
        "edge_energy_histogram": edge_hist.tolist(),
        "luminance_histogram": lum_hist.tolist(),
    }

    # Build a deterministic fixed-size embedding from real statistics:
    embed = []
    embed.extend([feats["mean_r"], feats["mean_g"], feats["mean_b"],
                  feats["std_r"], feats["std_g"], feats["std_b"],
                  feats["luminance_mean"], feats["luminance_std"],
                  feats["edge_mean_energy"]])
    hist = np.concatenate([lum_hist])[: embed_dim - len(embed)]
    embed.extend(hist.tolist())
    if len(embed) < embed_dim:
        embed.extend([0.0] * (embed_dim - len(embed)))
    embed = embed[:embed_dim]

    return FeatureResult(
        width=w, height=h, channels=3,
        mean_r=round(feats["mean_r"], 4), mean_g=round(feats["mean_g"], 4),
        mean_b=round(feats["mean_b"], 4),
        std_r=round(feats["std_r"], 4), std_g=round(feats["std_g"], 4),
        std_b=round(feats["std_b"], 4),
        luminance_mean=round(feats["luminance_mean"], 4),
        luminance_std=round(feats["luminance_std"], 4),
        edge_mean_energy=round(edge_mean, 6),
        edge_energy_histogram=edge_hist.tolist(),
        luminance_histogram=lum_hist.tolist(),
        dominant_colors=dominant,
        embedding=embed,
    )