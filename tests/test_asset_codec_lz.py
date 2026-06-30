"""The pure LZ decoder (asset_codecs.decode_lz_bytes) vs the oracle-verified ECF2 hook body.

decode_lz_bytes is the VM-free twin of decode_lz_asset (1010:ECF2), OVERKILL's 4 KiB-window LZSS used
for the bulk of its compressed assets.  The hook body is ASM-oracle-verified, so the airtight check runs
it on a blank Memory (input ring at DS:D8B8, dict at CS:DCB8 cleared, dest ES:DI from CS:ECEE/ECF0) and
compares its output (length from the CS:EDE5/EDE7 counter) to the pure form -- across literal runs, the
flag-byte refill boundary, a back-reference copy, the terminator, and the rare ax==0/extra!=0 resync.
"""
from __future__ import annotations

from dos_re.cpu import CPU8086, CPUState
from dos_re.memory import Memory

from overkill.asset_codecs import decode_lz_asset, decode_lz_bytes

SEG = 0x1010
OUT_SEG = 0x9000


# --- pure unit coverage (known outputs) ----------------------------------------------------------

def test_lz_literal_run():
    # flag 0xFF -> 8 literal bits; then a 0-bit back-reference with the 00 00 00 terminator.
    stream = [0xFF, 0x41, 0x42, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x00, 0x00, 0x00, 0x00]
    assert decode_lz_bytes(stream) == b"ABCDEFGH"


def test_lz_single_literal():
    assert decode_lz_bytes([0x01, 0x41, 0x00, 0x00, 0x00]) == b"A"


def test_lz_back_reference():
    # 4 literals "ABCD", then a back-reference copying 3 bytes from window offset 0xFEE ("ABC").
    stream = [0x0F, 0x41, 0x42, 0x43, 0x44, 0xEE, 0xF0, 0x00, 0x00, 0x00]
    assert decode_lz_bytes(stream) == b"ABCDABC"


def test_lz_empty():
    # First control item is a 0-bit back-reference; 00 00 00 terminates with no output.
    assert decode_lz_bytes([0x00, 0x00, 0x00, 0x00]) == b""


# --- airtight cross-check: pure form vs the ECF2 hook body ----------------------------------------

def _run_hook(stream):
    mem = Memory()
    cpu = CPU8086(mem, CPUState(cs=SEG, ds=SEG, es=OUT_SEG, ss=0x6000, sp=0x8000, ip=0xECF2, flags=0x0202))
    cpu.trace_enabled = False
    mem.load(SEG, 0xD8B8, bytes(b & 0xFF for b in stream))  # input ring
    for off in range(0x1000):                               # clear the 4 KiB window
        mem.wb(SEG, (0xDCB8 + off) & 0xFFFF, 0)
    mem.ww(SEG, 0xECEE, 0)                                  # dest DI
    mem.ww(SEG, 0xECF0, OUT_SEG)                            # dest ES
    cpu.s.si = 0
    decode_lz_asset(cpu)
    count = mem.rw(SEG, 0xEDE5) | (mem.rw(SEG, 0xEDE7) << 16)
    return bytes(mem.rb(OUT_SEG, i & 0xFFFF) for i in range(count))


def test_lz_pure_matches_hook():
    cases = [
        [0xFF, 0x41, 0x42, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x00, 0x00, 0x00, 0x00],  # literal run
        [0x01, 0x41, 0x00, 0x00, 0x00],                                                  # one literal
        [0x0F, 0x41, 0x42, 0x43, 0x44, 0xEE, 0xF0, 0x00, 0x00, 0x00],                    # back-reference
        [0x00, 0x00, 0x00, 0x00],                                                        # immediate terminate
        [0x00, 0x00, 0x00, 0x41, 0x05, 0xF0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],        # ax==0/extra!=0 resync
        [0xFF, *range(8), 0xFF, *range(8, 16), 0x00, 0x00, 0x00, 0x00],                  # two flag groups
    ]
    for stream in cases:
        assert decode_lz_bytes(list(stream)) == _run_hook(stream), stream
