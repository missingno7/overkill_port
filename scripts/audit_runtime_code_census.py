#!/usr/bin/env python
"""Census runtime writes that could be mistaken for self-modifying code.

The goal is to separate three things that all live in OVERKILL's CS segment:

* transient 32FF:* bootstrap materialization/unpack writes,
* normal code-segment data/config words such as the video mode selector,
* actual executable runtime-code slots that require staticization.

This is an evidence tool, not a game hook.  It runs the original interpreter with
replacement hooks disabled so the write provenance comes from the DOS binary.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "dos_re"))  # submodule repo root (no editable install under PyPy)

from overkill.runtime_code import (  # noqa: E402
    RUNTIME_CODE_SLOTS,
    RuntimeCodeWriteEvent,
    RuntimeCodeWriteTracer,
    describe_live_runtime_code_state,
)
from dos_re.memory import linear  # noqa: E402
from overkill.runtime import create_overkill_runtime  # noqa: E402

VIDEO_TAILS: dict[str, bytes] = {
    "cga": b"",
    "ega": bytes((0x0D, 0x01)),
    "tandy": bytes((0x0D, 0x02)),
}

# These addresses are mutable words/bytes in the code segment, but they are not
# executable code bodies.  They are useful evidence when deciding whether a write
# is real self-modifying code or just original DOS-era code+data cohabitation.
KNOWN_CODE_SEGMENT_DATA: dict[int, str] = {
    0x95BC: "video mode selector / shared video-dispatch index (00=CGA, 01=EGA, 02=Tandy)",
    0x95C4: "runtime data segment word cached by init",
    0x95C6: "runtime extra/data segment word cached by init",
    0x95C8: "startup/runtime byte cached by init",
    0xC88C: "asset/checksum loader scratch word",
    0xC88E: "asset/checksum loader scratch word",
    0xC890: "asset/checksum loader rolling word",
    0xC892: "asset/checksum loader scratch word",
}


@dataclass(frozen=True)
class SlotEventSummary:
    slot_addr: tuple[int, int]
    slot_name: str
    count: int
    writers: tuple[tuple[tuple[int, int], int], ...]
    first_offset: int
    last_offset: int

    def format_line(self) -> str:
        writers = ", ".join(f"{seg:04X}:{off:04X} x{count}" for (seg, off), count in self.writers)
        seg, off = self.slot_addr
        return (
            f"  {seg:04X}:{off:04X} {self.slot_name}: {self.count} writes, "
            f"targets {self.first_offset:04X}-{self.last_offset:04X}, writers {writers}"
        )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--exe", default="assets/OVERKILL")
    p.add_argument("--game-root", default="assets")
    p.add_argument("--steps", type=int, default=250_000)
    p.add_argument(
        "--video",
        choices=("all", "cga", "ega", "tandy"),
        default="all",
        help="Mode command tail to test. 'all' compares CGA/EGA/Tandy.",
    )
    p.add_argument(
        "--show-bootstrap",
        action="store_true",
        help="Also print the high-volume 32FF:* bootstrap/unpack write count.",
    )
    return p.parse_args()


def _slot_for_event(event: RuntimeCodeWriteEvent) -> tuple[tuple[int, int], str] | None:
    event_start = event.target_phys
    event_end = event.target_phys + event.size
    for addr, slot in RUNTIME_CODE_SLOTS.items():
        start = linear(*addr)
        end = start + slot.max_signature_size + 0x40
        if event_start < end and event_end > start:
            return addr, slot.name
    return None


def _summarize_slot_events(events: Iterable[RuntimeCodeWriteEvent]) -> list[SlotEventSummary]:
    grouped: dict[tuple[tuple[int, int], str], list[RuntimeCodeWriteEvent]] = defaultdict(list)
    for event in events:
        slot = _slot_for_event(event)
        if slot is not None:
            grouped[slot].append(event)
    rows: list[SlotEventSummary] = []
    for (addr, name), slot_events in grouped.items():
        writers = tuple(Counter(e.writer for e in slot_events).most_common())
        offsets = [e.target_phys - linear(addr[0], 0) for e in slot_events]
        sizes = [e.size for e in slot_events]
        rows.append(
            SlotEventSummary(
                slot_addr=addr,
                slot_name=name,
                count=len(slot_events),
                writers=writers,
                first_offset=min(offsets),
                last_offset=max(off + size - 1 for off, size in zip(offsets, sizes)),
            )
        )
    return sorted(rows, key=lambda r: r.slot_addr)


def _summarize_post_bootstrap_data(events: Iterable[RuntimeCodeWriteEvent]) -> list[str]:
    rows: list[str] = []
    for event in events:
        if event.writer[0] == 0x32FF:
            continue
        if _slot_for_event(event) is not None:
            continue
        off = event.target_phys - linear(0x1010, 0)
        if off < 0 or off > 0xFFFF:
            continue
        label = KNOWN_CODE_SEGMENT_DATA.get(off, "unclassified CS-segment data write")
        rows.append(
            f"  writer={event.writer[0]:04X}:{event.writer[1]:04X} "
            f"target=1010:{off:04X} old={event.old.hex(' ')} new={event.new.hex(' ')}  {label}"
        )
    return rows


def _run_mode(video: str, args: argparse.Namespace) -> int:
    exe = Path(args.exe)
    game_root = Path(args.game_root)
    rt = create_overkill_runtime(exe, game_root=game_root, command_tail=VIDEO_TAILS[video])
    rt.cpu.trace_enabled = False
    rt.cpu.replacement_hooks.clear()
    rt.cpu.hook_names.clear()

    tracer = RuntimeCodeWriteTracer(rt.cpu, regions=(((0x1010, 0x0000), 0x10000),)).install()
    error = None
    try:
        for _ in range(args.steps):
            rt.cpu.step()
    except Exception as exc:  # keep whatever evidence was collected
        error = exc
    finally:
        tracer.uninstall()

    events = tracer.events
    bootstrap_events = [e for e in events if e.writer[0] == 0x32FF]
    slot_rows = _summarize_slot_events(events)
    slot_post_bootstrap = [e for e in events if e.writer[0] != 0x32FF and _slot_for_event(e) is not None]
    post_bootstrap_data = _summarize_post_bootstrap_data(events)

    print(f"\n{video.upper()} runtime-code census")
    print("=" * (len(video) + 21))
    print(f"steps attempted: {args.steps}")
    if error is not None:
        print(f"stopped by {type(error).__name__}: {error}")
    if args.show_bootstrap:
        writers = ", ".join(
            f"{seg:04X}:{off:04X} x{count}"
            for (seg, off), count in Counter(e.writer for e in bootstrap_events).most_common(5)
        )
        print(f"bootstrap/code-materialization writes: {len(bootstrap_events)} ({writers})")

    print("registered runtime-code slot writes:")
    if slot_rows:
        for row in slot_rows:
            print(row.format_line())
    else:
        print("  none")
    if slot_post_bootstrap:
        print(f"post-bootstrap writes into registered runtime-code slots: {len(slot_post_bootstrap)}")
    else:
        print("post-bootstrap writes into registered runtime-code slots: none")

    print("final registered slot variants:")
    for addr in sorted(RUNTIME_CODE_SLOTS):
        state = describe_live_runtime_code_state(rt.cpu, addr)
        print(
            f"  {state['addr']} {state['slot']} "
            f"variant={state['variant']} status={state['status']} sha1={state['sha1']}"
        )

    print("post-bootstrap CS-segment data/config writes:")
    if post_bootstrap_data:
        for line in post_bootstrap_data[:40]:
            print(line)
        if len(post_bootstrap_data) > 40:
            print(f"  ... {len(post_bootstrap_data) - 40} more")
    else:
        print("  none")

    return 1 if slot_post_bootstrap else 0


def main() -> int:
    args = parse_args()
    videos = ("cga", "ega", "tandy") if args.video == "all" else (args.video,)
    failures = 0
    for video in videos:
        failures += _run_mode(video, args)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
