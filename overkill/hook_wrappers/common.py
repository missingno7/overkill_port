"""Shared helpers for OVERKILL address-bound hook wrappers.

``signature_matches``/``code_matches``/``self_disable_if_patched``/
``interpret_current_instruction_without_hook`` were promoted verbatim into
``dos_re.hooks`` (generalized from this exact module); they're re-exported
here under their historical names/signatures. ``call_hook_like_near_call``
has no dos_re equivalent (it's a simpler, distinct primitive: push+call with
no verifier routing) and stays as real local code.
"""

from __future__ import annotations

from typing import Callable

from dos_re.hooks import (
    call_installed_hook_like_near_call as _call_installed_hook_like_near_call,
    code_matches,
    interpret_current_instruction_without_hook,
    jump_installed_hook_boundary as _jump_installed_hook_boundary,
    self_disable_if_patched,
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


__all__ = [
    "call_hook_like_near_call",
    "call_installed_hook_like_near_call",
    "jump_installed_hook_boundary",
    "code_matches",
    "interpret_current_instruction_without_hook",
    "self_disable_if_patched",
]
