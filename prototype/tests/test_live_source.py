"""
LiveSource: the audio path the demo's microphone rides on.

These are the properties the browser path depends on and that no other test
covers: exact framing across chunk boundaries, stream time that survives a
resample, dropped-oldest accounting, and a clean end. They run without any
model, so they are fast enough to run on every change.
"""
from __future__ import annotations

import queue

import numpy as np

from sentinel.audio.live_source import LiveSource


def chunk(ms: int, sr: int, value: float = 0.0) -> np.ndarray:
    return np.full(int(sr * ms / 1000), value, dtype=np.float32)


def test_frames_are_exact_and_contiguous_at_16k():
    src = LiveSource(sample_rate=16000, frame_ms=20)
    for _ in range(10):
        src.push(chunk(20, 16000, 0.1), 16000)
    src.close()

    frames = list(src.frames())
    assert len(frames) == 10
    assert all(len(f.pcm) == 320 for f in frames)
    assert [f.t_start_ms for f in frames] == [i * 20 for i in range(10)]
    assert [f.seq for f in frames] == list(range(10))
    assert all(f.sr == 16000 for f in frames)


def test_chunks_smaller_than_a_frame_are_carried_over():
    """A client that sends 10 ms chunks must still produce 20 ms frames."""
    src = LiveSource(sample_rate=16000, frame_ms=20)
    for _ in range(2):
        src.push(chunk(10, 16000, 0.1), 16000)
    src.close()

    frames = list(src.frames())
    assert len(frames) == 1
    assert len(frames[0].pcm) == 320
    assert frames[0].t_start_ms == 0


def test_48k_input_is_resampled_and_keeps_stream_time():
    """The browser picks the device rate; the frames are always 16 kHz."""
    src = LiveSource(sample_rate=16000, frame_ms=20)
    for _ in range(10):
        src.push(chunk(20, 48000, 0.1), 48000)
    src.close()

    frames = list(src.frames())
    assert len(frames) == 10, f"expected 10 frames, got {len(frames)}"
    assert all(len(f.pcm) == 320 for f in frames)
    assert [f.t_start_ms for f in frames] == [i * 20 for i in range(10)]


def test_overflow_drops_the_oldest_and_leaves_a_time_gap():
    """
    Dropping is the live path's overflow policy: the present matters more than
    the past. The stream clock must still advance, or the call silently
    shortens -- so the first surviving frame starts where the dropped audio did.
    """
    src = LiveSource(sample_rate=16000, frame_ms=20, max_queue_frames=2)
    for _ in range(4):
        src.push(chunk(20, 16000, 0.1), 16000)
    src.close()

    frames = list(src.frames())
    assert len(frames) == 2, "the queue should hold exactly two chunks"
    assert src.dropped_ms == 40
    assert src.dropped_chunks == 2
    assert frames[0].t_start_ms == 40, (
        "the first surviving frame must be 40 ms into the stream, not 0 -- "
        "otherwise dropped audio silently compresses the timeline"
    )
    assert frames[1].t_start_ms == 60


def test_close_ends_the_iterator_and_drops_the_partial_tail():
    """
    A sub-frame tail is dropped, exactly as FileSource drops the tail of a WAV.
    That equivalence is what makes the live path the same pipeline rather than a
    similar one (test_live_pipeline compares the event streams).
    """
    src = LiveSource(sample_rate=16000, frame_ms=20)
    src.push(chunk(30, 16000, 0.1), 16000)   # 1.5 frames
    src.close()

    frames = list(src.frames())
    assert len(frames) == 1
    assert len(frames[0].pcm) == 320
    assert frames[0].t_start_ms == 0


def test_a_source_with_no_audio_ends_on_close_instead_of_blocking():
    src = LiveSource(sample_rate=16000, frame_ms=20)
    src.close()
    assert list(src.frames()) == []


def test_max_seconds_closes_the_source():
    src = LiveSource(sample_rate=16000, frame_ms=20, max_seconds=0.05)
    for _ in range(4):
        src.push(chunk(20, 16000, 0.1), 16000)
    assert src.closed
    frames = list(src.frames())
    assert 0 < len(frames) <= 3


def test_push_after_close_is_ignored():
    src = LiveSource(sample_rate=16000, frame_ms=20)
    src.close()
    before = src.pushed_chunks
    src.push(chunk(20, 16000, 0.1), 16000)
    assert src.pushed_chunks == before


def test_nonfinite_input_is_counted_not_propagated():
    src = LiveSource(sample_rate=16000, frame_ms=20)
    bad = chunk(20, 16000, 0.1)
    bad[0] = np.nan
    src.push(bad, 16000)
    src.close()
    frames = list(src.frames())
    assert src.nonfinite_chunks == 1
    assert np.isfinite(frames[0].pcm).all()


def test_input_rates_are_recorded_for_the_run_header():
    src = LiveSource(sample_rate=16000, frame_ms=20)
    src.push(chunk(20, 48000, 0.1), 48000)
    src.close()
    list(src.frames())
    assert src.input_rates == [48000]


def test_peak_rms_is_reported_for_the_no_audio_check():
    src = LiveSource(sample_rate=16000, frame_ms=20)
    src.push(chunk(20, 16000, 0.0), 16000)
    assert src.peak_rms == 0.0
    src.push(chunk(20, 16000, 0.5), 16000)
    assert src.peak_rms == 0.5


def test_frames_waits_for_audio_instead_of_ending():
    """A silence between sentences must not look like the end of the call.

    frames() blocks until a chunk or a close; the pipeline thread sits in it
    for as long as the person stays quiet, which is correct.
    """
    import threading
    import time

    src = LiveSource(sample_rate=16000, frame_ms=20)
    seen = []
    done = threading.Event()

    def consume():
        for frame in src.frames():
            seen.append(frame.t_start_ms)
        done.set()

    worker = threading.Thread(target=consume, daemon=True)
    worker.start()
    time.sleep(0.4)
    assert not done.is_set(), "frames() ended while the source was still open"

    src.push(chunk(20, 16000, 0.1), 16000)
    src.close()
    worker.join(timeout=2.0)
    assert done.is_set()
    assert seen == [0]
