from __future__ import annotations

import json
from types import SimpleNamespace

from dos_re.input_demo import InputDemoPlayback, dos_key_value


class DummyRuntime:
    def __init__(self) -> None:
        self.dos = SimpleNamespace(key_queue=[])
        self.scans: list[int] = []


def _deliver(rt: DummyRuntime, scancode: int) -> None:
    rt.scans.append(scancode & 0xFF)


def test_input_demo_playback_applies_events_once_at_recorded_boundaries(tmp_path):
    demo = tmp_path / "demo"
    demo.mkdir()
    (demo / "snapshot").mkdir()
    (demo / "input_demo.json").write_text(
        json.dumps(
            {
                "version": 1,
                "snapshot": "snapshot",
                "events": [
                    {"boundary": 0, "seq": 0, "kind": "scan", "value": 0x4D},
                    {"boundary": 2, "seq": 1, "kind": "dos_key", "value": 0x3920, "scancode": 0x39, "text": " "},
                    {"boundary": 2, "seq": 2, "kind": "scan", "value": 0xCD},
                ],
            }
        ),
        encoding="utf-8",
    )

    playback = InputDemoPlayback.load(demo)
    rt = DummyRuntime()

    assert playback.snapshot_path() == demo / "snapshot"
    assert playback.apply_to_runtime(0, rt, deliver=_deliver) == 1
    assert rt.scans == [0x4D]
    assert rt.dos.key_queue == []

    assert playback.apply_to_runtime(1, rt, deliver=_deliver) == 0
    assert playback.apply_to_runtime(2, rt, deliver=_deliver) == 2
    assert rt.scans == [0x4D, 0xCD]
    assert rt.dos.key_queue == [0x3920]

    assert playback.apply_to_runtime(99, rt, deliver=_deliver) == 0


def test_input_demo_playback_can_feed_reference_and_candidate_pair(tmp_path):
    demo = tmp_path / "demo"
    demo.mkdir()
    (demo / "input_demo.json").write_text(
        json.dumps(
            {
                "version": 1,
                "snapshot": "snapshot",
                "events": [
                    {"boundary": 1, "seq": 0, "kind": "scan", "value": 0x39},
                ],
            }
        ),
        encoding="utf-8",
    )

    playback = InputDemoPlayback.load(demo)
    ref = DummyRuntime()
    cand = DummyRuntime()

    assert playback.apply_to_runtimes(0, (ref, cand), deliver=_deliver) == 0
    assert playback.apply_to_runtimes(1, (ref, cand), deliver=_deliver) == 1
    assert ref.scans == cand.scans == [0x39]


def test_dos_key_value_matches_text_prompt_encoding():
    assert dos_key_value(0x39, "") == 0x3920
    assert dos_key_value(0x1C, "") == 0x1C0D
    assert dos_key_value(0x2C, "z") == 0x2C7A
    assert dos_key_value(0x3B, "") is None
