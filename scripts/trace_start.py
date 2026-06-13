from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from overkill_port.cli import main
raise SystemExit(main(["trace", str(ROOT / "assets" / "OVERKILL"), "--steps", "5000", "--out", str(ROOT / "trace_start.txt")]))
