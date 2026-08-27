"""
SPEC §9: ~30 sentences, half triggering, half not, INCLUDING paraphrases with
zero keyword overlap.

This test is the answer to "isn't this just keyword matching?". If the hard
positives below pass while the negatives stay quiet, the two-stage design is
doing something a keyword list cannot, and that is a claim we can make on stage
because it is checked here.
"""
from __future__ import annotations

import pytest

from sentinel.trigger.engine import TriggerEngine, lexical_hits
from sentinel.trigger.intents import (
    ASR_NOISE,
    HARD_POSITIVES,
    HELD_OUT_NEGATIVES,
    KNOWN_FALSE_POSITIVES,
    KNOWN_MISSES,
    NEGATIVES,
)
from sentinel.types import Utterance

# Fifteen that must fire.
POSITIVES = (
    "I need you to transfer two crore to this account tonight",
    "Please send the money to the account number I am giving you now",
    "Move the funds across to this beneficiary immediately",
    "Read out the OTP you just received on your phone",
    "Tell me the one time password that came through",
    "Give me your net banking password so I can check it",
    "This is the managing director and I need it done in the next ten minutes",
    "The chairman is on the line and this cannot wait until tomorrow",
    "Skip the usual approval process just this once",
    "There isn't time for the normal verification, do it now",
    "We don't need the second signatory on this one",
    "Do not call the branch about this transfer",
    "Don't mention this to anyone in the office until it is done",
    "Release the payment to this vendor right now, it is urgent",
    "Wire the amount to the new account details before the deadline",
    # Colloquial, but "paperwork" is a keyword, so this is not a hard case.
    "we can do the paperwork afterwards, get it out the door first",
    # Regression: "director" standalone (not just "managing director" or
    # "board of directors") must still be a keyword hit on its own.
    "I am the director, wire it now",
)


@pytest.fixture(scope="module")
def engine(cfg):
    return TriggerEngine(cfg.trigger, cfg.models)


def _utt(text: str) -> Utterance:
    return Utterance(text=text, t_start_ms=0, t_end_ms=3000)


@pytest.mark.parametrize("text", POSITIVES)
def test_high_risk_instructions_fire(engine, text):
    event = engine.evaluate(_utt(text))
    assert event is not None, f"trigger missed a high-risk instruction: {text!r}"
    assert event.intent
    assert event.stage in ("lexical", "semantic", "both")


@pytest.mark.parametrize("text", NEGATIVES)
def test_ordinary_banking_talk_stays_quiet(engine, text):
    event = engine.evaluate(_utt(text))
    assert event is None, (
        f"false trigger on ordinary call content: {text!r} "
        f"(intent={event.intent}, stage={event.stage}, sim={event.similarity:.3f})"
    )


@pytest.mark.parametrize("text", HARD_POSITIVES)
def test_paraphrases_with_no_keyword_overlap_fire(engine, text):
    """
    The test that matters. These must fire, and stage 1 must NOT be what
    catches them -- otherwise the semantic stage is decoration.
    """
    assert not lexical_hits(text), (
        f"{text!r} contains a keyword, so it does not belong in HARD_POSITIVES "
        "-- move it to POSITIVES and find a genuinely keyword-free paraphrase"
    )
    event = engine.evaluate(_utt(text))
    assert event is not None, f"semantic stage failed to catch a paraphrase: {text!r}"
    assert event.stage == "semantic", (
        f"{text!r} fired via stage {event.stage}; the point of this case is that "
        "the lexical prefilter cannot see it"
    )


@pytest.mark.parametrize("text", ASR_NOISE)
def test_real_transcriber_output_does_not_trigger(engine, text):
    """
    The demo lives or dies on this.

    These are verbatim faster-whisper outputs from the demo calls — VCTK read
    speech over a degraded line. On the first full run the trigger fired on
    three of them, because the benign anchors were all banking sentences and
    real transcripts are not. If any of these starts firing again, the demo
    opens with the system alarming at nothing and the whole argument is lost.
    """
    event = engine.evaluate(_utt(text))
    assert event is None, (
        f"trigger fired on ordinary transcribed speech: {text!r} "
        f"(intent={event.intent}, stage={event.stage}, margin={event.margin:+.3f})"
    )


def test_held_out_negatives_mostly_stay_quiet(engine):
    """
    The only honest generalisation measure in this file.

    HELD_OUT_NEGATIVES were never consulted while curating the benign anchors or
    choosing thresholds. One of them does fire, and it is named rather than
    tuned away. The bar is that the failure rate stays where we measured it, so
    a change that quietly makes the trigger noisier gets caught.
    """
    fired = [t for t in HELD_OUT_NEGATIVES if engine.evaluate(_utt(t)) is not None]
    assert set(fired) <= set(KNOWN_FALSE_POSITIVES), (
        "new false positives on held-out call content: "
        + ", ".join(repr(t) for t in fired if t not in KNOWN_FALSE_POSITIVES)
    )
    rate = len(fired) / len(HELD_OUT_NEGATIVES)
    assert rate <= 1 / 12 + 1e-9, f"held-out false-positive rate rose to {rate:.0%}"


