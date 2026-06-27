"""Probe: trace the per-object draw hierarchy for one frame.

To build the sprite-draw extractor we need to know how a table object maps to
compositor blocks, and where the object's identity (sprite id / screen_di) is
readable. This wraps the candidate per-object draw dispatchers (5A92 present,
5AC8 draw, 75A6/768E/7746 layer) and the masked compositors (2E6E/2F81/2FB6),
recording an ordered trace for one even (object-scan) frame: at the high-level
calls it reads the object record at SS:BP (sprite id +08, screen_di +0C); at the
compositors it reads the destination DI. The interleaving reveals the grouping.

Usage:
    python -m overkill.probes.witness_draw_structure <demo_dir> [frame]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXE = ROOT / "assets" / "OVERKILL"
ASSETS = ROOT / "assets"
CS = 0x1010

HIGH = {0x5A92: "5A92.present", 0x5AC8: "5AC8.draw",
        0x75A6: "75A6.layer2", 0x768E: "768E.layer1", 0x7746: "7746.compact",
        0x35CC: "35CC.objblock", 0x356C: "356C.objsplit", 0x3657: "3657.objtiny",
        0x5A6C: "5A6C.cellblit"}
COMP = {0x2E6E: "2E6E(8w)", 0x2F81: "2F81(4w)", 0x2FB6: "2FB6(2w)",
        0x2F40: "2F40(4w-OR)", 0x2ECB: "2ECB(8w-OR)"}


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    demo_dir = Path(argv[0])
    target = int(argv[1]) if len(argv) > 1 else 4

    from dos_re.input_demo import InputDemoPlayback
    import overkill.hooks  # noqa: F401
    from dos_re.hooks import registry
    from overkill.frame_verify import FrameVerifyConfig, run_frame_verifier

    demo = InputDemoPlayback.load(demo_dir)
    snapshot = demo.snapshot_path()
    video = str(demo.manifest.get("metadata", {}).get("video", "tandy"))

    st = {"frame": 0}
    trace = []
    wrapped = []

    def wrap(ip, name, is_high):
        try:
            rep = registry.replacements[(CS, ip)]
        except KeyError:
            return
        orig = rep.handler

        def hook(cpu):
            if st["frame"] == target:
                if is_high:
                    ss, bp = cpu.s.ss & 0xFFFF, cpu.s.bp & 0xFFFF
                    spr = cpu.mem.rw(ss, (bp + 0x08) & 0xFFFF)
                    di = cpu.mem.rw(ss, (bp + 0x0C) & 0xFFFF)
                    trace.append(f"{name} bp={bp:04X} sprite={spr:04X} di0C={di:04X}")
                else:
                    trace.append(f"    {name} di={cpu.s.di & 0xFFFF:04X}")
            orig(cpu)
        object.__setattr__(rep, "handler", hook)
        wrapped.append((rep, orig))

    for ip, name in HIGH.items():
        wrap(ip, name, True)
    for ip, name in COMP.items():
        wrap(ip, name, False)

    boundary = {"n": 0}

    def pump_inputs(ref_rt, cand_rt):
        demo.apply_to_runtimes(boundary["n"], (ref_rt, cand_rt))
        boundary["n"] += 1

    def publish_candidate(rt, sample):
        st["frame"] += 1

    config = FrameVerifyConfig(video=video, source="candidate", max_frames=target + 2,
                               semantic_state_check=False, stop_on_diff=False, log_every=0)
    try:
        run_frame_verifier(exe=EXE, assets=ASSETS, snapshot=str(snapshot), command_tail=b"",
                           config=config, pump_inputs=pump_inputs, publish_candidate=publish_candidate)
    finally:
        for rep, orig in wrapped:
            object.__setattr__(rep, "handler", orig)

    print(f"demo {demo_dir.name}  frame {target}  trace ({len(trace)} events):")
    for line in trace:
        print(" ", line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
