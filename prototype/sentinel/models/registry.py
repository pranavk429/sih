"""
The one and only place that reaches into detector/src.

SPEC §5: "Import them by adding detector/src to sys.path in one place. Do not
copy-paste them -- a divergent copy is how the experiment and the demo start
disagreeing about what the system does."

If you need something from the detector, add an accessor here. Do not add a
second sys.path insert anywhere else, and do not vendor a copy of the algorithm.

(Later, detector/src becomes an installable voiceguard_core package that both
sides depend on. Not during a four-day build.)
"""
from __future__ import annotations

import os
import sys
from typing import Any, Callable, Tuple

from sentinel.config import ROOT, Config

DETECTOR_SRC = os.path.normpath(os.path.join(os.path.dirname(ROOT), "detector", "src"))


def _ensure_on_path() -> None:
    if not os.path.isdir(DETECTOR_SRC):
        raise RuntimeError(
            f"detector source not found at {DETECTOR_SRC}. "
            "Sentinel reuses the pilot's scoring core rather than duplicating it; "
            "the prototype must sit alongside detector/ in the repo."
        )
    if DETECTOR_SRC not in sys.path:
        sys.path.insert(0, DETECTOR_SRC)


def probe_backbone(device: str = "auto") -> Any:
    """detector.probe_model.ProbeBackbone -- frozen, task-naive wav2vec2."""
    _ensure_on_path()
    from probe_model import ProbeBackbone

    return ProbeBackbone(device=None if device == "auto" else device)


def speaker_fns() -> Tuple[Callable[..., Any], Callable[..., float]]:
    """(embed, similarity) from detector.speaker_id. Note: similarity, NOT risk."""
    _ensure_on_path()
    from speaker_id import embed, similarity

    return embed, similarity


def degrade_fn() -> Callable[..., Any]:
    """detector.channel_sim.degrade -- the telephony channel simulator."""
    _ensure_on_path()
    from channel_sim import degrade

    return degrade


def eer_fn() -> Callable[..., Any]:
    """detector.metrics.eer -> (eer, threshold)."""
    _ensure_on_path()
    from metrics import eer

    return eer


def build_models(cfg: Config) -> Tuple[Any, Any]:
    """
    (countermeasure, speaker_encoder), both already obeying the risk convention.

    Loading is eager: a demo that discovers a missing probe_head.npz halfway
    through a call is worse than one that refuses to start.
    """
    from sentinel.models.probe_cm import ProbeCountermeasure
    from sentinel.models.resemblyzer_spk import ResemblyzerSpeakerEncoder

    cm = ProbeCountermeasure(
        head_path=cfg.models.probe_head_path,
        device=cfg.models.device,
    )
    spk = ResemblyzerSpeakerEncoder(min_rms=cfg.audio.min_embed_rms)
    return cm, spk