@pytest.mark.parametrize("text", KNOWN_FALSE_POSITIVES)
def test_known_false_positives_are_documented_not_hidden(engine, text):
    """
    These fire and should not. Pinned so the limitation stays visible.

    If one starts passing, delete it from KNOWN_FALSE_POSITIVES -- the trigger
    got better and the docs should say so.
    """
    assert engine.evaluate(_utt(text)) is not None, (
        f"{text!r} no longer misfires -- remove it from KNOWN_FALSE_POSITIVES"
    )


@pytest.mark.parametrize("text", KNOWN_MISSES)
def test_known_misses_are_documented_not_hidden(engine, text):
    """A high-risk paraphrase stage 2 does not catch. Same contract as above."""
    assert engine.evaluate(_utt(text)) is None, (
        f"{text!r} now fires -- promote it into HARD_POSITIVES"
    )


def test_raw_similarity_alone_would_not_separate_the_classes(engine):
    """
    Why the margin exists, pinned as a test.

    If someone reverts stage 2 to a plain similarity threshold, this documents
    what they are giving up: the innocent sentence scores HIGHER than the
    high-risk paraphrase on raw similarity, and only the benign-anchor
    comparison puts them on the right sides.
    """
    innocent = engine.matcher.best_match(
        "Please visit the branch at your convenience with the documents"
    )
    high_risk = engine.matcher.best_match("push the funds across tonight")

    assert innocent.intent_similarity > high_risk.intent_similarity, (
        "raw similarity used to rank the innocent sentence above the fraud "
        "paraphrase; if that has changed, the margin may no longer be needed"
    )
    assert high_risk.margin > innocent.margin
    assert innocent.margin < 0 < high_risk.margin


def test_the_canonical_false_positive_is_rejected(engine):
    """
    "I'll transfer you to the other line" contains 'transfer' and is not fraud.

    Stage 1 must hit it -- proving the naive approach would fire -- and the
    engine must still stay quiet. This single case is the whole argument for
    having two stages.
    """
    text = "I'll transfer you to the other line, please hold"
    assert lexical_hits(text), "stage 1 should hit this, that is the point"
    assert engine.evaluate(_utt(text)) is None


def test_very_short_utterances_do_not_fire(engine):
    """A bare word is not an instruction."""
    assert engine.evaluate(_utt("transfer")) is None
    assert engine.evaluate(_utt("")) is None
    assert engine.evaluate(_utt("OTP")) is None


def test_trigger_event_carries_the_scripted_flag(engine):
    """The overlay marker must survive into the TriggerEvent (2.6 honesty rule)."""
    scripted = Utterance(
        text="I need you to transfer two crore to this account tonight",
        t_start_ms=0,
        t_end_ms=3000,
        scripted=True,
    )
    event = engine.evaluate(scripted)
    assert event is not None
    assert event.utterance.scripted is True
    assert event.to_json()["scripted"] is True


def test_describe_is_presentable(engine):
    event = engine.evaluate(_utt(POSITIVES[0]))
    text = engine.describe(event)
    assert "TRIGGER" in text
    assert POSITIVES[0][:20] in text


def test_scripted_overlay_emits_each_line_once(cfg):
    from sentinel.trigger.engine import ScriptedOverlay

    overlay = ScriptedOverlay(cfg.trigger.scripted_overlay)
    assert overlay.enabled

    first = overlay.due(16000)
    assert len(first) == 1
    assert first[0].scripted is True
    assert overlay.due(16000) == [], "an overlay line must not be emitted twice"

    rest = overlay.due(30000)
    assert len(rest) == 2
    assert all(u.scripted for u in rest)


def test_overlay_lines_actually_trigger(engine, cfg):
    """
    The demo depends on this: at least one configured overlay line must fire.

    If someone edits config.yaml's overlay into something the trigger ignores,
    the demo silently becomes 'nothing ever happens' — this catches that.
    """
    from sentinel.trigger.engine import ScriptedOverlay

    overlay = ScriptedOverlay(cfg.trigger.scripted_overlay)
    fired = [engine.evaluate(u) for u in overlay.due(10 ** 9)]
    assert any(e is not None for e in fired), (
        "no line in config.yaml trigger.scripted_overlay fires the trigger — "
        "the demo would show monitoring and then nothing"
    )
