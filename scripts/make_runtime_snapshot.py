from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from overkill_port.cli import main

raise SystemExit(main([
    "snapshot",
    str(ROOT / "assets" / "OVERKILL.UNLZEXE.EXE"),
    "--game-root", str(ROOT / "assets"),
    "--steps", "100000",
    "--trace-tail", "128",
    "--out-dir", str(ROOT / "artifacts" / "snapshot_after_bootstrap_100k"),
]))
