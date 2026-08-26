"""
SPEC §7.5: "Privacy is a code property, not a slide claim."

Slide 2 says Sentinel does not store customer voice. This test walks the entire
output tree after enrolling and running, and fails if anything that could be
played back exists. It is what makes that sentence true rather than aspirational.

The demo WAVs under artifacts/demo/ are excluded by name: they are the inputs we
deliberately created and shipped, not customer audio the system persisted.
"""
from __future__ import annotations

import os

import numpy as np
import pytest

from conftest import read_wav

AUDIO_SUFFIXES = (
    ".wav", ".flac", ".mp3", ".m4a", ".ogg", ".opus", ".aac",
    ".pcm", ".raw", ".aiff", ".aif", ".wma", ".webm",
)


def _audio_files_under(root: str, exclude_dirs) -> list:
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if os.path.normpath(os.path.join(dirpath, d)) not in exclude_dirs
        ]
        for name in filenames:
            if name.lower().endswith(AUDIO_SUFFIXES):
                found.append(os.path.join(dirpath, name))
    return found


def test_enrolment_persists_features_and_never_audio(tmp_path, speaker_encoder, demo_dir):
    from sentinel.enrolment.store import EnrolmentStore

    store = EnrolmentStore(str(tmp_path / "enrolments"))
    pcm, sr = read_wav(os.path.join(demo_dir, "enrol.wav"))
    meta = store.enrol("LA_0022", pcm, sr, speaker_encoder)

    assert store.get("LA_0022") is not None
    assert meta["embedding_dim"] == 256
    assert meta["model_id"] == speaker_encoder.model_id

    leaks = _audio_files_under(str(tmp_path), set())
    assert leaks == [], f"enrolment wrote audio files: {leaks}"

    # And nothing else large enough to BE audio smuggled under another name.
    for dirpath, _dirnames, filenames in os.walk(str(tmp_path)):
        for name in filenames:
            path = os.path.join(dirpath, name)
            assert os.path.getsize(path) < 64 * 1024, (
                f"{path} is {os.path.getsize(path)} bytes -- too large for a "
                "256-float embedding or its metadata. Is audio being stored?"
            )


def test_stored_embedding_is_not_the_audio(tmp_path, speaker_encoder, demo_dir):
    """An embedding is 256 floats. Six seconds of 16 kHz audio is 96,000."""
    from sentinel.enrolment.store import EnrolmentStore

    store = EnrolmentStore(str(tmp_path / "enrolments"))
    pcm, sr = read_wav(os.path.join(demo_dir, "enrol.wav"))
    store.enrol("LA_0022", pcm, sr, speaker_encoder)

    stored = store.get("LA_0022")
    assert stored.shape == (256,)
    assert stored.size < len(pcm) / 100, (
        "the stored vector is within two orders of magnitude of the source "
        "audio's sample count -- that is not a feature vector"
    )


def test_artifacts_tree_holds_no_persisted_call_audio(cfg):
    """
    The whole-system check: after any run, only the demo inputs are audio.

    Anything else with an audio extension under artifacts/ means the pipeline
    started keeping what it heard.
    """
    artifacts = os.path.dirname(cfg.paths.enrolments_dir)
    if not os.path.isdir(artifacts):
        pytest.skip("no artifacts directory yet")

    leaks = _audio_files_under(
        artifacts, exclude_dirs={os.path.normpath(cfg.paths.demo_dir)}
    )
    assert leaks == [], (
        "audio found outside artifacts/demo/: "
        + ", ".join(os.path.relpath(p, artifacts) for p in leaks)
    )


def test_serialised_events_never_carry_pcm():
    """to_json() on the audio-bearing types must not emit samples."""
    from sentinel.types import Frame, Window

    pcm = np.linspace(-1, 1, 320, dtype=np.float32)
    frame = Frame(pcm=pcm, sr=16000, t_start_ms=0, seq=0).to_json()
    window = Window(pcm=pcm, sr=16000, t_start_ms=0, t_end_ms=3000, seq=0).to_json()

    for payload in (frame, window):
        flat = repr(payload)
        assert "pcm" not in payload
        assert "-1.0" not in flat and "0.0062" not in flat
