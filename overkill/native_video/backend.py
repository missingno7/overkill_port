"""The native presentation backend logic (display-independent).

``NativeOverkillVideoBackend`` consumes a stream of :class:`NativeSourceFrame` at
the game cadence and answers :meth:`present` at the *display* cadence (e.g. one
call per monitor refresh). This module is the pure logic — it returns the
``(200,320,3)`` RGB to show — so it is fully testable without a display; the thin
pygame/SDL surface blit is a separate adapter.

Stages implemented here:
  * Stage 1 — native passthrough: present holds the latest source frame's faithful
    playfield baseline (source-boundary parity: at a source frame's arrival the
    presented RGB *is* that frame's baseline).
  * Stage 2 — presentation clock: present is driven by wall-clock ``now`` and is
    fully decoupled from the source cadence; with no new source frame it re-holds.

Interpolation (Stages 3–4) is gated behind config flags and is **not** silently
faked: requesting an unimplemented flag raises, per the project rules.
"""
from __future__ import annotations

from typing import Optional

from overkill.native_video.frame import (
    BackendConfig,
    BackendDiagnostics,
    NativeSourceFrame,
    PresentedFrame,
)


class NativeOverkillVideoBackend:
    """Display-independent native presentation backend (faithful hold + clock)."""

    def __init__(self, config: Optional[BackendConfig] = None) -> None:
        self.config = config or BackendConfig()
        self._require_supported(self.config)
        self._latest: Optional[NativeSourceFrame] = None
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

    def submit_source_frame(self, frame: NativeSourceFrame) -> None:
        """Hand the backend a new game-cadence source frame."""
        if self._last_submit_ts is not None:
            dt = frame.timestamp - self._last_submit_ts
            if dt > 0:
                self._diag.source_fps = 1.0 / dt
        self._last_submit_ts = frame.timestamp
        self._latest = frame

    def present(self, now: float) -> PresentedFrame:
        """Return the frame to display at wall-clock time ``now`` (one refresh).

        Stage 1/2: holds the latest source frame's faithful playfield baseline.
        Raises if asked to present before any source frame — explicit, never a
        blank/VM-framebuffer fallback.
        """
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
        return self._diag
