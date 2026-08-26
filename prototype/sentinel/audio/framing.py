"""
Frames in, sliding analysis windows out.

3.0 s wide, 0.5 s hop by default -- so a window is emitted twice a second and
each one overlaps its neighbour by 2.5 s. That overlap is what lets the risk
timeline move smoothly instead of stepping, and it is why the per-window scores
in the demo are correlated rather than independent samples.

The Framer keeps a ring of recent frames. It is also the pre-roll buffer that
TriggeredGating depends on (SPEC §7.3): by the time a trigger fires, the
incriminating audio has already gone past, so the gating policy scores backwards
over windows this buffer still holds.
"""
from __future__ import annotations

from collections import deque
from typing import Deque, Iterator, List, Optional

import numpy as np

from sentinel.types import Frame, Window


class Framer:
    """Accumulates frames and emits a Window every `hop_s` once it has `window_s`."""

    def __init__(
        self,
        sample_rate: int = 16000,
        window_s: float = 3.0,
        hop_s: float = 0.5,
        history_s: float = 0.0,
    ) -> None:
        self.sample_rate = sample_rate
        self.window_s = window_s
        self.hop_s = hop_s
        self.window_n = int(round(window_s * sample_rate))
        self.hop_n = int(round(hop_s * sample_rate))

        self._buf: Deque[np.ndarray] = deque()
        self._buf_len = 0
        self._buf_start_ms = 0  # stream time of _buf[0]'s first sample
        self._emitted_up_to = 0  # samples consumed by hops so far
        self._seq = 0

        # Recent windows, kept for pre-roll scoring.
        self.history_s = history_s
        self._history: Deque[Window] = deque()

    def push(self, frame: Frame) -> List[Window]:
        """Feed one frame; get back zero or more completed windows."""
        if frame.sr != self.sample_rate:
            raise ValueError(
                f"framer expects {self.sample_rate}Hz, got {frame.sr}Hz "
                "-- resample at the source"
            )
        if not self._buf:
            self._buf_start_ms = frame.t_start_ms
        self._buf.append(np.asarray(frame.pcm, dtype=np.float32))
        self._buf_len += len(frame.pcm)

        out: List[Window] = []
        while self._buf_len - self._emitted_up_to >= self.window_n:
            flat = np.concatenate(self._buf) if len(self._buf) > 1 else self._buf[0]
            if len(self._buf) > 1:
                self._buf = deque([flat])
            start = self._emitted_up_to
            pcm = flat[start:start + self.window_n]
            t_start_ms = self._buf_start_ms + int(round(start / self.sample_rate * 1000))
            window = Window(
                pcm=pcm,
                sr=self.sample_rate,
                t_start_ms=t_start_ms,
                t_end_ms=t_start_ms + int(round(self.window_s * 1000)),
                seq=self._seq,
            )
            out.append(window)
            self._remember(window)
            self._seq += 1
            self._emitted_up_to += self.hop_n
            self._trim()
        return out

    def _remember(self, window: Window) -> None:
        if self.history_s <= 0:
            return
        self._history.append(window)
        cutoff = window.t_end_ms - int(self.history_s * 1000)
        while self._history and self._history[0].t_end_ms < cutoff:
            self._history.popleft()

    def history(self, since_ms: Optional[int] = None) -> List[Window]:
        """Recent windows, newest last. This is the pre-roll buffer."""
        if since_ms is None:
            return list(self._history)
        return [w for w in self._history if w.t_end_ms >= since_ms]

    def _trim(self) -> None:
        """Drop audio that no future window can reach."""
        if self._emitted_up_to <= 0 or not self._buf:
            return
        flat = self._buf[0]
        keep_from = self._emitted_up_to
        if keep_from <= 0:
            return
        self._buf = deque([flat[keep_from:]])
        self._buf_len -= keep_from
        self._buf_start_ms += int(round(keep_from / self.sample_rate * 1000))
        self._emitted_up_to = 0

    def flush(self) -> List[Window]:
        """
        Emit a final short window if meaningful audio would otherwise be lost.

        A 37 s call at a 0.5 s hop leaves under a hop of tail; padding it to a
        full window would feed the models fabricated silence, so we only flush
        when at least half a window of real audio remains, and we pad the rest.
        """
        remaining = self._buf_len - self._emitted_up_to
        if remaining < self.window_n // 2:
            return []
        flat = np.concatenate(self._buf) if len(self._buf) > 1 else self._buf[0]
        pcm = flat[self._emitted_up_to:]
        pad = self.window_n - len(pcm)
        if pad > 0:
            pcm = np.concatenate([pcm, np.zeros(pad, dtype=np.float32)])
        t_start_ms = self._buf_start_ms + int(
            round(self._emitted_up_to / self.sample_rate * 1000)
        )
        window = Window(
            pcm=pcm,
            sr=self.sample_rate,
            t_start_ms=t_start_ms,
            t_end_ms=t_start_ms + int(round(self.window_s * 1000)),
            seq=self._seq,
        )
        self._seq += 1
        self._emitted_up_to = self._buf_len
        self._remember(window)
        return [window]


def windows(frames: Iterator[Frame], **kwargs) -> Iterator[Window]:
    """Convenience wrapper for tests and one-off scripts."""
    framer = Framer(**kwargs)
    for frame in frames:
        for window in framer.push(frame):
            yield window
    for window in framer.flush():
        yield window
