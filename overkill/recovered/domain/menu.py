"""Front-end (intro/title/menu/map) domain records -- the VM-free counterpart of the scenes
shown before/around a level.  Like ``domain/frame_loop.py`` for gameplay, this stays pure:
no ``cpu``/``mem``, only source-level state the native side owns.
"""
from __future__ import annotations

from dataclasses import dataclass

MENU_ATTRACT_TIMEOUT = 0x02EE  # DS:22BF reaching this (750) transitions to the attract-mode demo


@dataclass(frozen=True, slots=True)
class MenuIdleOutcome:
    """Result of one ``1010:558B`` main-menu idle-loop iteration (the hot no-shortcut path)."""

    attract_counter: int
    result: str  # "loop" | "exit" | "attract_timeout"
