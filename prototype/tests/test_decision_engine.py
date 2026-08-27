"""
SPEC §9: table-driven over every branch of decide(). The logic a judge will
interrogate.

decide() is pure, so this file needs no models, no audio, and no clock -- which
is the entire reason it was made pure. Every row below is a claim about what the
system does, stated in a form that cannot drift from the code.
"""
from __future__ import annotations

import pytest

from sentinel.decision.engine import aggregate, decide
from sentinel.decision.fusion import LogisticFusion, MeanFusion
from sentinel.types import (
    CM,
    ERROR,
    FUSED,
    LIKELY_IMPERSONATION,
    MONITORING,
    OK,
    SILENT,
    SPEAKER,
    UNCERTAIN,
    VERIFIED,
    EvidenceSegment,
    RiskScore,
)


@pytest.fixture(scope="module")
def cal(cfg):
    from sentinel.decision.calibration import Calibration

    return Calibration.load(cfg.models.calibration_path)


def score(kind, value, status=OK, t0=0, t1=3000):
    return RiskScore(kind, value, t0, t1, f"test-{kind}", status)


def call(cal, cfg, *, cm=None, spk=None, enrolled=True, triggered=True, n_windows=6, **kw):
    return decide(cm, spk, enrolled, triggered, cal, cfg.decision,
                  n_windows=n_windows, **kw)


# --------------------------------------------------------------------------
# The four states
# --------------------------------------------------------------------------
def test_not_triggered_is_monitoring_whatever_the_scores_say(cal, cfg):
    """
    The thesis in one test: even a screaming-high risk stays MONITORING if no
    high-risk intent was spoken. This is what stops base rates burying us.
    """
    verdict = call(cal, cfg, cm=score(CM, 0.99), spk=score(SPEAKER, 0.99), triggered=False)
    assert verdict.state == MONITORING
    assert verdict.reasons


def test_low_risk_when_triggered_and_enrolled_is_verified(cal, cfg):
    verdict = call(cal, cfg, cm=score(CM, 0.10), spk=score(SPEAKER, 0.10))
    assert verdict.state == VERIFIED
    assert verdict.risk == pytest.approx(0.10)
    assert verdict.confidence > 0


def test_high_risk_when_triggered_and_enrolled_is_impersonation(cal, cfg):
    verdict = call(cal, cfg, cm=score(CM, 0.95), spk=score(SPEAKER, 0.85))
    assert verdict.state == LIKELY_IMPERSONATION
    assert verdict.confidence > 0
    assert "fraud desk" in verdict.recommended_action


def test_risk_inside_the_band_is_uncertain(cal, cfg):
    mid = (cfg.decision.low_thr + cfg.decision.high_thr) / 2
    verdict = call(cal, cfg, cm=score(CM, mid), spk=score(SPEAKER, mid))
    assert verdict.state == UNCERTAIN
    assert verdict.confidence == 0.0
    assert any("abstention band" in r for r in verdict.reasons)
    assert "registered number" in verdict.recommended_action


# --------------------------------------------------------------------------
# Every route into UNCERTAIN
# --------------------------------------------------------------------------
def test_not_enrolled_is_uncertain_even_at_very_high_risk(cal, cfg):
    """Without a reference voice, a high artifact score is not an accusation."""
    verdict = call(cal, cfg, cm=score(CM, 0.99), spk=None, enrolled=False)
    assert verdict.state == UNCERTAIN
    assert any("no enrolment" in r.lower() for r in verdict.reasons)


@pytest.mark.parametrize("status", [SILENT, ERROR])
@pytest.mark.parametrize("which", ["cm", "spk"])
def test_unusable_score_is_uncertain(cal, cfg, status, which):
    kwargs = {"cm": score(CM, 0.9), "spk": score(SPEAKER, 0.9)}
    kwargs[which] = score(CM if which == "cm" else SPEAKER, 0.0, status=status)
    verdict = call(cal, cfg, **kwargs)
    assert verdict.state == UNCERTAIN
    assert verdict.reasons


def test_both_scores_missing_is_uncertain_and_says_so(cal, cfg):
    verdict = call(cal, cfg, cm=None, spk=None)
    assert verdict.state == UNCERTAIN
    assert any("no usable audio" in r.lower() for r in verdict.reasons)
    assert not any("fabricat" in r.lower() and "score was" not in r.lower()
                   for r in verdict.reasons[:1])


