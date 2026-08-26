"""
Speech to text, on its own thread. The only place concurrency earns its cost.

SPEC §7.2 ran the numbers: speaker embedding is 30-60 ms and the countermeasure
40-80 ms, both comfortably inside a 500 ms hop, so they stay in the sequential
pipeline loop. ASR is 300-600 ms per utterance, which is the one stage whose
worst case can exceed the hop. So it gets a thread and nothing else does.

The queue policy matters and is the opposite of the UI's. A gap in the
transcript is a MISSED TRIGGER -- the one thing this system exists to catch --
so the ASR input queue blocks when full rather than dropping. The pipeline
slowing down is a visible, reportable problem (pipeline_lag_ms). A silently
missing sentence is not.

Chunking is on silence, using the same VAD as the rest of the system, with a
maximum length so a caller who never pauses still gets transcribed.
"""
from __future__ import annotations

import queue
import threading
from typing import Callable, List, Optional

import numpy as np

from sentinel.audio.vad import EnergyVad, rms
from sentinel.config import AudioConfig, ModelConfig
from sentinel.types import Frame, Utterance

# Utterance boundaries. In config-speak these would be more knobs; they are
# properties of how people speak rather than of our models, so they live here.
SILENCE_TO_CUT_MS = 500
MIN_UTTERANCE_MS = 700
MAX_UTTERANCE_MS = 12_000


class Transcriber:
    """faster-whisper, int8 on CPU, wrapped so a failure never kills the run."""

    def __init__(self, cfg: ModelConfig) -> None:
        from faster_whisper import WhisperModel

        from sentinel.config import prefer_local_model_cache

        prefer_local_model_cache()
        self.model_id = f"faster-whisper:{cfg.asr_model_id}:{cfg.asr_compute_type}"
        self._model = WhisperModel(
            cfg.asr_model_id,
            device=cfg.asr_device,
            compute_type=cfg.asr_compute_type,
            download_root=cfg.asr_cache_dir,
        )

    def transcribe(self, pcm: np.ndarray, sr: int, t_start_ms: int) -> Optional[Utterance]:
        segments, _info = self._model.transcribe(
            np.asarray(pcm, dtype=np.float32),
            language="en",
            beam_size=1,          # greedy: this is a live stream, not a transcript job
            vad_filter=False,     # we already gate with our own VAD
            condition_on_previous_text=False,
        )
        parts: List[str] = []
        confidences: List[float] = []
        for segment in segments:
            text = (segment.text or "").strip()
            if text:
                parts.append(text)
                if getattr(segment, "avg_logprob", None) is not None:
                    confidences.append(float(np.exp(segment.avg_logprob)))

        if not parts:
            return None
        duration_ms = int(round(len(pcm) / sr * 1000))
        return Utterance(
            text=" ".join(parts),
            t_start_ms=t_start_ms,
            t_end_ms=t_start_ms + duration_ms,
            scripted=False,
            confidence=float(np.mean(confidences)) if confidences else None,
        )


class AsrThread:
    """
    Consumes frames from a bounded queue, emits Utterances via a callback.

    Start it, push frames, then call close() -- close drains what is left and
    joins, so a run cannot end with a half-transcribed final sentence.
    """

    def __init__(
        self,
        transcriber: Transcriber,
        audio_cfg: AudioConfig,
        on_utterance: Callable[[Utterance], None],
        maxsize: int = 200,
    ) -> None:
        self.transcriber = transcriber
        self.audio_cfg = audio_cfg
        self.on_utterance = on_utterance
        self.vad = EnergyVad(audio_cfg)

        self.queue: "queue.Queue" = queue.Queue(maxsize=maxsize)
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._blocked_pushes = 0
        self.errors = 0

        self._buffer: List[np.ndarray] = []
        self._buffer_start_ms: Optional[int] = None
        self._silence_ms = 0

    @property
    def blocked_pushes(self) -> int:
        """How often the pipeline had to wait for ASR. Reported, not hidden."""
        return self._blocked_pushes

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="sentinel-asr", daemon=True)
        self._thread.start()

    def push(self, frame: Frame) -> None:
        """Blocks when full. Deliberately -- see the module docstring."""
        if self._stop.is_set():
            return
        if self.queue.full():
            self._blocked_pushes += 1
        self.queue.put(frame)

    def close(self, timeout: float = 10.0) -> None:
        self.queue.put(None)  # sentinel: drain and finish
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        self._stop.set()

    # -- worker ------------------------------------------------------------
    def _run(self) -> None:
        while True:
            item = self.queue.get()
            if item is None:
                self._flush()
                return
            try:
                self._consume(item)
            except Exception:  # noqa: BLE001 - a bad frame must not kill the thread
                self.errors += 1

    def _consume(self, frame: Frame) -> None:
        voiced = rms(frame.pcm) >= self.audio_cfg.vad_rms_floor

        if voiced:
            if self._buffer_start_ms is None:
                self._buffer_start_ms = frame.t_start_ms
            self._buffer.append(frame.pcm)
            self._silence_ms = 0
        elif self._buffer:
            # Keep trailing silence in the buffer: whisper does better with a
            # little room after the last word than with a hard cut on it.
            self._buffer.append(frame.pcm)
            self._silence_ms += frame.duration_ms

        if not self._buffer:
            return

        buffered_ms = int(round(sum(len(c) for c in self._buffer)
                                / self.audio_cfg.sample_rate * 1000))
        if self._silence_ms >= SILENCE_TO_CUT_MS or buffered_ms >= MAX_UTTERANCE_MS:
            self._flush()

    def _flush(self) -> None:
        if not self._buffer or self._buffer_start_ms is None:
            self._reset()
            return
        pcm = np.concatenate(self._buffer)
        start_ms = self._buffer_start_ms
        self._reset()

        duration_ms = int(round(len(pcm) / self.audio_cfg.sample_rate * 1000))
        if duration_ms < MIN_UTTERANCE_MS:
            return
        try:
            utterance = self.transcriber.transcribe(pcm, self.audio_cfg.sample_rate, start_ms)
        except Exception:  # noqa: BLE001
            self.errors += 1
            return
        if utterance is not None:
            self.on_utterance(utterance)

    def _reset(self) -> None:
        self._buffer = []
        self._buffer_start_ms = None
        self._silence_ms = 0
