"""
Equal Error Rate (EER): the standard metric in every anti-spoofing paper we cited.

Definition: the error rate at the threshold where the false-accept rate equals the
false-reject rate. Lower is better. This is what lets our pilot numbers be compared
directly against ASVspoof 5 leaderboard numbers (9-20% EER) and against SASV
leaderboard numbers (<1% EER).
"""
from __future__ import annotations
import numpy as np
from sklearn.metrics import roc_curve


def eer(scores: np.ndarray, labels: np.ndarray) -> tuple[float, float]:
    """
    scores: higher = more "fake"/"impostor"-like
    labels: 1 = fake/impostor (positive class), 0 = bonafide/genuine
    Returns (eer, threshold).
    """
    fpr, tpr, thresholds = roc_curve(labels, scores)
    fnr = 1 - tpr
    idx = np.nanargmin(np.abs(fpr - fnr))
    eer_value = (fpr[idx] + fnr[idx]) / 2
    return float(eer_value), float(thresholds[idx])
