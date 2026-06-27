"""PresentationLoop: independent present cadence + thread-safe producer/consumer."""
from __future__ import annotations

import threading
import time

import pytest

from overkill.native_video.backend import NativeOverkillVideoBackend
from overkill.native_video.frame import NativeSourceFrame
from overkill.native_video.loop import PresentationLoop


def _np():
    try:
        import numpy as np
        return np
    except Exception:  # pragma: no cover
        pytest.skip("numpy not installed")


def _frame(np, frame_id, ts):
    return NativeSourceFrame(
        frame_id=frame_id, timestamp=ts,
        playfield_rgb=np.zeros((200, 320, 3), dtype=np.uint8), source_cursor=0x1000,
    )


def test_run_once_skips_before_first_source_frame():
    loop = PresentationLoop(NativeOverkillVideoBackend(), draw=lambda p: None, clock=lambda: 0.0)
    assert loop.run_once() is None
    assert loop.skipped_not_ready == 1 and loop.presented_count == 0


def test_presents_independently_of_source_cadence():
    np = _np()
    be = NativeOverkillVideoBackend()
    t = [0.0]

    def clock():
        t[0] += 1 / 240.0
        return t[0]

    drawn = []
    loop = PresentationLoop(be, drawn.append, clock=clock)
    be.submit_source_frame(_frame(np, 1, 0.0))
    for _ in range(8):  # 8 monitor refreshes, one source frame
        loop.run_once()
    assert loop.presented_count == 8 and len(drawn) == 8
    assert all(p.source_frame_id == 1 for p in drawn)
    assert be.diagnostics().frame_hold_count == 7  # first present + 7 holds


def test_new_source_frame_clears_hold():
    np = _np()
    be = NativeOverkillVideoBackend()
    drawn = []
    loop = PresentationLoop(be, drawn.append, clock=lambda: 0.0)
    be.submit_source_frame(_frame(np, 1, 0.0))
    loop.run_once()
    be.submit_source_frame(_frame(np, 2, 0.0))
    out = loop.run_once()
    assert out.source_frame_id == 2 and out.held is False


def test_thread_start_stop_presents_on_its_own():
    np = _np()
    be = NativeOverkillVideoBackend()
    be.submit_source_frame(_frame(np, 1, 0.0))
    count = [0]
    lock = threading.Lock()

    def draw(_p):
        with lock:
            count[0] += 1

    loop = PresentationLoop(be, draw, target_hz=1000.0)
    loop.start()
    assert loop.running
    time.sleep(0.05)
    loop.stop()
    assert not loop.running
    with lock:
        assert count[0] > 0  # the loop presented independently of any new source frame


def test_concurrent_producer_and_present_thread_are_safe():
    np = _np()
    be = NativeOverkillVideoBackend()
    drawn = []
    lock = threading.Lock()

    def draw(p):
        with lock:
            drawn.append(p.source_frame_id)

    loop = PresentationLoop(be, draw, target_hz=2000.0)
    be.submit_source_frame(_frame(np, 0, 0.0))
    loop.start()

    def produce():
        for i in range(1, 60):
            be.submit_source_frame(_frame(np, i, i / 70.0))
            time.sleep(0.001)

    producer = threading.Thread(target=produce)
    producer.start()
    producer.join()
    time.sleep(0.02)
    loop.stop()

    with lock:
        assert len(drawn) > 0
        assert max(drawn) <= 59  # never presents a frame id that was never submitted
    # diagnostics remain consistently readable from the main thread
    assert be.diagnostics().frame_hold_count >= 0
