from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from dos_re.cpu import CPUState
from overkill.static_runtime_bundle import (
    DEFAULT_STATIC_RUNTIME_ENTRY,
    build_static_runtime_bundle_manifest,
    materialized_globals,
    sha256_bytes,
    static_runtime_segments,
)
from dos_re.memory import Memory, linear


def _fake_runtime():
    mem = Memory()
    psp_segment = 0x1000
    mem.load(psp_segment, 0x0000, b"PSP")
    mem.wb(psp_segment, 0x0080, 3)
    mem.load(psp_segment, 0x0081, bytes((0x0D, 0x02, 0x41)))

    mem.ww(0x1010, 0x95BC, 2)
    mem.load(0x1010, 0x0000, b"INNER-RUNTIME")
    mem.wb(0x25CC, 0x0055, 1)
    mem.ww(0x25CC, 0x95DA, 0x2B5C)
    mem.load(0x2032, 0x0000, b"ADLIB-DRIVER")

    state = CPUState(cs=0x1010, ip=0xD007, ds=0x25CC, es=0x25CC, ss=0x25CC, sp=0xA274)
    cpu = SimpleNamespace(s=state, addr=lambda: (state.cs, state.ip))
    exe = SimpleNamespace(path=Path("assets/OVERKILL"), load_module=b"mz")
    program = SimpleNamespace(memory=mem, psp_segment=psp_segment, exe=exe, overlay=b"overlay")
    return SimpleNamespace(program=program, cpu=cpu)


def test_static_runtime_segments_hash_named_ranges_and_include_sound_driver():
    rt = _fake_runtime()

    segments = {segment.name: segment for segment in static_runtime_segments(rt)}

    assert set(segments) == {
        "psp_and_command_tail",
        "relocated_inner_runtime_1010",
        "optional_sound_driver_2032",
    }
    assert segments["psp_and_command_tail"].start_phys == linear(0x1000, 0)
    assert segments["relocated_inner_runtime_1010"].size == 0x10000
    assert segments["optional_sound_driver_2032"].nonzero_bytes >= len(b"ADLIB-DRIVER")


def test_materialized_globals_record_bootstrap_contract_values():
    globals_by_name = {item.name: item for item in materialized_globals(_fake_runtime())}

    assert globals_by_name["video_selector_word"].value == 2
    assert globals_by_name["sound_driver_active_flag"].value == 1
    assert globals_by_name["object_allocator_cursor"].value == 0x2B5C


def test_static_runtime_bundle_manifest_is_reviewable_and_boundary_anchored():
    rt = _fake_runtime()
    manifest = build_static_runtime_bundle_manifest(
        rt,
        video="tandy",
        sound="adlib",
        status="reached 1010:D007",
        steps=123,
        stop_at=DEFAULT_STATIC_RUNTIME_ENTRY,
        trace_tail=("one", "two"),
    )

    assert manifest["schema"] == "overkill.static_runtime_bundle.v1"
    assert manifest["boundary"]["schema"] == "overkill.static_runtime_boundary.v1"
    assert manifest["command_tail_hex"] == "0D 02 41"
    assert manifest["reached_requested_entry"] is True
    assert manifest["current_addr"] == "1010:D007"
    assert manifest["memory_1mb_sha256"] == sha256_bytes(rt.program.memory.data[:1024 * 1024])
    assert {segment["name"] for segment in manifest["segments"]} >= {"relocated_inner_runtime_1010"}
    assert "memory_1mb.bin" == manifest["snapshot_files"]["memory"]
