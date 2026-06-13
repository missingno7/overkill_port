"""Runtime-code variant and staticization support for OVERKILL.

Some OVERKILL addresses are not single static routines.  The cold executable can
contain one routine body while startup/gameplay materializes a different body at
the same CS:IP.  Hooking such addresses by address alone is unsafe: the hook must
first prove which live byte variant is installed.

The source-port policy is stricter than merely emulating self-modifying code:
runtime-installed bodies are treated as old-school specialization/dispatch
installation.  Every accepted body must become a named, documented, verified
static Python implementation.  Unknown byte variants fail fast; they are new
reverse-engineering frontiers, not an excuse to run interpreted ASM silently.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
from pathlib import Path
from typing import Callable, Iterable, TextIO

from overkill_port.memory import linear

Addr = tuple[int, int]


class UnknownRuntimeCodeVariant(RuntimeError):
    """Raised when a hook reaches a runtime-patched address with unknown bytes."""


class RuntimeCodeStaticizationError(RuntimeError):
    """Raised when runtime-code slots are not ready for source-port lifting."""


@dataclass(frozen=True)
class RuntimeCodeVariant:
    addr: Addr
    name: str
    signature: bytes
    island: str
    status: str
    observed_in: tuple[str, ...] = ()
    notes: str = ""

    @property
    def size(self) -> int:
        return len(self.signature)

    @property
    def sha1(self) -> str:
        return sha1(self.signature).hexdigest()

    @property
    def is_accepted_runtime_body(self) -> bool:
        """Whether this variant may be executed by a staticized hook."""
        return self.status.startswith("hooked") or self.status.startswith("staticized")


@dataclass(frozen=True)
class RuntimeCodeStaticization:
    """How a runtime-installed code body is represented in the source port.

    This records the intended transformation:

        patched bytes -> named variant -> explicit static Python source logic

    It intentionally does not install or mutate code.  It is a manifest entry and
    audit target proving that a runtime-code slot has a flat source-port owner.
    """

    source_module: str
    source_function: str
    dispatch: str
    parameters: tuple[str, ...] = ()
    state_inputs: tuple[str, ...] = ()
    asm_visible_side_effects: tuple[str, ...] = ()
    notes: str = ""

    @property
    def target(self) -> str:
        return f"{self.source_module}.{self.source_function}"


@dataclass(frozen=True)
class RuntimeCodeSlot:
    """A polyvariant executable slot in the original runtime image.

    A slot is the stable source-port concept.  Variants are the original byte
    bodies observed in that slot.  Staticization describes the Python logic that
    replaces accepted runtime-installed variants without preserving Python-level
    self-modifying behavior.
    """

    addr: Addr
    name: str
    island: str
    owner: Addr | None
    role: str
    variants: tuple[RuntimeCodeVariant, ...]
    staticization: RuntimeCodeStaticization | None
    installer_status: str
    installer_evidence: tuple[str, ...] = ()
    notes: str = ""

    @property
    def max_signature_size(self) -> int:
        return max(v.size for v in self.variants)

    @property
    def accepted_variants(self) -> tuple[RuntimeCodeVariant, ...]:
        return tuple(v for v in self.variants if v.is_accepted_runtime_body)

    @property
    def is_staticized(self) -> bool:
        return self.staticization is not None and bool(self.accepted_variants)

    @property
    def has_installer_evidence(self) -> bool:
        return self.installer_status.startswith("observed") or self.installer_status.startswith("static")


# This is the hot gameplay materialized body observed in
# artifacts/snapshot_play_tandy_20260613_220042.  It covers the entry body and
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
    observed_in=("snapshot_play_tandy_20260613_220042",),
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
            source_module="overkill_port.games.overkill.gameplay.object_runtime",
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
RUNTIME_CODE_VARIANTS: dict[Addr, tuple[RuntimeCodeVariant, ...]] = {
    addr: slot.variants for addr, slot in RUNTIME_CODE_SLOTS.items()
}


def iter_runtime_code_slots() -> Iterable[RuntimeCodeSlot]:
    return RUNTIME_CODE_SLOTS.values()


def live_code_bytes(cpu, addr: Addr, size: int) -> bytes:
    seg, off = addr
    start = linear(seg, off)
    return bytes(cpu.mem.data[start:start + size])


def identify_runtime_code_variant(cpu, addr: Addr) -> RuntimeCodeVariant:
    """Return the known runtime-code variant currently installed at ``addr``.

    The match is exact for the registered signature length.  Unknown bytes are a
    reverse-engineering frontier and therefore fail fast.
    """
    variants = RUNTIME_CODE_VARIANTS.get(addr, ())
    if not variants:
        raise UnknownRuntimeCodeVariant(
            f"no runtime-code variants are registered for {addr[0]:04X}:{addr[1]:04X}"
        )
    max_len = max(v.size for v in variants)
    live = live_code_bytes(cpu, addr, max_len)
    for variant in variants:
        if live[:variant.size] == variant.signature:
            return variant
    sample = live[:min(64, len(live))]
    expected = "; ".join(f"{v.name}[{v.size}B]={v.signature[:16].hex(' ')}..." for v in variants)
    raise UnknownRuntimeCodeVariant(
        f"unknown runtime-code variant at {addr[0]:04X}:{addr[1]:04X}; "
        f"live[{len(sample)}B]={sample.hex(' ')}; expected one of: {expected}"
    )


def require_runtime_code_variant(cpu, addr: Addr, expected_name: str) -> RuntimeCodeVariant:
    """Identify the live variant and require that it is the hook's target body."""
    variant = identify_runtime_code_variant(cpu, addr)
    if variant.name != expected_name:
        live = live_code_bytes(cpu, addr, min(64, variant.size))
        raise UnknownRuntimeCodeVariant(
            f"runtime-code variant {variant.name!r} at {addr[0]:04X}:{addr[1]:04X} "
            f"is known but not valid for hook {expected_name!r}; "
            f"status={variant.status}; live={live.hex(' ')}"
        )
    return variant


