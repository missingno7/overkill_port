"""Driven-oracle gate for ``1010:77F6`` -- the HUD energy (fuel) bar.

The owner reported the meter drawing solid, where the original has GAPS between its bars.

Why the existing panel gate could not see it: ``verify_native_hud_panel`` compares a freshly composed
panel against the VM's video page -- but the original only REDRAWS the panel when ``981F`` runs, so on
most frames that page is a stale composition from some earlier moment.  A fresh-vs-stale comparison is
meaningless, and the old gate hid that by only ever checking frame 0.

This gate instead drives the ORIGINAL's own bar routine: trap ``77F6`` entry, snapshot the page and
``[A97A]``, run the VM to the routine's own return address (read off the stack), and diff the VM's
resulting bar COLUMN against what ``compose_energy_bar_77f6`` writes over the same pre-page.  Only the
column the routine owns (cell-col 0x1D, 4 bytes per scanline) is compared -- everything else on the
page belongs to other layers.

Usage:
    pypy -m overkill.probes.verify_native_energy_bar_77f6 [demo] [max_calls]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from overkill.native_video.hud_panel import (  # noqa: E402
    ENERGY_BAR_X_CELL, compose_energy_bar_77f6,
)
from overkill.probes._harness import load_demo, run_ref_step_probe  # noqa: E402

CS = 0x1010
DS = 0x25CC
BAR_ENTRY = 0x77F6
PAGE_SEG_CELL = 0x95A4          # CS:[95A4] -- the page 77F6 draws into
DEFAULT_DEMO = "demo_play_tandy_L2_full_20260617_180221"
VERIFIER_FRAMES = 120
DEFAULT_MAX_CALLS = 12
SCANLINES = 200


def _row_base(y: int) -> int:
    return ((y & 3) * 0x2000 + (y >> 2) * 0xA0) & 0xFFFF


def _bar_column(page: np.ndarray) -> np.ndarray:
    """The 4 bytes 77F6 owns on each scanline, as a (200, 4) array."""
    out = np.empty((SCANLINES, 4), dtype=np.uint8)
    for y in range(SCANLINES):
        b = (_row_base(y) + ENERGY_BAR_X_CELL * 4) & 0xFFFF
        out[y] = page[b:b + 4]
    return out


class _Done(Exception):
    pass


def main(argv) -> int:
    demo = load_demo(argv[0] if argv and argv[0] else None, DEFAULT_DEMO)
    max_calls = int(argv[1]) if len(argv) > 1 else DEFAULT_MAX_CALLS

    st: dict = {"pending": None, "installed": False}
    results: list = []

    def _capture(cpu) -> None:
        """Watch every instruction for 77F6's entry and its own return address.

        Installed ONCE, permanently.  An earlier version restored the plain ``step`` after each call,
        which silently removed the harness's trap observer -- so only the FIRST call was ever seen.
        """
        s = cpu.s
        cs, ip = s.cs & 0xFFFF, s.ip & 0xFFFF
        if cs != CS:
            return
        if st["pending"] is None:
            if ip != BAR_ENTRY:
                return
            seg = cpu.mem.rw(CS, PAGE_SEG_CELL)
            ret = cpu.mem.rw(s.ss & 0xFFFF, s.sp & 0xFFFF)   # the routine's own return address
            page = np.frombuffer(bytes(cpu.mem.data[seg * 16: seg * 16 + 0x10000]), dtype=np.uint8)
            st["pending"] = (ret, cpu.mem.rw(DS, 0xA97A), seg, page.copy())
        elif ip == st["pending"][0]:
            _ret, a97a, seg_, pre_page = st["pending"]
            post = np.frombuffer(bytes(cpu.mem.data[seg_ * 16: seg_ * 16 + 0x10000]), dtype=np.uint8)
            results.append((a97a, pre_page, post.copy()))
            st["pending"] = None
            if len(results) >= max_calls:
                raise _Done

    def on_step(cpu) -> None:
        if st["installed"]:
            return
        st["installed"] = True
        orig = cpu.__class__.step

        def step(_c=cpu):
            _capture(_c)
            return orig(_c)

        cpu.step = step

    try:
        run_ref_step_probe(demo, VERIFIER_FRAMES, on_step, trap=frozenset({(CS, BAR_ENTRY)}))
    except _Done:
        pass

    if not results:
        print("RESULT: FAIL -- 77F6 never ran in this demo window")
        return 1

    bad = 0
    for i, (a97a, pre_page, vm_post) in enumerate(results, start=1):
        native = pre_page.copy()
        compose_energy_bar_77f6(native, a97a)
        nat_col, vm_col = _bar_column(native), _bar_column(vm_post)
        diff_rows = [y for y in range(SCANLINES) if not np.array_equal(nat_col[y], vm_col[y])]
        vm_filled = [y for y in range(SCANLINES) if vm_col[y].any()]
        print(f"  call #{i}  [A97A]={a97a:#06x} (units {a97a >> 1:2d})  "
              f"vm lit scanlines {len(vm_filled)}  diverging rows {len(diff_rows)}")
        if diff_rows:
            bad += 1
            if i == 1:
                print(f"      vm lit rows: {vm_filled[:14]}{' ...' if len(vm_filled) > 14 else ''}")
                for y in diff_rows[:6]:
                    print(f"      y={y:3d}  vm={vm_col[y].tolist()}  nat={nat_col[y].tolist()}")

    print(f"\n77F6 calls verified: {len(results)}  diverging: {bad}")
    ok = bad == 0
    print("RESULT:", "PASS -- the native energy bar reproduces 77F6's column exactly"
          if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
