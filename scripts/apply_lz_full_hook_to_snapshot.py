from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from overkill_port.cpu import CPU8086, CPUState
from overkill_port.dos import DOSMachine, FileHandle
from overkill_port.memory import Memory
from overkill_port.replacements import overkill_lz_decoder_ecf2


def main() -> int:
    src = ROOT / "artifacts" / "snapshot_before_lz_full_hook_ecf2"
    out = ROOT / "artifacts" / "snapshot_after_lz_full_hook_ecf2"
    meta = json.loads((src / "state.json").read_text(encoding="utf-8"))

    mem = Memory()
    mem.data[:] = (src / "memory_1mb.bin").read_bytes()
    cpu = CPU8086(mem, CPUState(**meta["cpu"]))
    cpu.trace_enabled = False

    dos = DOSMachine(ROOT / "assets")
    for handle_text, info in meta["dos"]["open_files"].items():
        path = ROOT / info["path"] if not Path(info["path"]).is_absolute() else Path(info["path"])
        dos.files[int(handle_text)] = FileHandle(path, bytearray(path.read_bytes()), info["pos"])
    cpu.interrupt_handler = dos.interrupt
    cpu.port_reader = dos.port_read
    cpu.port_writer = dos.port_write

    before = cpu.s.snapshot()
    overkill_lz_decoder_ecf2(cpu)

    out.mkdir(parents=True, exist_ok=True)
    (out / "memory_1mb.bin").write_bytes(bytes(mem.data))
    (out / "trace_tail.txt").write_text(
        "Applied verified Python hook 1010:ECF2 overkill_lz_decoder_ecf2 directly to the before snapshot.\n",
        encoding="utf-8",
    )
    after_meta = {
        "status": "applied verified full LZ decoder hook 1010:ECF2 to snapshot_before_lz_full_hook_ecf2",
        "before_cpu_snapshot": before,
        "cpu": asdict(cpu.s),
        "cpu_snapshot": cpu.s.snapshot(),
        "dos": {
            "video_mode": dos.video_mode,
            "ticks": dos.ticks,
            "vga_status_reads": dos.vga_status_reads,
            "open_files": {
                str(handle): {"path": str(f.path), "pos": f.pos, "size": len(f.data)}
                for handle, f in dos.files.items()
            },
            "stdout_tail": "".join(dos.stdout)[-4096:],
            "port_log_tail": dos.port_log[-128:],
        },
        "observed_lz_output_counter_low": mem.rw(0x1010, 0xEDE5),
        "observed_lz_output_counter_high": mem.rw(0x1010, 0xEDE7),
    }
    (out / "state.json").write_text(json.dumps(after_meta, indent=2), encoding="utf-8")
    print(after_meta["status"])
    print(after_meta["cpu_snapshot"])
    print("output bytes:", mem.rw(0x1010, 0xEDE5) + (mem.rw(0x1010, 0xEDE7) << 16))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
