"""Address-bound hook wrappers for OVERKILL timer and PC-speaker helpers."""

from __future__ import annotations

from ....hooks import registry
from ..sounds import (
    SIG_FAST_TIMER_ISR_06E5,
    SIG_PC_SPEAKER_TICK_D50E,
    SIG_SOUND_ACTIVE_WAIT_9921,
    SIG_TIMER_WAIT_0679,
    deliver_overkill_timer_irq0,
    run_clear_timer_tick_flag_0672,
    run_fast_timer_isr_06e5,
    run_pc_speaker_tick_d50e,
    run_sound_active_wait_9921,
    run_wait_timer_tick_0679,
)
from .common import self_disable_if_patched


@registry.replace(0x1010, 0x06E5, "overkill_fast_timer_isr_06e5")
def overkill_fast_timer_isr_06e5(cpu):
    """OVERKILL 1010:06E5 fast timer ISR."""
    if self_disable_if_patched(cpu, 0x06E5, SIG_FAST_TIMER_ISR_06E5, "overkill_fast_timer_isr_06e5"):
        return
    run_fast_timer_isr_06e5(cpu)


@registry.replace(0x1010, 0xD50E, "overkill_pc_speaker_tick_d50e")
def overkill_pc_speaker_tick_d50e(cpu):
    """OVERKILL 1010:D50E PC speaker tick helper."""
    if self_disable_if_patched(cpu, 0xD50E, SIG_PC_SPEAKER_TICK_D50E, "overkill_pc_speaker_tick_d50e"):
        return
    run_pc_speaker_tick_d50e(cpu)


# Backward-compatible import point for older diagnostics/scripts.  New code should
# import from overkill_port.games.overkill.sounds directly.
_deliver_overkill_timer_irq0 = deliver_overkill_timer_irq0


@registry.replace(0x1010, 0x0672, "overkill_clear_timer_tick_flag_0672")
def overkill_clear_timer_tick_flag_0672(cpu):
    """OVERKILL 1010:0672 clear timer tick flag helper."""
    run_clear_timer_tick_flag_0672(cpu, self_disable_if_patched)


@registry.replace(0x1010, 0x0679, "overkill_wait_timer_tick_0679")
def overkill_wait_timer_tick_0679(cpu):
    """OVERKILL 1010:0679 wait-for-timer-tick loop."""
    if self_disable_if_patched(cpu, 0x0679, SIG_TIMER_WAIT_0679, "overkill_wait_timer_tick_0679"):
        return
    run_wait_timer_tick_0679(cpu)


@registry.replace(0x1010, 0x9921, "overkill_sound_active_wait_9921")
def overkill_sound_active_wait_9921(cpu):
    """OVERKILL 1010:9921 sound-active wait loop."""
    if self_disable_if_patched(cpu, 0x9921, SIG_SOUND_ACTIVE_WAIT_9921, "overkill_sound_active_wait_9921"):
        return
    run_sound_active_wait_9921(cpu)