def describe_live_runtime_code_state(cpu, addr: Addr) -> dict[str, object]:
    """Return a diagnostic description of the live bytes at a runtime-code slot."""
    slot = RUNTIME_CODE_SLOTS.get(addr)
    if slot is None:
        raise UnknownRuntimeCodeVariant(
            f"no runtime-code slot is registered for {addr[0]:04X}:{addr[1]:04X}"
        )
    sample = live_code_bytes(cpu, addr, slot.max_signature_size)
    try:
        variant = identify_runtime_code_variant(cpu, addr)
        variant_name = variant.name
        status = variant.status
    except UnknownRuntimeCodeVariant:
        variant_name = "UNKNOWN"
        status = "unknown-live-bytes"
    return {
        "addr": f"{addr[0]:04X}:{addr[1]:04X}",
        "slot": slot.name,
        "variant": variant_name,
        "status": status,
        "sha1": sha1(sample).hexdigest(),
        "bytes": sample.hex(" "),
    }


def runtime_code_staticization_report(*, strict_installers: bool = False) -> list[dict[str, object]]:
    """Describe every runtime-code slot and whether it is source-port staticized."""
    report: list[dict[str, object]] = []
    for slot in iter_runtime_code_slots():
        staticization = slot.staticization
        missing: list[str] = []
        if not slot.accepted_variants:
            missing.append("accepted runtime variant")
        if staticization is None:
            missing.append("static source target")
        if strict_installers and not slot.has_installer_evidence:
            missing.append("installer provenance")
        report.append({
            "addr": f"{slot.addr[0]:04X}:{slot.addr[1]:04X}",
            "slot": slot.name,
            "island": slot.island,
            "accepted_variants": tuple(v.name for v in slot.accepted_variants),
            "all_variants": tuple(v.name for v in slot.variants),
            "staticized": slot.is_staticized,
            "static_target": staticization.target if staticization else "",
            "dispatch": staticization.dispatch if staticization else "",
            "installer_status": slot.installer_status,
            "missing": tuple(missing),
        })
    return report


