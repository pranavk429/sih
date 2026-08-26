"""
SPEC §9: fixed WAV -> snapshot the event sequence. Catches regressions across
the whole spine, which no unit test can.

Two assertions, and they protect different things:

1. STABILITY. The same audio through the same pipeline twice must produce
   byte-identical events. This is what SPEC §7.1 buys us -- every timestamp is
   stream time, so a replay is reproducible. If this fails, something in the
   pipeline has picked up a dependency on the wall clock, on iteration order, or
   on model non-determinism, and every other number in the demo becomes a claim
   rather than a measurement.

2. THE COMMITTED SNAPSHOT. `golden/pipeline_attack.json` records what the
   attack call actually produced. If a change to framing, VAD, gating, fusion or
   the decision engine moves it, this test says so and names the event. It is
   not a correctness oracle -- it is a "you changed something, was that on
   purpose?" alarm. Regenerate deliberately:

       SENTINEL_UPDATE_GOLDEN=1 ../detector/venv/bin/python -m pytest \
           tests/test_pipeline_golden.py -q

   and read the diff before committing it.

ASR is off here. faster-whisper is the one stage that is not reproducible
run-to-run, and the trigger mechanism is demonstrated by the scripted overlay,
which is deterministic. `test_trigger.py` covers the transcript path.

Wall-clock fields (`pipeline_lag_ms`, `wall_s`, `max_lag_ms`) are stripped from
the digest on purpose. They are measurements of this machine on this run, not
properties of the pipeline, and including them would make the snapshot flap.
"""
from __future__ import annotations

import json
import os

import pytest

from sentinel.audio.source import FileSource
from sentinel.decision.calibration import Calibration
from sentinel.enrolment.store import EnrolmentStore
from sentinel.pipeline.orchestrator import Orchestrator
from sentinel.trigger.engine import TriggerEngine
from sentinel.types import LIKELY_IMPERSONATION

GOLDEN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden")
GOLDEN_PATH = os.path.join(GOLDEN_DIR, "pipeline_attack.json")

# Model scores are floats off MPS/CPU kernels. Identical inputs give identical
# outputs on one machine -- that is what test 1 asserts -- but the committed
# snapshot also has to survive a torch point release, so it compares numbers
# with a tolerance well below anything that could move a verdict. The abstention
# band is 0.094 wide; this is a hundredth of that.
FLOAT_TOL = 1e-3


# --- the digest -------------------------------------------------------------
# One compact, reviewable line per event. A raw dump of every field would be a
# 200 KB file nobody reads, and an unread snapshot is not a test.
def _digest_event(event):
    kind = event.get("type")
    if kind == "run_start":
        return {
            "type": kind,
            "mode": event["mode"],
            "ground_truth": event["ground_truth"],
            "scripted_overlay": event["scripted_overlay"],
            "band": event["band"],
            "calibration_id": event["calibration"]["calibration_id"],
            "model_ids": event["model_ids"],
        }
    if kind == "utterance":
        return {
            "type": kind,
            "t_start_ms": event["t_start_ms"],
            "t_end_ms": event["t_end_ms"],
            "scripted": event["scripted"],
            "text": event["text"],
        }
    if kind == "trigger":
        return {
            "type": kind,
            "t_ms": event["t_ms"],
            "intent": event["intent"],
            "stage": event["stage"],
            "margin": event["margin"],
            "scripted": event["scripted"],
        }
    if kind == "risk_score":
        return {
            "type": kind,
            "kind": event["kind"],
            "seq": event["seq"],
            "t_start_ms": event["t_start_ms"],
            "t_end_ms": event["t_end_ms"],
            "status": event["status"],
            "value": event["value"],
        }
    if kind in ("verdict", "final"):
        out = {
            "type": kind,
            "t_ms": event["t_ms"],
            "state": event["state"],
            "risk": event["risk"],
            "confidence": event["confidence"],
            "triggered": event["triggered"],
            "enrolled": event["enrolled"],
            "n_windows": event["n_windows"],
            "n_segments": len(event["segments"]),
        }
        if kind == "verdict":
            out["alerts"] = event["alerts"]
            out["false_alarms"] = event["false_alarms"]
            out["mode"] = event["mode"]
        else:
            stats = dict(event["stats"])
            # Wall-clock measurements of this machine, not properties of the
            # pipeline. Keeping them would make the snapshot flap on every run.
            for wall in ("max_lag_ms", "wall_s"):
                stats.pop(wall, None)
            out["stats"] = stats
        return out
    raise AssertionError(f"unknown event type {kind!r} -- add it to the digest")


