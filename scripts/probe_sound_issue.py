from pathlib import Path
import sys, json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from overkill_port.snapshot import load_snapshot
from overkill_port.interrupts import deliver_scancode
from overkill_port.games.overkill.sounds import deliver_overkill_timer_irq0

snap=Path('/mnt/data/work_overkill/snapshot/snapshot_play_tandy_20260612_155451')
rt=load_snapshot(ROOT/'assets'/'OVERKILL', snap, game_root=ROOT/'assets')
print('addr', rt.cpu.s.snapshot())
print('int8', hex(rt.cpu.mem.rw(0,0x20)), hex(rt.cpu.mem.rw(0,0x22)))
print('int9', hex(rt.cpu.mem.rw(0,0x24)), hex(rt.cpu.mem.rw(0,0x26)))
# speaker events
rt.dos.speaker_callback=lambda en,f: print('SPEAKER', rt.cpu.s.cs, hex(rt.cpu.s.ip), en, f, 'reload', rt.dos.pit_channel2_reload, 'ctrl', rt.dos.speaker_control)
# Trace current and deliver space make, run some steps
rt.cpu.trace_enabled=True
print('deliver space')
deliver_scancode(rt,0x39)
print('after key', rt.cpu.s.snapshot(), 'queue', rt.dos.key_queue)
for i in range(2000):
    try:
        rt.cpu.step()
    except Exception as e:
        print('EXC', type(e), e); break
    if rt.cpu.trace:
        for line in rt.cpu.trace:
            if any(x in line for x in ['0679','06E5','D50E','CD','D4','OUT','out','INT','IRET']):
                print(line)
        rt.cpu.trace.clear()
print('end', rt.cpu.s.snapshot())
print('ports', rt.dos.port_log[-40:])
