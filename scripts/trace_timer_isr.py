from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from overkill_port.snapshot import load_snapshot
from overkill_port.games.overkill.sounds import deliver_overkill_timer_irq0
snap=Path('/mnt/data/work_overkill/snapshot/snapshot_play_tandy_20260612_155451')
rt=load_snapshot(ROOT/'assets'/'OVERKILL.UNLZEXE.EXE', snap, game_root=ROOT/'assets')
rt.cpu.trace_enabled=True
rt.dos.speaker_callback=lambda en,f: print(f'EV @ {rt.cpu.s.cs:04X}:{rt.cpu.s.ip:04X} enabled={en} freq={f:.1f} reload={rt.dos.pit_channel2_reload} ctrl={rt.dos.speaker_control:02X}')
print('before',rt.cpu.s.snapshot())
try:
    ok=deliver_overkill_timer_irq0(rt.cpu, max_steps=5000)
    print('ok',ok)
except Exception as e: print('ERR',e)
print('after',rt.cpu.s.snapshot())
for line in rt.cpu.trace:
    print(line)
