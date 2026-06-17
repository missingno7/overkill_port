#!/usr/bin/env python3
"""Summarise recovered world/object-table write traces.

`trace_world_writes.py` records raw write events.  This script turns those events
into a small materialisation map: which routines write which recovered fields,
which fields are still unknown, and which runtime tables appear to be populated
or mutated first.  It is evidence tooling for level/editor reconstruction, not a
runtime dependency.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _writer_key(event: dict[str, Any]) -> str:
    return str(event.get("csip") or f"{int(event.get('cs', 0)):04X}:{int(event.get('ip', 0)):04X}")


def _target_key(event: dict[str, Any]) -> str:
    target = event.get("target")
    if not isinstance(target, dict):
        return str(event.get("region", "unknown"))
    kind = target.get("kind")
    if kind == "object_slot_field":
        return (
            f"{target.get('object_slot_table')}[{target.get('object_slot_index')}]."
            f"{target.get('field')}+{target.get('field_byte_offset', 0)}"
        )
    if kind == "pointer_table_entry":
        return f"{target.get('pointer_table')}[{target.get('pointer_index')}]"
    if kind == "boss_group_pointer":
        return f"boss_group_a8ba[{target.get('pointer_index')}]"
    if kind == "runtime_global":
        return str(target.get("global"))
    return f"{target.get('region')}+0x{int(target.get('relative', 0)):04X}"


def _target_family(event: dict[str, Any]) -> str:
    target = event.get("target")
    if not isinstance(target, dict):
        return str(event.get("region", "unknown"))
    kind = target.get("kind")
    if kind == "object_slot_field":
        return f"{target.get('object_slot_table')}.{target.get('field')}"
    if kind == "pointer_table_entry":
        return str(target.get("pointer_table"))
    if kind == "boss_group_pointer":
        return "boss_group_a8ba"
    if kind == "runtime_global":
        return str(target.get("global"))
    return str(target.get("region", "unknown"))


def summarise_trace(trace: dict[str, Any]) -> dict[str, Any]:
    events = [event for event in trace.get("events", []) if isinstance(event, dict)]
    by_writer: dict[str, dict[str, Any]] = {}
    writer_targets: dict[str, Counter[str]] = defaultdict(Counter)
    target_writers: dict[str, Counter[str]] = defaultdict(Counter)
    target_counts: Counter[str] = Counter()
    family_counts: Counter[str] = Counter()
    unknown_field_counts: Counter[str] = Counter()
    first_by_target: dict[str, dict[str, Any]] = {}

    for event in events:
        writer = _writer_key(event)
        target = _target_key(event)
        family = _target_family(event)
        writer_info = by_writer.setdefault(
            writer,
            {
                "csip": writer,
                "island": event.get("writer_island"),
                "symbol": event.get("writer_symbol"),
                "count": 0,
                "first_step": event.get("step"),
                "last_step": event.get("step"),
            },
        )
        writer_info["count"] += 1
        writer_info["last_step"] = event.get("step")
        writer_targets[writer][target] += 1
        target_writers[target][writer] += 1
        target_counts[target] += 1
        family_counts[family] += 1
        first_by_target.setdefault(target, event)
        target_info = event.get("target")
        if isinstance(target_info, dict) and target_info.get("kind") == "object_slot_field":
            field = str(target_info.get("field"))
            if field.startswith("unknown_0x"):
                unknown_field_counts[f"{target_info.get('object_slot_table')}.{field}"] += 1

    writer_rows = []
    for writer, info in by_writer.items():
        row = dict(info)
        row["top_targets"] = [
            {"target": target, "count": count} for target, count in writer_targets[writer].most_common(12)
        ]
        writer_rows.append(row)
    writer_rows.sort(key=lambda item: (-int(item["count"]), str(item["csip"])))

    target_rows = []
    for target, count in target_counts.most_common():
        first = first_by_target[target]
        target_rows.append(
            {
                "target": target,
                "count": count,
                "first_step": first.get("step"),
                "first_writer": first.get("csip"),
                "first_writer_island": first.get("writer_island"),
                "first_writer_symbol": first.get("writer_symbol"),
                "writers": [
                    {"writer": writer, "count": writer_count}
                    for writer, writer_count in target_writers[target].most_common(8)
                ],
            }
        )

    return {
        "source": trace.get("source"),
        "status": trace.get("status"),
        "steps": trace.get("steps"),
        "event_count": len(events),
        "writer_count": len(by_writer),
        "target_count": len(target_counts),
        "by_writer": writer_rows,
        "by_target": target_rows,
        "by_target_family": [
            {"target_family": family, "count": count} for family, count in family_counts.most_common()
        ],
        "unknown_object_field_writes": [
            {"field": field, "count": count} for field, count in unknown_field_counts.most_common()
        ],
    }


def _text_summary(summary: dict[str, Any]) -> str:
    lines = [
        f"events={summary['event_count']} writers={summary['writer_count']} targets={summary['target_count']}",
        "top writers:",
    ]
    for row in summary["by_writer"][:12]:
        lines.append(
            f"  {row['csip']} {row.get('island')} {row.get('symbol') or ''} count={row['count']}"
        )
        for target in row.get("top_targets", [])[:4]:
            lines.append(f"    {target['target']} x{target['count']}")
    lines.append("top target families:")
    for row in summary["by_target_family"][:12]:
        lines.append(f"  {row['target_family']} x{row['count']}")
    unknown = summary.get("unknown_object_field_writes", [])
    if unknown:
        lines.append("unknown object fields:")
        for row in unknown[:12]:
            lines.append(f"  {row['field']} x{row['count']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", help="JSON trace produced by scripts/trace_world_writes.py")
    parser.add_argument("--output", "-o", help="write JSON summary to this path")
    parser.add_argument("--text", action="store_true", help="print a compact text summary to stderr")
    args = parser.parse_args(argv)

    trace = json.loads(Path(args.trace).read_text(encoding="utf-8"))
    summary = summarise_trace(trace)
    text = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    if args.text:
        print(_text_summary(summary), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
