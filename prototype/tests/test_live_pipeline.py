"""
The live path is the SAME pipeline, not a parallel one.

This is the test that makes that claim true rather than aspirational: the same
audio pushed through a LiveSource in 30 ms chunks must produce exactly the same
events as the same audio read from a FileSource. If the two ever diverge,
something downstream has started depending on how the frames arrived.

The live source is fed from a thread, which is how the server feeds it -- the
queue is bounded and the pipeline consumes while audio arrives.
"""
from __future__ import annotations

import json
import os
import threading

import numpy as np
import pytest
import soundfile as sf

from sentinel.audio.live_source import LiveSource
from sentinel.audio.resample import prepare
from sentinel.audio.source import FileSource
from sentinel.decision.calibration import Calibration
from sentinel.enrolment.store import EnrolmentStore
from sentinel.pipeline.orchestrator import Orchestrator
from sentinel.trigger.engine import TriggerEngine
from sentinel.types import Utterance


@pytest.fixture(scope="module")
def orchestrator(cfg, countermeasure, speaker_encoder):
    cal = Calibration.load(cfg.models.calibration_path)
    return Orchestrator(
        cfg, countermeasure, speaker_encoder, cal,
        TriggerEngine(cfg.trigger, cfg.models),
        asr_thread_factory=None,
        evidence_log=None,
    )


@pytest.fixture(scope="module")
def reference(cfg, demo_dir):
    with open(os.path.join(demo_dir, "manifest.json")) as fh:
        manifest = json.load(fh)
    ref = EnrolmentStore(cfg.paths.enrolments_dir).get(manifest["speaker_id"])
    if ref is None:
        pytest.skip("demo speaker is not enrolled")
    return ref


def _weather(event):
    """Strip the fields that are properties of the SOURCE or the MACHINE."""
    if event["type"] == "run_start":
        return {k: event[k] for k in
                ("type", "mode", "ground_truth", "scripted_overlay", "band",
                 "model_ids")}
    if event["type"] == "verdict":
        # `pipeline_lag_ms` is how fast this machine was on this run. The golden
        # test strips it for the same reason: it would make a deterministic
        # comparison flap.
        return {k: v for k, v in event.items() if k != "pipeline_lag_ms"}
    if event["type"] == "final":
        stats = dict(event["stats"])
        for wall in ("max_lag_ms", "wall_s"):
            stats.pop(wall, None)
        return {**event, "stats": stats}
    return event


def test_the_live_source_reproduces_the_file_run(cfg, demo_dir, orchestrator, reference):
    path = os.path.join(demo_dir, "attack.wav")

    file_events = []
    orchestrator.run(
        FileSource(path, sample_rate=cfg.audio.sample_rate,
                   frame_ms=cfg.audio.frame_ms, realtime=False),
        reference_embedding=reference, speaker_id="LA_0022", mode="triggered",
        ground_truth="spoof", on_event=file_events.append,
    )

    pcm, sr = sf.read(path, dtype="float32", always_2d=False)
    pcm = prepare(pcm, sr, cfg.audio.sample_rate)

    live = LiveSource(sample_rate=cfg.audio.sample_rate,
                      frame_ms=cfg.audio.frame_ms,
                      # Big enough that a fast feeder cannot overflow it: this
                      # test isolates "same frames -> same events". The drop
                      # policy has its own tests in test_live_source.py.
                      max_queue_frames=4000)

    def feeder():
        step = int(cfg.audio.sample_rate * 0.03)   # 30 ms chunks, as a browser sends
        for i in range(0, len(pcm), step):
            live.push(pcm[i:i + step], cfg.audio.sample_rate)
        live.close()

    thread = threading.Thread(target=feeder, daemon=True)
    thread.start()

    live_events = []
    orchestrator.run(
        live, reference_embedding=reference, speaker_id="LA_0022", mode="triggered",
        ground_truth="spoof", on_event=live_events.append,
        # NOTE: live=False deliberately. Live MODE disables the scripted overlay
        # (that is a separate, tested property); this test is about the SOURCE.
    )
    thread.join(timeout=5.0)
    assert not thread.is_alive()

    assert [e["type"] for e in live_events] == [e["type"] for e in file_events], (
        "the live source produced a different event sequence from the file source"
    )
    assert [_weather(e) for e in live_events] == [_weather(e) for e in file_events]
    assert live.dropped_ms == 0, "the feeder must not outrun the queue in this test"


