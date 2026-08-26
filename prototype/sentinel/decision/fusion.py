"""
Combining the two signals into one risk.

MeanFusion is what the pilot experiment did -- (cm + speaker) / 2 -- and it is
what produced the 11.68% EER we quote. It stays the default so the demo and the
experiment agree about what the system does.

LogisticFusion reads its weights from calibration.json and exists for after the
Kaggle run, when there is enough data to fit them honestly. Selected by config,
so switching is a one-line change and not a code change.

Both handle the case that actually happens on a call: one of the two scores is
missing, because the window was silent or a model errored. The rule is that a
present score still carries information -- the fused value is the mean of what
we have -- but the caller is told how many inputs it was built from, so the
decision engine can refuse to make a confident call on one signal alone.
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

try:
    from typing import Protocol, runtime_checkable
except ImportError:  # pragma: no cover
    from typing_extensions import Protocol, runtime_checkable  # type: ignore


@runtime_checkable
class FusionStrategy(Protocol):
    name: str

    def fuse(self, cm: Optional[float], speaker: Optional[float]) -> Tuple[Optional[float], int]:
        """Returns (fused_risk, n_inputs). fused is None when nothing was usable."""
        ...


class MeanFusion:
    """
    Unweighted mean. Reproduces run_experiment_v2.py exactly.

    With one input present it returns that input, which is the honest behaviour:
    a mean of one number is that number. The n_inputs return value is what stops
    the decision engine treating it as if it had both.
    """

    name = "mean"

    def fuse(self, cm: Optional[float], speaker: Optional[float]) -> Tuple[Optional[float], int]:
        present = [v for v in (cm, speaker) if v is not None]
        if not present:
            return None, 0
        return sum(present) / len(present), len(present)


class LogisticFusion:
    """
    Weighted fusion, weights from calibration.json.

    Not used at pilot scale: with 119 test trials, fitting two fusion weights on
    the same trials we report EER on would be fitting to noise. It is wired up so
    that when the Kaggle run provides a proper held-out set, switching to it is
    a config edit.
    """

    name = "logistic"

    def __init__(self, weights: Sequence[float], bias: float = 0.0) -> None:
        weights = list(weights)
        if len(weights) != 2:
            raise ValueError(f"expected 2 fusion weights (cm, speaker), got {len(weights)}")
        total = sum(abs(w) for w in weights)
        if total <= 1e-9:
            raise ValueError("fusion weights are all zero")
        self.weights: List[float] = weights
        self.bias = float(bias)

    def fuse(self, cm: Optional[float], speaker: Optional[float]) -> Tuple[Optional[float], int]:
        pairs = [(w, v) for w, v in zip(self.weights, (cm, speaker)) if v is not None]
        if not pairs:
            return None, 0
        # Renormalise over the weights that actually have a score behind them,
        # so a missing signal does not silently drag the fused value toward zero.
        total_w = sum(abs(w) for w, _ in pairs)
        value = sum(w * v for w, v in pairs) / total_w + self.bias
        return min(1.0, max(0.0, value)), len(pairs)


def build_fusion(strategy: str, calibration=None) -> FusionStrategy:
    """Pick a strategy by name. Unknown names fail loudly rather than defaulting."""
    if strategy == "mean":
        return MeanFusion()
    if strategy == "logistic":
        weights = calibration.fusion_weights if calibration else [0.5, 0.5]
        return LogisticFusion(weights)
    raise ValueError(
        f"unknown fusion strategy {strategy!r}; expected 'mean' or 'logistic'"
    )
