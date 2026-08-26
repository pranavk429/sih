"""
Every tunable number in Sentinel lives here and nowhere else.

IMPLEMENTATION-PLAN rule 3: "No magic numbers outside config.yaml. If you type a
threshold into a module, you've created a bug that will be found on stage."

The tree is frozen dataclasses loaded from YAML. Unknown keys raise with the
offending key name rather than being silently ignored -- a typo'd threshold that
silently keeps its default is exactly the failure that surfaces during a demo.

Relative paths in the YAML are resolved against the prototype root (the parent
of this package), so the CLI works from any working directory.
"""
from __future__ import annotations

import os
import dataclasses
from dataclasses import dataclass, field, fields, is_dataclass
from typing import Any, Dict, Optional, Tuple

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG_PATH = os.path.join(ROOT, "config.yaml")

# Fields whose values are filesystem paths and get resolved against ROOT.
_PATH_FIELDS = frozenset(
    {
        "probe_head_path",
        "calibration_path",
        "hf_cache_dir",
        "asr_cache_dir",
        "enrolments_dir",
        "demo_dir",
        "evidence_dir",
        "static_dir",
    }
)


def resolve(path: str) -> str:
    """
    Resolve a possibly-relative path against the prototype root.

    An empty string stays empty -- it means "not set" (see ModelConfig.hf_cache),
    and resolving it would silently turn it into the prototype root.
    """
    if not path:
        return ""
    return path if os.path.isabs(path) else os.path.normpath(os.path.join(ROOT, path))


@dataclass(frozen=True)
class AudioConfig:
    """Framing and the VAD gate that keeps Resemblyzer alive (SPEC Gap 3)."""

    sample_rate: int = 16000
    frame_ms: int = 20
    window_s: float = 3.0
    hop_s: float = 0.5
    # RMS below this is treated as line noise, not speech.
    vad_rms_floor: float = 0.006
    # ...and at least this fraction of a window's frames must clear the floor.
    # Measured, not guessed -- see config.yaml.
    vad_min_voiced_ratio: float = 0.10
    # Backstop inside the speaker adapter. Resemblyzer does not raise on
    # silence; it returns a plausible-looking embedding. See resemblyzer_spk.
    min_embed_rms: float = 0.0015


@dataclass(frozen=True)
class ModelConfig:
    cm_backbone_id: str = "facebook/wav2vec2-base"
    probe_head_path: str = "artifacts/probe_head.npz"
    calibration_path: str = "artifacts/calibration.json"
    # torch device for the CM backbone: "auto" picks MPS on Apple Silicon.
    device: str = "auto"

    asr_model_id: str = "base.en"
    asr_device: str = "cpu"
    asr_compute_type: str = "int8"

    trigger_encoder_id: str = "sentence-transformers/all-MiniLM-L6-v2"

    # Empty means the huggingface_hub default cache. Keep it empty: the
    # detector's ProbeBackbone calls from_pretrained() with no cache_dir, so a
    # custom directory here would give us two caches, and the one the CM
    # actually reads would be the one prefetch never filled.
    hf_cache_dir: str = ""
    asr_cache_dir: str = "artifacts/models/asr"

    def hf_cache(self) -> Optional[str]:
        """cache_dir argument for transformers/sentence-transformers."""
        return self.hf_cache_dir or None


@dataclass(frozen=True)
class ScriptedUtterance:
    """
    A line injected into the transcript for demo audio.

    ASVspoof clips are read speech from VCTK -- they do not contain financial
    instructions, so the trigger would never fire on them naturally
    (IMPLEMENTATION-PLAN 2.6). Overlay lines make the trigger *mechanism*
    demonstrable on audio that isn't a fraud call.

    Every overlay line is flagged `scripted=True` all the way to the UI and is
    rendered visibly marked. Never ship this silently.
    """

    t_ms: int
    text: str


@dataclass(frozen=True)
class TriggerConfig:
    # Stage 2 fires on MARGIN, not raw similarity: how much closer the utterance
    # is to a fraud intent than to a benign anchor. Raw similarity does not
    # separate the classes -- see trigger/engine.py and config.yaml.
    semantic_margin: float = 0.05
    # A stage-1 keyword hit fires only if the sentence is at least as close to a
    # fraud intent as to normal call content, plus a small buffer against
    # spurious ASR fragments.
    lexical_confirm_floor: float = 0.02
    # Utterances shorter than this are too weak a signal to judge semantically.
    min_words: int = 3
    scripted_overlay: Tuple[ScriptedUtterance, ...] = ()


@dataclass(frozen=True)
class GatingConfig:
    # "triggered" = Sentinel's thesis. "always_on" = the naive design, kept so
    # the demo can show it generating false alarms (SPEC §1).
    mode: str = "triggered"
    # Score backwards from a trigger: by the time it fires, the incriminating
    # audio has already gone past (SPEC §7.3).
    pre_roll_s: float = 3.0
    hold_s: float = 10.0


