"""
The live endpoints, tested without models.

The pipeline is stubbed for the same reason test_server.py stubs it: the things
under test here are the socket protocol, the run lifecycle, the voice store
CRUD and the assessment endpoint -- not wav2vec2. The stub consumes the real
LiveSource, so the framing, the queue and the close path are all exercised for
real.
"""
from __future__ import annotations

import base64
import dataclasses
import json
import os
import time
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

from sentinel.server.app import create_app
from sentinel.types import IntentAssessment

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


class StubCalibration:
    calibration_id = "stub00000000"

    def header(self):
        return {
            "calibration_id": self.calibration_id,
            "dataset": "stub",
            "eer": 0.1168,
            "n_test_trials": 119,
            "band": [0.3636, 0.4575],
        }


class StubSpeaker:
    model_id = "stub-speaker"

    def embed(self, pcm, sr):
        vector = np.ones(256, dtype=np.float32)
        vector[0] = 2.0
        return vector / np.linalg.norm(vector)


class StubTriggerEngine:
    def assess(self, utterance):
        return IntentAssessment(
            fired=False, stage="none", intent_key="", intent_label="",
            intent_similarity=0.10, benign_similarity=0.20, benign_text="stub anchor",
            margin=-0.10, reason="stub engine",
        ), None


class LiveStubOrchestrator:
    """Consumes whatever frames arrive and publishes a minimal event sequence."""

    def __init__(self) -> None:
        self.evidence = None
        self.frames = 0
        self.runs = 0
        self._stop = False
        self.spk = StubSpeaker()
        self.trigger_engine = StubTriggerEngine()

    def stop(self) -> None:
        self._stop = True

    def run(self, source, reference_embedding=None, speaker_id=None, mode=None,
            ground_truth=None, on_event=None, live=False, gallery=None):
        # `Runner.start_live` calls stop() on any previous run first, and the
        # real orchestrator resets its flag at the top of run(). The stub must
        # do the same or it stops before it starts.
        self._stop = False
        self.runs += 1
        on_event({
            "type": "run_start", "mode": mode or "triggered", "live": live,
            "source": "live" if live else "file", "ground_truth": ground_truth,
            "speaker_id": speaker_id, "scripted_overlay": False, "duration_s": None,
            "calibration": {"calibration_id": "stub"}, "band": [0.36, 0.46],
            "model_ids": ["stub"], "gallery": None, "honesty": "stub",
        })
        for _frame in source.frames():
            self.frames += 1
            if self.frames == 2 and on_event:
                on_event({"type": "utterance", "text": "hello", "t_start_ms": 0,
                          "t_end_ms": 60, "scripted": False, "confidence": 0.5})
            if self._stop:
                break
        on_event({
            "type": "final", "state": "MONITORING", "t_ms": 0, "risk": 0.0,
            "confidence": 0.0, "reasons": [], "calibration_id": "stub",
            "triggered": False, "enrolled": reference_embedding is not None,
            "n_windows": 0, "segments": [], "cm_risk": None, "speaker_risk": None,
            "challenge_prompt": "", "recommended_action": "", "model_ids": ["stub"],
            "stats": {"windows_total": self.frames},
        })
        return SimpleNamespace(verdict=None)


@pytest.fixture
def app(cfg, tmp_path):
    """A server whose enrolment store is a temp dir, so tests never touch the
    repository's real voices."""
    temp_cfg = dataclasses.replace(
        cfg,
        paths=dataclasses.replace(cfg.paths, enrolments_dir=str(tmp_path / "enrol")),
    )
    application = create_app(temp_cfg, load_models=False)
    runner = application.state.runner
    runner.orchestrator = LiveStubOrchestrator()
    runner.calibration = StubCalibration()
    return application


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def _read_until(ws, kind, limit=400):
    out = []
    for _ in range(limit):
        event = json.loads(ws.receive_text())
        out.append(event)
        if event.get("type") == kind:
            return out
    raise AssertionError(f"never saw a {kind!r} event; got "
                         f"{[e.get('type') for e in out[-10:]]}")


def _tone_bytes(samples=320, sr=16000, freq=220.0, amp=0.2):
    t = np.arange(samples, dtype=np.float32) / sr
    return (amp * np.sin(2 * np.pi * freq * t)).astype("<f4").tobytes()


def _tone_int16_base64(seconds=1.5, sr=16000):
    t = np.arange(int(seconds * sr), dtype=np.float32) / sr
    pcm = (0.2 * np.sin(2 * np.pi * 220.0 * t) * 32767).astype("<i2")
    return base64.b64encode(pcm.tobytes()).decode("ascii")


# --- the live socket --------------------------------------------------------
def test_the_live_socket_starts_a_run_and_audio_reaches_the_pipeline(app, client):
    runner = app.state.runner

    with client.websocket_connect("/stream") as stream:
        assert json.loads(stream.receive_text())["type"] == "hello"

        with client.websocket_connect("/live/audio") as audio:
            audio.send_text(json.dumps({
                "type": "start", "mode": "triggered", "sample_rate": 16000,
            }))
            ready = json.loads(audio.receive_text())
            assert ready["type"] == "live_ready"
            assert ready["meta"]["live"] is True
            assert ready["sample_rate"] == 16000
            assert runner.live_source is not None

            packet = _tone_bytes()
            for _ in range(5):
                audio.send_bytes(packet)

            deadline = time.time() + 5
            while runner.orchestrator.frames < 5 and time.time() < deadline:
                time.sleep(0.02)
            assert runner.orchestrator.frames >= 3, (
                "the server never handed the audio to the pipeline"
            )

            audio.send_text(json.dumps({"type": "stop"}))
            assert json.loads(audio.receive_text())["type"] == "live_stopped"

        events = _read_until(stream, "run_end")

    kinds = [e["type"] for e in events]
    assert "run_meta" in kinds and "run_start" in kinds and "final" in kinds
    meta = next(e for e in events if e["type"] == "run_meta")
    assert meta["live"] is True
    assert meta["gallery_size"] == 0
    assert runner.live_source.closed, "the source stayed open after the run"

    # Nothing now holds the models: a second live run can start.
    assert client.post("/stop").json() == {"stopped": False}


