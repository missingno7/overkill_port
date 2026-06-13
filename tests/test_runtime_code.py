from __future__ import annotations

from pathlib import Path

import pytest

from overkill_port.games.overkill.runtime_code import (
    RuntimeCodeWriteTracer,
    UnknownRuntimeCodeVariant,
    assert_runtime_code_staticization_ready,
    runtime_code_staticization_report,
    identify_runtime_code_variant,
    require_runtime_code_variant,
)
from overkill_port.runtime import create_runtime
from overkill_port.snapshot import load_snapshot


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
EXE = ASSETS / "OVERKILL"
SNAP_5E42 = ROOT / "artifacts" / "snapshot_play_tandy_20260613_220042"


def _run_until_5e42_gameplay_variant(rt, *, max_steps: int = 1_300_000) -> None:
    for _ in range(max_steps):
        try:
            variant = identify_runtime_code_variant(rt.cpu, (0x1010, 0x5E42))
        except UnknownRuntimeCodeVariant:
            pass
        else:
            if variant.name == "gameplay_object_steer_5e42":
                return
        rt.cpu.step()
    raise AssertionError("original OVERKILL bootstrap did not install gameplay 5E42 body")


def test_runtime_code_manifest_distinguishes_packed_start_and_gameplay_5e42():
    cold = create_runtime(EXE, game_root=ASSETS)
    with pytest.raises(UnknownRuntimeCodeVariant, match="unknown runtime-code variant at 1010:5E42"):
        identify_runtime_code_variant(cold.cpu, (0x1010, 0x5E42))

    gameplay = load_snapshot(EXE, SNAP_5E42, game_root=ASSETS)
    gameplay_variant = identify_runtime_code_variant(gameplay.cpu, (0x1010, 0x5E42))
    assert gameplay_variant.name == "gameplay_object_steer_5e42"


def test_runtime_patched_5e42_hook_rejects_packed_start_without_fallback():
    rt = create_runtime(EXE, game_root=ASSETS)
    with pytest.raises(UnknownRuntimeCodeVariant, match="unknown runtime-code variant at 1010:5E42"):
        require_runtime_code_variant(rt.cpu, (0x1010, 0x5E42), "gameplay_object_steer_5e42")


def test_runtime_patched_5e42_hook_rejects_unknown_live_bytes_without_fallback():
    rt = load_snapshot(EXE, SNAP_5E42, game_root=ASSETS)
    rt.cpu.trace_enabled = False
    for _ in range(20_000):
        if rt.cpu.addr() == (0x1010, 0x5E42):
            break
        rt.cpu.step()
    assert rt.cpu.addr() == (0x1010, 0x5E42)

    # Corrupt the installed runtime body.  The hook must not pop itself and run
    # interpreted ASM as an escape hatch; unknown live code is an exhaustion
    # frontier and therefore fails fast.
    rt.cpu.mem.wb(0x1010, 0x5E42, 0x90)
    with pytest.raises(UnknownRuntimeCodeVariant, match="unknown runtime-code variant at 1010:5E42"):
        rt.cpu.step()


def test_runtime_code_write_tracer_records_writes_to_registered_variant_regions():
    rt = create_runtime(EXE, game_root=ASSETS)
    tracer = RuntimeCodeWriteTracer(rt.cpu).install()
    try:
        old = rt.cpu.mem.rb(0x1010, 0x5E42)
        rt.cpu.mem.wb(0x1010, 0x5E42, old ^ 0xFF)
    finally:
        tracer.uninstall()
    assert tracer.events
    event = tracer.events[-1]
    assert event.writer == (rt.cpu.s.cs, rt.cpu.s.ip)
    assert event.matched_region.startswith("1010:5E42+")
    assert event.target_phys == 0x1010 * 16 + 0x5E42


def test_runtime_code_staticization_manifest_has_static_source_owner_for_accepted_variants():
    report = runtime_code_staticization_report()
    row = next(item for item in report if item["addr"] == "1010:5E42")
    assert row["staticized"] is True
    assert row["accepted_variants"] == ("gameplay_object_steer_5e42",)
    assert row["dispatch"] == "variant_guarded_static_hook"
    assert row["static_target"].endswith("object_runtime.run_runtime_patched_object_steer_5e42")
    assert_runtime_code_staticization_ready()


def test_runtime_code_staticization_strict_installer_gate_accepts_bootstrap_provenance():
    # The accepted body is staticized, and the final writer is still classified
    # as the transient 32FF:* inner unpack/self-relocation bootstrap.  Original
    # packed startup has earlier decompressor writes before that final install.
    assert_runtime_code_staticization_ready(strict_installers=True)
    report = runtime_code_staticization_report(strict_installers=True)
    row = next(item for item in report if item["addr"] == "1010:5E42")
    assert row["installer_status"] == "observed-bootstrap-inner-unpack"
    assert row["missing"] == ()


def test_runtime_patched_5e42_bootstrap_installs_same_body_for_video_modes():
    # 5E42 is not the CGA/EGA/Tandy selector.  The transient 32FF bootstrap
    # installs the same gameplay steering body before the normal video-mode
    # configuration diverges.
    tails = {
        "cga": b"",
        "ega": bytes((0x0D, 0x01)),
        "tandy": bytes((0x0D, 0x02)),
    }
    for tail in tails.values():
        rt = create_runtime(EXE, game_root=ASSETS, command_tail=tail)
        rt.cpu.trace_enabled = False
        rt.cpu.replacement_hooks.clear()
        rt.cpu.hook_names.clear()
        tracer = RuntimeCodeWriteTracer(rt.cpu).install()
        try:
            _run_until_5e42_gameplay_variant(rt)
        finally:
            tracer.uninstall()
        assert tracer.events
        assert (0x32FF, 0x009B) in {event.writer for event in tracer.events}
        assert min(event.target_phys for event in tracer.events) == 0x1010 * 16 + 0x5E42
        assert max(event.target_phys for event in tracer.events) == 0x1010 * 16 + 0x5F1A
        variant = identify_runtime_code_variant(rt.cpu, (0x1010, 0x5E42))
        assert variant.name == "gameplay_object_steer_5e42"
