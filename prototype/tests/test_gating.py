"""
IMPLEMENTATION-PLAN 2.4: a trigger at t=10s must cause windows from t=7s onward
to be scored.

The pre-roll is the part that is easy to get wrong and impossible to notice: by
the time an utterance has been transcribed and its intent recognised, the audio
that mattered is already seconds in the past. A gating policy that only looks
forward scores the caller's NEXT sentence and reports confidently on it.
"""
from __future__ import annotations

import pytest

from sentinel.decision.gating import AlwaysOnGating, TriggeredGating, build_gating
from sentinel.types import TriggerEvent, Utterance


def trigger_at(t_ms: int) -> TriggerEvent:
    return TriggerEvent(
        t_ms=t_ms,
        utterance=Utterance("transfer two crore tonight", t_ms - 2000, t_ms),
        intent="Fund transfer instruction",
        similarity=0.9,
        margin=0.5,
        stage="both",
    )


def test_trigger_at_ten_seconds_scores_from_seven(cfg):
    """The literal acceptance criterion from the plan."""
    gate = TriggeredGating(pre_roll_s=3.0, hold_s=10.0)
    triggers = [trigger_at(10_000)]

    assert gate.should_run_deep(7_000, triggers) is True
    assert gate.should_run_deep(8_500, triggers) is True
    assert gate.should_run_deep(10_000, triggers) is True
    assert gate.should_run_deep(6_999, triggers) is False


def test_hold_keeps_scoring_after_the_trigger(cfg):
    gate = TriggeredGating(pre_roll_s=3.0, hold_s=10.0)
    triggers = [trigger_at(10_000)]
    assert gate.should_run_deep(19_999, triggers) is True
    assert gate.should_run_deep(20_001, triggers) is False


def test_nothing_is_scored_before_any_trigger():
    gate = TriggeredGating(pre_roll_s=3.0, hold_s=10.0)
    assert gate.should_run_deep(5_000, []) is False
    assert gate.backfill_from_ms([]) is None


def test_backfill_reaches_back_to_the_earliest_pre_roll():
    gate = TriggeredGating(pre_roll_s=3.0, hold_s=10.0)
    assert gate.backfill_from_ms([trigger_at(10_000)]) == 7_000
    assert gate.backfill_from_ms([trigger_at(30_000), trigger_at(10_000)]) == 7_000


def test_pre_roll_cannot_reach_before_the_start_of_the_call():
    gate = TriggeredGating(pre_roll_s=3.0, hold_s=10.0)
    assert gate.window_for(trigger_at(1_000))[0] == 0
    assert gate.should_run_deep(0, [trigger_at(1_000)]) is True


def test_overlapping_trigger_regions_merge_for_the_timeline():
    gate = TriggeredGating(pre_roll_s=3.0, hold_s=10.0)
    regions = gate.active_regions([trigger_at(10_000), trigger_at(15_000)])
    assert regions == [(7_000, 25_000)], "adjacent triggers must shade as one span"

    apart = gate.active_regions([trigger_at(10_000), trigger_at(40_000)])
    assert len(apart) == 2


def test_always_on_scores_everything_including_before_any_trigger():
    """The naive design must be real, or the comparison proves nothing."""
    gate = AlwaysOnGating()
    assert gate.should_run_deep(0, []) is True
    assert gate.should_run_deep(999_999, []) is True
    assert gate.active_regions([]) == []


def test_build_gating_matches_config_and_rejects_typos(cfg):
    assert isinstance(build_gating("triggered", 3.0, 10.0), TriggeredGating)
    assert isinstance(build_gating("always_on", 3.0, 10.0), AlwaysOnGating)
    with pytest.raises(ValueError):
        build_gating("sometimes", 3.0, 10.0)
    # And the configured mode is one we can actually build.
    build_gating(cfg.gating.mode, cfg.gating.pre_roll_s, cfg.gating.hold_s)


def test_framer_history_holds_enough_audio_for_the_pre_roll(cfg):
    """
    Gating can only score backwards over windows the Framer still has.

    If history_s is shorter than pre_roll_s, backfill_from_ms points at audio
    that has already been discarded and the pre-roll silently does nothing.
    """
    import numpy as np

    from sentinel.audio.framing import Framer
    from sentinel.types import Frame

    history_s = cfg.gating.pre_roll_s + cfg.audio.window_s
    framer = Framer(
        sample_rate=cfg.audio.sample_rate,
        window_s=cfg.audio.window_s,
        hop_s=cfg.audio.hop_s,
        history_s=history_s,
    )
    n = int(cfg.audio.sample_rate * cfg.audio.frame_ms / 1000)
    for seq in range(int(15.0 * 1000 / cfg.audio.frame_ms)):
        framer.push(
            Frame(
                pcm=np.full(n, 0.1, dtype=np.float32),
                sr=cfg.audio.sample_rate,
                t_start_ms=seq * cfg.audio.frame_ms,
                seq=seq,
            )
        )

    gate = TriggeredGating(cfg.gating.pre_roll_s, cfg.gating.hold_s)
    backfill_ms = gate.backfill_from_ms([trigger_at(10_000)])
    recoverable = framer.history(since_ms=backfill_ms)
    assert recoverable, "no windows survived long enough to be scored backwards"
    assert min(w.t_start_ms for w in recoverable) <= 10_000 - int(
        cfg.gating.pre_roll_s * 1000
    ), "the Framer's history is shorter than the configured pre-roll"
