"""Find the first frame where native (hooked) diverges from the VM oracle for a demo."""
import sys
from pathlib import Path
sys.path.insert(0, ".")
from dos_re.input_demo import InputDemoPlayback
from overkill.frame_verify import FrameVerifyConfig, run_frame_verifier

demo_dir = sys.argv[1]
max_frames = int(sys.argv[2]) if len(sys.argv) > 2 else 6000
root = Path(".").resolve()
demo = InputDemoPlayback.load(demo_dir)

boundary = {"n": 0}
def pump(ref_rt, cand_rt):
    demo.apply_to_runtimes(boundary["n"], (ref_rt, cand_rt)); boundary["n"] += 1

diverged = {"flag": False, "at": None}
def status_cb(text):
    if "divergence" in text and diverged["at"] is None:
        diverged["flag"] = True
def stop_req():
    return diverged["flag"]

cfg = FrameVerifyConfig(video="tandy", source="both", max_frames=max_frames,
                        semantic_state_check=True, stop_on_diff=True, log_every=200)
rc = run_frame_verifier(exe=root/"assets"/"OVERKILL", assets=root/"assets",
                        snapshot=str(demo.snapshot_path()), command_tail=b"",
                        config=cfg, pump_inputs=pump, stop_requested=stop_req,
                        status_callback=status_cb)
print(f"HUNT DONE rc={rc} frames_reached={boundary['n']}")
