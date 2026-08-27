"""
The event vocabulary. Frozen dataclasses, one serialisation format.

Two contracts live here, both from SPEC §7.1 and §6:

1. TIME IS ALWAYS STREAM TIME. Every `t_*_ms` is measured from the start of the
   stream, never from the wall clock. This is what makes a file replay and a
   live mic run produce identical event logs, which is what makes the golden
   test possible. A wall-clock timestamp anywhere in the event path destroys
   both, so there is exactly one wall-clock number in the system --
   `pipeline_lag_ms` -- and it is explicitly labelled as such.

2. ONE SERIALISER. `to_json()` is defined here and used by both the evidence log
   and the WebSocket. Two serialisation paths drift, and then the log and the
   screen disagree about what the system decided.

`to_json()` deliberately never emits PCM. Audio does not leave the process.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# --- RiskScore.status -------------------------------------------------------
OK = "OK"
SILENT = "SILENT"  # VAD found no speech. Expected during a call, not an error.
ERROR = "ERROR"  # the model raised. Degrades to UNCERTAIN, never to a number.

# --- Verdict.state ----------------------------------------------------------
MONITORING = "MONITORING"  # no trigger yet; the system is deliberately quiet
VERIFIED = "VERIFIED"
UNCERTAIN = "UNCERTAIN"  # a first-class outcome, not an error path
LIKELY_IMPERSONATION = "LIKELY_IMPERSONATION"

# --- RiskScore.kind ---------------------------------------------------------
CM = "cm"
SPEAKER = "speaker"
FUSED = "fused"


@dataclass(frozen=True)
class Frame:
    """20 ms of mono float32 audio."""

    pcm: np.ndarray
    sr: int
    t_start_ms: int
    seq: int

    @property
    def duration_ms(self) -> int:
        return int(round(len(self.pcm) / self.sr * 1000))

    def to_json(self) -> Dict[str, Any]:
        # No PCM. Frames are never sent anywhere; this exists for debugging.
        return {
            "type": "frame",
            "sr": self.sr,
            "t_start_ms": self.t_start_ms,
            "seq": self.seq,
            "n_samples": int(len(self.pcm)),
        }


@dataclass(frozen=True)
class Window:
    """A sliding analysis window -- 3.0 s wide, 0.5 s hop by default."""

    pcm: np.ndarray
    sr: int
    t_start_ms: int
    t_end_ms: int
    seq: int

    def to_json(self) -> Dict[str, Any]:
        return {
            "type": "window",
            "sr": self.sr,
            "t_start_ms": self.t_start_ms,
            "t_end_ms": self.t_end_ms,
            "seq": self.seq,
        }


@dataclass(frozen=True)
class RiskScore:
    """
    One score over one window.

    value is ALWAYS a risk in [0,1] where higher = more suspicious, whatever the
    underlying library's native orientation was (SPEC Gap 2). When status is not
    OK, value carries no information and downstream code must not read it as a
    number -- that is why status exists instead of a magic sentinel value.
    """

    kind: str
    value: float
    t_start_ms: int
    t_end_ms: int
    model_id: str
    status: str = OK

    @property
    def usable(self) -> bool:
        return self.status == OK

    def to_json(self) -> Dict[str, Any]:
        return {
            "type": "risk_score",
            "kind": self.kind,
            "value": round(float(self.value), 6) if self.usable else None,
            "t_start_ms": self.t_start_ms,
            "t_end_ms": self.t_end_ms,
            "model_id": self.model_id,
            "status": self.status,
        }


@dataclass(frozen=True)
class Utterance:
    """
    A transcribed span of speech.

    `scripted` marks a line injected from config.trigger.scripted_overlay rather
    than transcribed from audio (IMPLEMENTATION-PLAN 2.6). It is carried all the
    way to the UI and rendered with a visible marker. Never let this flag get
    lost between here and the screen -- an unlabelled scripted line is the one
    thing that would make this demo dishonest.
    """

    text: str
    t_start_ms: int
    t_end_ms: int
    scripted: bool = False
    confidence: Optional[float] = None

    def to_json(self) -> Dict[str, Any]:
        return {
            "type": "utterance",
            "text": self.text,
            "t_start_ms": self.t_start_ms,
            "t_end_ms": self.t_end_ms,
            "scripted": self.scripted,
            "confidence": round(self.confidence, 4) if self.confidence is not None else None,
        }


@dataclass(frozen=True)
class TriggerEvent:
    """
    High-risk intent detected. This is what wakes deep verification.

    `stage` records which of the two stages fired ("lexical", "semantic", or
    "both") -- the two-stage structure is the answer to "isn't this just keyword
    matching?", so the evidence panel shows which one actually caught it.
    """

    t_ms: int
    utterance: Utterance
    intent: str
    similarity: float
    stage: str
    # How much closer this sentence is to a fraud intent than to normal call
    # content. This, not `similarity`, is what the decision is made on -- raw
    # similarity does not separate the two classes. See trigger/engine.py.
    margin: float = 0.0
    matched_terms: Tuple[str, ...] = ()

    def to_json(self) -> Dict[str, Any]:
        return {
            "type": "trigger",
            "t_ms": self.t_ms,
            "utterance": self.utterance.to_json(),
            "intent": self.intent,
            "similarity": round(float(self.similarity), 4),
            "margin": round(float(self.margin), 4),
            "stage": self.stage,
            "matched_terms": list(self.matched_terms),
            "scripted": self.utterance.scripted,
        }


@dataclass(frozen=True)
class EvidenceSegment:
    """One suspicious span, for the evidence panel."""

    t_start_ms: int
    t_end_ms: int
    fused_risk: float
    cm_risk: Optional[float]
    speaker_risk: Optional[float]
    n_inputs: int = 2

    def to_json(self) -> Dict[str, Any]:
        return {
            "t_start_ms": self.t_start_ms,
            "t_end_ms": self.t_end_ms,
            "fused_risk": round(float(self.fused_risk), 4),
            "cm_risk": round(float(self.cm_risk), 4) if self.cm_risk is not None else None,
            "speaker_risk": (
                round(float(self.speaker_risk), 4) if self.speaker_risk is not None else None
            ),
            "n_inputs": self.n_inputs,
        }


@dataclass(frozen=True)
class Verdict:
    """
    The decision. Produced only by decision.engine.decide(), which is pure.

    `reasons` is never empty -- the evidence panel shows it verbatim, and a
    verdict a presenter cannot explain is worse than no verdict at all.
    `calibration_id` ties the decision to the calibration that produced it, so
    when the Kaggle run replaces calibration.json the old decisions stay
    attributable to the old numbers.
    """

    state: str
    risk: float
    confidence: float
    reasons: List[str]
    t_ms: int
    calibration_id: str
    triggered: bool = False
    enrolled: bool = False
    n_windows: int = 0
    cm_risk: Optional[float] = None
    speaker_risk: Optional[float] = None
    attack_type: str = "UNKNOWN"  # SPEC §3: TTS-vs-RVC is explicitly not built
    segments: List[EvidenceSegment] = field(default_factory=list)
    recommended_action: str = ""
    model_ids: List[str] = field(default_factory=list)
    # The prompt to say to the caller before hanging up to verify independently.
    # Non-empty only on UNCERTAIN (SPEC §7.4 abstention; IMPLEMENTATION-PLAN
    # 4.2). Scripted, not an interactive/adaptive challenge -- the UI must
    # label it as such.
    challenge_prompt: str = ""

    def to_json(self) -> Dict[str, Any]:
        return {
            "type": "verdict",
            "state": self.state,
            "risk": round(float(self.risk), 4),
            "confidence": round(float(self.confidence), 4),
            "reasons": list(self.reasons),
            "t_ms": self.t_ms,
            "calibration_id": self.calibration_id,
            "triggered": self.triggered,
            "enrolled": self.enrolled,
            "n_windows": self.n_windows,
            "cm_risk": round(float(self.cm_risk), 4) if self.cm_risk is not None else None,
            "speaker_risk": (
                round(float(self.speaker_risk), 4) if self.speaker_risk is not None else None
            ),
            "attack_type": self.attack_type,
            "segments": [s.to_json() for s in self.segments],
            "recommended_action": self.recommended_action,
            "model_ids": list(self.model_ids),
            "challenge_prompt": self.challenge_prompt,
        }
