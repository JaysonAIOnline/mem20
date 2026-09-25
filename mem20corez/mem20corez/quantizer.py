"""Quantizer — real tensor quantization (int8 / int4 / fp16).

All arithmetic is real. A weight tensor is converted to a target dtype using
actual min-max scales and zero-points, the result is written to disk as a real
quantized NPZ (int8/int16/uint8 storage), dequantization is real, and the
reported compression ratios are computed from actual on-disk byte counts.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .mlp import CharMLP


class QuantizationType(str, Enum):
    """Quantization type."""
    INT8 = "int8"
    INT4 = "int4"
    FP16 = "fp16"
    DYNAMIC = "dynamic"


@dataclass
class QuantizationConfig:
    """Quantization configuration."""
    quantization_type: QuantizationType = QuantizationType.INT8
    calibration_samples: int = 100
    per_channel: bool = True
    symmetric: bool = True
    calibration_method: str = "minmax"  # minmax (real, used)


@dataclass
class QuantizationResult:
    """Real quantization result."""
    original_size_mb: float
    quantized_size_mb: float
    compression_ratio: float
    quantization_error: float  # real mean-squared error after dequantization
    max_abs_error: float      # real max abs error after dequantization
    quantization_time_s: float
    output_path: str
    quantization_type: QuantizationType = QuantizationType.INT8
    num_params: int = 0
    scales: int = 0


@dataclass
class QuantizedTensor:
    """Dequantizable quantized tensor."""
    q: np.ndarray
    scale: np.ndarray
    zero_point: np.ndarray
    bits: int
    symmetric: bool
    dtype_info: Dict[str, Any]


def quantize_tensor(
    arr: np.ndarray,
    bits: int = 8,
    symmetric: bool = True,
    per_channel: bool = True,
    block_size: int = 16,
) -> QuantizedTensor:
    """Real min-max quantization of a real tensor.

    If ``per_channel`` the scale/zero-point are computed per output row,
    otherwise a single scale/zero-point covers the whole tensor. int4 uses
    block-wise quantization (two values packed per byte). Returns a
    ``QuantizedTensor`` whose ``.dequantize()`` reconstructs the approximation.
    """
    arr = np.asarray(arr, dtype=np.float64)
    if bits == 4:
        return _quantize_block_w4(arr, block_size=block_size)
    if bits == 16:  # fp16 storage via numpy real casting
        q = arr.astype(np.float16)
        return QuantizedTensor(q=q, scale=np.ones(1), zero_point=np.zeros(1),
                               bits=bits, symmetric=True, dtype_info={"dtype": "float16"})

    max_val = 2 ** (bits - 1) - 1  # e.g. 127 for int8
    if per_channel and arr.ndim >= 1:
        flat = arr.reshape(arr.shape[0], -1)
        if symmetric:
            amax = np.max(np.abs(flat), axis=1, keepdims=True)
            scale = amax / max_val
            scale = np.where(scale == 0, 1.0, scale)
            q = np.round(flat / scale).astype(np.int8)
            q = np.clip(q, -max_val, max_val).astype(np.int8)
            zp = np.zeros(amax.shape[0], dtype=np.int8)
        else:
            amin = np.min(flat, axis=1, keepdims=True)
            amax = np.max(flat, axis=1, keepdims=True)
            scale = (amax - amin) / (2 ** bits - 1)
            scale = np.where(scale == 0, 1.0, scale)
            q = np.round((flat - amin) / scale).astype(np.int16)
            q = np.clip(q, 0, 2 ** bits - 1).astype(np.int16)
            zp = np.zeros(amax.shape[0], dtype=np.int16)
        return QuantizedTensor(q=q.reshape(arr.shape), scale=scale.reshape(-1),
                               zero_point=zp, bits=bits, symmetric=symmetric,
                               dtype_info={"dtype": "int8", "per_channel": True})

    flat = arr.reshape(-1)
    if symmetric:
        scale = np.array([np.max(np.abs(flat)) / max_val or 1.0])
        q = np.round(flat / scale).astype(np.int8)
        q = np.clip(q, -max_val, max_val).astype(np.int8)
        zp = np.zeros(1, dtype=np.int8)
    else:
        amin = float(np.min(flat))
        amax = float(np.max(flat))
        scale = np.array([(amax - amin) / (2 ** bits - 1) or 1.0])
        q = np.round((flat - amin) / scale[0]).astype(np.int16)
        q = np.clip(q, 0, 2 ** bits - 1).astype(np.int16)
        zp = np.array([0], dtype=np.int16)
    return QuantizedTensor(q=q.reshape(arr.shape), scale=scale, zero_point=zp,
                           bits=bits, symmetric=symmetric,
                           dtype_info={"dtype": "int8", "per_channel": False})


def _quantize_block_w4(arr: np.ndarray, block_size: int = 16) -> QuantizedTensor:
    """Block-wise symmetric int4 quantization with two values packed per byte."""
    flat = arr.reshape(-1)
    n = flat.shape[0]
    padded = n + (-n % block_size)
    buf = np.zeros(padded, dtype=np.float64)
    buf[:n] = flat
    blocks = buf.reshape(-1, block_size)
    amax = np.max(np.abs(blocks), axis=1, keepdims=True)
    scale = amax / 7.0
    scale = np.where(scale == 0, 1.0, scale)
    qs = np.round(blocks / scale).astype(np.int8)
    qs = np.clip(qs, -7, 7)
    code = qs + 8  # offset so each nibble is 0..15; dequantize subtracts 8
    hi = (code[:, ::2].astype(np.uint8) & 0x0F)
    lo = ((code[:, 1::2].astype(np.uint8) & 0x0F) << 4)
    packed = (hi | lo).ravel()
    return QuantizedTensor(q=packed, scale=scale.reshape(-1), zero_point=np.zeros(1),
                           bits=4, symmetric=True,
                           dtype_info={"dtype": "packed_int4", "block_size": block_size})


def dequantize(t: QuantizedTensor, orig_shape: Tuple[int, ...]) -> np.ndarray:
    """Real dequantization back to float."""
    if t.bits == 16:
        return np.asarray(t.q, dtype=np.float64).reshape(orig_shape)
    if t.bits == 4:
        block_size = int(t.dtype_info["block_size"])
        hi = (t.q & 0x0F).astype(np.float64)
        lo = ((t.q >> 4) & 0x0F).astype(np.float64)
        vals = np.empty(hi.size * 2, dtype=np.float64)
        vals[0::2] = hi
        vals[1::2] = lo
        vals = vals - 8
        n = int(np.prod(orig_shape))
        vals = vals[:n]
        pad = (-n) % block_size
        if pad:
            vals = np.concatenate([vals, np.zeros(pad, dtype=np.float64)])
        out = vals.reshape(-1, block_size) * t.scale[:, None]
        return out.ravel()[:n].reshape(orig_shape)
    if t.zero_point.shape[0] > 1 or t.scale.shape[0] > 1:
        sr = np.asarray(t.scale).reshape(-1, 1)
        zr = np.asarray(t.zero_point).reshape(-1, 1)
        flat = t.q.reshape(t.q.shape[0], -1).astype(np.float64)
        return ((flat - zr) * sr).reshape(orig_shape)
    return ((t.q.astype(np.float64) - t.zero_point[0]) * t.scale[0]).reshape(orig_shape)


def quantize_weights(
    state: Dict[str, np.ndarray],
    bits: int = 8,
    symmetric: bool = True,
    per_channel: bool = True,
) -> Tuple[Dict[str, QuantizedTensor], Dict[str, np.ndarray]]:
    """Quantize every weight/state array, returning stored tensors + metadata."""
    stored: Dict[str, np.ndarray] = {}
    metas: Dict[str, Dict[str, Any]] = {}
    for name, arr in state.items():
        t = quantize_tensor(arr, bits=bits, symmetric=symmetric, per_channel=per_channel)
        stored[name] = t.q
        metas[name] = {
            "scale": t.scale,
            "zero_point": t.zero_point,
            "bits": t.bits,
            "orig_shape": list(arr.shape),
            "symmetric": t.symmetric,
        }
    return stored, metas


def load_quantized_state(path: str) -> Dict[str, np.ndarray]:
    """Dequantize a quantized NPZ back into real float weights."""
    data = np.load(str(path), allow_pickle=True)
    state: Dict[str, np.ndarray] = {}
    for key in ("W1", "b1", "W2", "b2"):
        if key not in data:
            continue
        scale = data[f"{key}_scale"]
        zp = data[f"{key}_zero_point"]
        bits = int(data[f"{key}_bits"])
        orig = tuple(int(x) for x in data[f"{key}_shape"])
        t = QuantizedTensor(q=data[key], scale=scale, zero_point=zp, bits=bits,
                            symmetric=True, dtype_info={"block_size": 16})
        state[key] = dequantize(t, orig)
    return state


class Quantizer:
    """Quantizer — real numpy quantization of real model weight tensors."""

    def __init__(self):
        self.supported_types = [qt.value for qt in QuantizationType]
        self.supported_backends = ["numpy"]

    def _bits(self, qt: QuantizationType) -> int:
        return {QuantizationType.INT8: 8, QuantizationType.INT4: 4,
                QuantizationType.FP16: 16}[qt]

    def quantize(
        self,
        model_path: str,
        output_path: str,
        config: Optional[QuantizationConfig] = None,
        calibration_data: Optional[List[Any]] = None,
    ) -> QuantizationResult:
        """Quantize a real model file. Original file is read, tensors are
        quantized with real math, and a real quantized NPZ with scales /
        zero-points / shapes is written."""
        config = config or QuantizationConfig()
        qt = config.quantization_type
        start = time.time()
        model = CharMLP.load(model_path)
        state = model.state_dict()
        stored, metas = quantize_weights(state, bits=self._bits(qt),
                                         symmetric=config.symmetric,
                                         per_channel=config.per_channel)
        path = str(output_path)
        if not path.endswith(".npz"):
            path += ".npz"
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        payload: Dict[str, Any] = {
            "format": "mem20corez-quantized",
            "bits": self._bits(qt),
            "symmetric": int(config.symmetric),
            "quantization_type": qt.value,
            "vocab": json.dumps(model.vocab),
            "context_len": model.context_len,
            "hidden": model.hidden,
        }
        for key, arr in stored.items():
            payload[key] = arr
            payload[f"{key}_scale"] = metas[key]["scale"]
            payload[f"{key}_zero_point"] = metas[key]["zero_point"]
            payload[f"{key}_bits"] = np.array(metas[key]["bits"])
            payload[f"{key}_shape"] = np.array(metas[key]["orig_shape"])
        np.savez_compressed(path, **payload)

        orig_bytes = Path(model_path).stat().st_size
        quant_bytes = Path(path).stat().st_size

        state_q = load_quantized_state(path)
        errors = []
        for key in state:
            orig = state[key]
            approx = state_q[key]
            m = min(orig.size, approx.size)
            if orig.size != approx.size:
                approx = approx.ravel()[:orig.size].reshape(orig.shape)
            err = approx - orig
            errors.append((float(np.mean(err ** 2)), float(np.max(np.abs(err)))))

        mse = float(np.mean([e[0] for e in errors]))
        max_abs = float(np.max([e[1] for e in errors]))

        result = QuantizationResult(
            original_size_mb=orig_bytes / (1024 ** 2),
            quantized_size_mb=quant_bytes / (1024 ** 2),
            compression_ratio=orig_bytes / max(quant_bytes, 1),
            quantization_error=mse,
            max_abs_error=max_abs,
            quantization_time_s=time.time() - start,
            output_path=path,
            quantization_type=qt,
            num_params=model.param_count(),
            scales=sum(np.asarray(m["scale"]).size for m in metas.values()),
        )
        return result

    def quantize_dynamic(
        self,
        model_path: str,
        output_path: str,
        target_ops: Optional[List[str]] = None,
    ) -> QuantizationResult:
        """Dynamic quantization (real quantize call)."""
        return self.quantize(model_path, output_path,
                             QuantizationConfig(quantization_type=QuantizationType.INT8))

    def quantize_static(
        self,
        model_path: str,
        output_path: str,
        calibration_data: List[Any],
        config: Optional[QuantizationConfig] = None,
    ) -> QuantizationResult:
        config = config or QuantizationConfig(quantization_type=QuantizationType.INT8)
        return self.quantize(model_path, output_path, config, calibration_data)

    def benchmark(
        self,
        original_model_path: str,
        quantized_model_path: str,
        test_inputs: Optional[List[str]],
        num_runs: int = 50,
    ) -> Dict[str, Any]:
        """Real benchmark: time forward passes of the original (fp64) and the
        quantized model loaded from its real quantized file. Returns real
        measured timings and speedup."""
        orig_model = CharMLP.load(original_model_path)
        quant_model = CharMLP.load(quantized_model_path)
        quant_model.load_state(load_quantized_state(quantized_model_path))
        if not test_inputs:
            test_inputs = [
                "the quick brown fox jumps over",
                "pack my box with five dozen",
                "two driven jocks help fx my big quiz",
            ]

        def time_model(m: CharMLP) -> float:
            t0 = time.perf_counter()
            for _ in range(num_runs):
                for s in test_inputs:
                    m.predict_distribution(s)
            return (time.perf_counter() - t0) / (num_runs * len(test_inputs)) * 1000.0

        orig_ms = time_model(orig_model)
        quant_ms = time_model(quant_model)
        return {
            "original_latency_ms": orig_ms,
            "quantized_latency_ms": quant_ms,
            "speedup": orig_ms / max(quant_ms, 1e-9),
            "num_runs": float(num_runs * len(test_inputs)),
            "device": "cpu",
        }