def assert_runtime_code_staticization_ready(*, strict_installers: bool = False) -> None:
    """Fail if any accepted runtime-code slot lacks a static source owner.

    This is the project-level gate for the policy "no self-modifying Python".
    The default gate allows installer provenance to remain pending while the
    accepted variant is already staticized; pass ``strict_installers=True`` when
    preparing to declare 100% runtime-code exhaustion.
    """
    bad = [row for row in runtime_code_staticization_report(strict_installers=strict_installers) if row["missing"]]
    if bad:
        lines = ["runtime-code staticization is incomplete:"]
        for row in bad:
            missing = ", ".join(row["missing"])
            lines.append(f"  {row['addr']} {row['slot']}: missing {missing}")
        raise RuntimeCodeStaticizationError("\n".join(lines))


@dataclass(frozen=True)
class RuntimeCodeWriteEvent:
    writer: Addr
    target_phys: int
    size: int
    old: bytes
    new: bytes
    matched_region: str

    def line(self) -> str:
        return (
            f"writer={self.writer[0]:04X}:{self.writer[1]:04X} "
            f"target={self.target_phys:05X} size={self.size} "
            f"region={self.matched_region} old={self.old.hex(' ')} new={self.new.hex(' ')}"
        )


class RuntimeCodeWriteTracer:
    """Optional write tracer for discovering code materialization/installers.

    Install it on a CPU to watch writes that overlap runtime-code addresses.  It
    is intentionally opt-in so normal gameplay and tests do not pay for code
    write logging.
    """

    def __init__(
        self,
        cpu,
        regions: Iterable[tuple[Addr, int]] | None = None,
        *,
        sink: Callable[[RuntimeCodeWriteEvent], None] | TextIO | Path | None = None,
    ):
        self.cpu = cpu
        self.regions = tuple(regions or _default_runtime_code_regions())
        self.events: list[RuntimeCodeWriteEvent] = []
        self._sink = sink

    def install(self) -> "RuntimeCodeWriteTracer":
        self.cpu.mem.write_watchers.append(self._on_memory_write)
        return self

    def uninstall(self) -> None:
        try:
            self.cpu.mem.write_watchers.remove(self._on_memory_write)
        except ValueError:
            pass

    def _on_memory_write(self, phys: int, old: bytes, new: bytes) -> None:
        if old == new:
            return
        end = phys + len(new)
        for (seg, off), size in self.regions:
            start = linear(seg, off)
            region_end = start + size
            if phys < region_end and end > start:
                event = RuntimeCodeWriteEvent(
                    writer=(self.cpu.s.cs & 0xFFFF, self.cpu.s.ip & 0xFFFF),
                    target_phys=phys & 0xFFFFF,
                    size=len(new),
                    old=old,
                    new=new,
                    matched_region=f"{seg:04X}:{off:04X}+{size:04X}",
                )
                self.events.append(event)
                self._emit(event)
                break

    def _emit(self, event: RuntimeCodeWriteEvent) -> None:
        sink = self._sink
        if sink is None:
            return
        line = event.line() + "\n"
        if isinstance(sink, Path):
            with sink.open("a", encoding="utf-8") as f:
                f.write(line)
        elif hasattr(sink, "write"):
            sink.write(line)
        else:
            sink(event)


def _default_runtime_code_regions() -> tuple[tuple[Addr, int], ...]:
    regions: list[tuple[Addr, int]] = []
    for slot in iter_runtime_code_slots():
        # Add a little context after the known signature to catch nearby tails or
        # a variant body growing beyond the current observed end.
        regions.append((slot.addr, slot.max_signature_size + 0x40))
    return tuple(regions)
