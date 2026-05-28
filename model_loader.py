import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import torch

log = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).parent / "model"

_model: torch.jit.ScriptModule | None = None
_metadata: dict[str, Any] = {}
_scaler_mean: np.ndarray | None = None
_scaler_scale: np.ndarray | None = None
_labels: list[str] = []


def load_model() -> None:
    global _model, _metadata, _scaler_mean, _scaler_scale, _labels

    with open(MODEL_DIR / "preprocessing_metadata.json") as f:
        _metadata = json.load(f)

    _scaler_mean = np.array(_metadata["scaler_mean"], dtype=np.float32)
    _scaler_scale = np.array(_metadata["scaler_scale"], dtype=np.float32)
    _labels = _metadata["class_labels"]

    model = torch.jit.load(str(MODEL_DIR / "gesture_model_torchscript.pt"), map_location="cpu")
    model.eval()
    _model = model

    log.info(
        "Loaded gesture model: window=%d, features=%d, classes=%d",
        _metadata["window_size"],
        _metadata["scaler_n_features_in"],
        len(_labels),
    )


def predict(points: list) -> dict[str, Any]:
    if _model is None or _scaler_mean is None or _scaler_scale is None:
        raise RuntimeError("Model not loaded; call load_model() at startup")

    window_size = _metadata["window_size"]
    n_features = _metadata["scaler_n_features_in"]

    arr = np.asarray(points, dtype=np.float32)
    if arr.ndim == 2:
        arr = arr[np.newaxis, ...]
    if arr.ndim != 3 or arr.shape[1] != window_size or arr.shape[2] != n_features:
        raise ValueError(
            f"expected shape [batch, {window_size}, {n_features}], got {arr.shape}"
        )

    arr = (arr - _scaler_mean) / _scaler_scale
    arr = arr.transpose(0, 2, 1)

    with torch.no_grad():
        logits = _model(torch.from_numpy(arr))
        probs = torch.softmax(logits, dim=1).cpu().numpy()

    top_idx = int(probs[0].argmax())
    return {
        "label": _labels[top_idx],
        "confidence": float(probs[0, top_idx]),
        "probabilities": {_labels[i]: float(probs[0, i]) for i in range(len(_labels))},
    }
