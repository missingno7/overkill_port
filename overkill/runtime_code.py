"""Runtime-code variant and staticization support for OVERKILL.

Some OVERKILL addresses are not single static routines. The cold executable can
contain one routine body while startup/gameplay materializes a different body
at the same CS:IP. Hooking such addresses by address alone is unsafe: the hook
must first prove which live byte variant is installed.

The mechanism (variant/slot/staticization model, identification, the
staticization-readiness gate, the write tracer) was promoted verbatim into
``dos_re.runtime_code`` — it took no OVERKILL-specific logic, just the slot
table as a parameter instead of a module import. This module supplies that
table (real game knowledge: addresses, byte signatures, evidence) and keeps
the original module-level call signatures (no ``slots`` argument) so existing
call sites don't need to change.
"""
from __future__ import annotations

from typing import Iterable

from dos_re.runtime_code import (
    RuntimeCodeSlot,
    RuntimeCodeStaticization,
    RuntimeCodeStaticizationError,
    RuntimeCodeVariant,
    RuntimeCodeWriteEvent,
    UnknownRuntimeCodeVariant,
)
from dos_re.runtime_code import RuntimeCodeWriteTracer as _GenericRuntimeCodeWriteTracer
from dos_re.runtime_code import default_runtime_code_regions as _default_runtime_code_regions
from dos_re.runtime_code import describe_live_runtime_code_state as _describe_live_runtime_code_state
from dos_re.runtime_code import identify_runtime_code_variant as _identify_runtime_code_variant
from dos_re.runtime_code import live_code_bytes  # noqa: F401 - re-exported, no game data needed
from dos_re.runtime_code import require_runtime_code_variant as _require_runtime_code_variant
from dos_re.runtime_code import runtime_code_staticization_report as _runtime_code_staticization_report
from dos_re.runtime_code import (
    assert_runtime_code_staticization_ready as _assert_runtime_code_staticization_ready,
)
from dos_re.runtime_code import variants_by_addr

Addr = tuple[int, int]


# This is the hot gameplay materialized body observed in
# artifacts/test_oracles/runtime_code_5e42_gameplay_20260613_220042.  It covers the entry body and
# its two internal flag-bit leaves at 5EB5/5EC8.  The hook then tail-calls the
# already-lifted AF22/AF63 movement helpers.
SIG_5E42_GAMEPLAY_OBJECT_STEER = bytes.fromhex(
    "c7 06 0c 23 00 00 c7 06 0e 23 00 00 c7 06 10 23 "
    "00 00 8b 46 2c 0b c0 79 06 f7 d8 ff 06 0c 23 8b "
    "5e 2a 0b db 79 06 f7 db ff 06 0e 23 3b c3 74 21 "
    "77 0d 01 46 2e 39 5e 2e 76 1a 29 5e 2e eb 12 01 "
    "5e 2e 39 46 2e 76 05 29 46 2e eb 05 e8 24 00 eb "
    "06 e8 1f 00 e8 2f 00 bb 48 a3 a1 10 23 d7 3c ff "
    "75 01 c3 89 46 06 83 3e 12 23 03 75 03 e9 70 50 "
    "e9 ae 50 83 3e 0c 23 01 74 06 83 0e 10 23 02 c3 "
    "83 0e 10 23 01 c3 83 3e 0e 23 01 74 06 83 0e 10 "
    "23 08 c3 83 0e 10 23 04 c3"
)

# The cold executable body at 1010:5E42 is deliberately not hooked by the
# movement implementation.  It is recorded so diagnostics can say "known cold
# body reached through the wrong hook" instead of "random unknown bytes".
SIG_5E42_COLD_DISPLAY_HELPER_PREFIX = bytes.fromhex(
    "55 2e 8e 06 96 95 bf 68 23 b9 06 00 b8 04 00 f3 "
    "ab 8b 0e 5c a9 e3 09 0b c9 78 05 e8 cd ff e2 fb "
    "b4 40 b0 1f e8 fd f7 2e 8e 1e b4 95 36 8b 36 "
    "68 23 e8 86 00 36 8b 36 6a 23 e8 7e 00 36 8b 36 6c"
)

_VARIANT_5E42_GAMEPLAY_OBJECT_STEER = RuntimeCodeVariant(
    addr=(0x1010, 0x5E42),
    name="gameplay_object_steer_5e42",
    signature=SIG_5E42_GAMEPLAY_OBJECT_STEER,
    island="movement",
    status="hooked-verified-staticized",
    observed_in=("runtime_code_5e42_gameplay_20260613_220042",),
    notes=(
        "Runtime-materialized gameplay steering helper.  Converts signed "
        "target deltas into a movement direction and then uses AF22/AF63."
    ),
)

