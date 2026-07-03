"""The 8086 FLAGS-register bit constants this package's VM-hook-body forms replay.

Deliberately independent of ``dos_re.cpu`` (which defines the same values): ``overkill.asset_codecs``
backs the VM-free level/asset loader (``native_level.py`` -> ``overkill.native_game`` -> the standalone
entrypoint, ``scripts/play_native.py``), which must not import ``dos_re`` -- the whole 8086
interpreter/emulator package -- at all, so a genuinely standalone build never needs it on disk. These
are plain integer bit positions (the 8086 FLAGS register layout never changes), not emulator logic, so
duplicating them here is safe and keeps this package's only remaining VM-hook-body code
(``asm_adapters.py``, ``rle.py``, etc. -- kept for the ``--backend vm`` oracle path) from pulling the
emulator into the standalone's import closure.
"""
from __future__ import annotations

CF = 0x0001  # Carry Flag
DF = 0x0400  # Direction Flag