def test_a_disconnecting_client_ends_the_run(app, client):
    """A vanished browser must not leave a pipeline holding the models."""
    runner = app.state.runner

    with client.websocket_connect("/stream") as stream:
        json.loads(stream.receive_text())

        with client.websocket_connect("/live/audio") as audio:
            audio.send_text(json.dumps({"type": "start", "sample_rate": 16000}))
            json.loads(audio.receive_text())
            audio.send_bytes(_tone_bytes())

        events = _read_until(stream, "run_end")

    assert runner.live_source.closed
    assert runner.orchestrator.frames >= 1
    assert any(e["type"] == "final" for e in events)


def test_audio_before_start_is_ignored_rather_than_crashing(app, client):
    runner = app.state.runner

    with client.websocket_connect("/live/audio") as audio:
        audio.send_bytes(_tone_bytes())          # no run yet
        audio.send_text(json.dumps({"type": "start", "sample_rate": 16000}))
        json.loads(audio.receive_text())
        audio.send_bytes(_tone_bytes())
        audio.send_bytes(_tone_bytes())
        audio.send_text(json.dumps({"type": "stop"}))
        audio.receive_text()

    deadline = time.time() + 5
    while runner.orchestrator.frames < 2 and time.time() < deadline:
        time.sleep(0.02)
    assert runner.orchestrator.frames == 2, (
        "the pre-start frame was counted as audio from the call"
    )


# --- voices -----------------------------------------------------------------
def test_voices_can_be_enrolled_listed_and_deleted(app, client, cfg):
    assert client.get("/voices").json() == {"voices": []}

    response = client.post("/voices", json={
        "display_name": "Demo Coordinator",
        "sample_rate": 16000,
        "pcm_int16_b64": _tone_int16_base64(1.5),
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["enrolled"] is True
    speaker_id = body["meta"]["speaker_id"]
    assert speaker_id == "demo-coordinator"
    assert body["meta"]["embedding_dim"] == 256

    listed = client.get("/voices").json()["voices"]
    assert [v["speaker_id"] for v in listed] == [speaker_id]
    assert listed[0]["display_name"] == "Demo Coordinator"

    # Privacy is a code property: fingerprints and metadata only, every time.
    store_dir = app.state.cfg.paths.enrolments_dir
    files = sorted(os.listdir(store_dir))
    assert files, "enrolment wrote nothing"
    assert all(f.endswith((".npy", ".json")) for f in files), files
    assert f"{speaker_id}.npy" in files and f"{speaker_id}.json" in files

    assert client.delete(f"/voices/{speaker_id}").json()["removed"] is True
    assert client.get("/voices").json() == {"voices": []}


def test_voice_enrolment_validates_its_input(app, client):
    assert client.post("/voices", json={}).status_code == 400
    assert client.post("/voices", json={
        "display_name": "X", "sample_rate": 16000, "pcm_int16_b64": "not base64!!",
    }).status_code == 400
    assert client.post("/voices", json={
        "display_name": "X", "sample_rate": 16000,
        "pcm_int16_b64": _tone_int16_base64(0.2),
    }).status_code == 400, "a 0.2 s recording is too short to embed"
    assert client.post("/voices", json={
        "display_name": "X", "sample_rate": 123, "pcm_int16_b64": _tone_int16_base64(2),
    }).status_code == 400


def test_enrolment_is_refused_while_a_run_is_going(app, client):
    """Enrolling under a running verdict would make the verdict unattributable."""
    with client.websocket_connect("/live/audio") as audio:
        audio.send_text(json.dumps({"type": "start", "sample_rate": 16000}))
        json.loads(audio.receive_text())
        audio.send_bytes(_tone_bytes())

        response = client.post("/voices", json={
            "display_name": "Too Late", "sample_rate": 16000,
            "pcm_int16_b64": _tone_int16_base64(1.5),
        })
        assert response.status_code == 409

        audio.send_text(json.dumps({"type": "stop"}))
        audio.receive_text()


# --- try a line -------------------------------------------------------------
def test_assess_returns_the_engines_own_assessment(app, client):
    response = client.post("/assess", json={"text": "push the funds across tonight"})
    assert response.status_code == 200
    body = response.json()
    assert body["audio"] is False, "the text path must not claim an audio result"
    assert body["would_fire"] == body["assessment"]["fired"]
    assert body["assessment"]["type"] == "intent_assessment"
    assert body["assessment"]["reason"]


def test_assess_rejects_an_empty_line(app, client):
    assert client.post("/assess", json={"text": "   "}).status_code == 400
    assert client.post("/assess", json={}).status_code == 400


def test_hello_carries_the_live_and_lookup_settings(client):
    hello = client.get("/hello").json()
    assert hello["live"]["no_audio_warn_ms"] > 0
    assert 0.0 < hello["lookup"]["accept_similarity"] <= 1.0
    assert hello["lookup"]["min_consecutive_windows"] >= 1
    assert hello["voices"] == []
