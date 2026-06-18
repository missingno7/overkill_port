"""Checkpoint stepping: VM-until-checkpoint handoff for the source port.

The source-port runtime resumes only from stable logical boundaries (frame /
render / object-update / input).  This module makes that executable: given a
runtime positioned at *any* instruction, step the VM (instruction-exact oracle)
until it reaches the next compatible checkpoint, where game state is consistent
and a native phase-system could take over.

The checkpoint set is the curated, evidence-based phase map in
``overkill.hook_taxonomy`` (the per-frame ``CALL``/``RET`` phases of the gameplay
main loop ``1010:D007``).  Categorising by ``kind`` lets a caller wait for a
specific phase boundary (e.g. only the object-update checkpoint).
"""
from __future__ import annotations

from overkill.hook_taxonomy import CHECKPOINT_HOOKS

Addr = tuple[int, int]


def _kind(desc: str) -> str:
    # Descriptions are "frame: ...", "render: ...", "object-update: ...", "input: ...".
    return desc.split(":", 1)[0].strip()


# kind -> frozenset of checkpoint addresses
CHECKPOINTS_BY_KIND: dict[str, frozenset[Addr]] = {}
for _addr, _desc in CHECKPOINT_HOOKS.items():
    CHECKPOINTS_BY_KIND.setdefault(_kind(_desc), set()).add(_addr)  # type: ignore[arg-type]
CHECKPOINTS_BY_KIND = {k: frozenset(v) for k, v in CHECKPOINTS_BY_KIND.items()}

ALL_CHECKPOINTS: frozenset[Addr] = frozenset(CHECKPOINT_HOOKS)


def checkpoints_for(kinds: "str | tuple[str, ...] | None") -> frozenset[Addr]:
    """Resolve a kind (or kinds) to its checkpoint address set; None == all."""
    if kinds is None:
        return ALL_CHECKPOINTS
    if isinstance(kinds, str):
        kinds = (kinds,)
    out: set[Addr] = set()
    for k in kinds:
        if k not in CHECKPOINTS_BY_KIND:
            raise KeyError(f"unknown checkpoint kind {k!r}; known: {sorted(CHECKPOINTS_BY_KIND)}")
        out |= CHECKPOINTS_BY_KIND[k]
    return frozenset(out)


def run_to_next_checkpoint(
    cpu,
    *,
    kinds: "str | tuple[str, ...] | None" = None,
    max_steps: int = 5_000_000,
    skip_current: bool = True,
) -> Addr:
    """Step the VM until it reaches the next compatible checkpoint; return it.

    ``kinds`` filters which phase boundaries count (None = any).  ``skip_current``
    steps once first so a call made while already *at* a checkpoint advances to the
    following one (otherwise it would return immediately).  Raises ``TimeoutError``
    if no checkpoint is reached within ``max_steps``.
    """
    targets = checkpoints_for(kinds)
    if skip_current:
        cpu.step()
    for _ in range(max_steps):
        if cpu.addr() in targets:
            return cpu.addr()
        cpu.step()
    raise TimeoutError(f"no checkpoint in {kinds or 'any'} within {max_steps} steps")
