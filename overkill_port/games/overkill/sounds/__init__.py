"""OVERKILL-specific sound/timer island."""
from .pc_speaker import (
    AsyncTimerIrqDriver,
    OVERKILL_PIT_HZ,
    SIG_FAST_TIMER_ISR_06E5,
    SIG_PC_SPEAKER_TICK_D50E,
    deliver_overkill_timer_irq0,
    run_fast_timer_isr_06e5,
    run_pc_speaker_tick_d50e,
)

__all__ = [
    "AsyncTimerIrqDriver",
    "OVERKILL_PIT_HZ",
    "SIG_FAST_TIMER_ISR_06E5",
    "SIG_PC_SPEAKER_TICK_D50E",
    "deliver_overkill_timer_irq0",
    "run_fast_timer_isr_06e5",
    "run_pc_speaker_tick_d50e",
]
