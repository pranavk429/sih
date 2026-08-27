"""
SPEC §9: "A silent window yields SILENT, not a crash and not a fabricated score."

This guards Gap 3. Resemblyzer raises on silence; a streaming system meets
silence constantly. The whole point is that the failure mode is a labelled
status rather than an exception in the pipeline loop or, worse, a number.
"""
from __future__ import annotations

import numpy as np
import pytest

from conftest import silence, tone
from sentinel.audio.vad import EnergyVad, rms, voiced_ratio


def test_digital_silence_is_not_speech(cfg):
    vad = EnergyVad(cfg.audio)
    assert vad.is_speech(silence(3.0), cfg.audio.sample_rate) is False


def test_line_noise_below_floor_is_not_speech(cfg):
    """
    The demo audio's inter-segment gaps carry noise at 0.0008 RMS, deliberately
    well under the 0.006 floor. Those windows must read SILENT, not speech.
    """
    vad = EnergyVad(cfg.audio)
    noise = silence(3.0, noise_rms=0.0008)
    assert rms(noise) < cfg.audio.vad_rms_floor
    assert vad.is_speech(noise, cfg.audio.sample_rate) is False


def test_speech_like_signal_is_speech(cfg):
    vad = EnergyVad(cfg.audio)
    assert vad.is_speech(tone(3.0), cfg.audio.sample_rate) is True


def test_real_demo_call_is_mostly_scorable(cfg, demo_dir):
    """
    A real call must not be gated away wholesale by an over-eager floor.

    The bar is 'most of the call gets scored', not 'all of it'. ASVspoof clips
    are read speech with long pauses, so a third of the windows genuinely have
    too little voice in them to embed -- refusing those is the gate working.
    Measured at ~67% scorable on the genuine demo call.
    """
    import os

    from conftest import read_wav

    pcm, sr = read_wav(os.path.join(demo_dir, "genuine.wav"))
    vad = EnergyVad(cfg.audio)
    win = int(cfg.audio.window_s * sr)
    hop = int(cfg.audio.hop_s * sr)
    verdicts = [vad.is_speech(pcm[s:s + win], sr) for s in range(0, len(pcm) - win, hop)]
    scored = sum(verdicts) / len(verdicts)
    assert scored > 0.55, (
        f"only {sum(verdicts)}/{len(verdicts)} windows ({scored:.0%}) read as "
        "speech -- the gate is too tight and the risk timeline will be empty"
    )


def test_empty_window_does_not_crash(cfg):
    vad = EnergyVad(cfg.audio)
    assert vad.is_speech(np.zeros(0, dtype=np.float32), cfg.audio.sample_rate) is False
    assert rms(np.zeros(0, dtype=np.float32)) == 0.0


def test_voiced_ratio_is_monotonic_in_amplitude(cfg):
    sr = cfg.audio.sample_rate
    quiet = voiced_ratio(tone(1.0, amp=0.001), sr, cfg.audio.frame_ms, cfg.audio.vad_rms_floor)
    loud = voiced_ratio(tone(1.0, amp=0.5), sr, cfg.audio.frame_ms, cfg.audio.vad_rms_floor)
    assert quiet == 0.0
    assert loud == 1.0


def test_silence_is_refused_by_the_speaker_adapter(cfg, speaker_encoder):
    """Silence must produce a typed SilentAudio, never a score."""
    from sentinel.models.resemblyzer_spk import SilentAudio

    with pytest.raises(SilentAudio):
        speaker_encoder.embed(silence(3.0), cfg.audio.sample_rate)

    with pytest.raises(SilentAudio):
        speaker_encoder.embed(silence(3.0, noise_rms=0.0008), cfg.audio.sample_rate)

    with pytest.raises(SilentAudio):
        speaker_encoder.embed(np.zeros(0, dtype=np.float32), cfg.audio.sample_rate)