def test_live_mode_disables_the_scripted_overlay(cfg, demo_dir, orchestrator, reference):
    """
    Putting words in a live speaker's mouth would make the demo dishonest, so
    the overlay is off in live mode regardless of config.
    """
    assert cfg.trigger.scripted_overlay, (
        "config has no overlay -- this test cannot prove the disabling works"
    )
    live = LiveSource(sample_rate=cfg.audio.sample_rate, frame_ms=cfg.audio.frame_ms)
    live.close()

    events = []
    orchestrator.run(
        live, reference_embedding=reference, speaker_id="LA_0022",
        mode="triggered", ground_truth=None, on_event=events.append, live=True,
    )
    start = next(e for e in events if e["type"] == "run_start")
    assert start["live"] is True
    assert start["source"] == "live"
    assert start["scripted_overlay"] is False
    assert not [e for e in events if e["type"] == "utterance"], (
        "a live run injected a scripted line"
    )
    assert "Live microphone" in start["honesty"]


class _LateAsrStub:
    """
    An ASR thread whose only transcript line arrives after the source ends.

    That is not a contrived case: it is what the last sentence of any file run
    does, and what a live run does when the operator stops the microphone right
    after speaking. The orchestrator drains those lines after the frame loop;
    they must be assessed like every other line, or the last instruction of a
    demo take can never fire.
    """

    def __init__(self, text: str, t_end_ms: int, on_utterance) -> None:
        self.text = text
        self.t_end_ms = t_end_ms
        self.on_utterance = on_utterance
        self.blocked_pushes = 0

    def start(self) -> None:
        pass

    def push(self, frame) -> None:
        pass

    def close(self, timeout: float = 10.0) -> None:
        self.on_utterance(Utterance(
            text=self.text,
            t_start_ms=max(0, self.t_end_ms - 3000),
            t_end_ms=self.t_end_ms,
            scripted=False,
        ))


def test_a_sentence_flushed_after_the_source_ends_is_still_assessed(
        cfg, demo_dir, countermeasure, speaker_encoder, orchestrator):
    """
    The post-loop drain goes through the trigger, not around it.

    Regression: the drain used to emit the final transcript lines bare. On a
    live run that a presenter stops right after speaking, the last instruction
    appeared on screen with no margin chip, no trigger and no verdict -- the
    exact missed trigger the ASR queue's block-don't-drop policy exists to
    prevent, reintroduced at the end of the stream.
    """
    late = {}
    trigger_line = "transfer two crore to this account tonight"

    def factory(on_utterance):
        stub = _LateAsrStub(trigger_line, t_end_ms=2000, on_utterance=on_utterance)
        late["asr"] = stub
        return stub

    runner = Orchestrator(
        cfg, countermeasure, speaker_encoder,
        Calibration.load(cfg.models.calibration_path),
        # Reuse the module's trigger engine: MiniLM is the slow part of setup.
        orchestrator.trigger_engine,
        asr_thread_factory=factory,
        evidence_log=None,
    )

    live = LiveSource(sample_rate=cfg.audio.sample_rate,
                      frame_ms=cfg.audio.frame_ms)
    live.close()          # no audio at all: only the drained sentence matters

    events = []
    stats = runner.run(
        live, reference_embedding=None, speaker_id=None, mode="triggered",
        ground_truth=None, on_event=events.append, live=True,
    )

    utterances = [e for e in events if e["type"] == "utterance"]
    assert [u["text"] for u in utterances] == [trigger_line]
    assessment = utterances[0].get("assessment")
    assert assessment is not None, (
        "the drained utterance was emitted without an assessment -- the margin "
        "chip and the trigger both read this field"
    )
    assert assessment["fired"] is True
    triggers = [e for e in events if e["type"] == "trigger"]
    assert len(triggers) == 1, "the last sentence of the run was never allowed to fire"
    assert stats.triggers == 1
    assert events[-1]["type"] == "final"
    assert events[-1]["triggered"] is True, (
        "the verdict does not know the run was triggered"
    )


def test_the_gallery_is_reported_in_the_header_and_looked_up(cfg, demo_dir,
                                                            orchestrator, reference):
    """With a gallery present the run emits voice_lookup events; the header says
    how many candidates and with what thresholds.
    """
    from sentinel.enrolment.gallery import Gallery

    gallery = Gallery(["LA_0022"], {"LA_0022": "Demo speaker"},
                      np.vstack([reference]), accept_similarity=0.5,
                      min_margin=0.01)
    events = []
    orchestrator.run(
        FileSource(os.path.join(demo_dir, "genuine.wav"),
                   sample_rate=cfg.audio.sample_rate,
                   frame_ms=cfg.audio.frame_ms, realtime=False),
        reference_embedding=reference, speaker_id="LA_0022", mode="triggered",
        ground_truth="bonafide", on_event=events.append, gallery=gallery,
    )
    start = next(e for e in events if e["type"] == "run_start")
    assert start["gallery"]["size"] == 1
    assert start["gallery"]["accept_similarity"] == 0.5

    lookups = [e for e in events if e["type"] == "voice_lookup"]
    assert lookups, "a gallery was present but nothing was looked up"
    assert all(e["gallery_size"] == 1 for e in lookups)
    announced = [e for e in lookups if e["announced_id"] == "LA_0022"]
    assert announced, (
        "the genuine call's own speaker was never announced; check the threshold"
    )
