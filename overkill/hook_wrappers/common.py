"""Shared helpers for OVERKILL address-bound hook wrappers."""

from __future__ import annotations

from typing import Callable


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
    """Run an installed child hook with original near-CALL stack semantics.

    A Python parent hook often composes children directly instead of letting the
    VM fetch a CALL instruction and dispatch through ``CPU8086.step``.  That is
    convenient, but it used to bypass the live hook verifier at exactly the child
    address that the original ASM would have reached.  Route such nested calls
    through the verifier when it is active so the child entry becomes a real
    differential checkpoint instead of a shared black box inside the parent.
    """
    handler = cpu.replacement_hooks.get(key, default_handler)
    name = cpu.hook_names.get(key, getattr(handler, "__name__", "replacement"))
    cpu.push(return_ip & 0xFFFF)
    cpu.s.cs = key[0] & 0xFFFF
    cpu.s.ip = key[1] & 0xFFFF
    verifier = getattr(cpu, "hook_verifier", None)
    if (
        verifier is not None
        and getattr(cpu, "hook_verifier_verify_nested_calls", True)
        and key not in getattr(cpu, "hook_verifier_passthrough", set())
    ):
        verifier(cpu, key, handler, name)
    else:
        handler(cpu)
