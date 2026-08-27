"""
The countermeasure: task-naive wav2vec2 features + our own persisted linear probe.

Closes SPEC Gap 1. run_experiment_v2.py fits a LogisticRegression in memory and
throws it away; a live system cannot refit on startup, and a demo that refits
would be scoring with a different model each run. scripts/fit_probe.py writes
the coefficients out; LogisticHead reads them back.

LogisticHead is deliberately plain numpy rather than a pickled sklearn estimator:
a pickle ties the demo to one sklearn version and fails opaquely when it drifts,
which is exactly the kind of thing that breaks at 2am before a finale.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, Optional

import numpy as np

from sentinel.models import registry


class LogisticHead:
    """
    sklearn's LogisticRegression decision rule, reimplemented in eight lines.

    predict_proba(X)[:, 1] == sigmoid(X @ coef_.T + intercept_) for a binary
    fit. scripts/fit_probe.py asserts this reproduces the experiment's EER, so
    the equivalence is checked rather than assumed.
    """

    def __init__(self, coef: np.ndarray, intercept: float, meta: Optional[Dict[str, Any]] = None):
        self.coef = np.asarray(coef, dtype=np.float64).reshape(-1)
        self.intercept = float(intercept)
        self.meta = meta or {}

    @property
    def dim(self) -> int:
        return int(self.coef.shape[0])

    def proba(self, emb: np.ndarray) -> float:
        """P(spoof) for one embedding."""
        emb = np.asarray(emb, dtype=np.float64).reshape(-1)
        if emb.shape[0] != self.dim:
            raise ValueError(
                f"embedding dim {emb.shape[0]} != probe head dim {self.dim}. "
                "The backbone and the persisted head disagree -- refit with "
                "scripts/fit_probe.py."
            )
        z = float(np.dot(self.coef, emb) + self.intercept)
        return float(1.0 / (1.0 + np.exp(-z)))

    def save(self, path: str, **meta: Any) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        np.savez(
            path,
            coef=self.coef,
            intercept=np.array([self.intercept]),
            meta=np.array([json.dumps({**self.meta, **meta})]),
        )

    @staticmethod
    def load(path: str) -> "LogisticHead":
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"probe head not found: {path}\n"
                "Run: ../detector/venv/bin/python scripts/fit_probe.py"
            )
        with np.load(path, allow_pickle=False) as data:
            meta = json.loads(str(data["meta"][0])) if "meta" in data else {}
            return LogisticHead(data["coef"], float(data["intercept"][0]), meta)

    @staticmethod
    def fingerprint(path: str) -> str:
        """Short content hash, so the evidence log records which head decided."""
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()[:12]


class ProbeCountermeasure:
    """CountermeasureModel: raw PCM -> P(synthetic) in [0,1]."""

    def __init__(self, head_path: str, device: str = "auto", backbone: Any = None,
                 backbone_id: Optional[str] = None):
        self.head = LogisticHead.load(head_path)
        fit_backbone = self.head.meta.get("backbone")
        if backbone is None and backbone_id and fit_backbone and backbone_id != fit_backbone:
            raise ValueError(
                f"models.cm_backbone_id={backbone_id!r} does not match the backbone "
                f"{fit_backbone!r} that {head_path} was fit on. Re-run "
                "scripts/fit_probe.py after changing the backbone, or revert the config."
            )
        self.backbone = backbone if backbone is not None else registry.probe_backbone(
            device, model_id=backbone_id
        )
        self.model_id = f"probe-cm:{fit_backbone or 'unknown-backbone'}@{LogisticHead.fingerprint(head_path)}"

    def embed(self, pcm: np.ndarray, sr: int) -> np.ndarray:
        return self.backbone.embed(np.asarray(pcm, dtype=np.float32), sr)

    def risk(self, pcm: np.ndarray, sr: int) -> float:
        """[0,1]; higher = more likely synthetic. Already the right orientation."""
        return self.head.proba(self.embed(pcm, sr))
