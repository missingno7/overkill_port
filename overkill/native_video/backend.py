"""The native presentation backend logic (display-independent, thread-safe).

``NativeOverkillVideoBackend`` is the consumer half of a decoupled producer/
consumer: the **game thread** produces :class:`NativeSourceFrame` at the game
cadence via :meth:`submit_source_frame`; the **presentation thread** consumes via
:meth:`present` at the *display* cadence (one call per monitor refresh) — see
``loop.PresentationLoop``. The two run independently; the present side never
blocks on the game and re-holds (later: interpolates) when no new source frame has
arrived, so the display stays smooth at refresh rate while game logic advances at
its own pace.

This module is the pure logic — it returns the ``(200,320,3)`` RGB to show — so it
is fully testable without a display; the thin pygame/SDL surface blit is a separate
adapter. Stages:
  * Stage 1 — native passthrough: present holds the latest source frame's faithful
    playfield baseline (source-boundary parity).
  * Stage 2 — presentation clock: present is wall-clock (``now``) driven and fully
    decoupled from the source cadence.
Interpolation (Stages 3–4) is gated behind config flags and is **not** silently
faked: requesting an unimplemented flag raises.
"""
from __future__ import annotations

import copy
import threading
from typing import Optional

from overkill.native_video.frame import (
    BackendConfig,
    BackendDiagnostics,
    NativeSourceFrame,
    PresentedFrame,
)


class NativeOverkillVideoBackend:
    """Display-independent, thread-safe native presentation backend."""

    def __init__(self, config: Optional[BackendConfig] = None) -> None:
        self.config = config or BackendConfig()
        self._require_supported(self.config)
        self._lock = threading.RLock()
        self._latest: Optional[NativeSourceFrame] = None
        self._prev: Optional[NativeSourceFrame] = None  # kept for interpolation (Stages 3–4)
        self._last_submit_ts: Optional[float] = None
        self._last_present_now: Optional[float] = None
        self._last_presented_frame_id: Optional[int] = None
        self._diag = BackendDiagnostics()

    @staticmethod
    def _require_supported(config: BackendConfig) -> None:
        """Fail loudly for flags whose implementation has not landed yet — no
        silent fallback to passthrough."""
        unsupported = [
            name
            for name in ("camera_interpolation", "object_interpolation", "smooth_palette_fades")
            if getattr(config, name)
        ]
        if unsupported:
            raise NotImplementedError(
                "native_video: interpolation not implemented yet for flags "
                + ", ".join(unsupported)
                + " (Stages 3–5); leave them off until then"
            )

    @property
    def ready(self) -> bool:
        """True once at least one source frame has been submitted (the present
        loop may spin up before the game produces its first frame)."""
        with self._lock:
            return self._latest is not None

    def submit_source_frame(self, frame: NativeSourceFrame) -> None:
        """Producer (game thread): hand the backend a new game-cadence frame."""
        with self._lock:
            if self._last_submit_ts is not None:
                dt = frame.timestamp - self._last_submit_ts
                if dt > 0:
                    self._diag.source_fps = 1.0 / dt
            self._last_submit_ts = frame.timestamp
            self._prev = self._latest
            self._latest = frame

    def present(self, now: float) -> PresentedFrame:
        """Consumer (present thread): the frame to display at wall-clock ``now``.

        Stage 1/2: holds the latest source frame's faithful playfield baseline.
        Raises if asked to present before any source frame — explicit, never a
        blank/VM-framebuffer fallback. Callers driving a free-running present loop
        should gate on :attr:`ready` first.
        """
        with self._lock:
            if self._latest is None:
                raise RuntimeError("native_video: present() before any source frame was submitted")

            if self._last_present_now is not None:
                dt = now - self._last_present_now
                if dt > 0:
                    self._diag.present_fps = 1.0 / dt
            self._last_present_now = now

            frame = self._latest
            held = self._last_presented_frame_id == frame.frame_id
            if held:
                self._diag.frame_hold_count += 1
            self._last_presented_frame_id = frame.frame_id

            self._diag.source_snapshot_age_ms = max(0.0, (now - frame.timestamp) * 1000.0)
            self._diag.interpolation_alpha = 0.0
            self._diag.camera_interpolation_active = False
            self._diag.object_interpolation_active = False

            return PresentedFrame(
                rgb=frame.playfield_rgb,
                source_frame_id=frame.frame_id,
                alpha=0.0,
                held=held,
            )

    def diagnostics(self) -> BackendDiagnostics:
        """A consistent snapshot of the live diagnostics (safe to read from any
        thread)."""
        with self._lock:
            return copy.copy(self._diag)
