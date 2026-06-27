"""The native presentation backend logic (display-independent, thread-safe).

``NativeOverkillVideoBackend`` is the consumer half of a decoupled producer/
consumer: the **game thread** produces a :class:`RenderSnapshot` of semantic
render-state at the game cadence via :meth:`submit_source_frame`; the
**presentation thread** consumes via :meth:`present` at the *display* cadence (one
call per monitor refresh) — see ``loop.PresentationLoop``. The two run
independently; the present side never blocks on the game and re-holds (later:
interpolates) when no new snapshot has arrived.

The backend **owns the rendering**: it does not receive a finished RGB frame, it
renders one from the snapshot's indexed layers + palette via ``LayerRenderer``
(with caches — held presents at high refresh are served from the render cache).
This module is pure logic (returns the ``(200,320,3)`` RGB); the pygame/SDL surface
blit is a separate adapter. Interpolation (Stages 3–4) is gated behind config flags
and is **not** silently faked: requesting an unimplemented flag raises.
"""
from __future__ import annotations

import copy
import threading
import time
from typing import Optional

from overkill.native_video.frame import (
    BackendConfig,
    BackendDiagnostics,
    PresentedFrame,
    RenderSnapshot,
)
from overkill.native_video.renderer import LayerRenderer


class NativeOverkillVideoBackend:
    """Display-independent, thread-safe native presentation backend (renders the
    semantic snapshot itself, with caches)."""

    def __init__(self, config: Optional[BackendConfig] = None) -> None:
        self.config = config or BackendConfig()
        self._require_supported(self.config)
        self._lock = threading.RLock()
        self._renderer = LayerRenderer()
        self._latest: Optional[RenderSnapshot] = None
        self._prev: Optional[RenderSnapshot] = None  # kept for interpolation (Stages 3–4)
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
            for name in (
                "camera_interpolation",
                "object_interpolation",
                "smooth_palette_fades",
                "smooth_transitions",
            )
            if getattr(config, name)
        ]
        if unsupported:
            raise NotImplementedError(
                "native_video: not implemented yet for flags "
                + ", ".join(unsupported)
                + " (Stages 3–5); leave them off until then"
            )

    @property
    def ready(self) -> bool:
        """True once at least one snapshot has been submitted (the present loop may
        spin up before the game produces its first frame)."""
        with self._lock:
            return self._latest is not None

    def submit_source_frame(self, snapshot: RenderSnapshot) -> None:
        """Producer (game thread): hand the backend a new game-tick snapshot."""
        with self._lock:
            if self._last_submit_ts is not None:
                dt = snapshot.timestamp - self._last_submit_ts
                if dt > 0:
                    self._diag.source_fps = 1.0 / dt
            self._last_submit_ts = snapshot.timestamp
            self._prev = self._latest
            self._latest = snapshot

    def present(self, now: float) -> PresentedFrame:
        """Consumer (present thread): render + return the frame for wall-clock ``now``.

        Stage 1/2: renders the latest snapshot's playfield (held presents are served
        from the render cache). Raises if asked to present before any snapshot —
        explicit, never a blank/VM-framebuffer fallback. Callers driving a
        free-running present loop should gate on :attr:`ready` first.
        """
        with self._lock:
            if self._latest is None:
                raise RuntimeError("native_video: present() before any snapshot was submitted")

            if self._last_present_now is not None:
                dt = now - self._last_present_now
                if dt > 0:
                    self._diag.present_fps = 1.0 / dt
            self._last_present_now = now

            snapshot = self._latest
            held = self._last_presented_frame_id == snapshot.frame_id
            if held:
                self._diag.frame_hold_count += 1
            self._last_presented_frame_id = snapshot.frame_id

            t0 = time.perf_counter()
            rgb, from_cache = self._renderer.render(snapshot)
            self._diag.native_render_ms = (time.perf_counter() - t0) * 1000.0
            self._diag.colorize_ms = self._renderer.last_colorize_ms
            self._diag.cache_hits = self._renderer.cache_hits
            self._diag.cache_misses = self._renderer.cache_misses
            self._diag.source_snapshot_age_ms = max(0.0, (now - snapshot.timestamp) * 1000.0)
            self._diag.interpolation_alpha = 0.0
            self._diag.camera_interpolation_active = False
            self._diag.object_interpolation_active = False

            return PresentedFrame(
                rgb=rgb,
                source_frame_id=snapshot.frame_id,
                alpha=0.0,
                held=held,
                from_cache=from_cache,
            )

    def diagnostics(self) -> BackendDiagnostics:
        """A consistent snapshot of the live diagnostics (safe to read from any
        thread)."""
        with self._lock:
            return copy.copy(self._diag)
