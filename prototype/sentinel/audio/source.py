"""
Where audio comes from. One of the three interfaces SPEC §2 says will change.

    file  -> today, and the demo
    mic   -> a live teammate at the finale
    RTP   -> production, deliberately a stub

Everything downstream sees only `Frame`s, so swapping the source swaps nothing
else. That is the entire point of the abstraction, and it is the reason there
are exactly three of them in this codebase.

FileSource has a `realtime` switch that matters more than it looks:
  realtime=True   sleeps to track wall clock, so a replay behaves like a call
                  and the demo's pacing is honest
  realtime=False  runs flat out, so tests finish in under a second and the
                  golden test is deterministic
Both produce IDENTICAL frames with identical stream timestamps (SPEC §7.1).
"""
from __future__ import annotations

import os
import time
from typing import Iterator, Optional

import numpy as np
import soundfile as sf

from sentinel.audio.resample import prepare
from sentinel.types import Frame

try:
    from typing import Protocol, runtime_checkable
except ImportError:  # pragma: no cover
    from typing_extensions import Protocol, runtime_checkable  # type: ignore


@runtime_checkable
class AudioSource(Protocol):
    """Yields fixed-size frames of 16 kHz mono float32, with stream timestamps."""

    sample_rate: int

    def frames(self) -> Iterator[Frame]:
        ...

    def close(self) -> None:
        ...


class FileSource:
    """Replay a WAV as if it were arriving down a line."""

    def __init__(
        self,
        path: str,
        sample_rate: int = 16000,
        frame_ms: int = 20,
        realtime: bool = True,
    ) -> None:
        if not os.path.exists(path):
            raise FileNotFoundError(f"audio not found: {path}")
        self.path = path
        self.sample_rate = sample_rate
        self.frame_ms = frame_ms
        self.realtime = realtime
        self._closed = False

        pcm, sr_in = sf.read(path, dtype="float32", always_2d=False)
        self.pcm = prepare(pcm, sr_in, sample_rate)
        self.source_sample_rate = sr_in

    @property
    def duration_s(self) -> float:
        return len(self.pcm) / float(self.sample_rate)

    def frames(self) -> Iterator[Frame]:
        n = int(self.sample_rate * self.frame_ms / 1000)
        started = time.monotonic()
        seq = 0
        for start in range(0, len(self.pcm) - n + 1, n):
            if self._closed:
                return
            t_start_ms = int(round(start / self.sample_rate * 1000))
            if self.realtime:
                # Sleep against elapsed-since-start, not per-frame, so rounding
                # error cannot accumulate into drift over a 37-second call.
                target = (t_start_ms + self.frame_ms) / 1000.0
                lag = target - (time.monotonic() - started)
                if lag > 0:
                    time.sleep(lag)
            yield Frame(
                pcm=self.pcm[start:start + n],
                sr=self.sample_rate,
                t_start_ms=t_start_ms,
                seq=seq,
            )
            seq += 1

    def close(self) -> None:
        self._closed = True


class MicSource:
    """
    Live microphone via sounddevice.

    Used at the finale if someone wants to speak into it. Imports sounddevice
    lazily: it needs PortAudio, and a missing PortAudio must not stop the file
    demo from running.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        frame_ms: int = 20,
        device: Optional[int] = None,
        max_seconds: Optional[float] = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.frame_ms = frame_ms
        self.device = device
        self.max_seconds = max_seconds
        self._closed = False

    def frames(self) -> Iterator[Frame]:
        import sounddevice as sd  # lazy: PortAudio must not be a hard dependency

        n = int(self.sample_rate * self.frame_ms / 1000)
        seq = 0
        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=n,
            device=self.device,
        ) as stream:
            while not self._closed:
                block, overflowed = stream.read(n)
                del overflowed  # the pipeline reports lag itself
                t_start_ms = int(round(seq * self.frame_ms))
                if self.max_seconds and t_start_ms / 1000.0 >= self.max_seconds:
                    return
                yield Frame(
                    pcm=np.asarray(block, dtype=np.float32).reshape(-1),
                    sr=self.sample_rate,
                    t_start_ms=t_start_ms,
                    seq=seq,
                )
                seq += 1

    def close(self) -> None:
        self._closed = True


class RtpSource:
    """
    The production path: RTP off a SIP leg (Asterisk/FreeSWITCH, or an SBC fork).

    NOT BUILT, ON PURPOSE. SPEC §3: a telephony stack is days of setup and it
    breaks on venue networks. This class exists so the shape of the integration
    is visible and so nobody has to guess where it plugs in.

    What a real implementation does:
      1. Receive RTP (usually G.711 mu-law or Opus) from the media leg.
      2. Depacketise, handle jitter and lost sequence numbers -- a dropped
         packet must become silence at the right offset, not a shortened stream,
         or every timestamp after it is wrong.
      3. Decode to PCM, resample to 16 kHz mono float32 via audio.resample.
      4. Emit Frames whose t_start_ms comes from the RTP timestamp, so stream
         time stays anchored to the call rather than to our clock (SPEC §7.1).

    Nothing else in Sentinel changes. That is what the AudioSource protocol buys.
    """

    sample_rate = 16000

    def __init__(self, *args, **kwargs) -> None:
        raise NotImplementedError(
            "RtpSource is the production telephony path and is deliberately not "
            "built in the prototype (SPEC §3). Use FileSource for the demo or "
            "MicSource for a live voice."
        )

    def frames(self) -> Iterator[Frame]:  # pragma: no cover
        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover
        raise NotImplementedError
