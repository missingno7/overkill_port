"""Shared helpers for OVERKILL address-bound hook wrappers."""

from __future__ import annotations

from typing import Callable


def self_disable_if_patched(cpu, ip: int, expected: bytes, name: str) -> bool:
    """Fail fast when a hook entry no longer matches the lifted ASM bytes.

    OVERKILL patches parts of its live code segment during startup.  A Python
    replacement bypasses the live bytes at CS:IP, so wrappers that assume a fixed
    routine shape should refuse to run when the original bytes changed.  Synthetic
    tests often leave code bytes all zero; that fixture case is treated as
    "no live signature available" and remains enabled.
    """
    cs = cpu.s.cs & 0xFFFF
    start = ((cs << 4) + (ip & 0xFFFF)) & 0xFFFFF
    live = bytes(cpu.mem.data[start:start + len(expected)])
    if live == expected or all(b == 0 for b in live):
        return False
    raise RuntimeError(
        f"OVERKILL hook {name} at {cs:04X}:{ip:04X} saw runtime-patched code; "
        f"live bytes {live.hex(' ')} != expected {expected.hex(' ')}"
    )


def call_hook_like_near_call(cpu, handler: Callable, return_ip: int) -> None:
    """Run a replacement body with the same stack side effect as CALL/RET."""
    cpu.push(return_ip & 0xFFFF)
    handler(cpu)


def call_installed_hook_like_near_call(cpu, key: tuple[int, int], default_handler: Callable, return_ip: int) -> None:
    """Run the currently installed hook with original near-CALL stack semantics.

    Most fused replacements call leaf helpers directly so differential tests stay
    simple and do not accidentally recurse into the verifier.  Visual/timing
    boundaries are different: play.py wraps some present/retrace hooks to publish
    video.  This helper preserves that installed wrapper when a lifted parent
    performs a nested CALL to a timing-sensitive hook.
    """
    handler = cpu.replacement_hooks.get(key, default_handler)
    cpu.push(return_ip & 0xFFFF)
    handler(cpu)
