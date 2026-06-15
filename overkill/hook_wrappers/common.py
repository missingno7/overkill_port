"""Shared helpers for OVERKILL address-bound hook wrappers."""

from __future__ import annotations

from typing import Callable

from dos_re.hooks import (
    call_installed_hook_like_near_call as _call_installed_hook_like_near_call,
    jump_installed_hook_boundary as _jump_installed_hook_boundary,
)


def _signature_matches(live: bytes, expected: bytes | tuple[bytes, ...]) -> bool:
    variants = expected if isinstance(expected, tuple) else (expected,)
    return any(live[:len(sig)] == sig for sig in variants)


def _all_zero_signature_window(live: bytes, expected: bytes | tuple[bytes, ...]) -> bool:
    variants = expected if isinstance(expected, tuple) else (expected,)
    return any(all(b == 0 for b in live[:len(sig)]) for sig in variants)


def self_disable_if_patched(cpu, ip: int, expected: bytes | tuple[bytes, ...], name: str) -> bool:
    """Fail fast when a hook entry no longer matches the lifted ASM bytes.

    OVERKILL patches parts of its live code segment during startup.  A Python
    replacement bypasses the live bytes at CS:IP, so wrappers that assume a fixed
    routine shape should refuse to run when the original bytes changed.  Synthetic
    tests often leave code bytes all zero; that fixture case is treated as
    "no live signature available" and remains enabled.
    """
    cs = cpu.s.cs & 0xFFFF
    start = ((cs << 4) + (ip & 0xFFFF)) & 0xFFFFF
    variants = expected if isinstance(expected, tuple) else (expected,)
    max_len = max(len(sig) for sig in variants)
    live = bytes(cpu.mem.data[start:start + max_len])
    if _signature_matches(live, expected) or _all_zero_signature_window(live, expected):
        return False

    expected_text = " or ".join(sig.hex(" ") for sig in variants)
    raise RuntimeError(
        f"OVERKILL hook {name} at {cs:04X}:{ip:04X} saw runtime-patched code; "
        f"live bytes {live.hex(' ')} != expected {expected_text}"
    )


def call_hook_like_near_call(cpu, handler: Callable, return_ip: int) -> None:
    """Run a replacement body with the same stack side effect as CALL/RET."""
    cpu.push(return_ip & 0xFFFF)
    handler(cpu)


def call_installed_hook_like_near_call(cpu, key: tuple[int, int], default_handler: Callable, return_ip: int) -> None:
    """Backward-compatible OVERKILL import path for the generic DOS_RE helper."""
    _call_installed_hook_like_near_call(cpu, key, default_handler, return_ip)


def jump_installed_hook_boundary(cpu, key: tuple[int, int], default_handler: Callable) -> None:
    """Backward-compatible OVERKILL import path for verifier-visible JMP/fall-through child boundaries."""
    _jump_installed_hook_boundary(cpu, key, default_handler)
