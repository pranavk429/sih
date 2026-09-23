"""
Live audio in: frames pushed from outside the process, consumed by the pipeline.

`FileSource` replays a recording; `MicSource` reads the local sound card.
`LiveSource` is the third AudioSource and exists because the demo's live path is
a BROWSER microphone captured in JavaScript and delivered over a WebSocket: the
server process never opens the device, so it cannot use sounddevice. The
orchestrator does not know or care -- it sees `frames()` and nothing else, which
is the entire point of the AudioSource protocol in SPEC §2.

Two decisions worth stating, because both are demo-failure answers:

STREAM TIME COMES FROM SAMPLES RECEIVED, NOT FROM THE WALL CLOCK. Each pushed
chunk carries the stream time of its first sample, computed from the count of
samples accepted before it. A replay of the same audio through FileSource and
LiveSource therefore produces identical `t_start_ms` values (test_pipeline
compares them), and SPEC §7.1's "stream time, never wall clock" survives the
live path.

OVERFLOW DROPS THE OLDEST AUDIO AND COUNTS IT. The ASR queue blocks instead,
because a gap in a transcript is a missed trigger. But in a live call the past
is already gone; blocking the socket would trade a visible gap for an invisible,
growing delay. So this queue drops oldest, `dropped_ms` climbs, and the UI says
so (SPEC §12: if we fall behind, say so). The drop is also why the stream-time
counter is anchored to received samples: a dropped chunk leaves a gap in the
timeline rather than silently compressing it.
"""
from __future__ import annotations

import queue
import threading
from typing import Iterator, List, Optional, Tuple

import numpy as np

from sentinel.audio.resample import prepare
from sentinel.types import Frame

# The queue holds CHUNKS (20 ms each as sent by the browser), not windows.
# 400 chunks is ~8 s of slack -- more than any plausible hiccup in a local
# pipeline, and short enough that a dead client is noticed quickly.
DEFAULT_QUEUE_FRAMES = 400
_GET_TIMEOUT_S = 0.25