def _compare(actual, expected, path="events"):
    """Structure exactly, floats within tolerance, and say where it diverged."""
    if isinstance(expected, float) or isinstance(actual, float):
        assert actual is not None and expected is not None, f"{path}: {actual} != {expected}"
        assert abs(float(actual) - float(expected)) <= FLOAT_TOL, (
            f"{path}: {actual} != {expected} (tolerance {FLOAT_TOL})"
        )
        return
    if isinstance(expected, dict):
        assert isinstance(actual, dict), f"{path}: expected a mapping, got {type(actual).__name__}"
        assert sorted(actual) == sorted(expected), (
            f"{path}: keys differ\n  extra:   {sorted(set(actual) - set(expected))}"
            f"\n  missing: {sorted(set(expected) - set(actual))}"
        )
        for key in expected:
            _compare(actual[key], expected[key], f"{path}.{key}")
        return
    if isinstance(expected, list):
        assert isinstance(actual, list), f"{path}: expected a list, got {type(actual).__name__}"
        assert len(actual) == len(expected), (
            f"{path}: {len(actual)} entries, snapshot has {len(expected)}"
        )
        for i, (a, e) in enumerate(zip(actual, expected)):
            _compare(a, e, f"{path}[{i}]")
        return
    assert actual == expected, f"{path}: {actual!r} != {expected!r}"


# --- fixtures ---------------------------------------------------------------
@pytest.fixture(scope="module")
def orchestrator(cfg, countermeasure, speaker_encoder):
    cal = Calibration.load(cfg.models.calibration_path)
    return Orchestrator(
        cfg,
        countermeasure,
        speaker_encoder,
        cal,
        TriggerEngine(cfg.trigger, cfg.models),
        asr_thread_factory=None,   # whisper is the one non-deterministic stage
        evidence_log=None,         # a golden test must not write to artifacts/
    )


@pytest.fixture(scope="module")
def reference(cfg, demo_dir):
    with open(os.path.join(demo_dir, "manifest.json")) as fh:
        manifest = json.load(fh)
    ref = EnrolmentStore(cfg.paths.enrolments_dir).get(manifest["speaker_id"])
    if ref is None:
        pytest.skip(
            f"{manifest['speaker_id']} is not enrolled -- run: "
            "python -m sentinel.cli enrol --demo enrol"
        )
    return ref


def _replay(orchestrator, cfg, demo_dir, call_id, reference, mode="triggered",
            ground_truth="spoof"):
    events = []
    source = FileSource(
        os.path.join(demo_dir, f"{call_id}.wav"),
        sample_rate=cfg.audio.sample_rate,
        frame_ms=cfg.audio.frame_ms,
        realtime=False,   # flat out; identical frames, identical stream times
    )
    stats = orchestrator.run(
        source,
        reference_embedding=reference,
        speaker_id="LA_0022",
        mode=mode,
        ground_truth=ground_truth,
        on_event=events.append,
    )
    return [_digest_event(e) for e in events], stats


@pytest.fixture(scope="module")
def attack_run(orchestrator, cfg, demo_dir, reference):
    return _replay(orchestrator, cfg, demo_dir, "attack", reference)