def test_unguarded_countermeasure_confidently_flags_silence(cfg, countermeasure, demo_dir):
    """
    The other half of Gap 3, and the reason the VAD gate sits inside
    Orchestrator._run_deep rather than in its callers.

    Fed a window with no speech in it the probe does not crash and does not
    abstain -- it mostly returns a near-certain "synthetic". It is the mirror of
    the Resemblyzer behaviour below: a model handed no speech still returns a
    confident number, and the number is about nothing.

    This was live until the UI made it visible. The pre-roll backfill called the
    countermeasure without the VAD check, so nine silent windows of the GENUINE
    demo call were scored (eight of them above 0.86) and listed as suspicious
    evidence on a call the system had just verified.

    Measured on this call's VAD-refused windows, not asserted universally: the
    scores are not reliably high, they are reliably meaningless. One of the nine
    came back at 0.17. That is the point -- there is no threshold that rescues a
    score computed on silence, so the gate has to come first.
    """
    import os

    from conftest import read_wav

    pcm, sr = read_wav(os.path.join(demo_dir, "genuine.wav"))
    vad = EnergyVad(cfg.audio)
    win = int(cfg.audio.window_s * sr)
    hop = int(cfg.audio.hop_s * sr)

    refused = [
        pcm[s:s + win]
        for s in range(0, len(pcm) - win, hop)
        if not vad.is_speech(pcm[s:s + win], sr)
    ]
    assert refused, "the genuine call has no VAD-refused windows to test with"

    risks = [countermeasure.risk(w, sr) for w in refused]
    flagged = [r for r in risks if r > cfg.decision.high_thr]
    assert len(flagged) > len(risks) / 2, (
        f"only {len(flagged)}/{len(risks)} silent windows score above high_thr "
        f"(max {max(risks):.3f}). If this ever stops holding the docstring is "
        "out of date -- but do NOT remove the gate. A score computed on silence "
        "is meaningless whichever side of the threshold it lands on."
    )


def test_unguarded_resemblyzer_confidently_verifies_silence(cfg, speaker_encoder, demo_dir):
    """
    Why the guard above has to exist, pinned as a test.

    The SPEC expected Resemblyzer to crash on silence. It does not. It returns a
    well-formed unit-norm embedding that scores BELOW low_thr against a genuine
    enrolment -- i.e. untreated, the system reports VERIFIED while listening to
    nothing. If someone later decides the min_rms check is redundant and deletes
    it, this test explains what they just reintroduced.
    """
    import os

    from conftest import read_wav

    raw_embed, _ = speaker_encoder._embed, speaker_encoder._similarity
    silent_embedding = np.asarray(raw_embed(silence(3.0), cfg.audio.sample_rate))

    assert np.isfinite(silent_embedding).all(), "if this ever starts failing, good"
    assert abs(float(np.linalg.norm(silent_embedding)) - 1.0) < 1e-3, (
        "the silence embedding is unit-norm, i.e. structurally indistinguishable "
        "from a real one -- there is no post-hoc test that catches it"
    )

    enrol, sr = read_wav(os.path.join(demo_dir, "enrol.wav"))
    ref = speaker_encoder.embed(enrol, sr)
    risk_of_silence = speaker_encoder.risk(ref, silent_embedding)
    assert risk_of_silence < cfg.decision.low_thr, (
        f"silence scores {risk_of_silence:.3f}, low_thr is {cfg.decision.low_thr} "
        "-- this is the failure the min_rms guard prevents"
    )


def test_an_assertion_from_the_encoder_degrades_to_silent_audio(
    speaker_encoder, monkeypatch
):
    """
    Resemblyzer does not only fail in the ways the SPEC anticipated.
    preprocess_wav runs webrtcvad, which raises bare AssertionError on some
    edge-case frame lengths rather than ValueError. Uncaught, that kills the
    pipeline thread mid-call -- exactly the crash the SILENT status exists to
    turn into a labelled, survivable non-answer.
    """
    from sentinel.models.resemblyzer_spk import SilentAudio

    def boom(pcm, sr):
        raise AssertionError("webrtcvad frame length")

    monkeypatch.setattr(speaker_encoder, "_embed", boom)

    with pytest.raises(SilentAudio):
        speaker_encoder.embed(tone(3.0), 16000)