@dataclass(frozen=True)
class DecisionConfig:
    # Fused risk below low_thr -> VERIFIED; above high_thr -> LIKELY_IMPERSONATION;
    # between -> UNCERTAIN. Copied from calibration.json's decision_band.
    low_thr: float = 0.3636
    high_thr: float = 0.4575
    # "mean" matches the pilot experiment; "logistic" uses calibration weights.
    fusion: str = "mean"
    # A verdict needs at least this many OK windows behind it.
    min_windows: int = 2
    # Windows at or above this fused risk are listed in the evidence panel.
    evidence_risk_floor: float = 0.4575


@dataclass(frozen=True)
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8000
    static_dir: str = "sentinel/server/static"
    # SPEC §7.2: the UI is a view, so dropping events is harmless -- but counted.
    event_queue_size: int = 1000
    # ...whereas a gap in the transcript is a missed trigger, so ASR blocks.
    asr_queue_size: int = 200
    # Above this, the UI says out loud that it is behind real time (SPEC §12).
    # One hop. See config.yaml.
    lag_warn_ms: int = 500


@dataclass(frozen=True)
class PathsConfig:
    enrolments_dir: str = "artifacts/enrolments"
    demo_dir: str = "artifacts/demo"
    evidence_dir: str = "artifacts/evidence"


@dataclass(frozen=True)
class Config:
    audio: AudioConfig = field(default_factory=AudioConfig)
    models: ModelConfig = field(default_factory=ModelConfig)
    trigger: TriggerConfig = field(default_factory=TriggerConfig)
    gating: GatingConfig = field(default_factory=GatingConfig)
    decision: DecisionConfig = field(default_factory=DecisionConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)

    @staticmethod
    def load(path: Optional[str] = None) -> "Config":
        path = path or DEFAULT_CONFIG_PATH
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"config not found: {path}\n"
                "Sentinel refuses to run on defaults alone -- every number on "
                "screen must be traceable to a file."
            )
        with open(path) as fh:
            raw = yaml.safe_load(fh) or {}
        if not isinstance(raw, dict):
            raise ValueError(f"{path}: top level must be a mapping, got {type(raw).__name__}")
        return _build(Config, raw, path, "")

    def to_dict(self) -> Dict[str, Any]:
        return _unbuild(self)


def _build(cls: type, raw: Dict[str, Any], src: str, prefix: str) -> Any:
    """Construct a frozen dataclass from a mapping, rejecting unknown keys."""
    known = {f.name: f for f in fields(cls)}
    unknown = sorted(set(raw) - set(known))
    if unknown:
        raise ValueError(
            f"{src}: unknown config key{'s' if len(unknown) > 1 else ''} "
            f"{', '.join(repr(prefix + u) for u in unknown)} "
            f"in section '{prefix.rstrip('.') or '<root>'}'. "
            f"Valid keys here: {', '.join(sorted(known))}"
        )

    kwargs: Dict[str, Any] = {}
    for name, f in known.items():
        if name not in raw:
            continue
        value = raw[name]

        # scripted_overlay is the one list-of-dataclass field.
        if name == "scripted_overlay":
            kwargs[name] = tuple(
                _build(ScriptedUtterance, item, src, f"{prefix}{name}[].")
                for item in (value or [])
            )
            continue

        nested = _nested_type(cls, name)
        if nested is not None:
            if not isinstance(value, dict):
                raise ValueError(
                    f"{src}: '{prefix}{name}' must be a mapping, got {type(value).__name__}"
                )
            kwargs[name] = _build(nested, value, src, f"{prefix}{name}.")
        elif name in _PATH_FIELDS:
            kwargs[name] = resolve(str(value))
        else:
            kwargs[name] = value

    obj = cls(**kwargs)
    # Resolve path defaults that the YAML didn't override.
    replacements = {
        f.name: resolve(getattr(obj, f.name))
        for f in fields(cls)
        if f.name in _PATH_FIELDS and f.name not in kwargs
    }
    if replacements:
        obj = dataclasses.replace(obj, **replacements)
    return obj


def _nested_type(cls: type, name: str) -> Optional[type]:
    """The dataclass type of a nested section, or None for a scalar field."""
    factory = {f.name: f.default_factory for f in fields(cls)}.get(name)
    if factory is None or factory is dataclasses.MISSING:
        return None
    probe = factory()
    return type(probe) if is_dataclass(probe) else None


def _unbuild(obj: Any) -> Any:
    if is_dataclass(obj):
        return {f.name: _unbuild(getattr(obj, f.name)) for f in fields(obj)}
    if isinstance(obj, (list, tuple)):
        return [_unbuild(v) for v in obj]
    return obj
