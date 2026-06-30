"""Fail-loud tripwire for the un-produced-vs-VM-verified A378 player-shot follow-up spawn.

``native_a378_followup`` (overkill.recovered.systems.objects) mirrors the VM-verified ``run_a396_body``
lift and is unit-tested, but NO demo in the corpus fires A378 (its ``si != FFFF`` + ``A3A4 == 0`` gates
never co-occur with the right weapon), so it has no produced-vs-VM confirmation.

Rather than ship the spawn path silently unverified, the lifted A378 hook calls
:func:`witness_a378_spawn_gap` the moment A378 actually spawns.  It raises :class:`PlayerShotSpawnGap`,
and the harness's default crash-snapshot writes a repro -- which is exactly the witness we need.  Replay
it with::

    python -m overkill.probes.verify_native_player_shot_spawn <snapshot-dir>

to confirm ``native_a378_followup`` byte-exact against the VM, then retire this tripwire (or wire
``native_a378_followup`` in as the verified native A378).  Because no demo reaches the spawn path, this
tripwire is dormant in every current test -- it only fires on a real encounter (live play, or a future
demo).  The verify probe calls :func:`set_raise_on_encounter` ``(False)`` so it can replay the witness.
"""
from __future__ import annotations


class PlayerShotSpawnGap(RuntimeError):
    """The A378 player-shot follow-up spawn was encountered -- an un-VM-verified native spawn path."""


_raise_on_encounter = True


def set_raise_on_encounter(enabled: bool) -> None:
    """Toggle the A378 tripwire.  The verify probe disables it to replay a captured witness snapshot."""
    global _raise_on_encounter
    _raise_on_encounter = bool(enabled)


def witness_a378_spawn_gap(source_x: int, source_y: int) -> None:
    """Fail loud when A378 actually spawns so the harness captures a replayable witness snapshot."""
    if _raise_on_encounter:
        raise PlayerShotSpawnGap(
            f"A378 player-shot follow-up spawn encountered (schedule source x={source_x & 0xFFFF:#06x} "
            f"y={source_y & 0xFFFF:#06x}): native_a378_followup is correct-by-construction + unit-tested "
            f"but has no produced-vs-VM witness in the corpus. This crash-snapshot IS the witness -- "
            f"replay it with `python -m overkill.probes.verify_native_player_shot_spawn <snapshot-dir>` "
            f"to confirm native_a378_followup, then retire this tripwire."
        )
