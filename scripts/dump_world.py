#!/usr/bin/env python3
"""Dump recovered OVERKILL runtime-world state from a snapshot or input demo.

This is an evidence-gathering tool for semantic crystallisation.  It does not
execute gameplay.  It projects known runtime tables into source-like JSON so we
can compare levels, bosses, object families, and pointer-table roles without
sprinkling one-off memory reads through hooks.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from dataclasses import asdict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dos_re.input_demo import InputDemoPlayback  # noqa: E402
from overkill.recovered.adapters.world_adapter import (  # noqa: E402
    projection_to_jsonable,
    project_runtime_world,
    read_boss_group_pointer_entries,
    read_runtime_globals,
)
from overkill.runtime import load_overkill_snapshot  # noqa: E402


def _default_exe() -> Path:
    return ROOT / "assets" / "OVERKILL"


def _resolve_snapshot_from_args(args: argparse.Namespace) -> Path:
    if args.snapshot and args.demo:
        raise SystemExit("pass only one of --snapshot or --demo")
    if args.demo:
        return InputDemoPlayback.load(args.demo).snapshot_path()
    if args.snapshot:
        return Path(args.snapshot)
    raise SystemExit("pass --snapshot <dir> or --demo <dir|input_demo.json>")


def _hex_word(value: int) -> str:
    return f"0x{value & 0xFFFF:04X}"


def _summary(data: dict[str, object]) -> str:
    objects = data["objects"]
    assert isinstance(objects, list)
    active = [obj for obj in objects if isinstance(obj, dict) and obj.get("active_word", 0) != 0]
    active_logic = data.get("active_logic_counts", [])
    lines = [
        f"objects: {len(objects)} dumped, {len(active)} active/nonzero",
        "active logic ids: "
        + ", ".join(
            f"{_hex_word(int(entry['logic_id']))}x{entry['count']}"
            for entry in active_logic
            if isinstance(entry, dict)
        ),
    ]
    boss = data.get("boss_group_pointers", [])
    if boss:
        lines.append(
            "boss group pointers: "
            + ", ".join(
                f"{_hex_word(int(entry['value']))}->slot {entry.get('object_slot_index')}"
                for entry in boss
                if isinstance(entry, dict)
            )
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", help="runtime snapshot directory to inspect")
    parser.add_argument("--demo", help="input demo directory/json; inspects its start snapshot")
    parser.add_argument("--exe", default=str(_default_exe()), help="path to the original OVERKILL executable/container")
    parser.add_argument("--game-root", default=str(ROOT / "assets"), help="directory containing original game assets")
    parser.add_argument("--output", "-o", help="write JSON dump to this file instead of stdout")
    parser.add_argument("--active-only", action="store_true", help="omit inactive object slots from the JSON output")
    parser.add_argument("--pretty", action="store_true", default=True, help="pretty-print JSON output")
    parser.add_argument("--summary", action="store_true", help="print a compact human summary to stderr")
    args = parser.parse_args(argv)

    snapshot = _resolve_snapshot_from_args(args)
    rt = load_overkill_snapshot(args.exe, snapshot, game_root=args.game_root)
    projection = project_runtime_world(rt.cpu)
    data = projection_to_jsonable(projection, include_inactive=not args.active_only)
    data.update(
        {
            "source": {
                "snapshot": str(snapshot),
                "demo": str(args.demo) if args.demo else None,
                "exe": str(args.exe),
            },
            "cpu": {
                "cs": rt.cpu.s.cs,
                "ip": rt.cpu.s.ip,
                "ds": rt.cpu.s.ds,
                "ss": rt.cpu.s.ss,
                "bp": rt.cpu.s.bp,
            },
            "globals": {key: value for key, value in read_runtime_globals(rt.cpu).items()},
            "boss_group_pointers": [asdict(entry) for entry in read_boss_group_pointer_entries(rt.cpu)],
        }
    )

    text = json.dumps(data, indent=2 if args.pretty else None, sort_keys=True) + "\n"
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    if args.summary:
        print(_summary(data), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
