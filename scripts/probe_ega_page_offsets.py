from pathlib import Path
import sys,collections
ROOT=Path('/mnt/data/overkill_work')
sys.path.insert(0,str(ROOT))
from overkill_port.runtime import create_runtime
NON_CGA_DISABLE={(0x1010,0x58DF)}
BOUND={(0x1010,0x2750):'present',(0x1010,0x50C9):'retrace',(0x1010,0x0679):'timer'}
class B(Exception): pass
rt=create_runtime(ROOT/'assets/OVERKILL', game_root=ROOT/'assets', command_tail=bytes((0x0D,0x01)))
cpu=rt.cpu; cpu.trace_enabled=False
for k in NON_CGA_DISABLE: cpu.replacement_hooks.pop(k,None); cpu.hook_names.pop(k,None)
mem=cpu.mem
counts=collections.Counter(); examples={}
def bucket(off): return f'{off//0x2000:02X}:{off&0x1fff:04X}'
orig_wb,orig_ww,orig_rb,orig_rw=mem.wb,mem.ww,mem.rb,mem.rw
def log(kind,seg,off,n=1):
    a=(((seg&0xffff)<<4)+(off&0xffff))&0xfffff
    po=a-0xA0000
    if 0 <= po < 0x10000:
        b=po//0x2000
        counts[(kind,b)]+=1
        examples.setdefault((kind,b),(cpu.s.cs,cpu.s.ip,seg,off,cpu.mem.ega_map_mask,cpu.mem.ega_read_plane))
def wb(seg,off,val): log('wb',seg,off); return orig_wb(seg,off,val)
def ww(seg,off,val): log('ww',seg,off,2); return orig_ww(seg,off,val)
def rb(seg,off): log('rb',seg,off); return orig_rb(seg,off)
def rw(seg,off): log('rw',seg,off,2); return orig_rw(seg,off)
mem.wb=wb; mem.ww=ww; mem.rb=rb; mem.rw=rw
for addr,name in BOUND.items():
    base=cpu.replacement_hooks.get(addr)
    def make(base=base):
        def hook(c):
            if base: base(c)
            raise B()
        return hook
    cpu.replacement_hooks[addr]=make()
for n in range(1,1901):
    while True:
        try: cpu.run(100000)
        except B: break
print('Stopped',cpu.addr())
print('A000 access buckets by 8 KiB page:')
for (kind,b),c in sorted(counts.items()):
    print(f'  {kind} page {b}: {c}')
print('examples:')
for k,v in sorted(examples.items()):
    cs,ip,seg,off,mm,rp=v
    print(k, f'at {cs:04X}:{ip:04X} {seg:04X}:{off:04X} map={mm:X} read={rp}')
