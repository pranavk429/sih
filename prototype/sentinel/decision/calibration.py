"""
Loads calibration.json and answers "what does this number mean?"

This is the module that keeps the project honest. Every risk shown on screen and
every verdict in the evidence log carries a `calibration_id` that points back to
the exact file -- dataset, EER, thresholds, provenance -- that produced it. When
the Kaggle full-scale run lands and calibration.json is replaced, old decisions
stay attributable to the old numbers instead of being silently reinterpreted
under the new ones.

On the mapping: today it is the identity. The probe head already emits a
probability and MeanFusion averages two of them, so the fused score is already
in [0,1] and the thresholds in config.yaml were derived in that same space.
Inventing a sigmoid or a Platt scaling we have not validated would make the
number look more principled while making it less true. The mapping is declared
in calibration.json so a real one can be dropped in later without a code change.

What the per-class statistics ARE used for is `sigma_above_genuine()`, which
turns "cm risk 0.82" into "2.0 standard deviations above the genuine mean on the
calibration set". That is the sentence that belongs in an evidence panel.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, Optional

SUPPORTED_MAPPINGS = ("identity", "affine")


class CalibrationError(Exception):
    """calibration.json is missing or unusable. Never silently defaulted."""


class Calibration:
    """A loaded calibration.json, with the numbers the rest of the system asks for."""

    def __init__(self, data: Dict[str, Any], calibration_id: str, path: str) -> None:
        self.data = data
        self.calibration_id = calibration_id
        self.path = path

        self.eer = float(data["eer"])
        self.eer_threshold = float(data["eer_threshold"])
        self.dataset = str(data.get("dataset", "unknown"))
        self.created_utc = str(data.get("created_utc", ""))
        self.backbone = str(data.get("backbone", "unknown"))
        self.notes = str(data.get("notes", ""))
        self.n_test_trials = int(data.get("n_test_trials", 0))
        self.n_test_speakers = int(data.get("n_test_speakers", 0))

        fusion = data.get("fusion", {}) or {}
        self.fusion_strategy = str(fusion.get("strategy", "mean"))
        self.fusion_weights = [float(w) for w in fusion.get("weights", [0.5, 0.5])]

        band = data.get("decision_band", {}) or {}
        self.band_low = float(band.get("low_thr", self.eer_threshold))
        self.band_high = float(band.get("high_thr", self.eer_threshold))
        self.band_rule = str(band.get("rule", "eer_threshold"))

        self.score_stats = data.get("score_stats", {}) or {}

        mapping = data.get("mapping", {"type": "identity"}) or {}
        self.mapping_type = str(mapping.get("type", "identity"))
        if self.mapping_type not in SUPPORTED_MAPPINGS:
            raise CalibrationError(
                f"{path}: unsupported mapping type {self.mapping_type!r}; "
                f"expected one of {SUPPORTED_MAPPINGS}"
            )
        self._scale = float(mapping.get("scale", 1.0))
        self._offset = float(mapping.get("offset", 0.0))

    # -- loading -----------------------------------------------------------
    @staticmethod
    def load(path: str) -> "Calibration":
        if not os.path.exists(path):
            raise CalibrationError(
                f"calibration not found: {path}\n"
                "Sentinel will not run on an uncalibrated model -- a risk number "
                "with no provenance is worse than no number.\n"
                "Run: ../detector/venv/bin/python scripts/fit_probe.py"
            )
        with open(path, "rb") as fh:
            raw = fh.read()
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise CalibrationError(f"{path}: not valid JSON ({exc})") from exc

        for key in ("eer", "eer_threshold"):
            if key not in data:
                raise CalibrationError(f"{path}: missing required key {key!r}")

        # Hash the file bytes, not the parsed dict: reformatting the file is a
        # change, and a decision made under the reformatted file should say so.
        calibration_id = hashlib.sha256(raw).hexdigest()[:12]
        return Calibration(data, calibration_id, path)

    # -- the mapping -------------------------------------------------------
    def apply(self, raw_score: float) -> float:
        """Raw fused score -> calibrated risk in [0,1]. Monotone by construction."""
        if self.mapping_type == "identity":
            value = float(raw_score)
        else:  # affine
            value = self._scale * float(raw_score) + self._offset
        return min(1.0, max(0.0, value))

    # -- interpretation ----------------------------------------------------
    def sigma_above_genuine(self, kind: str, value: float) -> Optional[float]:
        """
        How far above the genuine mean this score sits, in standard deviations.

        This is what makes a raw number sayable out loud: "the artifact score
        was 2.0 sigma above the genuine mean for this calibration set."
        """
        stats = self.score_stats.get(kind, {}).get("bonafide")
        if not stats:
            return None
        std = float(stats.get("std", 0.0))
        if std <= 1e-9:
            return None
        return (float(value) - float(stats["mean"])) / std

    def check_band(self, low_thr: float, high_thr: float) -> Optional[str]:
        """
        Warn when config.yaml's thresholds have drifted from the calibration's.

        config.yaml stays authoritative -- an operator may deliberately widen the
        abstention band -- but a silent divergence between the numbers we
        calibrated and the numbers we decide with is exactly the kind of thing a
        judge is entitled to catch us on.
        """
        if abs(low_thr - self.band_low) < 1e-6 and abs(high_thr - self.band_high) < 1e-6:
            return None
        return (
            f"config thresholds [{low_thr}, {high_thr}] differ from "
            f"calibration decision_band [{self.band_low}, {self.band_high}] "
            f"({self.band_rule}). config.yaml wins; both are recorded in the "
            "evidence log."
        )

    def header(self) -> Dict[str, Any]:
        """The provenance block the UI shows next to the risk number (SPEC §12)."""
        return {
            "calibration_id": self.calibration_id,
            "dataset": self.dataset,
            "eer": self.eer,
            "eer_threshold": self.eer_threshold,
            "n_test_trials": self.n_test_trials,
            "n_test_speakers": self.n_test_speakers,
            "backbone": self.backbone,
            "created_utc": self.created_utc,
            "fusion": self.fusion_strategy,
            "band": [self.band_low, self.band_high],
            "notes": self.notes,
        }
