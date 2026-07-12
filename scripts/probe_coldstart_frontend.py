"""GROUND TRUTH: capture the cold-start demo's FRONT-END timeline from the pure reference VM.

play_native's front end (intro / menu / attract) is currently host-loop code that GUESSES the flow --
it is verified against nothing, so it drifts from the game.  This probe records what the ORIGINAL
actually does at every present-frame boundary of a cold-start demo: the attract scene id [BE06], its
countdown [BE08], the front-end START flag [98C3], and the CPU location (which distinguishes the
front-end loop from the 97B2 gameplay frame).  It is the reference the native front-end must reproduce
byte-for-byte -- the data that replaces guessing.

Usage:
    python scripts/probe_coldstart_frontend.py <demo_name> [--frames N]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dos_re"))

import overkill.frame_verify as fv  # noqa: E402
from overkill.frame_verify import FrameVerifyConfig, run_frame_verifier  # noqa: E402
from overkill.probes._harness import load_demo  # noqa: E402
from overkill.input_waits import pump_demo_frame  # noqa: E402
from dos_re.frontend_timeline import FrameRecord, collapse, format_sequence  # noqa: E402


def classify_screen(row) -> str:
    """A COARSE logical screen id for one VM present-frame (the `dos_re.frontend_timeline` witness): the
    cold-boot phase, from the CS:IP + attract scene [BE06].  A proxy for the framebuffer fingerprint --
    enough to prove the SCREEN ORDER (which screen, in what order) the native front end must reproduce."""
    cs, ip = row["cs_ip"].split(":")
    ipv = int(ip, 16)
    if cs != "1010":
        return "boot"
    if 0x9740 <= ipv <= 0x9C50:            # the 97B2 top .. 9B2E boundary gameplay frame
        return "gameplay"
    if row["scene_BE06"]:
        return f"attract:scene-{row['scene_BE06']:#04x}"
    if 0xCC00 <= ipv <= 0xCEFF:            # CC04/CC4F/CD68/CE.. -- the attract initial display
        return "attract:initial"
    if 0x5500 <= ipv <= 0x5C50:            # 558B menu / 5C04 compose
        return "menu"
    return f"front-end@{ip[:2]}xx"


def capture(demo_name: str, max_frames: int, dump_at: "int | None" = None):
    """Replay the cold-start demo through the ref VM; per present-frame record the front-end state."""
    demo = load_demo(demo_name, demo_name)
    meta = demo.manifest.get("metadata", {})
    video = str(meta.get("video", "tandy"))
    is_cold = demo.is_cold_start
    tail = str(meta.get("command_tail", "")) if is_cold else b""

    rows: "list[dict]" = []
    cur = {"f": 0, "ref": None, "dump_at": dump_at, "dump": None}
    orig_load = fv._load_runtime
    sides = iter(("ref", "cand"))

    def patched(exe, assets, snap, t):
        rt = orig_load(exe, assets, snap, t)
        if next(sides) == "ref":
            cur["ref"] = rt
        return rt

    fv._load_runtime = patched

    def pump(ref, cand):
        rt = cur["ref"]
        if rt is not None:
            ds = rt.cpu.s.ds & 0xFFFF
            def rb(o):
                return rt.cpu.mem.rb(ds, o & 0xFFFF)
            if cur["f"] == cur.get("dump_at"):
                cs = rt.cpu.s.cs & 0xFFFF
                bd81 = bytes(rt.cpu.mem.rb(ds, (0xBD81 + i) & 0xFFFF) for i in range(24))
                bank = rt.cpu.mem.rw(cs, 0x95B8)
                cells = {}
                for cid in (0x01, 0x15, 0x16, 0x02, 0x40):
                    off = rt.cpu.mem.rw(cs, (0x0BE4 + cid * 2) & 0xFFFF)
                    hdr = bytes(rt.cpu.mem.rb(bank, (off + i) & 0xFFFF) for i in range(6))
                    cells[f"{cid:#04x}"] = f"off={off:#06x} hdr={hdr.hex()}"
                cur["dump"] = {
                    "BD81": bd81.hex(),
                    "95B8_cellbank": bank,
                    "95BC_videomode": rt.cpu.mem.rw(cs, 0x95BC),
                    "BD9A": rt.cpu.mem.rw(ds, 0xBD9A), "BDA0": rt.cpu.mem.rw(ds, 0xBDA0),
                    **{f"cell{k}": v for k, v in cells.items()},
                }
            rows.append({
                "f": cur["f"],
                "cs_ip": f"{rt.cpu.s.cs:04X}:{rt.cpu.s.ip:04X}",
                "ds": f"{ds:04X}",
                "scene_BE06": rb(0xBE06),
                "count_BE08": rb(0xBE08),
                "start_98C3": rb(0x98C3),
            })
        pump_demo_frame(demo, cur["f"], (ref, cand), ref.cpu)
        cur["f"] += 1

    budget = {"frame_budget": 120_000_000} if is_cold else {}
    cfg = FrameVerifyConfig(video=video, source="candidate", max_frames=max_frames,
                            semantic_state_check=False, stop_on_diff=False, log_every=0, **budget)
    try:
        run_frame_verifier(exe=ROOT / "assets" / "OVERKILL", assets=ROOT / "assets",
                           snapshot=(None if is_cold else demo.snapshot_path()),
                           command_tail=tail, config=cfg, pump_inputs=pump)
    finally:
        fv._load_runtime = orig_load
    return rows, cur.get("dump")


def _phase(row) -> str:
    cs = row["cs_ip"].split(":")[0]
    return "gameplay(97B2)" if cs == "1010" and 0x9000 <= int(row["cs_ip"].split(":")[1], 16) <= 0x9FFF \
        else "front-end"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("demo")
    ap.add_argument("--frames", type=int, default=400)
    ap.add_argument("--raw", type=int, default=0, metavar="START",
                    help="print EVERY frame in [START, START+40) raw (to see the exact countdown)")
    ap.add_argument("--dump-at", type=int, default=None, metavar="F",
                    help="dump the live BD81 attract-display descriptors + cell bank at frame F")
    ap.add_argument("--sequence", action="store_true",
                    help="emit the coarse SCREEN sequence via dos_re.frontend_timeline (the front-end "
                         "lockstep witness -- the ground truth the native front end must reproduce)")
    args = ap.parse_args(argv)
    rows, dump = capture(args.demo, args.frames, dump_at=args.dump_at)
    if dump is not None:
        print(f"live attract-display state at frame {args.dump_at}:")
        for k, v in dump.items():
            print(f"  {k} = {v if isinstance(v, str) else hex(v)}")
        return 0
    if args.sequence:
        records = [FrameRecord(r["f"], classify_screen(r), "") for r in rows]
        runs = collapse(records)
        print(f"cold-boot SCREEN sequence ({len(records)} frames -> {len(runs)} screens):")
        print("  " + format_sequence(runs))
        return 0
    if args.raw:
        print(f"raw frames {args.raw}..{args.raw + 40}:")
        for r in rows:
            if args.raw <= r["f"] < args.raw + 40:
                print(f"  f={r['f']:5d}  scene={r['scene_BE06']:#04x}  count={r['count_BE08']:3d}  @ {r['cs_ip']}")
        return 0
    # compress into runs of (scene, start-flag) so the timeline is readable
    print(f"captured {len(rows)} present-frames")
    prev = None
    for r in rows:
        key = (r["scene_BE06"], r["start_98C3"])
        if key != prev:
            print(f"  f={r['f']:5d}  scene[BE06]={r['scene_BE06']:#04x}  count[BE08]={r['count_BE08']:3d}  "
                  f"start[98C3]={r['start_98C3']:#04x}  @ {r['cs_ip']}")
            prev = key
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
