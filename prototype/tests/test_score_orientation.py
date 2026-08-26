"""
SPEC §9 / Gap 2: identical voices must produce LOW risk.

Every score in Sentinel is a risk in [0,1] where higher = more suspicious.
Resemblyzer natively returns the opposite (higher = same person). The inversion
happens in exactly one place -- ResemblyzerSpeakerEncoder.risk -- and this file
is what stops someone "fixing" it a second time downstream and silently
inverting every verdict in the system.
"""
from __future__ import annotations

import os

import numpy as np
import pytest

from conftest import read_wav


def test_identical_audio_is_low_risk(speaker_encoder, demo_dir):
    """The trivial case, and the one that catches a flipped sign instantly."""
    pcm, sr = read_wav(os.path.join(demo_dir, "enrol.wav"))
    emb = speaker_encoder.embed(pcm, sr)
    assert speaker_encoder.risk(emb, emb) < 0.05


def test_risk_is_the_inverse_of_similarity(speaker_encoder, demo_dir):
    """risk == 1 - similarity, stated as an equation so it cannot drift."""
    pcm, sr = read_wav(os.path.join(demo_dir, "enrol.wav"))
    emb = speaker_encoder.embed(pcm, sr)
    other = speaker_encoder.embed(pcm[: len(pcm) // 2], sr)
    assert speaker_encoder.risk(emb, other) == pytest.approx(
        1.0 - speaker_encoder.similarity(emb, other), abs=1e-6
    )


def test_risk_is_bounded(speaker_encoder, demo_dir):
    pcm, sr = read_wav(os.path.join(demo_dir, "enrol.wav"))
    a = speaker_encoder.embed(pcm, sr)
    b = speaker_encoder.embed(np.ascontiguousarray(pcm[::-1]), sr)
    for r in (speaker_encoder.risk(a, a), speaker_encoder.risk(a, b)):
        assert 0.0 <= r <= 1.0


def test_same_speaker_scores_lower_than_a_different_speaker(speaker_encoder, cfg):
    """
    A real discrimination check, on pilot audio rather than the demo files.

    Two clips of one speaker must score lower risk than a clip of someone else.
    If this fails, the enrolment thesis on slide 2 is not true of our code.
    """
    import json

    from sentinel.config import ROOT

    pilot = os.path.normpath(os.path.join(ROOT, "..", "detector", "data", "pilot"))
    if not os.path.exists(os.path.join(pilot, "manifest.json")):
        pytest.skip("pilot data missing")
    with open(os.path.join(pilot, "manifest.json")) as fh:
        manifest = json.load(fh)

    by_speaker = {}
    for row in manifest:
        if row["label"] == "bonafide":
            by_speaker.setdefault(row["speaker_id"], []).append(row)
    pairs = [(spk, rows) for spk, rows in by_speaker.items() if len(rows) >= 2]
    assert len(pairs) >= 2, "need two speakers with two bonafide clips each"

    def emb(row):
        pcm = np.load(os.path.join(pilot, row["file"])).astype(np.float32)
        return speaker_encoder.embed(pcm, row["sr"])

    (spk_a, rows_a), (spk_b, rows_b) = pairs[0], pairs[1]
    ref = emb(rows_a[0])
    same_risk = speaker_encoder.risk(ref, emb(rows_a[1]))
    diff_risk = speaker_encoder.risk(ref, emb(rows_b[0]))

    assert same_risk < diff_risk, (
        f"{spk_a} vs itself scored {same_risk:.3f}, but {spk_a} vs {spk_b} scored "
        f"{diff_risk:.3f} -- the orientation is inverted"
    )


def test_countermeasure_ranks_spoof_above_its_genuine_pair(countermeasure, demo_dir):
    """
    The CM's orientation: higher = more synthetic.

    Averaged over windows rather than taken on a single one -- per-window scores
    on 3s of degraded telephony audio are noisy, which is precisely why the
    decision engine aggregates instead of reacting to one window.
    """
    genuine, sr = read_wav(os.path.join(demo_dir, "genuine.wav"))
    attack, _ = read_wav(os.path.join(demo_dir, "attack.wav"))

    def mean_risk(pcm):
        win, hop = int(3.0 * sr), int(1.5 * sr)
        scores = [countermeasure.risk(pcm[s:s + win], sr)
                  for s in range(0, len(pcm) - win, hop)]
        return float(np.mean(scores))

    genuine_risk, attack_risk = mean_risk(genuine), mean_risk(attack)
    assert attack_risk > genuine_risk, (
        f"attack scored {attack_risk:.3f} but genuine scored {genuine_risk:.3f} "
        "-- the countermeasure is inverted or the demo pair is wrong"
    )
