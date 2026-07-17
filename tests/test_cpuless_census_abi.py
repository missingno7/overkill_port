"""Unit test for the binary-wide census's per-function ABI metadata extractor (view B).

The memoryless (DOS-layout-less) stage consumes machine-readable metadata for EVERY discovered
function: which register channels it may read/write, whether it touches memory/ports, which fixed
global cells it depends on, and its indirect-dispatch callees.  This pins that extraction against a
tiny synthetic function so a regression in ``abi_metadata`` / ``_direct_cell`` is caught without the
full 626-function artifact.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "dos_re"))

from dos_re.lift.ir import scan_from_ir_record  # noqa: E402

import cpuless_census_view as cv  # noqa: E402


def _rec(*insts):
    """A minimal liftable IR function record from (ip, bytes-hex) instruction pairs."""
    return {
        "entry": f"1010:{insts[0][0]}",
        "liftable": True,
        "blocks": [{"start": None, "instructions": [
            {"ip": ip, "bytes": b, "kind": "seq", "mnemonic": "", "mem_operand": True}
            for ip, b in insts
        ]}],
    }


def test_abi_metadata_moffs_and_registers():
    # mov ax,[95BC] ; mov [A960],ax ; ret  -- a direct global read, a direct global write.
    rec = _rec(("0000", "a1bc95"), ("0003", "a360a9"), ("0006", "c3"))
    md = cv.abi_metadata(scan_from_ir_record(rec), dyn={}, cs="1010")
    assert "ax" in md["regs_read"] and "ax" in md["regs_written"]
    assert md["reads_mem"] and md["writes_mem"] and not md["port_io"]
    assert md["global_reads"] == ["ds:95BC"]
    assert md["global_writes"] == ["ds:A960"]
    assert md["callees_indirect"] == []


def test_abi_metadata_indirect_callee_from_evidence():
    # a jmp cs:[bx+disp] dispatch site whose observed target comes from the evidence map.
    rec = _rec(("5834", "ff27"))  # jmp [bx]  (a stand-in indirect transfer)
    dyn = {"1010:5834": ["1010:587E"]}
    md = cv.abi_metadata(scan_from_ir_record(rec), dyn=dyn, cs="1010")
    assert md["callees_indirect"] == ["1010:587E"]


def test_direct_cell_ignores_computed_operands():
    # mov ax,[bx+si] is a computed (array) access, NOT a fixed global cell.
    from dos_re.lift.decode import decode_one  # noqa: E402
    raw = bytes.fromhex("8b00")  # mov ax,[bx+si]
    inst = decode_one(lambda i: raw[i], 0)
    assert cv._direct_cell(inst) is None