# --- 1. stability -----------------------------------------------------------
def test_event_sequence_is_identical_across_runs(orchestrator, cfg, demo_dir,
                                                 reference, attack_run):
    first, _ = attack_run
    second, _ = _replay(orchestrator, cfg, demo_dir, "attack", reference)
    assert second == first, (
        "the same audio produced different events on a second replay -- "
        "something in the pipeline depends on the wall clock, on iteration "
        "order, or on a non-deterministic model"
    )


def test_stream_time_never_goes_backwards(attack_run):
    """SPEC §7.1. If this breaks, the timeline and the evidence log both lie."""
    events, _ = attack_run
    last = {}
    for i, event in enumerate(events):
        kind = event["type"]
        t = event.get("t_end_ms", event.get("t_ms"))
        if t is None:
            continue
        # Pre-roll deliberately reaches backwards, but only for cm scores.
        if kind == "risk_score" and event["kind"] == "cm":
            continue
        assert t >= last.get(kind, -1), (
            f"events[{i}] ({kind}) went back in stream time: {t} after {last[kind]}"
        )
        last[kind] = t


# --- 2. the committed snapshot ---------------------------------------------
def test_matches_committed_golden(attack_run):
    events, _ = attack_run

    if os.environ.get("SENTINEL_UPDATE_GOLDEN"):
        os.makedirs(GOLDEN_DIR, exist_ok=True)
        with open(GOLDEN_PATH, "w") as fh:
            json.dump(events, fh, indent=1)
            fh.write("\n")
        pytest.skip(f"golden snapshot rewritten: {GOLDEN_PATH}")

    assert os.path.exists(GOLDEN_PATH), (
        f"no golden snapshot at {GOLDEN_PATH}. Create it with:\n"
        "  SENTINEL_UPDATE_GOLDEN=1 ../detector/venv/bin/python -m pytest "
        "tests/test_pipeline_golden.py -q"
    )
    with open(GOLDEN_PATH) as fh:
        expected = json.load(fh)
    _compare(events, expected)


# --- 3. the shape the UI depends on ----------------------------------------
def test_the_attack_call_triggers_and_is_flagged(attack_run):
    events, stats = attack_run
    assert stats.triggers > 0, "the scripted overlay did not fire the trigger"
    assert stats.windows_deep > 0, "no window was deep-scored after the trigger"
    assert stats.verdict.state == LIKELY_IMPERSONATION
    assert stats.verdict.segments, "flagged with no evidence segments to show"
    assert stats.verdict.reasons, "SPEC §7.4: reasons is never empty"


def test_the_system_is_quiet_before_the_trigger(attack_run):
    """The thesis, pinned: no deep scoring until a high-risk intent appears."""
    events, _ = attack_run
    first_trigger = next(e["t_ms"] for e in events if e["type"] == "trigger")
    first_cm = next(
        e["t_end_ms"] for e in events
        if e["type"] == "risk_score" and e["kind"] == "cm"
    )
    verdicts_before = [
        e for e in events
        if e["type"] == "verdict" and e["t_ms"] < first_trigger
    ]
    assert verdicts_before, "no verdicts emitted before the trigger"
    assert all(v["state"] == "MONITORING" for v in verdicts_before), (
        "the system committed to a verdict before any trigger fired"
    )
    # ...but the pre-roll must have reached back BEHIND the trigger.
    assert first_cm < first_trigger, (
        f"pre-roll did not backfill: first cm score ends at {first_cm} ms, "
        f"trigger fired at {first_trigger} ms"
    )


def test_scripted_overlay_lines_are_flagged_all_the_way_to_the_event_stream(attack_run):
    """
    An unlabelled scripted line is the one thing that would make this demo
    dishonest (SPEC §12). The flag is set in ScriptedOverlay; this asserts it
    survives every hop to the UI.
    """
    events, _ = attack_run
    start = next(e for e in events if e["type"] == "run_start")
    assert start["scripted_overlay"] is True

    utterances = [e for e in events if e["type"] == "utterance"]
    assert utterances, "no transcript lines at all"
    assert all(u["scripted"] for u in utterances), (
        "ASR is off in this test, so every utterance must be a scripted overlay "
        "line and must say so"
    )
    for trigger in (e for e in events if e["type"] == "trigger"):
        assert trigger["scripted"] is True


