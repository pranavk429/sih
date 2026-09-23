"""
The server, tested without the models.

IMPLEMENTATION-PLAN 3.2 asks for two specific properties -- "two browser tabs
both receive the stream" and "stopping mid-run leaves no orphan thread" -- and
neither of them is about wav2vec2. So the orchestrator is stubbed out with one
that emits a scripted event list on a real worker thread. Everything under test
here (the fan-out, the history replay, the run lifecycle, the thread join) is
exercised for real; only the ten seconds of model loading is not.

The pipeline itself is covered by test_pipeline_golden.py.
"""
from __future__ import annotations

import json
import os
import threading
import time

import pytest
from fastapi.testclient import TestClient

from sentinel.server.app import create_app

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


class StubOrchestrator:
    """
    Emits a fixed event sequence, slowly enough to be stopped mid-run.

    `stop()` has to be honoured promptly, because the real orchestrator honours
    it once per 20 ms frame and the server's join timeout assumes that.
    """

    def __init__(self, n_events: int = 40, delay_s: float = 0.02) -> None:
        self.n_events = n_events
        self.delay_s = delay_s
        self.evidence = None
        self._stop = False
        self.runs = 0
        self.finished_naturally = 0
        self.emitted = 0

    def stop(self):
        self._stop = True

    def run(self, source, reference_embedding=None, speaker_id=None, mode=None,
            ground_truth=None, on_event=None, live=False, gallery=None):
        self.runs += 1
        self._stop = False
        on_event({"type": "run_start", "mode": mode or "triggered",
                  "ground_truth": ground_truth, "speaker_id": speaker_id,
                  "live": live, "gallery": None})
        for i in range(self.n_events):
            if self._stop:
                break
            self.emitted += 1
            on_event({"type": "verdict", "state": "MONITORING", "t_ms": i * 500,
                      "risk": 0.0, "seq": i})
            time.sleep(self.delay_s)
        else:
            self.finished_naturally += 1
        on_event({"type": "final", "state": "VERIFIED", "t_ms": self.n_events * 500})

        class _Stats:
            verdict = None
        return _Stats()


@pytest.fixture
def app(cfg):
    application = create_app(cfg, load_models=False)
    runner = application.state.runner
    runner.orchestrator = StubOrchestrator()
    runner.calibration = StubCalibration()
    return application


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def _read_until(ws, kind, limit=400):
    """Collect events off a socket until `kind` arrives."""
    out = []
    for _ in range(limit):
        event = json.loads(ws.receive_text())
        out.append(event)
        if event.get("type") == kind:
            return out
    raise AssertionError(f"never saw a {kind!r} event in {limit} messages; got "
                         f"{[e.get('type') for e in out[-10:]]}")


# --- the plain endpoints ----------------------------------------------------
def test_demos_lists_the_manifest(client, demo_dir):
    demos = client.get("/demos").json()
    ids = {c["id"] for c in demos["calls"]}
    assert {"genuine", "attack"} <= ids
    assert demos["speaker_id"]
    for call in demos["calls"]:
        assert call["ground_truth"] in ("bonafide", "spoof")
        # HANDOFF item 5: "where did 37 seconds come from" must be answerable.
        assert call["segments"], f"{call['id']} has no segment provenance"


def test_hello_carries_calibration_provenance(client):
    hello = client.get("/hello").json()
    assert hello["calibration"]["calibration_id"]
    assert hello["calibration"]["eer"] is not None
    assert "Simulated live call" in hello["honesty"]
    assert hello["band"] == pytest.approx([0.3636, 0.4575], abs=1e-4)


def test_unknown_demo_is_a_404_not_a_crash(client, demo_dir):
    response = client.post("/start", json={"demo": "nope"})
    assert response.status_code == 404
    assert "nope" in response.json()["error"]


# --- the stream -------------------------------------------------------------
def test_two_clients_both_receive_the_whole_run(client, demo_dir):
    """IMPLEMENTATION-PLAN 3.2: two browser tabs both receive the stream."""
    with client.websocket_connect("/stream") as a, \
            client.websocket_connect("/stream") as b:
        assert json.loads(a.receive_text())["type"] == "hello"
        assert json.loads(b.receive_text())["type"] == "hello"

        client.post("/start", json={"demo": "genuine", "fast": True})

        events_a = _read_until(a, "final")
        events_b = _read_until(b, "final")

    verdicts_a = [e for e in events_a if e["type"] == "verdict"]
    verdicts_b = [e for e in events_b if e["type"] == "verdict"]
    assert verdicts_a == verdicts_b, "the two tabs saw different runs"
    assert len(verdicts_a) == 40
    assert all(e["run_id"] for e in events_a if e["type"] != "run_meta")


def test_a_late_client_is_replayed_the_whole_run(client, demo_dir):
    """
    A tab opened mid-call sees the call from the start.

    This is the projector-plus-laptop case, and it is also what makes the demo
    recoverable if a browser is refreshed at the wrong moment.
    """
    client.post("/start", json={"demo": "genuine", "fast": True})
    time.sleep(0.3)  # let some of the run go past before connecting

    with client.websocket_connect("/stream") as ws:
        assert json.loads(ws.receive_text())["type"] == "hello"
        events = _read_until(ws, "final")

    kinds = [e["type"] for e in events]
    assert kinds[0] == "run_meta", "the late client did not get the run header"
    assert kinds[1] == "run_start"
    assert len([e for e in events if e["type"] == "verdict"]) == 40

    seqs = [e["seq"] for e in events if e["type"] == "verdict"]
    assert seqs == sorted(seqs), "history and live stream interleaved out of order"
    assert len(set(seqs)) == len(seqs), "an event was delivered twice"


