"""Game-specific host wiring for the standalone CPUless runtime (mirrors lemmings_port's runtime.py).

This holds the OVERKILL-specific HOST INPUTS the CPUless game needs -- the things the original read
through DOS/BIOS that a native host supplies instead -- kept OUT of the game-agnostic ``dos_re`` and,
critically, CARRIER-FREE: nothing here imports the interpreter, the VM runtime, or a VM-comparing
probe, so it is safe to import under the CPUless wall (``overkill.cpuless_host.install_import_guard``).

Today: the per-level asset bundle the gameplay frame reads on level load / death re-init (the original's
0B3E / 0E9C loaders do INT 21h file reads; the native port hands the decoded bytes in instead). The
decode itself lives in the pure ``overkill.asset_codecs`` package. As the front-end comes online this
module also gains the video-type selection and boot-key wiring, per the campaign blueprint.
"""
from __future__ import annotations

from pathlib import Path

from overkill.cpuless_host import CpuStandaloneWitness, FailLoudPlatform

ROOT = Path(__file__).resolve().parent.parent

#: The CGA/Tandy video-register block (3D0h-3DFh). These are WRITE-ONLY hardware registers
#: (mode control 3D8h, colour select 3D9h, CRTC 3D4/5h, ...): a write has NO effect on the
#: DGROUP image (the host renderer owns the actual display), so the standalone platform records
#: the value for a renderer and returns. This is correct by the hardware definition, independent
#: of the BIOS -- unlike INT 10h, which must be ported byte-faithfully (the next slice).
_CGA_TANDY_PORTS = range(0x3D0, 0x3E0)
#: CGA/Tandy status register (3DAh): bit0 = display-enable/retrace-in-progress, bit3 = vertical
#: retrace. The front-end paces on a `in 3DAh` poll; front-end tier is SCREEN-EXACT, so a toggle
#: that always eventually presents "retrace ready" is faithful enough to let the poll make progress.
_CGA_STATUS = 0x3DA

#: INT 10h AH values dos_re's int10 (dos.py) treats as a pure NO-OP -- registers + memory unchanged
#: (`if ah in (0x01, 0x0B, 0x12): return`). AH=0Bh (set CGA palette) is the one the front-end's 4F57
#: calls; the actual colour goes through the 3D9h port write. Kept byte-faithful + verified against
#: the dos_re oracle in tests/test_overkill_platform_int10.py. Other AH values fail loud until ported.
_INT10_NOOP_AH = frozenset({0x01, 0x0B, 0x12})
#: the register channels the platform intr contract echoes back (the VMless adapter's INT_REGS).
_INT_REGS = ("ax", "bx", "cx", "dx", "si", "di", "bp", "ds", "es")


class OverkillPlatform(FailLoudPlatform):
    """The standalone CPUless game's device model (carrier-free; grows toward the front-end).

    Today: the CGA/Tandy VIDEO PORTS the front-end drives -- write-only mode/colour registers
    (recorded, no DGROUP effect) and the 3DAh retrace poll. INT 10h and every other service still
    FAIL LOUD (inherited) until ported + verified against the dos_re oracle. Recorded writes live in
    :attr:`video_ports` so a host renderer can read the selected mode/palette."""

    def __init__(self, on_boundary=None) -> None:
        self.video_ports: dict[int, int] = {}
        self._retrace = 0
        #: host callback invoked at a SCHEDULER YIELD (see :meth:`boundary`), or None to just count.
        self._on_boundary = on_boundary
        #: yields seen, per kind -- the front-end's frame clock when the host does not pace it.
        self.boundaries: dict[str, int] = {}

    def boundary(self, kind: str = "timer") -> None:
        """A SCHEDULER YIELD: recovered code is blocking on something only the environment can
        supply (a timer tick, a retrace).  A CPUless build has no interrupt to deliver it, so the
        env-wait override (``overkill.cpuless_overrides``) hands control here instead of spinning.

        The host uses it to pace the frame, present, and pump input -- i.e. it is where the wall
        clock and the player re-enter a program that has no CPU underneath it."""
        self.boundaries[kind] = self.boundaries.get(kind, 0) + 1
        if self._on_boundary is not None:
            self._on_boundary(kind)

    def outp(self, port: int, value: int, width: int, cost: int) -> None:
        p = port & 0xFFFF
        if p in _CGA_TANDY_PORTS:          # write-only video register: record, no memory effect
            self.video_ports[p] = value & 0xFF
            return
        super().outp(port, value, width, cost)    # everything else fails loud

    def inp(self, port: int, width: int, cost: int) -> int:
        p = port & 0xFFFF
        if p == _CGA_STATUS:               # retrace poll: toggle so a wait-loop always progresses
            self._retrace ^= 0x09          # bit0 (display enable) + bit3 (vertical retrace)
            return self._retrace
        return super().inp(port, width, cost)     # everything else fails loud

    def intr(self, num: int, regs: dict, cost: int) -> dict:
        if (num & 0xFF) == 0x10:
            ah = (regs.get("ax", 0) >> 8) & 0xFF
            if ah in _INT10_NOOP_AH:       # dos_re int10 no-op: registers + memory unchanged
                out = {r: regs.get(r, 0) & 0xFFFF for r in _INT_REGS}
                out["flags"] = regs.get("_flags", 0) & 0xFFFF
                out["halted"] = False
                return out
            raise CpuStandaloneWitness(
                f"INT 10h AH={ah:02X}h not yet ported to OverkillPlatform (front-end frontier) -- "
                f"port it byte-faithfully against the dos_re int10 oracle before running this path")
        return super().intr(num, regs, cost)      # every other INT fails loud




#: Where the OVERKILL asset container and the static DGROUP bundle live (original-game bytes; never
#: packaged). A host that keeps them elsewhere overrides these before the first level load.
CONTAINER = ROOT / "assets" / "OVERKILL"
BUNDLE = ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"


def level_assets_for(planet: int, _cache: dict = {}):
    """The per-planet files ``advance_gameplay_frame_97b2`` reads on level load / death re-init /
    game-over / advance -- a HOST INPUT (the frame never emulates INT 21h). Decoded from the asset
    container via the pure ``asset_codecs`` package and cached per planet. Carrier-free."""
    if planet not in _cache:
        from overkill.asset_codecs.level_assets import (decode_level_blocks, decode_level_graphics,
                                                        decode_level_tile_map)
        from overkill.asset_codecs.native_level import (_read_class_override_pairs,
                                                        build_level_class_table)
        from overkill.native_frame import LevelAssets
        container = CONTAINER.read_bytes()
        exe = BUNDLE.read_bytes()
        _cache[planet] = LevelAssets(
            map_bytes=bytes(decode_level_tile_map(container, planet)),
            class_table=bytes(build_level_class_table(_read_class_override_pairs(exe, planet))),
            blocks=bytes(decode_level_blocks(container, planet)),
            graphics=bytes(decode_level_graphics(container, planet)),
        )
    return _cache[planet]


def assets_available() -> bool:
    """Whether the host data needed by :func:`level_assets_for` is present (both are original-game
    bytes, never committed) -- lets a caller SKIP asset-dependent paths with a clear message."""
    return CONTAINER.is_file() and BUNDLE.is_file()
