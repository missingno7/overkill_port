"""Address-bound hook wrappers for OVERKILL timer and PC-speaker helpers."""

from __future__ import annotations

from dos_re.hooks import registry
from ..sounds import (
    SIG_ADLIB_CHANNEL_MOD_A_2032_02C9,
    SIG_ADLIB_FAR_ENTRY_2032_0000,
    SIG_ADLIB_CHANNEL_TICK_2032_00CD,
    SIG_ADLIB_CHANNEL_MOD_B_2032_02F6,
    SIG_ADLIB_PAGE_GATE_2032_0409,
    SIG_ADLIB_CHANNEL_HELPER_2032_0244,
    SIG_ADLIB_CHANNEL_HELPER_2032_02AA,
    SIG_ADLIB_SET_INSTRUMENT_2032_0181,
    SIG_ADLIB_NOTE_FREQUENCY_2032_024F,
    SIG_ADLIB_DETECT_2032_04E9,
    SIG_ADLIB_DRIVER_TICK_2032_0063,
    SIG_ADLIB_WRITE_2032_0557,
    SIG_FAST_TIMER_ISR_06E5,
    SIG_PC_SPEAKER_TICK_D50E,
    SIG_SOUND_ACTIVE_WAIT_9921,
    SIG_TIMER_WAIT_0679,
    run_adlib_channel_mod_a_2032_02c9,
    run_adlib_far_entry_2032_0000,
    run_adlib_channel_mod_b_2032_02f6,
    run_adlib_page_gate_2032_0409,
    run_adlib_channel_helper_2032_0244,
    run_adlib_channel_helper_2032_02aa,
    run_adlib_set_instrument_2032_0181,
    run_adlib_note_frequency_2032_024f,
    run_adlib_channel_tick_2032_00cd,
    run_adlib_detect_2032_04e9,
    run_adlib_driver_tick_2032_0063,
    run_adlib_write_2032_0557,
    run_clear_timer_tick_flag_0672,
    run_fast_timer_isr_06e5,
    run_pc_speaker_tick_d50e,
    run_sound_active_wait_9921,
    run_wait_timer_tick_0679,
)
from .common import self_disable_if_patched



@registry.replace(0x2032, 0x0000, "overkill_adlib_far_entry_2032_0000")
def overkill_adlib_far_entry_2032_0000(cpu):
    """Loaded AdLib driver far-call entry: CALL 0063; RETF."""
    if self_disable_if_patched(cpu, 0x0000, SIG_ADLIB_FAR_ENTRY_2032_0000, "overkill_adlib_far_entry_2032_0000"):
        return
    run_adlib_far_entry_2032_0000(cpu)


@registry.replace(0x2032, 0x04E9, "overkill_adlib_detect_2032_04e9")
def overkill_adlib_detect_2032_04e9(cpu):
    """Loaded AdLib driver YM3812 probe without PIT delay busy loops."""
    if self_disable_if_patched(cpu, 0x04E9, SIG_ADLIB_DETECT_2032_04E9, "overkill_adlib_detect_2032_04e9"):
        return
    run_adlib_detect_2032_04e9(cpu)








@registry.replace(0x2032, 0x0063, "overkill_adlib_driver_tick_2032_0063")
def overkill_adlib_driver_tick_2032_0063(cpu):
    """Loaded AdLib driver top-level timer tick."""
    if self_disable_if_patched(cpu, 0x0063, SIG_ADLIB_DRIVER_TICK_2032_0063, "overkill_adlib_driver_tick_2032_0063"):
        return
    run_adlib_driver_tick_2032_0063(cpu)


@registry.replace(0x2032, 0x00CD, "overkill_adlib_channel_tick_2032_00cd")
def overkill_adlib_channel_tick_2032_00cd(cpu):
    """Fast-path loaded-AdLib per-channel idle tick."""
    if self_disable_if_patched(cpu, 0x00CD, SIG_ADLIB_CHANNEL_TICK_2032_00CD, "overkill_adlib_channel_tick_2032_00cd"):
        return
    run_adlib_channel_tick_2032_00cd(cpu)


