from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from overkill_port.snapshot import load_snapshot
from scripts.play import AsyncTimerIrqDriver, TANDY_PRESENT_HOOK, RETRACE_WAIT_HOOK

snap=Path('/mnt/data/work_overkill/snapshot/snapshot_play_tandy_20260612_155451')

def run(with_poll: bool):
    rt=load_snapshot(ROOT/'assets'/'OVERKILL.UNLZEXE.EXE', snap, game_root=ROOT/'assets')
    base_present=rt.cpu.replacement_hooks[TANDY_PRESENT_HOOK]
    base_retrace=rt.cpu.replacement_hooks.get(RETRACE_WAIT_HOOK)
    irq=AsyncTimerIrqDriver()
    events=[]
    rt.dos.set_speaker_callback(lambda en,f: events.append((rt.cpu.addr(),en,round(f,1),rt.dos.pit_channel2_reload,rt.dos.speaker_control)))
    class Frame(Exception): pass
    def present(cpu):
        if with_poll:
            irq._next=0.0
            irq.poll(cpu)
        base_present(cpu)
        raise Frame()
    def retrace(cpu):
        if with_poll:
            irq._next=0.0
            irq.poll(cpu)
        if base_retrace: base_retrace(cpu)
        raise Frame()
    rt.cpu.replacement_hooks[TANDY_PRESENT_HOOK]=present
    if base_retrace: rt.cpu.replacement_hooks[RETRACE_WAIT_HOOK]=retrace
    ds=rt.cpu.s.ds
    def rb(o): return rt.cpu.mem.rb(ds,o)
    for i in range(20):
        try:
            rt.cpu.run(200000)
        except Frame:
            pass
        except Exception as e:
            print('exc',e); break
    return rb(0xBEFF), rb(0xBEFE), rb(0xBF00), events[-10:], rt.dos.port_log[-20:], rt.cpu.s.snapshot()
for mode in [False, True]:
    print('\nwith_poll',mode)
    print(run(mode))
