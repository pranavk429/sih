"""
Countermeasure (CM) model wrapper: scores a clip for "how fake does this sound".

Uses a wav2vec2-XLSR checkpoint fine-tuned for spoof/deepfake classification
(Apache-2.0 licensed, commercially safe — see README for the license note on
why we deliberately avoided AASIST3's CC BY-NC-ND weights).

Model card confirms: id2label = {0: "real", 1: "fake"}, expects 16kHz mono.
"""
from __future__ import annotations
import numpy as np
import torch
from transformers import AutoFeatureExtractor, AutoModelForAudioClassification

MODEL_ID = "Gustking/wav2vec2-large-xlsr-deepfake-audio-classification"
TARGET_SR = 16000


class CountermeasureModel:
    def __init__(self, device: str | None = None):
        self.device = device or ("mps" if torch.backends.mps.is_available() else "cpu")
        self.extractor = AutoFeatureExtractor.from_pretrained(MODEL_ID)
        self.model = AutoModelForAudioClassification.from_pretrained(MODEL_ID)
        self.model.to(self.device)
        self.model.eval()
        # sanity-check the label mapping we're relying on
        assert self.model.config.id2label[1].lower() == "fake", \
            "label mapping changed upstream — re-check id2label before trusting scores"

    @torch.no_grad()
    def spoof_score(self, audio: np.ndarray, sr: int) -> float:
        """Returns P(fake) in [0, 1]. Higher = more likely synthetic."""
        if sr != TARGET_SR:
            raise ValueError(f"expected {TARGET_SR}Hz audio, got {sr}Hz — resample first")
        inputs = self.extractor(audio, sampling_rate=TARGET_SR, return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        logits = self.model(**inputs).logits
        probs = torch.softmax(logits, dim=-1)
        return float(probs[0, 1].item())
