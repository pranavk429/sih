"""
SPEC §7.5: "Privacy is a code property, not a slide claim."

Slide 2 says Sentinel does not store customer voice. This test walks the entire
output tree after enrolling and running, and fails if anything that could be
played back exists. It is what makes that sentence true rather than aspirational.

Two directories hold audio ON PURPOSE: `artifacts/demo/` (the demo calls) and
`artifacts/clones/` (the synthetic assets). Both are build-time inputs created
by scripts with a manifest beside them -- not customer audio, and not anything a
run wrote. They are excluded by directory, and a separate test asserts that
every audio file in them is declared in that manifest, so the exclusion cannot
become a place to hide a recording.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pytest

from conftest import read_wav

AUDIO_SUFFIXES = (
    ".wav", ".flac", ".mp3", ".m4a", ".ogg", ".opus", ".aac",
    ".pcm", ".raw", ".aiff", ".aif", ".wma", ".webm",
)


def _build_input_dirs(cfg) -> set:
    """The two directories whose audio is a shipped input, by construction."""
    artifacts = os.path.dirname(cfg.paths.enrolments_dir)
    return {
        os.path.normpath(cfg.paths.demo_dir),
        os.path.normpath(os.path.join(artifacts, "clones")),
    }


def _declared_audio(cfg) -> dict:
    """{directory: {filenames the manifest declares}} for the build inputs."""
    artifacts = os.path.dirname(cfg.paths.enrolments_dir)
    out = {}

    demo_manifest = os.path.join(cfg.paths.demo_dir, "manifest.json")
    if os.path.exists(demo_manifest):
        with open(demo_manifest) as fh:
            demo = json.load(fh)
        names = {call["file"] for call in demo.get("calls", [])}
        enrolment = demo.get("enrolment") or {}
        if enrolment.get("file"):
            names.add(enrolment["file"])
        out[os.path.normpath(cfg.paths.demo_dir)] = names

    clone_manifest = os.path.join(artifacts, "clones", "manifest.json")
    if os.path.exists(clone_manifest):
        with open(clone_manifest) as fh:
            clones = json.load(fh)
        out[os.path.normpath(os.path.join(artifacts, "clones"))] = {
            asset["file"] for asset in clones.get("assets", [])
        }
    return out


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
    The whole-system check: after any run, only the declared build inputs are audio.

    Anything else with an audio extension under artifacts/ means the pipeline
    started keeping what it heard.
    """
    artifacts = os.path.dirname(cfg.paths.enrolments_dir)
    if not os.path.isdir(artifacts):
        pytest.skip("no artifacts directory yet")

    leaks = _audio_files_under(artifacts, exclude_dirs=_build_input_dirs(cfg))
    assert leaks == [], (
        "audio found outside the declared build inputs: "
        + ", ".join(os.path.relpath(p, artifacts) for p in leaks)
    )


def test_the_build_input_directories_only_hold_declared_audio(cfg):
    """
    The exclusion above is by directory; this is what keeps it honest.

    An undeclared WAV sitting in artifacts/clones/ or artifacts/demo/ would sail
    through the privacy walk while being exactly the thing that walk exists to
    catch. Every audio file there has to be named in the manifest beside it.
    """
    artifacts = os.path.dirname(cfg.paths.enrolments_dir)
    if not os.path.isdir(artifacts):
        pytest.skip("no artifacts directory yet")

    declared = _declared_audio(cfg)
    for directory, names in declared.items():
        present = {
            name for name in os.listdir(directory)
            if name.lower().endswith(AUDIO_SUFFIXES)
        }
        undeclared = present - names
        assert not undeclared, (
            f"{os.path.relpath(directory, artifacts)} holds audio the manifest "
            f"does not declare: {sorted(undeclared)}"
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


def test_the_live_source_is_memory_only(cfg):
    """
    The live path is the one most likely to start "helpfully" saving audio.

    LiveSource has no path attribute and no writer; this walks the same tree
    test_artifacts_tree_holds_no_persisted_call_audio walks, before and after
    three seconds of audio goes through it.
    """
    from sentinel.audio.live_source import LiveSource

    artifacts = os.path.dirname(cfg.paths.enrolments_dir)
    if not os.path.isdir(artifacts):
        pytest.skip("no artifacts directory yet")

    def leaks():
        return _audio_files_under(artifacts, exclude_dirs=_build_input_dirs(cfg))

    before = leaks()

    source = LiveSource(sample_rate=cfg.audio.sample_rate,
                        frame_ms=cfg.audio.frame_ms)
    t = np.arange(3 * cfg.audio.sample_rate, dtype=np.float32) / cfg.audio.sample_rate
    tone = (0.2 * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32)
    step = int(cfg.audio.sample_rate * 0.02)
    for i in range(0, len(tone), step):
        source.push(tone[i:i + step], cfg.audio.sample_rate)
    source.close()
    frames = list(source.frames())

    assert frames, "the source produced no frames -- the test proved nothing"
    assert not hasattr(source, "path"), (
        "LiveSource grew a path attribute; something would eventually write to it"
    )
    assert leaks() == before, "the live path persisted audio to disk"
