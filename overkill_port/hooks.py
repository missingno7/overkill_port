from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .cpu import CPU8086


Hook = Callable[[CPU8086], None]


@dataclass(frozen=True)
class Replacement:
    cs: int
    ip: int
    name: str
    handler: Hook


class HookRegistry:
    """Maps original DOS addresses to Python replacements.

    The intended migration path is:
    1. execute original ASM and collect traces,
    2. understand a small routine,
    3. register a replacement at its CS:IP,
    4. let the rest of the original binary continue running.
    """

    def __init__(self) -> None:
        self.replacements: dict[tuple[int, int], Replacement] = {}

    def replace(self, cs: int, ip: int, name: str):
        key = (cs & 0xFFFF, ip & 0xFFFF)

        def deco(fn: Hook) -> Hook:
            # Fail fast on duplicate registrations.  The map is keyed by CS:IP, so
            # a second @replace at the same address would silently shadow the
            # first; that is exactly how superseded hook implementations used to
            # accrete unnoticed.  One address must have exactly one replacement.
            existing = self.replacements.get(key)
            if existing is not None:
                raise ValueError(
                    f"duplicate replacement at {key[0]:04X}:{key[1]:04X} "
                    f"({existing.name!r} then {name!r})"
                )
            self.replacements[key] = Replacement(key[0], key[1], name, fn)
            return fn
        return deco

    def install(self, cpu: CPU8086) -> None:
        for key, repl in self.replacements.items():
            cpu.replacement_hooks[key] = repl.handler
            cpu.hook_names[key] = repl.name


registry = HookRegistry()


def return_near(cpu: CPU8086, value_ax: int | None = None) -> None:
    if value_ax is not None:
        cpu.s.ax = value_ax & 0xFFFF
    cpu.s.ip = cpu.pop()


def return_far(cpu: CPU8086, value_ax: int | None = None) -> None:
    if value_ax is not None:
        cpu.s.ax = value_ax & 0xFFFF
    cpu.s.ip = cpu.pop()
    cpu.s.cs = cpu.pop()
