"""play_cpuless.py -- the standalone CPUless OVERKILL runner.

Runs the UNIFIED game with the CPUless wall ARMED before anything else loads: the manual gameplay port
(``native_frame``, the coarse override at the frame boundary -- ADR-2) and the generated corpus compose
over the one DGROUP image, and NO CPU carrier (the interpreter, the VM runtime, the VMless installer,
the CPU-ABI adapters) may be imported. A breach raises ``CpuStandaloneWitness`` instead of silently
falling back to the VM, so this runner's ENTIRE import + run closure is proven carrier-free every launch
(scripts/check_cpuless_wall.py is the CI gate for the same claim on paths a given run doesn't take).

Today it plays GAMEPLAY from a snapshot/bundle image; the generated front-end (boot -> title/menu ->
level load) fills in as the video platform shim and the tail-dispatch capability land -- see
docs/overkill/campaigns/cpuless_app.md. It is a thin wall-armed entry over play_native (which is already
carrier-free): the point of a separate runner is that the wall is ARMED, making "CPUless" enforced here,
not merely true by habit.

Usage:
    python scripts/play_cpuless.py                 # play (live window), gameplay from the default bundle
    python scripts/play_cpuless.py --snapshot DIR  # start from a captured image (it IS the state)
    python scripts/play_cpuless.py --frames N --no-sound   # headless self-test: N frames then exit
    # ...all other play_native.py arguments pass straight through.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dos_re"))

from overkill.cpuless_host import install_import_guard  # noqa: E402


def main(argv=None) -> int:
    # Arm the CPUless wall FIRST, so play_native and everything it pulls import under it.
    install_import_guard()
    import scripts.play_native as play_native  # imported under the wall (proven carrier-free)
    return play_native.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
