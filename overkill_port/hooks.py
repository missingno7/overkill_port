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
        def deco(fn: Hook) -> Hook:
            self.replacements[(cs & 0xFFFF, ip & 0xFFFF)] = Replacement(cs & 0xFFFF, ip & 0xFFFF, name, fn)
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
