"""
`assess()`: what the trigger thought, whether or not it fired.

The pipeline calls this once per utterance and the transcript shows the result,
so these tests pin the properties the UI depends on: the assessment and the
event can never disagree, the explanation is always populated, and the same
text always scores the same way.
"""
from __future__ import annotations

import pytest

from sentinel.trigger.engine import TriggerEngine
from sentinel.types import Utterance


@pytest.fixture(scope="module")
def engine(cfg):
    return TriggerEngine(cfg.trigger, cfg.models)


def _assess(engine, text):
    return engine.assess(Utterance(text=text, t_start_ms=0, t_end_ms=3000))


def test_a_firing_line_produces_both_the_event_and_the_explanation(engine):
    assessment, event = _assess(engine, "transfer two crore to this account tonight")
    assert assessment.fired
    assert event is not None
    assert assessment.intent_key == "fund_transfer"
    assert assessment.intent_label == "Fund transfer instruction"
    assert assessment.stage in ("lexical", "semantic", "both")
    assert assessment.margin >= engine.cfg.semantic_margin
    assert assessment.reason
    # One computation, so `evaluate` must return exactly the event `assess` built.
    again = engine.evaluate(Utterance(text="transfer two crore to this account tonight",
                                      t_start_ms=0, t_end_ms=3000))
    assert again is not None and again.intent == event.intent


def test_a_hard_paraphrase_fires_and_says_how(engine):
    assessment, event = _assess(engine, "push the funds across tonight")
    assert assessment.fired and event is not None
    assert assessment.stage == "semantic", (
        "a zero-keyword paraphrase must be caught by the semantic stage; if this "
        "is now 'both', stage 1 has been widened and the keyword criticism is back"
    )
    assert assessment.matched_terms == ()
    assert event.stage == "semantic"


def test_an_ordinary_line_is_quiet_and_explains_itself(engine):
    assessment, event = _assess(engine, "I'll transfer you to the other line, please hold")
    assert not assessment.fired
    assert event is None
    assert assessment.stage == "none"
    assert assessment.margin < engine.cfg.semantic_margin
    assert "keyword" in assessment.reason or "quiet" in assessment.reason
    assert assessment.benign_text, "the nearest ordinary line is part of the answer"


def test_a_short_line_is_not_judged(engine):
    assessment, event = _assess(engine, "transfer")
    assert not assessment.fired
    assert not assessment.min_words_met
    assert "too short" in assessment.reason


def test_top_intents_are_ranked_and_capped(engine):
    assessment, _ = _assess(engine, "read out the OTP you just received")
    assert 1 <= len(assessment.top_intents) <= 3
    sims = [s for _, _, s in assessment.top_intents]
    assert sims == sorted(sims, reverse=True)
    assert all(label for _, label, _ in assessment.top_intents)


def test_the_assessment_serialises_with_every_field_the_ui_reads(engine):
    assessment, _ = _assess(engine, "skip the usual approval process just this once")
    payload = assessment.to_json()
    assert payload["type"] == "intent_assessment"
    for key in ("fired", "stage", "intent_label", "margin", "benign_text",
                "top_intents", "reason", "min_words_met"):
        assert key in payload, f"the UI reads {key} but it is not serialised"
    assert isinstance(payload["top_intents"], list)


def test_the_same_text_scores_identically_twice(engine):
    """The typed box and the transcript must never disagree for the same words."""
    first, _ = _assess(engine, "keep this off the system until I say so")
    second, _ = _assess(engine, "keep this off the system until I say so")
    assert first.to_json() == second.to_json()


def test_empty_text_is_handled_without_a_model_call(engine):
    assessment, event = _assess(engine, "   ")
    assert not assessment.fired and event is None
    assert "empty" in assessment.reason