def test_one_socket_survives_two_consecutive_runs(client, demo_dir):
    """Between takes, the presenter does not have to reload the page."""
    with client.websocket_connect("/stream") as ws:
        json.loads(ws.receive_text())  # hello

        client.post("/start", json={"demo": "genuine", "fast": True})
        first = _read_until(ws, "final")
        client.post("/start", json={"demo": "attack", "fast": True})
        second = _read_until(ws, "final")

    assert first[0]["type"] == "run_meta" and first[0]["demo"] == "genuine"
    meta = next(e for e in second if e["type"] == "run_meta")
    assert meta["demo"] == "attack"
    assert meta["run_id"] != first[0]["run_id"]


# --- the run lifecycle ------------------------------------------------------
def test_stopping_mid_run_leaves_no_orphan_thread(app, client, demo_dir):
    """IMPLEMENTATION-PLAN 3.2, the other half."""
    runner = app.state.runner
    before = {t.name for t in threading.enumerate()}

    client.post("/start", json={"demo": "genuine", "fast": True})
    time.sleep(0.15)
    assert runner.is_running

    assert client.post("/stop").json() == {"stopped": True}
    assert not runner.is_running
    assert runner.orchestrator.emitted < runner.orchestrator.n_events, (
        "the run finished before we could stop it -- the test proves nothing"
    )
    assert runner.orchestrator.finished_naturally == 0

    leaked = {t.name for t in threading.enumerate()} - before
    assert not any(n.startswith("sentinel-run-") for n in leaked), (
        f"orphan pipeline thread(s): {leaked}"
    )


def test_stop_is_idempotent(client, demo_dir):
    assert client.post("/stop").json() == {"stopped": False}
    client.post("/start", json={"demo": "genuine", "fast": True})
    assert client.post("/stop").json() == {"stopped": True}
    assert client.post("/stop").json() == {"stopped": False}


def test_starting_twice_replaces_the_run_rather_than_erroring(app, client, demo_dir):
    """A presenter who clicks the button twice wants the second call."""
    runner = app.state.runner
    first = client.post("/start", json={"demo": "genuine", "fast": True})
    assert first.status_code == 200
    time.sleep(0.1)
    second = client.post("/start", json={"demo": "attack", "fast": True})
    assert second.status_code == 200
    assert second.json()["meta"]["run_id"] != first.json()["meta"]["run_id"]
    assert runner.orchestrator.runs == 2
    client.post("/stop")
    assert len([t for t in threading.enumerate()
                if t.name.startswith("sentinel-run-")]) == 0


def test_a_crashing_run_reaches_the_screen_instead_of_hanging(app, client, demo_dir):
    """A pipeline exception must become a visible error, not a silent stall."""
    runner = app.state.runner

    class Exploding(StubOrchestrator):
        def run(self, source, on_event=None, **kwargs):
            on_event({"type": "run_start", "mode": "triggered"})
            raise ValueError("boom")

    runner.orchestrator = Exploding()

    with client.websocket_connect("/stream") as ws:
        json.loads(ws.receive_text())  # hello
        client.post("/start", json={"demo": "genuine", "fast": True})
        events = _read_until(ws, "run_end")

    error = next(e for e in events if e["type"] == "run_error")
    assert "boom" in error["message"]
    assert events[-1]["error"] and "boom" in events[-1]["error"]


def test_state_reports_the_run(client, demo_dir):
    assert client.get("/state").json()["running"] is False
    client.post("/start", json={"demo": "genuine", "fast": True})
    state = client.get("/state").json()
    assert state["running"] is True
    assert state["meta"]["demo"] == "genuine"
    assert state["meta"]["ground_truth"] == "bonafide"
    client.post("/stop")


def test_the_run_writes_its_own_evidence_log(app, client, cfg, demo_dir):
    runner = app.state.runner
    client.post("/start", json={"demo": "genuine", "fast": True})
    time.sleep(0.1)
    log = runner.orchestrator.evidence
    assert log is not None
    assert os.path.dirname(os.path.abspath(log.path)) == \
        os.path.abspath(cfg.paths.evidence_dir)
    assert runner.session.meta["run_id"] in log.path
    client.post("/stop")


# --- the audio path is not a free filesystem handle -------------------------
def test_an_audio_path_outside_the_demo_directory_is_refused(client, demo_dir):
    """
    /start accepts an arbitrary `audio` string from the browser. Before the
    fence it became a filesystem path verbatim, so anything reaching the
    endpoint could ask the server to open any file the process could read and
    stream it back as a "call". The demo directory is the whole allowed world.
    """
    for attempt in ("../../../../etc/passwd", "/etc/passwd", "../config.yaml"):
        response = client.post("/start", json={"audio": attempt})
        assert response.status_code == 404, f"{attempt} was not refused"
        assert "outside the demo directory" in response.json()["error"]


def test_an_audio_path_inside_the_demo_directory_still_works(client, demo_dir):
    """The fence must not break the thing it is fencing."""
    response = client.post("/start", json={"audio": "enrol.wav", "fast": True})

    assert response.status_code == 200, response.text
    assert response.json()["started"] is True
    client.post("/stop")
