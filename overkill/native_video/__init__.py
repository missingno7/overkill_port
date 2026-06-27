"""Native, VM-independent video presentation backend for OVERKILL.

This package builds a modern presentation layer that draws with native
pygame/SDL surfaces driven by the *monitor* clock, while the original/hybrid
runtime keeps producing game state at its own cadence. It consumes the recovered
semantic model (``recovered/domain/frame_snapshot`` + the page decode) rather than
the VM framebuffer, so presentation is decoupled from the original ~70 Hz video
cadence and can run at the display refresh (e.g. 240 Hz) with optional, opt-in
object/camera interpolation.

Layering: this is a *backend* — it may import the pure recovered model and the
Tandy geometry/palette, but never the VM/hooks. See
``docs/overkill/native_video_plan.md``.
"""
