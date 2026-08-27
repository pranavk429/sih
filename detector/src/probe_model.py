"""
A leak-free countermeasure: a linear probe on top of a TASK-NAIVE backbone.

Why this exists: the off-the-shelf checkpoint in cm_model.py
(Gustking/wav2vec2-large-xlsr-deepfake-audio-classification) showed textbook
overfitting signatures on our pilot data -- bonafide scores clustered at
std=0.003, near-total separation, 0.0% EER. That model's encoder was
fine-tuned END-TO-END on (likely leaked) ASVspoof data, so even reusing its
encoder as a "frozen feature extractor" would carry the same contamination --
it's not enough to discard just the classification head.

This module uses facebook/wav2vec2-base instead: a self-supervised backbone
that has NEVER seen a bonafide/spoof label or the ASVspoof task. We train our
own logistic-regression head on frozen embeddings from it, fit only on a
FIT speaker group with zero overlap with the TEST speaker group. This is
standard "linear probing" methodology and is genuinely leak-free with
respect to the deepfake-detection task.

Trade-off, stated honestly: wav2vec2-base is smaller and English-only,
not XLSR-multilingual. That's fine for this pilot -- ASVspoof2019 is an
English benchmark -- but the Kaggle full run should probe a multilingual
XLSR backbone (also self-supervised only, e.g. facebook/wav2vec2-xls-r-300m
pretrained checkpoint -- NOT any ASVspoof fine-tune) for the Indian-language
generalization test.
"""
from __future__ import annotations
import numpy as np
import torch
from transformers import AutoFeatureExtractor, AutoModel

MODEL_ID = "facebook/wav2vec2-base"
TARGET_SR = 16000


class ProbeBackbone:
    """Frozen, task-naive feature extractor. No classification head at all."""

    def __init__(self, device: str | None = None, model_id: str | None = None):
        self.device = device or ("mps" if torch.backends.mps.is_available() else "cpu")
        self.model_id = model_id or MODEL_ID
        self.extractor = AutoFeatureExtractor.from_pretrained(self.model_id)
        self.model = AutoModel.from_pretrained(self.model_id)
        self.model.to(self.device)
        self.model.eval()

    @torch.no_grad()
    def embed(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """Mean-pooled last hidden state. Never trained on spoof/bonafide labels."""
        if sr != TARGET_SR:
            raise ValueError(f"expected {TARGET_SR}Hz audio, got {sr}Hz — resample first")
        inputs = self.extractor(audio, sampling_rate=TARGET_SR, return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        hidden = self.model(**inputs).last_hidden_state  # [1, T, 768]
        pooled = hidden.mean(dim=1).squeeze(0)  # [768]
        return pooled.cpu().numpy()
