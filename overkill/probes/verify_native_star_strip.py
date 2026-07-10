"""Driven-oracle gate for the 4CED star pass's INPUT: the derived tile+sprite strip.

``1010:4CED`` (the star draw, called at ``A876`` right after A846's sprite loop) decides where a
star may be plotted with ``cmp es:[bx],0`` -- ``es = CS:[9598]``, the tile STRIP.  The strip is not
in DGROUP, so the lockstep cache cannot carry it -- but this probe MEASURED what it holds there:
**tiles ONLY**.  At 4CED entry the strip is byte-identical to ``compose_tile_window`` alone: the
sprites are not in it yet (A846's per-object loop erases them; A90C's redraws them) and the previous
frame's stars are already gone.  Occupancy is therefore pure terrain -- a pure function of DGROUP:

    strip_window = pack(compose_tile_window(plane, [2350], [234E], ...))

The probe traps the ref (pure-VM) side at every 4CED entry and checks TWO things:

1. the derived strip window vs the VM's real strip, byte for byte (192 x 104);
2. the star DRAW LIST the pass produces -- computed from that window at entry N, compared against
   the VM's own ``DS:C7B1`` list read at entry N+1 (4CED is its only writer, so it still stands).

Both byte-exact is the precondition for lifting the star pass into ``native_frame``'s present half
(the list at DS:C7B1.. is implicated in ~4831 of the lockstep gate's diverging frames).

Usage:
    python -m overkill.probes.verify_native_star_strip [demo_name] [max_frames] [sample_stride]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from overkill.probes._harness import load_demo, run_ref_step_probe  # noqa: E402

CS = 0x1010
DS = 0x25CC
STAR_PASS = 0x4CED
STRIDE = 0x68          # 104 bytes / scanline (208 px at 2 px/byte)
WINDOW_ROWS = 192
WINDOW_TOP_Y = 4       # compose_tile_window puts the terrain window at screen y = 4
DEFAULT_DEMO = "demo_play_tandy_L3_full_20260617_202520"


def derive_strip_window(image) -> np.ndarray:
    """The (192, 104) strip bytes the star pass reads: the terrain window, and nothing else."""
    from overkill.native_video.tile_row import BANK2_ROW_BASE, compose_tile_window

    row_base = image.rw(DS, 0x2350)
    mem_np = np.frombuffer(bytes(image.data), dtype=np.uint8)
    plane_seg = image.rw(CS, 0x9592)
    plane = mem_np[plane_seg * 16: plane_seg * 16 + 0x10000]
    table = [image.rw(CS, (0x8D92 + 2 * k) & 0xFFFF) for k in range(0x100)]
    bank_ptr = 0x959C if row_base >= BANK2_ROW_BASE else 0x959A
    bank = image.rw(CS, bank_ptr)
    graphics = mem_np[bank * 16: bank * 16 + 0x10000]

    frame = np.zeros((200, 320), dtype=np.uint8)
    compose_tile_window(frame, plane, row_base, table, graphics, phase_234e=image.rw(DS, 0x234E))

    band = frame[WINDOW_TOP_Y:WINDOW_TOP_Y + WINDOW_ROWS, :STRIDE * 2].reshape(WINDOW_ROWS, STRIDE, 2)
    return ((band[:, :, 0] << 4) | band[:, :, 1]).astype(np.uint8)


#: the C6C1 star ring: three parallax layers of 20 / 10 / 10 entries, 6 bytes each
STAR_LAYERS = (0x14, 0x0A, 0x0A)
STAR_RING = 0xC6C1
STAR_LIST = 0xC7B1


def derive_star_list(image, window: np.ndarray) -> "list[int]":
    """The DS:C7B1 draw list 4CED builds: per ring star, plot into an UNOCCUPIED strip byte."""
    scroll = image.rw(DS, 0x234C)
    out: list[int] = []
    si = STAR_RING
    for count in STAR_LAYERS:
        for _ in range(count):
            tick = image.rw(DS, si)
            xoff = image.rw(DS, (si + 2) & 0xFFFF)
            px = image.rb(DS, (si + 4) & 0xFFFF)
            si = (si + 6) & 0xFFFF
            bx = (tick * STRIDE + scroll + xoff) & 0xFFFF
            t, c = divmod(bx - scroll, STRIDE)
            if not (0 <= t < WINDOW_ROWS and 0 <= c < STRIDE):
                continue
            if window[t, c]:
                continue                      # occupied -> the star is skipped (the 4D15 rule)
            window[t, c] = px                 # 4D59: plot it (so later stars see it)
            out.append(bx)                    # 4D5C: append to the list
    return out


def vm_star_list(cpu) -> "list[int]":
    out = []
    si = STAR_LIST
    for _ in range(0x28):
        v = cpu.mem.rw(DS, si)
        si += 2
        if v == 0xFFFF:
            break
        out.append(v)
    return out


def vm_strip_window(cpu) -> np.ndarray:
    """The VM's real strip window at this instant (the star pass's actual input)."""
    seg = cpu.mem.rw(CS, 0x9598)
    scroll = cpu.mem.rw(DS, 0x234C)
    assert scroll % STRIDE == 0, f"[234C]={scroll:04X} is not row-aligned"
    row0 = scroll // STRIDE
    base = seg * 16 + row0 * STRIDE
    raw = np.frombuffer(bytes(cpu.mem.data[base: base + WINDOW_ROWS * STRIDE]), dtype=np.uint8)
    return raw.reshape(WINDOW_ROWS, STRIDE)


def main(argv) -> int:
    from overkill.recovered.adapters.flat_memory import MutFlatMemory

    demo = load_demo(argv[0] if argv else None, DEFAULT_DEMO)
    max_frames = int(argv[1]) if len(argv) > 1 else 400
    stride = int(argv[2]) if len(argv) > 2 else 25

    res = {"hits": 0, "strip_checked": 0, "strip_bad": 0,
           "list_checked": 0, "list_bad": 0, "lines": []}
    pending: dict = {}

    def on_ref_step(cpu) -> None:
        res["hits"] += 1
        # The list this pass WRITES is only observable afterwards: 4CED is its only writer, so the
        # list standing at the NEXT entry is exactly what the previous entry produced.
        if "list" in pending:
            want = pending.pop("list")
            n = pending.pop("n")
            got = vm_star_list(cpu)
            res["list_checked"] += 1
            if want != got:
                res["list_bad"] += 1
                if len(res["lines"]) < 8:
                    first = next((i for i, (a, b) in enumerate(zip(want, got)) if a != b), None)
                    res["lines"].append(
                        f"  list @entry#{n}: native {len(want)} stars vs vm {len(got)}; "
                        f"first diff idx {first}")
        if (res["hits"] - 1) % stride:
            return
        image = MutFlatMemory(bytes(cpu.mem.data))
        model = derive_strip_window(image)
        vm = vm_strip_window(cpu)
        diff = int((vm != model).sum())
        res["strip_checked"] += 1
        if diff:
            res["strip_bad"] += 1
            if len(res["lines"]) < 8:
                where = np.argwhere(vm != model)[:4]
                cells = ",".join(f"(y={t},c={c}) vm={vm[t, c]:02X}/nat={model[t, c]:02X}"
                                 for t, c in where)
                res["lines"].append(f"  strip @entry#{res['hits']}: {diff} bytes -- {cells}")
        else:
            pending["list"] = derive_star_list(image, model.copy())
            pending["n"] = res["hits"]

    run_ref_step_probe(demo, max_frames, on_ref_step, trap=frozenset({(CS, STAR_PASS)}))

    print(f"4CED entries seen: {res['hits']}  strip sampled: {res['strip_checked']} "
          f"(bad {res['strip_bad']})  list checked: {res['list_checked']} (bad {res['list_bad']})")
    for line in res["lines"]:
        print(line)
    ok = (res["strip_checked"] > 0 and res["strip_bad"] == 0
          and res["list_checked"] > 0 and res["list_bad"] == 0)
    print("RESULT:", "PASS -- the derived terrain strip AND the star draw list are byte-exact vs "
          "the VM at every sampled 4CED entry" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
