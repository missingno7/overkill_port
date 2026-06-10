from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
trace = ROOT / "trace_start.txt"
if not trace.exists():
    raise SystemExit("Run scripts/trace_start.py first")
seen = []
for line in trace.read_text(encoding="utf-8", errors="replace").splitlines():
    m = re.match(r"^([0-9A-F]{4}):([0-9A-F]{4})", line)
    if m:
        seen.append((int(m.group(1), 16), int(m.group(2), 16)))
print(f"executed instruction addresses: {len(seen)}")
print(f"unique addresses: {len(set(seen))}")
for cs, ip in list(dict.fromkeys(seen))[:50]:
    print(f"{cs:04X}:{ip:04X}")