class LiveSource:
    """An AudioSource whose input arrives from a socket handler."""

    def __init__(
        self,
        sample_rate: int = 16000,
        frame_ms: int = 20,
        max_queue_frames: int = DEFAULT_QUEUE_FRAMES,
        max_seconds: Optional[float] = None,
    ) -> None:
        self.sample_rate = int(sample_rate)
        self.frame_ms = int(frame_ms)
        self.max_queue_frames = int(max_queue_frames)
        self.max_seconds = max_seconds

        self._queue: "queue.Queue[Optional[Tuple[np.ndarray, int]]]" = queue.Queue(
            maxsize=self.max_queue_frames
        )
        self._closed = threading.Event()
        self._seq = 0
        self._lock = threading.Lock()

        # --- accounting, all exposed to the run stats and the UI ---
        self._received_samples = 0   # output-rate samples accepted from the client
        self._dropped_samples = 0    # output-rate samples thrown away to make room
        self._dropped_chunks = 0
        self._pushed_chunks = 0
        self._input_rates: List[int] = []
        self._peak_rms = 0.0
        self._nonfinite_chunks = 0

    # ------------------------------------------------------------------ push
    def push(self, chunk, sample_rate: int) -> None:
        """
        Accept one chunk of mono audio. Called from the WebSocket handler.

        Never blocks: a full queue drops its oldest chunk, and the drop is
        counted. Resampling happens here, once, so `frames()` only ever handles
        16 kHz float32.
        """
        if self._closed.is_set():
            return

        pcm = np.asarray(chunk, dtype=np.float32).reshape(-1)
        if pcm.size == 0:
            return
        if not np.isfinite(pcm).all():
            self._nonfinite_chunks += 1
            pcm = np.nan_to_num(pcm, copy=False)

        if int(sample_rate) != self.sample_rate:
            pcm = prepare(pcm, int(sample_rate), self.sample_rate)

        with self._lock:
            self._pushed_chunks += 1
            if len(self._input_rates) < 8:
                self._input_rates.append(int(sample_rate))
            level = float(np.sqrt(np.mean(np.square(pcm, dtype=np.float64)))) if pcm.size else 0.0
            self._peak_rms = max(self._peak_rms, level)
            if self.max_seconds is not None and \
                    self._received_samples / self.sample_rate >= self.max_seconds:
                self._closed.set()
                self._signal_close()
                return
            t_start_ms = int(round(self._received_samples * 1000.0 / self.sample_rate))
            self._received_samples += int(pcm.size)

        self._enqueue((pcm, t_start_ms))

    def _enqueue(self, item) -> None:
        try:
            self._queue.put_nowait(item)
            return
        except queue.Full:
            pass
        # Make room by dropping the oldest chunk. Only audio is ever dropped;
        # an end-of-stream sentinel never comes through here (see _signal_close).
        try:
            old = self._queue.get_nowait()
        except queue.Empty:  # pragma: no cover -- only if another thread drained it
            old = None
        if isinstance(old, tuple):
            self._dropped_samples += int(old[0].size)
            self._dropped_chunks += 1
        try:
            self._queue.put_nowait(item)
        except queue.Full:  # pragma: no cover -- queue was refilled by another producer
            if isinstance(item, tuple):
                self._dropped_samples += int(item[0].size)
                self._dropped_chunks += 1

    def close(self) -> None:
        """Idempotent. Signals the frame generator to finish after what it has."""
        if self._closed.is_set():
            return
        self._closed.set()
        self._signal_close()

    def _signal_close(self) -> None:
        """
        Put the end-of-stream sentinel in the queue WITHOUT evicting audio.

        The sentinel is a courtesy, not the mechanism: `frames()` also ends when
        the queue drains and `closed` is set. Dropping a real chunk to make room
        for it would lose the last 20 ms of the call -- and count it as an
        overflow, which it is not.
        """
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass

    # ----------------------------------------------------------------- stats
    @property
    def closed(self) -> bool:
        return self._closed.is_set()

    @property
    def dropped_ms(self) -> int:
        return int(round(self._dropped_samples * 1000.0 / self.sample_rate))

    @property
    def dropped_chunks(self) -> int:
        return self._dropped_chunks

    @property
    def pushed_chunks(self) -> int:
        return self._pushed_chunks

    @property
    def peak_rms(self) -> float:
        return self._peak_rms

    @property
    def input_rates(self) -> List[int]:
        return list(self._input_rates)

    @property
    def nonfinite_chunks(self) -> int:
        return self._nonfinite_chunks

    @property
    def received_ms(self) -> int:
        return int(round(self._received_samples * 1000.0 / self.sample_rate))

    @property
    def queue_depth(self) -> int:
        return self._queue.qsize()

    # ---------------------------------------------------------------- frames
    def frames(self) -> Iterator[Frame]:
        """
        Yield exact `frame_ms` frames at the configured rate until closed.

        Chunk boundaries are carried over, so a client that sends 20 ms chunks
        at 48 kHz produces the same 16 kHz 20 ms frames as one that sends them
        at 16 kHz. A gap left by a dropped chunk shows up as a jump in
        `t_start_ms`, not as a shortened stream.
        """
        n = int(self.sample_rate * self.frame_ms / 1000)
        carry = np.zeros(0, dtype=np.float32)
        carry_t0 = 0
        seq = 0

        while True:
            try:
                item = self._queue.get(timeout=_GET_TIMEOUT_S)
            except queue.Empty:
                if self._closed.is_set():
                    break
                continue
            if item is None:
                break

            pcm, t0 = item
            if carry.size:
                block = np.concatenate((carry, pcm))
                block_t0 = carry_t0
            else:
                block = pcm
                block_t0 = t0

            i = 0
            while block.size - i >= n:
                yield Frame(
                    pcm=np.ascontiguousarray(block[i:i + n]),
                    sr=self.sample_rate,
                    t_start_ms=block_t0 + int(round(i * 1000.0 / self.sample_rate)),
                    seq=seq,
                )
                seq += 1
                i += n

            carry = np.ascontiguousarray(block[i:])
            carry_t0 = block_t0 + int(round(i * 1000.0 / self.sample_rate))

        # A partial frame at the end is dropped, exactly as FileSource drops the
        # sub-frame tail of a WAV. That is what makes a live stream and a replay
        # of the same audio produce identical frames (test_live_pipeline), and
        # 20 ms of tail changes nothing: the framer flushes the final window
        # either way.

    # The orchestrator calls source.close() in a finally block. For a live
    # source that is the same signal as the socket handler's close().
    def __enter__(self) -> "LiveSource":  # pragma: no cover -- convenience only
        return self

    def __exit__(self, *exc) -> None:  # pragma: no cover
        self.close()
