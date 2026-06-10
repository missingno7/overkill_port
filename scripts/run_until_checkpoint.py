from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from overkill_port.snapshot import run_until
from overkill_port.runtime import create_runtime

rt = create_runtime(ROOT / "assets" / "OVERKILL.UNLZEXE.EXE", game_root=ROOT / "assets")
status, steps, tail = run_until(rt, max_steps=100_000, trace_tail=200)
out = ROOT / "checkpoint_tail.txt"
out.write_text("\n".join([status, f"steps={steps}", rt.cpu.s.snapshot(), "", *tail]) + "\n", encoding="utf-8")
print(f"wrote {out}")