def test_a_single_signal_is_not_enough_to_commit(cal, cfg):
    """One score cannot separate 'synthetic voice' from 'bad line'."""
    verdict = call(cal, cfg, cm=score(CM, 0.05), spk=None)
    assert verdict.state == UNCERTAIN
    assert any("only one of the two signals" in r.lower() for r in verdict.reasons)


def test_too_few_windows_is_uncertain(cal, cfg):
    verdict = call(cal, cfg, cm=score(CM, 0.05), spk=score(SPEAKER, 0.05), n_windows=1)
    assert verdict.state == UNCERTAIN
    assert any("usable window" in r.lower() for r in verdict.reasons)


# --------------------------------------------------------------------------
# Invariants that hold on every branch
# --------------------------------------------------------------------------
ALL_CASES = [
    ("no trigger", dict(cm=score(CM, 0.9), spk=score(SPEAKER, 0.9), triggered=False)),
    ("verified", dict(cm=score(CM, 0.05), spk=score(SPEAKER, 0.05))),
    ("impersonation", dict(cm=score(CM, 0.95), spk=score(SPEAKER, 0.9))),
    ("band", dict(cm=score(CM, 0.42), spk=score(SPEAKER, 0.42))),
    ("not enrolled", dict(cm=score(CM, 0.9), enrolled=False)),
    ("cm silent", dict(cm=score(CM, 0.0, SILENT), spk=score(SPEAKER, 0.2))),
    ("spk error", dict(cm=score(CM, 0.2), spk=score(SPEAKER, 0.0, ERROR))),
    ("nothing", dict()),
    ("one signal", dict(cm=score(CM, 0.2))),
    ("thin evidence", dict(cm=score(CM, 0.05), spk=score(SPEAKER, 0.05), n_windows=0)),
]


@pytest.mark.parametrize("name,kwargs", ALL_CASES, ids=[c[0] for c in ALL_CASES])
def test_reasons_are_never_empty(cal, cfg, name, kwargs):
    """SPEC §7.4: the evidence panel shows reasons verbatim, so there must be some."""
    verdict = call(cal, cfg, **kwargs)
    assert verdict.reasons, f"{name}: reasons is empty"
    assert all(isinstance(r, str) and r.strip() for r in verdict.reasons)


@pytest.mark.parametrize("name,kwargs", ALL_CASES, ids=[c[0] for c in ALL_CASES])
def test_every_verdict_is_serialisable_and_attributed(cal, cfg, name, kwargs):
    verdict = call(cal, cfg, **kwargs)
    payload = verdict.to_json()
    assert payload["calibration_id"] == cal.calibration_id
    assert payload["state"] in (MONITORING, VERIFIED, UNCERTAIN, LIKELY_IMPERSONATION)
    assert 0.0 <= payload["risk"] <= 1.0
    assert 0.0 <= payload["confidence"] <= 1.0
    assert payload["recommended_action"]
    assert payload["attack_type"] == "UNKNOWN", (
        "SPEC §3: TTS-vs-RVC classification is explicitly not built, so this "
        "field must stay UNKNOWN rather than being quietly filled in"
    )


@pytest.mark.parametrize("name,kwargs", ALL_CASES, ids=[c[0] for c in ALL_CASES])
def test_challenge_prompt_is_scripted_and_only_shown_on_uncertain(cal, cfg, name, kwargs):
    """
    IMPLEMENTATION-PLAN 4.2: the CHALLENGE panel only has something to show on
    UNCERTAIN. VERIFIED needs no challenge; LIKELY_IMPERSONATION's action is
    already to stop and escalate, not keep the caller talking.
    """
    verdict = call(cal, cfg, **kwargs)
    if verdict.state == UNCERTAIN:
        assert verdict.challenge_prompt, f"{name}: UNCERTAIN with no challenge prompt"
    else:
        assert verdict.challenge_prompt == "", (
            f"{name}: {verdict.state} should carry no challenge prompt"
        )


def test_thresholds_are_boundaries_not_approximations(cal, cfg):
    """Exactly on a boundary is inside the band, not outside it."""
    low, high = cfg.decision.low_thr, cfg.decision.high_thr
    assert call(cal, cfg, cm=score(CM, low), spk=score(SPEAKER, low)).state == UNCERTAIN
    assert call(cal, cfg, cm=score(CM, high), spk=score(SPEAKER, high)).state == UNCERTAIN
    eps = 1e-4
    assert call(cal, cfg, cm=score(CM, low - eps),
                spk=score(SPEAKER, low - eps)).state == VERIFIED
    assert call(cal, cfg, cm=score(CM, high + eps),
                spk=score(SPEAKER, high + eps)).state == LIKELY_IMPERSONATION


