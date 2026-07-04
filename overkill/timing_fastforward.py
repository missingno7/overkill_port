"""The timing FAST-FORWARD tracing primitive -- advance a raw-bytes runtime by whole frames.

OVERKILL paces every frame with the ``1010:0679`` busy wait (``cmp cs:[066B],0; jz 0679``) on a flag
the installed IRQ0 ISR (``1010:06E5``) increments.  The Python VM receives no asynchronous hardware
IRQs, so a hooks-cleared (raw original bytes) free run STALLS in that spin forever -- which made every
forward trace either use the heavyweight demo frame-verifier or the ``CS:066B = 1`` poke, whose
skipped ISR side effects LOSE state (music/SFX ticks + the BIOS INT 08h chain never run; the probe
measures the resulting DGROUP divergence).

:func:`advance_frames_fast` fixes this the same way the frame verifier's ASM side does
(``verification._overkill_asm_wait_handler``): whenever the CPU sits at the game's own wait points --
``0679``/``067F`` with the flag clear, or the ``9921`` sound-active wait -- it delivers the REAL
installed IRQ0 ISR (``sounds.timing.deliver_overkill_timer_irq0``, original bytes, including the
every-4th-tick BIOS chain), then lets execution continue.  One completed wait (the ``0681`` RET) is
one boundary.  No game state is faked; the only synthetic element is the interrupt DELIVERY POINT,
which is pinned to the same instruction boundaries the verifier's oracle uses.

THE UNIT (measured, ``verify_timing_fastforward``): one completed wait is the game's PACING TICK; on
the gameplay path ONE LOGIC FRAME = ~4 waits -- the per-frame counter bank at ``1010:601E..6046``
(frame parity ``DS:2324``, the dividers ``2326``/``2328``/``2336``, and the WAVE CLOCK ``DS:A7A0``)
advances once per 4 completed waits.  Callers tracing frame-paced state should count ``DS:A7A0``
transitions via ``on_frame`` rather than assuming wait == logic frame.

This is the OVERKILL equivalent of pre2_port's ``timing_fastforward.advance_frame_fast`` -- the
primitive that makes forward traces (enemy waves, menu flows, sustained play) cheap AND drift-free.
Verified by ``probes/verify_timing_fastforward`` (frame-cadence, determinism, and the poke-drift
differential).
"""
from __future__ import annotations

from typing import Callable

_CS = 0x1010
_WAIT_IPS = (0x0679, 0x067F)     # the frame wait: cmp cs:[066B],0 / jz 0679
_WAIT_RET_IP = 0x0681            # the wait's RET -- executing it completes one frame
_FLAG_OFF = 0x066B               # the IRQ0-advanced frame flag
_SOUND_WAIT_IPS = (0x9921, 0x9926)   # the DS:BEFE sound-active spin (menus/foreground)
_SOUND_FLAG_OFF = 0xBEFE


def advance_frames_fast(cpu, frames: int, *, on_frame: Callable | None = None,
                        step_budget_per_frame: int = 3_000_000) -> int:
    """Advance a hooks-cleared runtime by ``frames`` whole frames (completed ``0679`` waits).

    Steps raw original bytes; at the game's own wait points delivers the real installed IRQ0 ISR
    exactly like the frame verifier's ASM-side wait handler (no ``CS:066B`` poke, no skipped ISR --
    no drift).  Calls ``on_frame(cpu, frame_index)`` right after each frame boundary (the wait's
    RET), with ``frame_index`` counting from 1.  Returns the number of frames advanced.

    Raises ``RuntimeError`` if no installed OVERKILL INT 08h can be delivered (nothing is faked)
    or if a frame does not complete within ``step_budget_per_frame`` instructions.
    """
    from overkill.sounds.timing import deliver_overkill_timer_irq0

    done = 0
    for _ in range(frames):
        for _ in range(step_budget_per_frame):
            cs, ip = cpu.s.cs & 0xFFFF, cpu.s.ip & 0xFFFF
            if cs == _CS and ip in _WAIT_IPS and cpu.mem.rb(_CS, _FLAG_OFF) == 0:
                if not deliver_overkill_timer_irq0(cpu):
                    raise RuntimeError(
                        "advance_frames_fast: no installed OVERKILL INT 08h at 1010:06E5; "
                        "cannot advance frames (no synthetic timer fallback is allowed)")
                continue
            if (cs == _CS and ip in _SOUND_WAIT_IPS
                    and cpu.mem.rb(cpu.s.ds & 0xFFFF, _SOUND_FLAG_OFF) != 0):
                if not deliver_overkill_timer_irq0(cpu):
                    raise RuntimeError(
                        "advance_frames_fast: no installed OVERKILL INT 08h at 1010:06E5; "
                        "cannot service the 9921 sound-active wait")
                continue
            if cs == _CS and ip == _WAIT_RET_IP:
                cpu.step()  # execute the wait's RET -- the frame boundary
                break
            cpu.step()
        else:
            raise RuntimeError(
                f"advance_frames_fast: frame {done + 1} did not complete a 1010:0679 wait "
                f"within {step_budget_per_frame} steps (not in the frame loop?)")
        done += 1
        if on_frame is not None:
            on_frame(cpu, done)
    return done
