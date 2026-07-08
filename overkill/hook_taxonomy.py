"""OVERKILL's curated hook taxonomy, over the generic ``dos_re.hook_taxonomy`` engine.

The four-category classification (checkpoint / env_wait / debug_probe / glue)
and its logic were promoted into ``dos_re.hook_taxonomy.HookTaxonomy`` — it
took no OVERKILL-specific logic, just the curated address sets as constructor
fields instead of module-level dicts. This module supplies OVERKILL's own
curated sets (real game knowledge, so it correctly stays here) and keeps the
original module-level function call signatures so existing call sites don't
need to change.
"""
from __future__ import annotations

from dos_re.hook_taxonomy import CATEGORIES, HookTaxonomy

Addr = tuple[int, int]

# Stable logical boundaries the native loop can resume from.  These are the
# per-frame phase calls of the gameplay main loop 1010:D007 (and the attract loop
# 97B2): the frame is already decomposed into RET-bounded phase systems, so each
# phase entry is a place where game state is consistent and verifiable.
CHECKPOINT_HOOKS: dict[Addr, str] = {
    # frame boundary - top of the per-frame loop
    (0x1010, 0xD007): "frame: gameplay main-loop dispatcher (top of frame)",
    (0x1010, 0x97B2): "frame: attract/menu frame-loop controller",
    # render phase: per-frame video setup -> layer-sprite scan -> present
    (0x1010, 0x511F): "render: per-frame video-page setup",
    (0x1010, 0xA846): "render: layer-sprite present scan",
    (0x1010, 0x5BDC): "render: present dispatcher (video jump table)",
    (0x1010, 0x3354): "render: Tandy frame present",
    (0x1010, 0x2750): "render: EGA frame present",
    (0x1010, 0x447B): "render: CGA frame present",
    # object-update phase: presence scan + per-frame state update + object scan
    (0x1010, 0xA90C): "object-update: present object-presence scan",
    (0x1010, 0xA940): "object-update: per-frame game-state update cluster",
    (0x1010, 0xAA10): "object-update: per-object scan/dispatch loop",
    # input phase
    (0x1010, 0x0162): "input: full keyboard/joystick poll",
}

# Hardware/environment waits the interpreter must keep hooked (no async PIT/IRQ0,
# CRTC retrace, or display-start the host satisfies); the verifier keeps these on
# the reference side too.  These bound the frame's pacing.
ENV_WAIT_HOOKS: dict[Addr, str] = {
    (0x1010, 0x0679): "wait for timer tick flag CS:[066B] (frame pacing)",
    (0x1010, 0x50C9): "wait for CRTC vertical retrace",
    (0x1010, 0x5160): "wait for EGA display-start",
    (0x1010, 0x06E5): "reprogrammed IRQ0 (INT 08h) timer ISR",
    (0x1010, 0x0672): "clear timer tick flag",
}

# Hooks that exist only to observe/verify, not to produce behaviour.
DEBUG_PROBE_HOOKS: dict[Addr, str] = {}

_TAXONOMY = HookTaxonomy(
    checkpoints=CHECKPOINT_HOOKS,
    env_waits=ENV_WAIT_HOOKS,
    debug_probes=DEBUG_PROBE_HOOKS,
)


def classify_hook(addr: Addr) -> str:
    """Return the taxonomy category for a hook address."""
    return _TAXONOMY.classify(addr)


def classify_registry(replacements) -> dict[str, list[Addr]]:
    """Group an iterable of registered hook addresses by taxonomy category."""
    return _TAXONOMY.classify_registry(replacements)


__all__ = [
    "CATEGORIES", "CHECKPOINT_HOOKS", "ENV_WAIT_HOOKS", "DEBUG_PROBE_HOOKS",
    "classify_hook", "classify_registry",
]