@registry.replace(0x2032, 0x0557, "overkill_adlib_write_2032_0557")
def overkill_adlib_write_2032_0557(cpu):
    """Loaded AdLib driver YM3812 register write without PIT delay loops."""
    if self_disable_if_patched(cpu, 0x0557, SIG_ADLIB_WRITE_2032_0557, "overkill_adlib_write_2032_0557"):
        return
    run_adlib_write_2032_0557(cpu)


@registry.replace(0x2032, 0x0409, "overkill_adlib_page_gate_2032_0409")
def overkill_adlib_page_gate_2032_0409(cpu):
    """Fast-path loaded-AdLib page/pause gate hot no-op route."""
    if self_disable_if_patched(cpu, 0x0409, SIG_ADLIB_PAGE_GATE_2032_0409, "overkill_adlib_page_gate_2032_0409"):
        return
    run_adlib_page_gate_2032_0409(cpu)


@registry.replace(0x2032, 0x0244, "overkill_adlib_channel_helper_2032_0244")
def overkill_adlib_channel_helper_2032_0244(cpu):
    """Fast-path loaded-AdLib per-channel disabled accumulator helper."""
    if self_disable_if_patched(cpu, 0x0244, SIG_ADLIB_CHANNEL_HELPER_2032_0244, "overkill_adlib_channel_helper_2032_0244"):
        return
    run_adlib_channel_helper_2032_0244(cpu)


@registry.replace(0x2032, 0x02AA, "overkill_adlib_channel_helper_2032_02aa")
def overkill_adlib_channel_helper_2032_02aa(cpu):
    """Fast-path loaded-AdLib no-pending-note helper."""
    if self_disable_if_patched(cpu, 0x02AA, SIG_ADLIB_CHANNEL_HELPER_2032_02AA, "overkill_adlib_channel_helper_2032_02aa"):
        return
    run_adlib_channel_helper_2032_02aa(cpu)


@registry.replace(0x2032, 0x0181, "overkill_adlib_set_instrument_2032_0181")
def overkill_adlib_set_instrument_2032_0181(cpu):
    """Loaded-AdLib instrument-select command body."""
    if self_disable_if_patched(cpu, 0x0181, SIG_ADLIB_SET_INSTRUMENT_2032_0181, "overkill_adlib_set_instrument_2032_0181"):
        return
    run_adlib_set_instrument_2032_0181(cpu)


@registry.replace(0x2032, 0x024F, "overkill_adlib_note_frequency_2032_024f")
def overkill_adlib_note_frequency_2032_024f(cpu):
    """Loaded-AdLib note/frequency register helper."""
    if self_disable_if_patched(cpu, 0x024F, SIG_ADLIB_NOTE_FREQUENCY_2032_024F, "overkill_adlib_note_frequency_2032_024f"):
        return
    run_adlib_note_frequency_2032_024f(cpu)


@registry.replace(0x2032, 0x02C9, "overkill_adlib_channel_mod_a_2032_02c9")
def overkill_adlib_channel_mod_a_2032_02c9(cpu):
    """Fast-path disabled loaded-AdLib channel modulation helper."""
    if self_disable_if_patched(cpu, 0x02C9, SIG_ADLIB_CHANNEL_MOD_A_2032_02C9, "overkill_adlib_channel_mod_a_2032_02c9"):
        return
    run_adlib_channel_mod_a_2032_02c9(cpu)


@registry.replace(0x2032, 0x02F6, "overkill_adlib_channel_mod_b_2032_02f6")
def overkill_adlib_channel_mod_b_2032_02f6(cpu):
    """Fast-path disabled loaded-AdLib channel modulation helper."""
    if self_disable_if_patched(cpu, 0x02F6, SIG_ADLIB_CHANNEL_MOD_B_2032_02F6, "overkill_adlib_channel_mod_b_2032_02f6"):
        return
    run_adlib_channel_mod_b_2032_02f6(cpu)


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
