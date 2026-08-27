"""
The pipeline loop. One thread, running everything except ASR, in order.

SPEC §7.2 ran the numbers before choosing this shape:

    speaker embed   30-60 ms    every 0.5 s hop
    CM embed        40-80 ms    only when gated on
    trigger MiniLM  ~10 ms      once per utterance
    ASR             300-600 ms  once per utterance   <- the only one over budget

Against a 500 ms hop that fits in one sequential loop with room to spare, so
that is what this is: read frame, window it, VAD, score, decide, emit. Three
async workers and a message bus would be speculative complexity solving a
problem we measured and do not have. Measured lag is emitted to the screen as
`pipeline_lag_ms` -- if we ever do fall behind, the demo says so rather than
quietly claiming to be real-time.

The one subtlety is the PRE-ROLL. When a trigger fires at t=21s, the audio worth
scoring is the audio that carried the instruction, which is already several
seconds in the past. So the loop reaches back into the Framer's history and
scores those windows retrospectively, before continuing forward. Without that,
deep verification would be scoring the caller's next sentence.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from sentinel.audio.framing import Framer
from sentinel.audio.vad import EnergyVad
from sentinel.config import Config
from sentinel.decision.calibration import Calibration
from sentinel.decision.engine import aggregate, decide
from sentinel.decision.fusion import build_fusion
from sentinel.decision.gating import AlwaysOnGating, build_gating
from sentinel.models.resemblyzer_spk import SilentAudio
from sentinel.trigger.engine import ScriptedOverlay, TriggerEngine
from sentinel.types import (
    CM,
    ERROR,
    LIKELY_IMPERSONATION,
    MONITORING,
    OK,
    SILENT,
    SPEAKER,
    EvidenceSegment,
    RiskScore,
    TriggerEvent,
    Utterance,
    Window,
)

EventSink = Callable[[Dict[str, Any]], None]


@dataclass
class RunStats:
    """What the run did, for the console summary and the UI footer."""

    windows_total: int = 0
    windows_scored: int = 0
    windows_silent: int = 0
    windows_deep: int = 0
    utterances: int = 0
    triggers: int = 0
    alerts: int = 0
    false_alarms: int = 0
    max_lag_ms: int = 0
    asr_blocked_pushes: int = 0
    events_dropped: int = 0
    wall_s: float = 0.0
    stream_s: float = 0.0
    verdict: Optional[Any] = None
    evidence_path: Optional[str] = None
    reasons: List[str] = field(default_factory=list)


class Orchestrator:
    """
    Runs one call end to end.

    Models, calibration and the trigger engine are injected rather than built
    here so the server can load them once at startup and reuse them across
    demo runs -- reloading wav2vec2 between takes would put a ten-second pause
    in the middle of a live demo.
    """

    def __init__(
        self,
        cfg: Config,
        countermeasure,
        speaker_encoder,
        calibration: Calibration,
        trigger_engine: TriggerEngine,
        asr_thread_factory: Optional[Callable[[Callable[[Utterance], None]], Any]] = None,
        evidence_log=None,
    ) -> None:
        self.cfg = cfg
        self.cm = countermeasure
        self.spk = speaker_encoder
        self.cal = calibration
        self.trigger_engine = trigger_engine
        self.asr_thread_factory = asr_thread_factory
        self.evidence = evidence_log

        self.vad = EnergyVad(cfg.audio)
        self.fusion = build_fusion(cfg.decision.fusion, calibration)
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    # ------------------------------------------------------------------
    def run(
        self,
        source,
        reference_embedding=None,
        speaker_id: Optional[str] = None,
        mode: Optional[str] = None,
        ground_truth: Optional[str] = None,
        on_event: Optional[EventSink] = None,
    ) -> RunStats:
        cfg = self.cfg
        emit: EventSink = on_event or (lambda _e: None)
        self._stop = False

        gating = build_gating(
            mode or cfg.gating.mode, cfg.gating.pre_roll_s, cfg.gating.hold_s
        )
        naive = isinstance(gating, AlwaysOnGating)

        # History must outlast the pre-roll or backfill points at audio that has
        # already been discarded and the pre-roll silently does nothing.
        framer = Framer(
            sample_rate=cfg.audio.sample_rate,
            window_s=cfg.audio.window_s,
            hop_s=cfg.audio.hop_s,
            history_s=cfg.gating.pre_roll_s + cfg.audio.window_s + 1.0,
        )

        overlay = ScriptedOverlay(cfg.trigger.scripted_overlay)
        stats = RunStats()
        triggers: List[TriggerEvent] = []
        pending_utterances: List[Utterance] = []
        spk_scores: Dict[int, RiskScore] = {}
        cm_scores: Dict[int, RiskScore] = {}
        window_index: Dict[int, Window] = {}
        deep_seqs: List[int] = []

        asr = None
        if self.asr_thread_factory is not None:
            asr = self.asr_thread_factory(pending_utterances.append)
            asr.start()

        emit(self._start_event(source, speaker_id, gating, overlay, ground_truth, mode))

        started = time.monotonic()
        last_verdict_state = None
        stream_ms = 0

        try:
            for frame in source.frames():
                if self._stop:
                    break
                stream_ms = frame.t_start_ms
                if asr is not None:
                    asr.push(frame)

                for utterance in overlay.due(frame.t_start_ms):
                    pending_utterances.append(utterance)

                while pending_utterances:
                    utterance = pending_utterances.pop(0)
                    stats.utterances += 1
                    emit(utterance.to_json())
                    event = self.trigger_engine.evaluate(utterance)
                    if event is None:
                        continue
                    triggers.append(event)
                    stats.triggers += 1
                    payload = event.to_json()
                    payload["description"] = self.trigger_engine.describe(event)
                    # The spans the UI shades on the timeline. Computed here
                    # rather than re-derived in JavaScript from pre_roll/hold --
                    # two implementations of the gating window would eventually
                    # disagree, and the screen would then be showing something
                    # other than what the system did.
                    payload["active_regions"] = [
                        list(r) for r in gating.active_regions(triggers)
                    ]
                    emit(payload)
                    if self.evidence is not None:
                        self.evidence.append("trigger", payload, t_ms=event.t_ms)

                    # Pre-roll: score the windows the instruction actually
                    # landed in, which have already gone past.
                    self._backfill(
                        framer, gating, triggers, window_index, cm_scores,
                        deep_seqs, stats, emit,
                    )

                for window in framer.push(frame):
                    window_index[window.seq] = window
                    stats.windows_total += 1
                    self._score_window(
                        window, gating, triggers, reference_embedding,
                        spk_scores, cm_scores, deep_seqs, stats, emit,
                    )

                    verdict = self._decide(
                        gating, triggers, spk_scores, cm_scores, window_index,
                        deep_seqs, reference_embedding is not None, window.t_end_ms,
                    )
                    alerted = verdict.state == LIKELY_IMPERSONATION
                    if naive:
                        # The naive design has no verdict to speak of -- it just
                        # alerts on any window over threshold. Counting it that
                        # way is what makes the comparison fair rather than a
                        # strawman.
                        fused = self._window_fused(window.seq, spk_scores, cm_scores)
                        alerted = fused is not None and fused > cfg.decision.high_thr
                    if alerted:
                        stats.alerts += 1
                        if ground_truth == "bonafide":
                            stats.false_alarms += 1

                    lag_ms = int(
                        max(0.0, (time.monotonic() - started) * 1000 - window.t_end_ms)
                    )
                    stats.max_lag_ms = max(stats.max_lag_ms, lag_ms)

                    payload = verdict.to_json()
                    payload["pipeline_lag_ms"] = lag_ms
                    payload["alerts"] = stats.alerts
                    payload["false_alarms"] = stats.false_alarms
                    payload["mode"] = gating.name
                    emit(payload)

                    if (
                        self.evidence is not None
                        and verdict.state != last_verdict_state
                        and verdict.state != MONITORING
                    ):
                        self.evidence.append_verdict(
                            verdict,
                            extra={
                                "mode": gating.name,
                                "speaker_id": speaker_id,
                                "config_band": [cfg.decision.low_thr, cfg.decision.high_thr],
                                "calibration_band": [self.cal.band_low, self.cal.band_high],
                            },
                        )
                    last_verdict_state = verdict.state

            for window in framer.flush():
                window_index[window.seq] = window
                stats.windows_total += 1
                self._score_window(
                    window, gating, triggers, reference_embedding,
                    spk_scores, cm_scores, deep_seqs, stats, emit,
                )
        finally:
            if asr is not None:
                asr.close()
                stats.asr_blocked_pushes = asr.blocked_pushes

        # Drain anything ASR produced during its final flush.
        while pending_utterances:
            utterance = pending_utterances.pop(0)
            stats.utterances += 1
            emit(utterance.to_json())

        final = self._decide(
            gating, triggers, spk_scores, cm_scores, window_index, deep_seqs,
            reference_embedding is not None, stream_ms,
        )
        stats.verdict = final
        stats.reasons = list(final.reasons)
        stats.wall_s = time.monotonic() - started
        stats.stream_s = stream_ms / 1000.0
        if self.evidence is not None:
            self.evidence.append_verdict(
                final,
                extra={
                    "final": True,
                    "mode": gating.name,
                    "speaker_id": speaker_id,
                    "ground_truth": ground_truth,
                    "alerts": stats.alerts,
                    "false_alarms": stats.false_alarms,
                },
            )
            stats.evidence_path = self.evidence.path

        payload = final.to_json()
        payload["type"] = "final"
        payload["stats"] = {
            "windows_total": stats.windows_total,
            "windows_scored": stats.windows_scored,
            "windows_silent": stats.windows_silent,
            "windows_deep": stats.windows_deep,
            "utterances": stats.utterances,
            "triggers": stats.triggers,
            "alerts": stats.alerts,
            "false_alarms": stats.false_alarms,
            "max_lag_ms": stats.max_lag_ms,
            "wall_s": round(stats.wall_s, 2),
            "stream_s": round(stats.stream_s, 2),
            "mode": gating.name,
        }
        emit(payload)
        return stats

    # ------------------------------------------------------------------
    def _start_event(self, source, speaker_id, gating, overlay, ground_truth, mode):
        return {
            "type": "run_start",
            "mode": gating.name,
            "requested_mode": mode or self.cfg.gating.mode,
            "speaker_id": speaker_id,
            "ground_truth": ground_truth,
            "duration_s": getattr(source, "duration_s", None),
            "scripted_overlay": overlay.enabled,
            "calibration": self.cal.header(),
            "band": [self.cfg.decision.low_thr, self.cfg.decision.high_thr],
            "window_s": self.cfg.audio.window_s,
            "hop_s": self.cfg.audio.hop_s,
            "pre_roll_s": self.cfg.gating.pre_roll_s,
            "hold_s": self.cfg.gating.hold_s,
            "model_ids": [self.cm.model_id, self.spk.model_id],
            "honesty": "Simulated live call — recorded audio streamed in real time.",
        }

    def _score_window(self, window, gating, triggers, reference,
                      spk_scores, cm_scores, deep_seqs, stats, emit) -> None:
        is_speech, ratio = self.vad.measure(window.pcm, window.sr)
        if not is_speech:
            stats.windows_silent += 1
            silent = RiskScore(SPEAKER, 0.0, window.t_start_ms, window.t_end_ms,
                               self.spk.model_id, SILENT)
            spk_scores[window.seq] = silent
            emit({**silent.to_json(), "seq": window.seq, "voiced_ratio": round(ratio, 3)})
            return

        stats.windows_scored += 1

        # The speaker check runs ALWAYS. It is cheap and it is the primary
        # signal; the countermeasure is what gets gated. That ordering is the
        # thesis expressed in code (SPEC §7.3).
        if reference is not None:
            spk_scores[window.seq] = self._safe_score(
                SPEAKER, window,
                lambda: self.spk.risk(reference, self.spk.embed(window.pcm, window.sr)),
                self.spk.model_id,
            )
            emit({**spk_scores[window.seq].to_json(), "seq": window.seq,
                  "voiced_ratio": round(ratio, 3)})

        if gating.should_run_deep(window.t_end_ms, triggers):
            self._run_deep(window, cm_scores, deep_seqs, stats, emit,
                            vad_result=(is_speech, ratio))

    def _run_deep(self, window, cm_scores, deep_seqs, stats, emit,
                  vad_result: Optional[Tuple[bool, float]] = None) -> None:
        """
        The countermeasure, on one window. The ONLY place it is ever called.

        The VAD gate lives here rather than in the caller because there are two
        callers -- the forward pass and the pre-roll backfill -- and the backfill
        used to reach the model without it. That mattered: fed a silent window
        the probe does not fail, it returns ~0.99, near-certain "synthetic". It
        is the exact mirror of the Resemblyzer behaviour in test_vad_silence.py
        (fed silence, confidently "genuine"), and the same lesson: a model given
        no speech still returns a confident number, and the number is about
        nothing. On the genuine demo call this put nine 0.99 windows into the
        evidence panel of a call the system had just verified.

        So: one entry point, one gate. A refused window gets a SILENT score --
        recorded and shown, not omitted -- and stays out of the aggregate.

        `vad_result` lets the forward pass hand in the measurement it already
        took in `_score_window` for this same window, rather than measuring it
        twice. The backfill path has no prior measurement, so it leaves this
        None and the gate below computes it fresh.
        """
        if window.seq in cm_scores:
            return

        is_speech, ratio = (
            vad_result if vad_result is not None
            else self.vad.measure(window.pcm, window.sr)
        )
        if not is_speech:
            silent = RiskScore(CM, 0.0, window.t_start_ms, window.t_end_ms,
                               self.cm.model_id, SILENT)
            cm_scores[window.seq] = silent
            emit({**silent.to_json(), "seq": window.seq,
                  "voiced_ratio": round(ratio, 3)})
            return

        stats.windows_deep += 1
        cm_scores[window.seq] = self._safe_score(
            CM, window, lambda: self.cm.risk(window.pcm, window.sr), self.cm.model_id
        )
        deep_seqs.append(window.seq)
        emit({**cm_scores[window.seq].to_json(), "seq": window.seq,
              "voiced_ratio": round(ratio, 3)})

    def _backfill(self, framer, gating, triggers, window_index,
                  cm_scores, deep_seqs, stats, emit) -> None:
        since_ms = gating.backfill_from_ms(triggers)
        if since_ms is None:
            return
        for window in framer.history(since_ms=since_ms):
            window_index.setdefault(window.seq, window)
            if gating.should_run_deep(window.t_end_ms, triggers):
                self._run_deep(window, cm_scores, deep_seqs, stats, emit)

    def _safe_score(self, kind, window, fn, model_id) -> RiskScore:
        """A model failure becomes a status, never an exception in the loop."""
        try:
            value = float(fn())
        except SilentAudio:
            return RiskScore(kind, 0.0, window.t_start_ms, window.t_end_ms,
                             model_id, SILENT)
        except Exception:  # noqa: BLE001
            return RiskScore(kind, 0.0, window.t_start_ms, window.t_end_ms,
                             model_id, ERROR)
        return RiskScore(kind, value, window.t_start_ms, window.t_end_ms, model_id, OK)

    def _window_fused(self, seq, spk_scores, cm_scores) -> Optional[float]:
        spk = spk_scores.get(seq)
        cm = cm_scores.get(seq)
        fused, _ = self.fusion.fuse(
            cm.value if cm is not None and cm.usable else None,
            spk.value if spk is not None and spk.usable else None,
        )
        return fused

    def _decide(self, gating, triggers, spk_scores, cm_scores, window_index,
                deep_seqs, enrolled, t_ms):
        if not triggers and not isinstance(gating, AlwaysOnGating):
            return decide(None, None, enrolled, False, self.cal, self.cfg.decision,
                          t_ms=t_ms, fusion=self.fusion,
                          model_ids=[self.cm.model_id, self.spk.model_id])

        seqs = [s for s in deep_seqs if s in cm_scores]
        cm_run = [cm_scores[s] for s in seqs]
        spk_run = [spk_scores[s] for s in seqs if s in spk_scores]

        segments = []
        for seq in seqs:
            fused = self._window_fused(seq, spk_scores, cm_scores)
            if fused is None or seq not in window_index:
                continue
            window = window_index[seq]
            cm = cm_scores.get(seq)
            spk = spk_scores.get(seq)
            segments.append(
                EvidenceSegment(
                    t_start_ms=window.t_start_ms,
                    t_end_ms=window.t_end_ms,
                    fused_risk=fused,
                    cm_risk=cm.value if cm is not None and cm.usable else None,
                    speaker_risk=spk.value if spk is not None and spk.usable else None,
                )
            )

        usable = sum(
            1 for s in seqs
            if cm_scores.get(s) is not None and cm_scores[s].usable
        )
        trigger_reason = (
            self.trigger_engine.describe(triggers[-1]) if triggers else
            "Naive mode: deep verification runs continuously, with no trigger."
        )
        return decide(
            aggregate(CM, cm_run, self.cm.model_id),
            aggregate(SPEAKER, spk_run, self.spk.model_id),
            enrolled,
            bool(triggers) or isinstance(gating, AlwaysOnGating),
            self.cal,
            self.cfg.decision,
            t_ms=t_ms,
            fusion=self.fusion,
            window_scores=segments,
            n_windows=usable,
            model_ids=[self.cm.model_id, self.spk.model_id],
            trigger_reason=trigger_reason,
        )
