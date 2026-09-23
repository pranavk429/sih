"""
Voice lookup: open-set identification over the enrolment gallery.

Two layers are tested separately, because they fail differently:

- `Gallery.lookup` is the arithmetic: threshold and margin, orientation, and
  what happens with one candidate versus several. Synthetic vectors make the
  expected answer obvious.
- `LookupTracker` is the debounce: a name needs consecutive windows.

Then one test with the real encoder and the real demo audio, which is the only
place the (cos+1)/2 scale meets an actual voice.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pytest

from sentinel.enrolment.gallery import Gallery, LookupTracker


def unit(seed: int, dim: int = 256) -> np.ndarray:
    rng = np.random.default_rng(seed)
    v = rng.normal(size=dim).astype(np.float32)
    return v / np.linalg.norm(v)


def build_gallery(*vectors, accept=0.88, margin=0.05):
    return Gallery(
        [f"voice{i}" for i in range(len(vectors))],
        {f"voice{i}": f"Voice {i}" for i in range(len(vectors))},
        np.vstack(vectors),
        accept_similarity=accept,
        min_margin=margin,
    )


# --- Gallery ---------------------------------------------------------------
def test_an_exact_match_is_accepted_with_the_name():
    a = unit(1)
    g = build_gallery(a, unit(2))
    match = g.lookup(a)
    assert match is not None
    assert match.accepted
    assert match.best.speaker_id == "voice0"
    assert match.best.display_name == "Voice 0"
    assert match.best.similarity == pytest.approx(1.0, abs=1e-5)


def test_the_second_voice_is_found_when_it_is_the_one_speaking():
    a, b = unit(1), unit(2)
    g = build_gallery(a, b, unit(3))
    match = g.lookup(b)
    assert match.best.speaker_id == "voice1"
    assert match.accepted


def test_a_stranger_is_rejected_with_the_best_score_still_shown():
    g = build_gallery(unit(1), unit(2), accept=0.99, margin=0.01)
    match = g.lookup(unit(99))
    assert match is not None
    assert not match.accepted
    assert match.best is not None, "the best guess is shown even when rejected"
    assert "below accept threshold" in match.reason


def test_two_candidates_too_close_together_fail_the_margin_gate():
    """Without a margin gate, a gallery with a near-twin accepts the twin."""
    a = unit(1)
    twin = a + 0.02 * unit(2)
    twin = twin / np.linalg.norm(twin)
    g = build_gallery(a, twin, accept=0.5, margin=0.30)
    match = g.lookup(a)
    assert not match.accepted
    assert "margin" in match.reason
    assert match.runner_up is not None


def test_a_single_voice_gallery_has_no_runner_up_and_no_margin_problem():
    a = unit(1)
    g = build_gallery(a, accept=0.5, margin=0.05)
    match = g.lookup(a)
    assert match.accepted
    assert match.runner_up is None
    assert match.margin == pytest.approx(1.0)


def test_an_empty_gallery_returns_none():
    g = Gallery([], {}, np.zeros((0, 0), dtype=np.float32), 0.88, 0.05)
    assert not g
    assert g.lookup(unit(1)) is None


def test_a_degenerate_embedding_is_not_a_match():
    g = build_gallery(unit(1), accept=0.5, margin=0.05)
    assert g.lookup(np.zeros(256, dtype=np.float32)) is None
    assert g.lookup(np.full(256, np.nan, dtype=np.float32)) is None


def test_similarity_matches_the_detector_formula():
    """(cos+1)/2, the same scale detector/src/speaker_id.py returns."""
    a = unit(7)
    b = unit(8)
    cos = float(np.dot(a, b))
    expected = (cos + 1.0) / 2.0
    g = build_gallery(a, accept=0.0, margin=0.0)
    match = g.lookup(b)
    assert match.best.similarity == pytest.approx(expected, abs=1e-5)


# --- LookupTracker ---------------------------------------------------------
def _match(speaker_id, similarity=0.95, accepted=True):
    from sentinel.enrolment.gallery import VoiceCandidate, VoiceMatch

    best = VoiceCandidate(speaker_id, speaker_id.title(), similarity)
    return VoiceMatch(best, None, similarity, accepted, "synthetic")


def test_a_name_needs_two_consecutive_windows():
    tracker = LookupTracker(min_consecutive=2)
    first = tracker.update(_match("voice0"))
    assert first["announced_id"] is None, "one window is not a speaker"
    assert first["consecutive"] == 1

    second = tracker.update(_match("voice0"))
    assert second["announced_id"] == "voice0"
    assert second["consecutive"] == 2


def test_a_rejected_window_clears_the_streak():
    tracker = LookupTracker(min_consecutive=2)
    tracker.update(_match("voice0"))
    tracker.update(_match("voice0", accepted=False))
    assert tracker.announced_id is None


def test_switching_speaker_restarts_the_streak():
    tracker = LookupTracker(min_consecutive=2)
    tracker.update(_match("voice0"))
    state = tracker.update(_match("voice1"))
    assert state["announced_id"] is None
    assert state["consecutive"] == 1
    assert state["pending_id"] == "voice1"


def test_closing_a_decision_requires_the_same_speaker_throughout():
    tracker = LookupTracker(min_consecutive=3)
    tracker.update(_match("voice0"))
    tracker.update(_match("voice0"))
    assert tracker.announced_id is None
    tracker.update(_match("voice0"))
    assert tracker.announced_id == "voice0"


# --- the real encoder, on the real demo audio ------------------------------
def test_a_genuine_window_matches_the_enrolment_and_a_stranger_does_not(
        cfg, demo_dir, speaker_encoder):
    """
    The orientation test for the lookup, on the same scale the pipeline uses.

    Enrol the demo speaker's clip, then look up (a) a window from the genuine
    call, which must match that speaker, and (b) a window from a different
    speaker, which must not clear a strict threshold. The second half needs a
    different speaker's audio; the pilot slice has plenty, but it is gitignored,
    so the test skips cleanly when the data is not on this machine.
    """
    import soundfile as sf

    from sentinel.audio.resample import prepare

    pcm, sr = sf.read(os.path.join(demo_dir, "enrol.wav"), dtype="float32",
                      always_2d=False)
    reference = speaker_encoder.embed(prepare(pcm, sr, cfg.audio.sample_rate),
                                      cfg.audio.sample_rate)

    genuine, sr = sf.read(os.path.join(demo_dir, "genuine.wav"), dtype="float32",
                          always_2d=False)
    genuine = prepare(genuine, sr, cfg.audio.sample_rate)
    # A 3 s window from the middle of the genuine call.
    window = genuine[8000:8000 + 3 * cfg.audio.sample_rate]
    same = speaker_encoder.embed(window, cfg.audio.sample_rate)

    gallery = Gallery(["LA_0022"], {"LA_0022": "Demo speaker"},
                      np.vstack([reference]), accept_similarity=0.80,
                      min_margin=0.05)
    match = gallery.lookup(same)
    assert match is not None and match.accepted, (
        f"the genuine window did not match its own enrolment: {match}"
    )

    pilot = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "..", "detector", "data", "pilot")
    pilot = os.path.normpath(pilot)
    if not os.path.isdir(pilot):
        pytest.skip("pilot data not on this machine -- stranger half skipped")

    # LA_0022's own files, from the manifest; anything else is a stranger.
    own = {"LA_E_4148077.npy", "LA_E_8177958.npy", "LA_E_7255033.npy"}
    stranger_path = next(
        (os.path.join(pilot, f) for f in sorted(os.listdir(pilot))
         if f.endswith(".npy") and f not in own),
        None,
    )
    if stranger_path is None:
        pytest.skip("no other speaker in the pilot slice")

    stranger = np.load(stranger_path).astype(np.float32).reshape(-1)
    stranger = prepare(stranger, cfg.audio.sample_rate, cfg.audio.sample_rate)
    stranger = stranger[: 3 * cfg.audio.sample_rate]
    other = speaker_encoder.embed(stranger, cfg.audio.sample_rate)

    strict = Gallery(["LA_0022"], {"LA_0022": "Demo speaker"},
                     np.vstack([reference]), accept_similarity=0.95,
                     min_margin=0.05)
    unknown = strict.lookup(other)
    assert unknown is not None and not unknown.accepted, (
        f"a stranger cleared a strict threshold: {unknown}"
    )
    assert unknown.best.similarity < match.best.similarity, (
        "the stranger scored at least as high as the enrolled speaker"
    )