def test_every_event_carries_what_the_ui_needs(attack_run):
    """The payload contract in HANDOFF.md, asserted rather than trusted."""
    events, _ = attack_run
    seen = {e["type"] for e in events}
    assert seen >= {"run_start", "utterance", "trigger", "risk_score", "verdict", "final"}
    assert events[0]["type"] == "run_start"
    assert events[-1]["type"] == "final"

    start = events[0]
    assert start["calibration_id"], "SPEC §12: the header needs calibration provenance"
    assert start["band"] == pytest.approx([0.3636, 0.4575], abs=1e-4)

    for score in (e for e in events if e["type"] == "risk_score"):
        assert score["status"] in ("OK", "SILENT", "ERROR")
        # A non-OK score carries no number. That is the Gap 3 contract: never a
        # fabricated value standing in for silence.
        assert (score["value"] is None) == (score["status"] != "OK")

    for verdict in (e for e in events if e["type"] == "verdict"):
        assert verdict["state"] in (
            "MONITORING", "VERIFIED", "UNCERTAIN", "LIKELY_IMPERSONATION"
        )


def test_the_pre_roll_never_scores_a_window_the_vad_refused(
        orchestrator, cfg, demo_dir, reference):
    """
    The gate applies to the backfill too, not just the forward pass.

    The pre-roll reaches back over windows that have already gone past, and it
    used to call the countermeasure on them directly -- VAD and all. Silent
    windows came back at ~0.99 (see test_vad_silence.py) and landed in the
    evidence panel of a VERIFIED call. The genuine call is the one with silence
    in it, so it is the one this has to be checked on.
    """
    events, stats = _replay(orchestrator, cfg, demo_dir, "genuine", reference,
                            ground_truth="bonafide")
    scores = {}
    for event in events:
        if event["type"] == "risk_score":
            scores.setdefault(event["seq"], {})[event["kind"]] = event

    silent_but_scored = [
        seq for seq, kinds in scores.items()
        if kinds.get("speaker", {}).get("status") == "SILENT"
        and kinds.get("cm", {}).get("status") == "OK"
    ]
    assert not silent_but_scored, (
        f"windows {silent_but_scored} were refused by the VAD for the speaker "
        "model but scored anyway by the countermeasure"
    )
    assert stats.windows_silent > 0, (
        "the genuine call has silent windows in it -- if it stopped having "
        "them, this test no longer proves anything and needs a new fixture"
    )
    for segment in stats.verdict.segments:
        assert segment.cm_risk is None or segment.speaker_risk is not None, (
            f"evidence segment at {segment.t_start_ms} ms rests on the "
            "countermeasure alone, with no voice-match score beside it"
        )


def test_a_stopped_run_ends_cleanly(orchestrator, cfg, demo_dir, reference):
    """`POST /stop` in the server rides on this. A half-finished run still
    produces a final verdict rather than leaving the UI hanging."""
    events = []
    source = FileSource(
        os.path.join(demo_dir, "attack.wav"),
        sample_rate=cfg.audio.sample_rate,
        frame_ms=cfg.audio.frame_ms,
        realtime=False,
    )

    def on_event(event):
        events.append(event)
        if event.get("type") == "trigger":
            orchestrator.stop()

    stats = orchestrator.run(
        source, reference_embedding=reference, speaker_id="LA_0022",
        ground_truth="spoof", on_event=on_event,
    )
    assert events[-1]["type"] == "final"
    assert stats.verdict is not None
    assert stats.stream_s < source.duration_s, "stop() did not cut the run short"
