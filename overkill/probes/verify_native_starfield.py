"""Produced-vs-VM gate for the recovered starfield move (overkill.recovered.systems.starfield).

Step-observes the live star stream (``DS:0xC6C1``) + the layer counters (``DS:0xC812/14/16``) + the gate
(``DS:0xA95A``) at every present (``1010:5BDC``), and asserts that the pure ``advance_starfield`` exactly
reproduces the VM's next-frame stream + counters -- the recovered parallax move, byte-exact.  Also checks
the plot offset model (``row*0x68 + cursor + dx``) against the live working list (``DS:0xC7B1``).

Usage:
    python -m overkill.probes.verify_native_starfield <demo_dir> [frames]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXE = ROOT / "assets" / "OVERKILL"
ASSETS = ROOT / "assets"
CS = 0x1010


def _read_state(cpu):
    from overkill.recovered.domain.starfield import STAR_COUNT, Star, StarfieldState
    ds = cpu.s.ds & 0xFFFF
    stars = tuple(
        Star(cpu.mem.rw(ds, (0xC6C1 + i * 6) & 0xFFFF),
             cpu.mem.rw(ds, (0xC6C3 + i * 6) & 0xFFFF),
             cpu.mem.rw(ds, (0xC6C5 + i * 6) & 0xFFFF))
        for i in range(STAR_COUNT)
    )
    counters = (cpu.mem.rw(ds, 0xC812), cpu.mem.rw(ds, 0xC814), cpu.mem.rw(ds, 0xC816))
    enabled = cpu.mem.rw(ds, 0xA95A) != 0xFFFF
    cursor = cpu.mem.rw(ds, 0x234C)
    work = []
    for i in range(64):
        w = cpu.mem.rw(ds, (0xC7B1 + i * 2) & 0xFFFF)
        if w == 0xFFFF:
            break
        work.append(w)
    return StarfieldState(stars, counters, enabled), cursor, work


def main(argv) -> int:
    if not argv:
        print(__doc__)
        return 2
    # Accept either a full demo path or a bare demo name (resolved under artifacts/demos, like the
    # other producer probes + the verify_native_producers gate, which pass a bare name).
    demo_dir = Path(argv[0])
    if not demo_dir.is_dir():
        demo_dir = ROOT / "artifacts" / "demos" / argv[0]
    frames = int(argv[1]) if len(argv) > 1 else 400

    from dos_re.input_demo import InputDemoPlayback
    import overkill.hooks  # noqa: F401
    from dos_re.hooks import registry
    from overkill.frame_verify import FrameVerifyConfig, run_frame_verifier
    from overkill.recovered.systems.starfield import advance_starfield, star_page_offset

    demo = InputDemoPlayback.load(demo_dir)
    snapshot = demo.snapshot_path()
    video = str(demo.manifest.get("metadata", {}).get("video", "tandy"))

    agg = {"calls": 0, "ok": 0, "fail": 0, "off_calls": 0, "off_ok": 0, "prev": None}
    rep = registry.replacements[(CS, 0x5BDC)]
    orig = rep.handler

    def hook(cpu):
        state, cursor, work = _read_state(cpu)
        prev = agg["prev"]
        if prev is not None:
            pstate, _pcur = prev
            pred = advance_starfield(pstate)
            agg["calls"] += 1
            if pred.stars == state.stars and pred.layer_counters == state.layer_counters:
                agg["ok"] += 1
            else:
                agg["fail"] += 1
        # plot-offset model: every recorded working-list offset must equal some star's offset.
        if work:
            offs = {star_page_offset(s, cursor) for s in state.stars}
            agg["off_calls"] += 1
            if set(work) <= offs:
                agg["off_ok"] += 1
        agg["prev"] = (state, cursor)
        orig(cpu)

    object.__setattr__(rep, "handler", hook)
    boundary = {"n": 0}

    def pump_inputs(ref_rt, cand_rt):
        demo.apply_to_runtimes(boundary["n"], (ref_rt, cand_rt))
        boundary["n"] += 1

    config = FrameVerifyConfig(video=video, source="candidate", max_frames=frames,
                               semantic_state_check=False, stop_on_diff=False, log_every=0)
    try:
        run_frame_verifier(exe=EXE, assets=ASSETS, snapshot=str(snapshot), command_tail=b"",
                           config=config, pump_inputs=pump_inputs)
    finally:
        object.__setattr__(rep, "handler", orig)

    print(f"demo {demo_dir.name}  move: calls={agg['calls']} ok={agg['ok']} fail={agg['fail']}  "
          f"plot-offset: {agg['off_ok']}/{agg['off_calls']}")
    return 0 if agg["fail"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
