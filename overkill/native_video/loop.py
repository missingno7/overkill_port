"""The native backend's independent presentation loop.

Runs on its own thread so presentation is decoupled from the game-logic loop: it
presents at the display cadence (monitor refresh / a target rate) regardless of
when the game produces a new source frame, re-holding (later: interpolating) in
between. The game thread just calls ``backend.submit_source_frame(...)`` whenever
it finishes a frame; this loop keeps drawing independently.

The loop is display-agnostic — it hands each :class:`PresentedFrame` to a ``draw``
callback (the pygame/SDL surface blit lives in the separate display adapter). The
clock and sleep are injectable so the loop is testable without real time or a
display: drive :meth:`run_once` directly, or :meth:`start`/:meth:`stop` the thread.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from overkill.native_video.backend import NativeOverkillVideoBackend
from overkill.native_video.frame import PresentedFrame

DrawFn = Callable[[PresentedFrame], None]


class PresentationLoop:
    """Drive ``backend.present`` at the display cadence on a dedicated thread."""

    def __init__(
        self,
        backend: NativeOverkillVideoBackend,
        draw: DrawFn,
        *,
        target_hz: Optional[float] = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.backend = backend
        self.draw = draw
        # None = present as fast as the loop is driven (the real display adapter is
        # vsync-bound by its blit/flip); a number caps the present rate.
        self.target_hz = target_hz
        self._clock = clock
        self._sleep = sleep
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.presented_count = 0
        self.skipped_not_ready = 0

    def run_once(self) -> Optional[PresentedFrame]:
        """One present iteration. Returns the presented frame, or ``None`` if the
        backend has no source frame yet (the loop may start before the game
        produces its first frame — that case is counted, never an error/blank)."""
        if not self.backend.ready:
            self.skipped_not_ready += 1
            return None
        presented = self.backend.present(self._clock())
        self.draw(presented)
        self.presented_count += 1
        return presented

    def _run(self) -> None:
        period = (1.0 / self.target_hz) if self.target_hz else 0.0
        while not self._stop.is_set():
            t0 = self._clock()
            self.run_once()
            if period > 0.0:
                remaining = period - (self._clock() - t0)
                if remaining > 0:
                    self._sleep(remaining)

    def start(self) -> None:
        """Start the presentation thread (idempotent while running)."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="overkill-native-present", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        """Signal the thread to stop and join it."""
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
            self._thread = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()
