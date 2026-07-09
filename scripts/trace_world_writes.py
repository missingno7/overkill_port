#!/usr/bin/env python3
"""Trace writes to recovered OVERKILL world/object tables.

This helps answer the next level-editor question: which routines materialise or
mutate object slots, pointer tables, and boss-group links?  The tracer is kept
separate from hooks so it can be used as an evidence probe without changing the
runtime path.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dos_re"))  # submodule repo root (no editable install under PyPy)

from dos_re.input_demo import InputDemoPlayback  # noqa: E402
from dos_re.memory import linear  # noqa: E402
from overkill.coverage import OverkillCoverageClassifier, fmt_addr  # noqa: E402
from overkill.recovered.adapters.world_adapter import (  # noqa: E402
    BOSS_GROUP_POINTERS,
    OBJECT_SLOT_TABLE_SPECS,
    POINTER_TABLE_SPECS,
    RUNTIME_GLOBAL_WORDS,
    describe_world_write_target,
    resolve_pointer_value,
)
from overkill.runtime import load_overkill_snapshot  # noqa: E402


def _default_exe() -> Path:
    return ROOT / "assets" / "OVERKILL"


def _resolve_snapshot(snapshot: str | None, demo: str | None) -> Path:
    if snapshot and demo:
        raise SystemExit("pass only one of --snapshot or --demo")
    if demo:
        return InputDemoPlayback.load(demo).snapshot_path()
    if snapshot:
        return Path(snapshot)
    raise SystemExit("pass --snapshot <dir> or --demo <dir|input_demo.json>")


def _watch_regions(ds: int) -> list[tuple[str, int, int]]:
    regions: list[tuple[str, int, int]] = []
    for spec in OBJECT_SLOT_TABLE_SPECS:
        regions.append((spec.name, linear(ds, spec.base), spec.count * 0x38))
    for name, offset, count in POINTER_TABLE_SPECS:
        regions.append((name, linear(ds, offset), count * 2))
    for name, offset in RUNTIME_GLOBAL_WORDS:
        regions.append((name, linear(ds, offset), 2))
    for index, offset in enumerate(BOSS_GROUP_POINTERS):
        regions.append((f"boss_group_a8ba[{index}]", linear(ds, offset), 2))
    return regions


def _hit_region(addr: int, size: int, regions: list[tuple[str, int, int]]) -> tuple[str, int] | None:
    end = addr + size
    for name, start, length in regions:
        region_end = start + length
        if addr < region_end and end > start:
            return name, addr - start
    return None


def _load_symbol_names() -> dict[tuple[int, int], str]:
    symbols_path = ROOT / "symbols.json"
    if not symbols_path.exists():
        return {}
    try:
        raw = json.loads(symbols_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    names: dict[tuple[int, int], str] = {}
    for key, value in raw.items():
        try:
            cs_text, ip_text = key.split(":", 1)
            addr = (int(cs_text, 16) & 0xFFFF, int(ip_text, 16) & 0xFFFF)
        except Exception:
            continue
        if isinstance(value, dict):
            name = str(value.get("name", ""))
        else:
            name = str(value)
        if name:
            names[addr] = name
    return names


def _word_from_trace_bytes(hex_text: str) -> int | None:
    data = bytes.fromhex(hex_text)
    if len(data) != 2:
        return None
    return data[0] | (data[1] << 8)


def _decorate_value_target(target: dict[str, object], old_hex: str, new_hex: str) -> dict[str, object]:
    old_word = _word_from_trace_bytes(old_hex)
    new_word = _word_from_trace_bytes(new_hex)
    if old_word is None or new_word is None:
        return {}
    if target.get("kind") in {"pointer_table_entry", "boss_group_pointer"}:
        return {"old_ref": resolve_pointer_value(old_word), "new_ref": resolve_pointer_value(new_word)}
    return {"old_word": old_word, "new_word": new_word}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", help="runtime snapshot directory to inspect")
    parser.add_argument("--demo", help="input demo directory/json; traces from its start snapshot")
    parser.add_argument("--exe", default=str(_default_exe()), help="path to the original OVERKILL executable/container")
    parser.add_argument("--game-root", default=str(ROOT / "assets"), help="directory containing original game assets")
    parser.add_argument("--max-steps", type=int, default=20000, help="maximum CPU steps to execute")
    parser.add_argument("--max-events", type=int, default=2000, help="stop after this many traced writes")
    parser.add_argument("--output", "-o", help="write JSON trace to this file instead of stdout")
    args = parser.parse_args(argv)

    snapshot = _resolve_snapshot(args.snapshot, args.demo)
    rt = load_overkill_snapshot(args.exe, snapshot, game_root=args.game_root)
    regions = _watch_regions(rt.cpu.s.ds & 0xFFFF)
    classifier = OverkillCoverageClassifier(ROOT / "symbols.json")
    symbol_names = _load_symbol_names()
    events: list[dict[str, object]] = []

    def watcher(addr: int, old: bytes, new: bytes) -> None:
        if len(events) >= args.max_events:
            return
        hit = _hit_region(addr, len(new), regions)
        if hit is None:
            return
        region, relative = hit
        writer = (rt.cpu.s.cs & 0xFFFF, rt.cpu.s.ip & 0xFFFF)
        target = describe_world_write_target(region, relative, len(new))
        event: dict[str, object] = {
            "step": rt.cpu.instruction_count,
            "cs": writer[0],
            "ip": writer[1],
            "csip": fmt_addr(writer),
            "writer_island": classifier.classify(writer, symbol_names.get(writer, "")),
            "writer_symbol": symbol_names.get(writer),
            "region": region,
            "relative": relative,
            "addr": addr,
            "size": len(new),
            "old": old.hex(),
            "new": new.hex(),
            "target": target,
        }
        event.update(_decorate_value_target(target, old.hex(), new.hex()))
        events.append(event)

    rt.cpu.mem.write_watchers.append(watcher)
    status = "max_steps"
    steps = 0
    try:
        for steps in range(1, max(0, args.max_steps) + 1):
            if len(events) >= args.max_events:
                status = "max_events"
                break
            rt.cpu.step()
    except Exception as exc:  # keep trace useful at unsupported/fail-fast boundaries
        status = f"exception:{type(exc).__name__}:{exc}"
    finally:
        try:
            rt.cpu.mem.write_watchers.remove(watcher)
        except ValueError:
            pass

    data = {
        "source": {"snapshot": str(snapshot), "demo": str(args.demo) if args.demo else None, "exe": str(args.exe)},
        "status": status,
        "steps": steps,
        "event_count": len(events),
        "events": events,
    }
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
