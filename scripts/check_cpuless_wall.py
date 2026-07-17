"""DYNAMIC CPUless-wall check: arm the import guard, exercise BOTH runtime layers of the unified
game -- the MANUAL gameplay port and the GENERATED corpus -- and assert NO CPU carrier was imported.

The guard is a global side effect (it replaces ``builtins.__import__``), so this runs as its own
process: ``tests/test_cpuless_wall.py`` and any release check spawn it. Exit 0 = the wall holds; a
nonzero exit + message names the breach. Mirrors lemmings_port's scripts/check_cpuless_runtime.py.

The wall is what makes "CPUless" a PROVEN property rather than a claim: neither the readable gameplay
override (native_frame + its domain/systems/views closure) nor the generated corpus may reach the
interpreter, the VMless graph, the VM runtime, or the CPU-ABI adapters.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dos_re"))

from overkill.cpuless_host import (FORBIDDEN_IMPORTS, install_import_guard,  # noqa: E402
                                   run_recovered)
from overkill.recovered.adapters.flat_memory import MutFlatMemory  # noqa: E402


def _carrier_present() -> "list[str]":
    return sorted(m for m in sys.modules
                  for f in FORBIDDEN_IMPORTS if m == f or m.startswith(f + "."))


def _breach(where: str) -> int:
    print(f"CPULESS WALL BREACHED ({where}): carrier modules loaded:", _carrier_present())
    return 1


def main() -> int:
    import glob

    install_import_guard()          # arm the wall; everything below runs under it

    # (1) the MANUAL gameplay layer must import carrier-free under the wall.
    from overkill.native_frame import advance_gameplay_frame_97b2

    # (2) the GENERATED corpus must RUN carrier-free under the wall.
    mem = MutFlatMemory(bytes(0x100000))
    out = run_recovered("1010:5F61", mem, ds=0x25CC, es=0x25CC, ss=0x2000, sp=0x1000)
    assert set(out) >= {"ax", "bx"}, f"unexpected outputs {sorted(out)}"
    if _carrier_present():
        return _breach("import + generated run")

    # (3) the manual gameplay frame must EXECUTE carrier-free -- run real frames over a demo image
    #     with the carrier-free host asset loader. Artifact-gated (original-game bytes, never committed).
    from overkill.cpuless_runtime import assets_available, level_assets_for
    snaps = sorted(glob.glob(str(ROOT / "artifacts" / "demos" / "*" / "snapshot" / "memory_1mb.bin")))
    if snaps and assets_available():
        img = MutFlatMemory(Path(snaps[0]).read_bytes())
        for _ in range(5):
            advance_gameplay_frame_97b2(img, isr_ticks=2, level_assets=level_assets_for, menu_pick=0)
        if _carrier_present():
            return _breach("gameplay execution")
        print("CPULESS WALL HOLDS: manual gameplay EXECUTED (5 frames) + generated corpus, carrier-free")
    else:
        print("CPULESS WALL HOLDS: manual gameplay + generated corpus imported/ran carrier-free "
              "(gameplay-execution stage SKIPPED -- no demo image / asset container present)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
