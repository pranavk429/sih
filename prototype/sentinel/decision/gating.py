"""
When does deep verification run? This module is the project's thesis in code.

The speaker check runs ALWAYS -- it is cheap and it is our primary signal. The
countermeasure is what gets gated. That ordering is deliberate and it is the
argument: a bank does not need to know whether every call is synthetic, it needs
to know whether the person asking for two crore is who they claim to be.

TriggeredGating runs deep scoring only inside a window around a trigger. The
PRE-ROLL is the part that is easy to get wrong: by the time speech has been
transcribed and the intent recognised, the incriminating audio is already two or
three seconds in the past. Scoring forward from the trigger would score the
caller's next sentence, not the one that mattered. So the policy reaches
backwards over windows the Framer still holds.

AlwaysOnGating is the naive design the problem statement describes. It exists so
the demo can show it failing: run it on a genuine call and watch the false-alarm
counter climb. That comparison is the strongest thing in the demo, and it needs
the naive path to be real code rather than a strawman.
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from sentinel.types import TriggerEvent

try:
    from typing import Protocol, runtime_checkable
except ImportError:  # pragma: no cover
    from typing_extensions import Protocol, runtime_checkable  # type: ignore


@runtime_checkable
class GatingPolicy(Protocol):
    name: str

    def should_run_deep(self, t_ms: int, triggers: Sequence[TriggerEvent]) -> bool:
        ...


class TriggeredGating:
    """Deep scoring inside [trigger - pre_roll, trigger + hold]."""

    name = "triggered"

    def __init__(self, pre_roll_s: float, hold_s: float) -> None:
        self.pre_roll_ms = int(pre_roll_s * 1000)
        self.hold_ms = int(hold_s * 1000)

    def window_for(self, trigger: TriggerEvent) -> Tuple[int, int]:
        return (
            max(0, trigger.t_ms - self.pre_roll_ms),
            trigger.t_ms + self.hold_ms,
        )

    def should_run_deep(self, t_ms: int, triggers: Sequence[TriggerEvent]) -> bool:
        for trigger in triggers:
            start, end = self.window_for(trigger)
            if start <= t_ms <= end:
                return True
        return False

    def backfill_from_ms(self, triggers: Sequence[TriggerEvent]) -> Optional[int]:
        """
        Earliest stream time the pre-roll needs, across all triggers so far.

        The orchestrator uses this to pull already-passed windows out of the
        Framer's history and score them retrospectively.
        """
        if not triggers:
            return None
        return min(self.window_for(t)[0] for t in triggers)

    def active_regions(self, triggers: Sequence[TriggerEvent]) -> List[Tuple[int, int]]:
        """Merged [start, end] spans, for shading the risk timeline."""
        spans = sorted(self.window_for(t) for t in triggers)
        merged: List[Tuple[int, int]] = []
        for start, end in spans:
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        return merged


class AlwaysOnGating:
    """
    Score every window, forever. The design the PS describes, kept honest.

    Not a strawman: it runs the same countermeasure over the same windows with
    the same thresholds. The only difference is that nothing gates it. On a
    genuine call that is enough to generate a steady stream of false alarms,
    which is the point.
    """

    name = "always_on"

    def should_run_deep(self, t_ms: int, triggers: Sequence[TriggerEvent]) -> bool:
        return True

    def backfill_from_ms(self, triggers: Sequence[TriggerEvent]) -> Optional[int]:
        return None

    def active_regions(self, triggers: Sequence[TriggerEvent]) -> List[Tuple[int, int]]:
        return []


def build_gating(mode: str, pre_roll_s: float, hold_s: float) -> GatingPolicy:
    if mode == "triggered":
        return TriggeredGating(pre_roll_s, hold_s)
    if mode == "always_on":
        return AlwaysOnGating()
    raise ValueError(
        f"unknown gating mode {mode!r}; expected 'triggered' or 'always_on'"
    )
