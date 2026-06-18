"""Hook taxonomy: classify replacement hooks by their *role*, not their address.

The original 8086 ASM (the VM) stays instruction-level snapshotable/stepable as
the oracle.  The source-port runtime, by contrast, is meant to be *checkpoint*-
level snapshotable: it resumes only from stable logical boundaries (frame,
object-update, render, input).  Between two checkpoints, lifted source-like code
may run as one atomic deterministic chain - it does NOT need to preserve every
historical CS:IP bounce or support arbitrary mid-chain resume.  A snapshot
requested mid-chain is deferred to the next checkpoint (or represented as the
previous checkpoint + deterministic replay).

So a registered hook address is one of four things:

* ``checkpoint``      - a real logical boundary the source-port loop resumes from.
* ``env_wait``        - a hardware/environment wait the interpreter can't satisfy
                        natively (PIT/IRQ0 timer, CRTC retrace) and that must stay
                        a hook even in the oracle reference.
* ``debug_probe``     - exists only for verification/observation, not behaviour.
* ``glue``            - accidental ASM-boundary plumbing: behaviours, tails,
                        helpers, per-object/per-row scan steps.  These are the
                        collapse target - they should fuse into source-like code
                        between checkpoints, with correctness protected by the
                        semantic frame/state verifier, not by their CS:IP.

Curated sets are intentionally small and explicit; everything not named here is
``glue`` by default (the honest majority).  Refine the curated sets as logical
boundaries are confirmed; do not pad them.
"""
from __future__ import annotations

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

CATEGORIES = ("checkpoint", "env_wait", "debug_probe", "glue")


def classify_hook(addr: Addr) -> str:
    """Return the taxonomy category for a hook address."""
    if addr in CHECKPOINT_HOOKS:
        return "checkpoint"
    if addr in ENV_WAIT_HOOKS:
        return "env_wait"
    if addr in DEBUG_PROBE_HOOKS:
        return "debug_probe"
    return "glue"


def classify_registry(replacements) -> dict[str, list[Addr]]:
    """Group an iterable of registered hook addresses by taxonomy category."""
    out: dict[str, list[Addr]] = {c: [] for c in CATEGORIES}
    for addr in replacements:
        out[classify_hook(addr)].append(addr)
    for cat in out:
        out[cat].sort()
    return out
