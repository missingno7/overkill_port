"""Render a recorded demo's AdLib (OPL3) audio to a WAV, VM-side.

The game drives an AdLib/YM3812 music+SFX driver (the loaded module at segment 2032, register writes
through ports 388h/389h).  dos_re intercepts those port writes and exposes them via
``dos.set_adlib_callback``; this tool replays a demo through the reference VM, captures the per-frame
OPL register stream, and synthesizes it through dos_re's Nuked-OPL3 backend (``pynuked_opl3``) into a
stereo WAV -- the same register stream + synth path the live viewer's ``AdlibSpeakerSink`` uses, just
rendered offline so it can be inspected / attached.

This is the AUDIO oracle: it produces the byte-faithful reference music for a demo, which the live
play_native sound path is verified against.  (play_native's own live music runs the driver over its
VM-less image; see overkill/native_audio.)

Usage:
    python scripts/render_demo_music.py <demo_name> [--frames N] [--out PATH] [--rate HZ] [--fps HZ]
"""
from __future__ import annotations

import argparse
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dos_re"))

import overkill.frame_verify as fv  # noqa: E402
from overkill.frame_verify import FrameVerifyConfig, run_frame_verifier  # noqa: E402
from overkill.input_waits import pump_demo_frame  # noqa: E402
from overkill.probes._harness import load_demo  # noqa: E402


def capture_opl_writes(demo_name: str, max_frames: int) -> "list[list[tuple[int, int]]]":
    """Replay the demo through the ref VM; return per-frame lists of (reg, val) OPL writes."""
    demo = load_demo(demo_name, demo_name)
    meta = demo.manifest.get("metadata", {})
    video = str(meta.get("video", "tandy"))
    is_cold = demo.is_cold_start
    tail = str(meta.get("command_tail", "")) if is_cold else b""

    writes: "list[list[tuple[int, int]]]" = [[] for _ in range(max_frames + 2)]
    cur = {"f": 0}
    orig_load = fv._load_runtime
    sides = iter(("ref", "cand"))

    def patched(exe, assets, snap, t):
        rt = orig_load(exe, assets, snap, t)
        if next(sides) == "ref":
            def cb(reg, val, _w=writes, _c=cur):
                f = _c["f"]
                if f < len(_w):
                    _w[f].append((reg, val))
            rt.dos.set_adlib_callback(cb, emit_current=True)
        return rt

    fv._load_runtime = patched
    boundary = {"n": 0}

    def pump(ref, cand):
        boundary["n"], _ = pump_demo_frame(demo, boundary["n"], (ref, cand), ref.cpu)
        boundary["n"] += 1
        cur["f"] = min(cur["f"] + 1, max_frames + 1)

    budget = {"frame_budget": 120_000_000} if is_cold else {}
    cfg = FrameVerifyConfig(video=video, source="candidate", max_frames=max_frames,
                            semantic_state_check=False, stop_on_diff=False, log_every=0, **budget)
    try:
        run_frame_verifier(exe=ROOT / "assets" / "OVERKILL", assets=ROOT / "assets",
                           snapshot=(None if is_cold else demo.snapshot_path()),
                           command_tail=tail, config=cfg, pump_inputs=pump)
    finally:
        fv._load_runtime = orig_load
    return writes


def render_wav(writes, out_path: Path, rate: int, fps: int) -> float:
    """Synthesize the per-frame OPL writes through Nuked-OPL3 into a stereo WAV; return seconds."""
    from pynuked_opl3 import OPL3

    opl = OPL3(sample_rate=rate)
    n = rate // fps
    pcm = bytearray()
    for frame_writes in writes:
        for reg, val in frame_writes:
            opl.write(reg, val)
        pcm += opl.generate_stereo(n)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(pcm))
    return len(pcm) / 4 / rate


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("demo", help="demo name under artifacts/demos/")
    ap.add_argument("--frames", type=int, default=2400, help="max frames to render (60 fps)")
    ap.add_argument("--out", type=Path, default=None, help="output WAV path")
    ap.add_argument("--rate", type=int, default=44100, help="sample rate")
    ap.add_argument("--fps", type=int, default=60, help="present rate (frames/sec) for chunking")
    args = ap.parse_args(argv)

    writes = capture_opl_writes(args.demo, args.frames)
    total = sum(len(w) for w in writes)
    out = args.out or (ROOT / "artifacts" / f"music_{args.demo}.wav")
    secs = render_wav(writes, out, args.rate, args.fps)
    print(f"captured {total} OPL register writes over {args.frames} frames")
    print(f"wrote {out} ({secs:.1f}s @ {args.rate} Hz)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
