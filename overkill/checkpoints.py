"""OVERKILL-bound checkpoint stepping, over the generic ``dos_re.checkpoints`` engine.

The stepping mechanism (group by kind, resolve a kind filter, run the VM to
the next match) was promoted verbatim into ``dos_re.checkpoints`` — it took no
OVERKILL-specific logic, just the checkpoint table as a parameter instead of
a module import. This module supplies that table
(``overkill.hook_taxonomy.CHECKPOINT_HOOKS``) and keeps the original
OVERKILL-style call signatures (no ``checkpoint_hooks`` argument) so existing
call sites don't need to change.
"""
from __future__ import annotations

from dos_re.checkpoints import checkpoints_by_kind as _checkpoints_by_kind
from dos_re.checkpoints import checkpoints_for as _checkpoints_for
from dos_re.checkpoints import run_to_next_checkpoint as _run_to_next_checkpoint
from overkill.hook_taxonomy import CHECKPOINT_HOOKS

Addr = tuple[int, int]

# kind -> frozenset of checkpoint addresses
CHECKPOINTS_BY_KIND: dict[str, frozenset[Addr]] = _checkpoints_by_kind(CHECKPOINT_HOOKS)

ALL_CHECKPOINTS: frozenset[Addr] = frozenset(CHECKPOINT_HOOKS)


def checkpoints_for(kinds: "str | tuple[str, ...] | None" = None) -> frozenset[Addr]:
    """Resolve a kind (or kinds) to its checkpoint address set; None == all."""
    return _checkpoints_for(CHECKPOINT_HOOKS, kinds)


def run_to_next_checkpoint(
    cpu,
    *,
    kinds: "str | tuple[str, ...] | None" = None,
    max_steps: int = 5_000_000,
    skip_current: bool = True,
) -> Addr:
    """Step the VM until it reaches the next compatible checkpoint; return it."""
    return _run_to_next_checkpoint(
        cpu, CHECKPOINT_HOOKS, kinds=kinds, max_steps=max_steps, skip_current=skip_current,
    )
