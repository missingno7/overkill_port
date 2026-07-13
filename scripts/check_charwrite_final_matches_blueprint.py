"""One-off check: does the cold-boot char-writer's FINAL revealed frame match the already-verified
`compose_blueprint` (grid + all 15 attract-cycle recipe cells)?  If so, the cold-boot reveal converges
on the exact same end-state already modeled byte-exact -- the animation is a different-paced reveal of
the SAME content, not different content.

Usage: pypy scripts/check_charwrite_final_matches_blueprint.py [demo_name] [--frame F]
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dos_re"))

import numpy as np  # noqa: E402
import overkill.frame_verify as fv  # noqa: E402
from overkill.frame_verify import FrameVerifyConfig, run_frame_verifier  # noqa: E402
from overkill.input_waits import pump_demo_frame  # noqa: E402
from overkill.probes._harness import load_demo  # noqa: E402
from overkill.native_video.blueprint import compose_blueprint  # noqa: E402
from overkill.recovered.adapters.flat_memory import MutFlatMemory  # noqa: E402
from scripts.render_frame import TANDY_BANK_STRIDE, TANDY_BYTES_PER_ROW  # noqa: E402

DEFAULT_DEMO = "demo_cold_start_intro_20260711_203259"


def decode_tandy_indices(mem: bytes, seg: int) -> np.ndarray:
    base = seg * 16
    out = np.zeros((200, 320), dtype=np.uint8)
    for y in range(200):
        row = (y & 3) * TANDY_BANK_STRIDE + (y >> 2) * TANDY_BYTES_PER_ROW
        for xb in range(TANDY_BYTES_PER_ROW):
            value = mem[base + row + xb]
            out[y, xb * 2] = (value >> 4) & 0x0F
            out[y, xb * 2 + 1] = value & 0x0F
    return out


def run(demo_name: str, target_frame: int):
    demo = load_demo(demo_name, demo_name)
    meta = demo.manifest.get("metadata", {})
    video = str(meta.get("video", "tandy"))
    tail = str(meta.get("command_tail", ""))
    state = {"f": 0, "ref": None, "captured": None}
    orig_load = fv._load_runtime
    sides = iter(("ref", "cand"))

    def patched(exe, assets, snap, t):
        rt = orig_load(exe, assets, snap, t)
        if next(sides) == "ref":
            state["ref"] = rt
        return rt

    fv._load_runtime = patched

    def pump(ref, cand):
        f = state["f"]
        rt = state["ref"]
        if rt is not None and f == target_frame:
            state["captured"] = bytes(rt.cpu.mem.data)
        pump_demo_frame(demo, f, (ref, cand), ref.cpu)
        state["f"] = f + 1

    cfg = FrameVerifyConfig(video=video, source="candidate", max_frames=target_frame + 2,
                            semantic_state_check=False, stop_on_diff=False, log_every=0,
                            frame_budget=120_000_000)
    try:
        run_frame_verifier(exe=str(ROOT / "assets" / "OVERKILL"), assets=str(ROOT / "assets"),
                           snapshot=None, command_tail=tail, config=cfg, pump_inputs=pump)
    finally:
        fv._load_runtime = orig_load
    return state["captured"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("demo", nargs="?", default=DEFAULT_DEMO)
    ap.add_argument("--frame", type=int, default=600)
    args = ap.parse_args(argv)
    mem_bytes = run(args.demo, args.frame)
    if mem_bytes is None:
        print(f"never reached frame {args.frame}")
        return 1

    b800 = decode_tandy_indices(mem_bytes, 0xB800)
    b800_nz = int(np.count_nonzero(b800))
    b800_sha = hashlib.sha256(b800.tobytes()).hexdigest()[:16]
    print(f"cold-boot B800 @f{args.frame}: nz={b800_nz} sha16={b800_sha}")

    mem = MutFlatMemory(bytearray(mem_bytes))
    bp = compose_blueprint(mem)
    bp_nz = int(np.count_nonzero(bp))
    bp_sha = hashlib.sha256(bp.tobytes()).hexdigest()[:16]
    print(f"compose_blueprint(same image): nz={bp_nz} sha16={bp_sha}")

    diff = int(np.count_nonzero(b800 != bp))
    print(f"diff vs compose_blueprint: {diff}/64000 pixels differ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