def test_confidence_grows_with_distance_from_the_boundary(cal, cfg):
    near = call(cal, cfg, cm=score(CM, 0.35), spk=score(SPEAKER, 0.35))
    far = call(cal, cfg, cm=score(CM, 0.02), spk=score(SPEAKER, 0.02))
    assert near.state == far.state == VERIFIED
    assert far.confidence > near.confidence


def test_confidence_grows_with_evidence(cal, cfg):
    thin = call(cal, cfg, cm=score(CM, 0.02), spk=score(SPEAKER, 0.02), n_windows=2)
    thick = call(cal, cfg, cm=score(CM, 0.02), spk=score(SPEAKER, 0.02), n_windows=20)
    assert thick.confidence >= thin.confidence


def test_evidence_segments_are_filtered_and_ranked(cal, cfg):
    floor = cfg.decision.evidence_risk_floor
    segments = [
        EvidenceSegment(0, 3000, floor - 0.2, 0.1, 0.1),
        EvidenceSegment(3000, 6000, floor + 0.3, 0.9, 0.2),
        EvidenceSegment(6000, 9000, floor + 0.1, 0.7, 0.2),
    ]
    verdict = call(cal, cfg, cm=score(CM, 0.95), spk=score(SPEAKER, 0.9),
                   window_scores=segments)
    assert len(verdict.segments) == 2, "sub-floor windows must not reach the panel"
    assert verdict.segments[0].fused_risk > verdict.segments[1].fused_risk


# --------------------------------------------------------------------------
# aggregate()
# --------------------------------------------------------------------------
def test_aggregate_uses_the_mean_and_ignores_unusable_windows():
    scores = [
        score(CM, 0.2, t0=0, t1=3000),
        score(CM, 0.0, status=SILENT, t0=500, t1=3500),
        score(CM, 0.6, t0=1000, t1=4000),
    ]
    result = aggregate(CM, scores, "m")
    assert result.status == OK
    assert result.value == pytest.approx(0.4)
    assert (result.t_start_ms, result.t_end_ms) == (0, 4000)


def test_aggregate_preserves_why_nothing_was_usable():
    silent = aggregate(CM, [score(CM, 0.0, SILENT)], "m")
    assert silent.status == SILENT and not silent.usable

    errored = aggregate(CM, [score(CM, 0.0, SILENT), score(CM, 0.0, ERROR)], "m")
    assert errored.status == ERROR, "an error must not be reported as mere silence"

    assert aggregate(CM, [], "m") is None


# --------------------------------------------------------------------------
# fusion
# --------------------------------------------------------------------------
def test_mean_fusion_matches_the_experiment():
    assert MeanFusion().fuse(0.8, 0.2) == (pytest.approx(0.5), 2)
    assert MeanFusion().fuse(0.8, None) == (pytest.approx(0.8), 1)
    assert MeanFusion().fuse(None, None) == (None, 0)


def test_logistic_fusion_renormalises_over_present_signals():
    fusion = LogisticFusion([0.7, 0.3])
    assert fusion.fuse(1.0, 0.0)[0] == pytest.approx(0.7)
    # With only the CM present, the answer is the CM -- not 0.7 of it.
    assert fusion.fuse(1.0, None)[0] == pytest.approx(1.0)
    assert fusion.fuse(None, None) == (None, 0)


def test_unknown_fusion_strategy_fails_loudly():
    from sentinel.decision.fusion import build_fusion

    with pytest.raises(ValueError):
        build_fusion("magic")


def test_an_evidence_segment_records_how_many_signals_fused_it():
    """
    SPEC §12. A "fused" risk computed from ONE usable signal is not the two-way
    corroboration that the word fused implies, and on a window where the
    speaker check abstained the fused number is just the countermeasure wearing
    a different label. The count rides along with the segment so the console
    and the UI can mark it rather than quietly presenting it as agreement.
    """
    from sentinel.types import EvidenceSegment

    both = EvidenceSegment(0, 3000, fused_risk=0.5, cm_risk=0.8,
                           speaker_risk=0.2, n_inputs=2)
    single = EvidenceSegment(0, 3000, fused_risk=0.8, cm_risk=0.8,
                             speaker_risk=None, n_inputs=1)

    assert both.to_json()["n_inputs"] == 2
    assert single.to_json()["n_inputs"] == 1