_VARIANT_5E42_COLD_DISPLAY_HELPER_PREFIX = RuntimeCodeVariant(
    addr=(0x1010, 0x5E42),
    name="cold_display_helper_5e42_prefix",
    signature=SIG_5E42_COLD_DISPLAY_HELPER_PREFIX,
    island="unknown/cold-code",
    status="known-not-this-hook",
    observed_in=("cold MZ load",),
    notes=(
        "Cold executable body at the same address.  The gameplay movement "
        "hook must not silently run or emulate this body."
    ),
)

RUNTIME_CODE_SLOTS: dict[Addr, RuntimeCodeSlot] = {
    (0x1010, 0x5E42): RuntimeCodeSlot(
        addr=(0x1010, 0x5E42),
        name="runtime_patched_object_steer_5e42",
        island="movement",
        owner=(0x1010, 0xB9F0),
        role=(
            "Gameplay-installed object steering helper.  The DOS runtime places "
            "a movement-specific body over an unrelated cold display helper."
        ),
        variants=(
            _VARIANT_5E42_GAMEPLAY_OBJECT_STEER,
            _VARIANT_5E42_COLD_DISPLAY_HELPER_PREFIX,
        ),
        staticization=RuntimeCodeStaticization(
            source_module="overkill.gameplay.object_runtime",
            source_function="run_runtime_patched_object_steer_5e42",
            dispatch="variant_guarded_static_hook",
            parameters=("SS:BP object slot",),
            state_inputs=(
                "SS:[BP+2A] signed X delta",
                "SS:[BP+2C] signed Y delta",
                "SS:[BP+2E] fractional accumulator",
                "DS:2312 movement-speed selector",
                "DS:A348 direction lookup table",
            ),
            asm_visible_side_effects=(
                "DS:230C/230E/2310 scratch words",
                "SS:[BP+06] direction byte/word write",
                "balanced internal CALL scratch below SP",
                "tail-call-equivalent AF22/AF63 movement helper effects",
            ),
            notes=(
                "The port does not preserve runtime self-modifying behavior.  The "
                "installed body is flattened into this explicit source function; "
                "live bytes are only used as an oracle/variant guard."
            ),
        ),
        installer_status="observed-bootstrap-inner-unpack",
        installer_evidence=(
            "scripts/trace_runtime_code_writes.py --no-hooks --steps 500000 "
            "records 211 byte writes from 32FF:009B into 1010:5E42-5F1A.",
            "The same gameplay_object_steer_5e42 body is installed for CGA, EGA, "
            "and Tandy command tails, so this slot is not a video/sound/input selector.",
            "32FF:* is the already-classified transient inner unpack/self-relocation "
            "bootstrap, not a durable source-port game island.",
        ),
        notes=(
            "Accepted runtime body is staticized.  The installer is now classified "
            "as bootstrap materialization: the port should not emulate it as "
            "runtime self-modifying behavior, but should keep guarding the accepted "
            "static Python body by signature until the original binary oracle is retired."
        ),
    ),
}

# Backwards-compatible lookup used by existing hook guards/tests.
RUNTIME_CODE_VARIANTS: dict[Addr, tuple[RuntimeCodeVariant, ...]] = variants_by_addr(RUNTIME_CODE_SLOTS)


def iter_runtime_code_slots() -> Iterable[RuntimeCodeSlot]:
    return RUNTIME_CODE_SLOTS.values()


def identify_runtime_code_variant(cpu, addr: Addr) -> RuntimeCodeVariant:
    return _identify_runtime_code_variant(cpu, addr, RUNTIME_CODE_SLOTS)


def require_runtime_code_variant(cpu, addr: Addr, expected_name: str) -> RuntimeCodeVariant:
    return _require_runtime_code_variant(cpu, addr, expected_name, RUNTIME_CODE_SLOTS)


def describe_live_runtime_code_state(cpu, addr: Addr) -> dict[str, object]:
    return _describe_live_runtime_code_state(cpu, addr, RUNTIME_CODE_SLOTS)


def runtime_code_staticization_report(*, strict_installers: bool = False) -> list[dict[str, object]]:
    return _runtime_code_staticization_report(RUNTIME_CODE_SLOTS, strict_installers=strict_installers)


def assert_runtime_code_staticization_ready(*, strict_installers: bool = False) -> None:
    _assert_runtime_code_staticization_ready(RUNTIME_CODE_SLOTS, strict_installers=strict_installers)


def _default_regions() -> tuple[tuple[Addr, int], ...]:
    return _default_runtime_code_regions(RUNTIME_CODE_SLOTS)


class RuntimeCodeWriteTracer(_GenericRuntimeCodeWriteTracer):
    """Same as ``dos_re.runtime_code.RuntimeCodeWriteTracer``, but defaults
    ``regions`` to OVERKILL's own runtime-code slots when omitted (the
    original OVERKILL-only call convention)."""

    def __init__(self, cpu, regions=None, *, sink=None):
        super().__init__(cpu, regions if regions is not None else _default_regions(), sink=sink)
