"""Probe: find what writes the bulk of the source page [9598] (the bg-draw).

The background is composed into [9598] before the present (5BDC -> 3354 is just
the blit). To locate the bg-draw routine, install a memory write-watcher for one
full gameplay frame and histogram, by writing IP, the word/byte writes that land
in the [9598] segment. The dominant IPs that are NOT the known sprite compositors
(2E6E/2F81/2FB6) are the background draw to recover.

Usage:
    python -m overkill.probes.witness_page_writers <demo_dir> [frame]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXE = ROOT / "assets" / "OVERKILL"
ASSETS = ROOT / "assets"
CS = 0x1010
P_SOURCE = 0x9598
SPRITE_COMPOSITORS = {0x2E6E, 0x2F81, 0x2FB6, 0x2F40, 0x2ECB}


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    demo_dir = Path(argv[0])
    target = int(argv[1]) if len(argv) > 1 else 6

    from dos_re.input_demo import InputDemoPlayback
    import overkill.hooks  # noqa: F401
    from dos_re.hooks import registry
    from overkill.frame_verify import FrameVerifyConfig, run_frame_verifier

    demo = InputDemoPlayback.load(demo_dir)
    snapshot = demo.snapshot_path()
    video = str(demo.manifest.get("metadata", {}).get("video", "tandy"))

    st = {"frame": 0, "active": False, "watcher": None, "cpu": None, "base": 0}
    hist: dict[int, int] = {}

    a846 = registry.replacements[(CS, 0xA846)]
    a846_orig = a846.handler

    def a846_hook(cpu):
        if st["frame"] == target and not st["active"]:
            base = (cpu.mem.rw(CS, P_SOURCE) << 4) & 0xFFFFF
            st["base"], st["cpu"] = base, cpu

            def watcher(addr, old, new, _b=base, _c=cpu):
                if _b <= addr < _b + 0x10000:
                    hist[_c.s.ip & 0xFFFF] = hist.get(_c.s.ip & 0xFFFF, 0) + 1
            st["watcher"] = watcher
            cpu.mem.write_watchers.append(watcher)
            st["active"] = True
        elif st["frame"] > target and st["active"]:
            _stop(cpu)
        a846_orig(cpu)

    def _stop(cpu):
        try:
            cpu.mem.write_watchers.remove(st["watcher"])
        except ValueError:
            pass
        st["active"] = False

    object.__setattr__(a846, "handler", a846_hook)

    boundary = {"n": 0}

    def pump_inputs(ref_rt, cand_rt):
        demo.apply_to_runtimes(boundary["n"], (ref_rt, cand_rt))
        boundary["n"] += 1

    def publish_candidate(rt, sample):
        st["frame"] += 1

    config = FrameVerifyConfig(video=video, source="candidate", max_frames=target + 3,
                               semantic_state_check=False, stop_on_diff=False, log_every=0)
    try:
        run_frame_verifier(exe=EXE, assets=ASSETS, snapshot=str(snapshot), command_tail=b"",
                           config=config, pump_inputs=pump_inputs, publish_candidate=publish_candidate)
    finally:
        object.__setattr__(a846, "handler", a846_orig)
        if st["active"] and st["cpu"] is not None:
            _stop(st["cpu"])

    total = sum(hist.values())
    print(f"demo {demo_dir.name}  frame {target}  [9598] base={st['base']:05X}  total word/byte writes={total}")
    print("  top writers by IP (cs:1010):")
    for ip, n in sorted(hist.items(), key=lambda kv: -kv[1])[:18]:
        tag = " <- sprite compositor" if ip in SPRITE_COMPOSITORS else ""
        print(f"    {ip:04X}: {n:6d}  ({n*100//max(1,total):2d}%){tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
