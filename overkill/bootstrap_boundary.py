"""Bootstrap/static-runtime boundary manifest for OVERKILL.

The original OVERKILL startup is intentionally split from the target source-port
runtime.  The packed/container executable, launcher, unpacker, relocation code,
command-tail parser, and optional sound-driver loader are treated as an oracle and
build-time extraction layer.  They are not meant to survive as gameplay systems in
the clean source port.

This module records that boundary in one importable place so scripts, tests, and
future extraction tooling do not have to rediscover the policy from prose docs.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .launch import build_command_tail


@dataclass(frozen=True)
class RuntimeAddress:
    """Human-readable runtime address used by the bootstrap boundary manifest."""

    segment: int
    offset: int
    role: str
    confidence: str
    notes: str = ""

    @property
    def text(self) -> str:
        return f"{self.segment:04X}:{self.offset:04X}"

    def to_manifest(self) -> dict[str, Any]:
        data = asdict(self)
        data["addr"] = self.text
        return data


@dataclass(frozen=True)
class StaticRuntimeBoundary:
    """Current source-port contract between original bootstrap and game runtime."""

    original_inputs: tuple[str, ...]
    generated_noncanonical_inputs: tuple[str, ...]
    bootstrap_islands: tuple[str, ...]
    first_inner_transfer: RuntimeAddress
    canonical_runtime_entries: tuple[RuntimeAddress, ...]
    required_initial_state: tuple[str, ...]
    derived_asset_classes: tuple[str, ...]
    source_port_rule: str

    def to_manifest(self, *, video: str = "tandy", sound: str = "pc") -> dict[str, Any]:
        tail = build_command_tail(video, sound)
        return {
            "schema": "overkill.static_runtime_boundary.v1",
            "video": video,
            "sound": sound,
            "command_tail_hex": tail.hex(" ").upper(),
            "command_tail_notes": (
                "The inner game reads compact raw PSP bytes, not launcher ASCII "
                "switches. PSP:82 selects video; PSP:83 optionally selects the "
                "sound driver."
            ),
            "original_inputs": self.original_inputs,
            "generated_noncanonical_inputs": self.generated_noncanonical_inputs,
            "bootstrap_islands": self.bootstrap_islands,
            "first_inner_transfer": self.first_inner_transfer.to_manifest(),
            "canonical_runtime_entries": [addr.to_manifest() for addr in self.canonical_runtime_entries],
            "required_initial_state": self.required_initial_state,
            "derived_asset_classes": self.derived_asset_classes,
            "source_port_rule": self.source_port_rule,
        }


STATIC_RUNTIME_BOUNDARY = StaticRuntimeBoundary(
    original_inputs=(
        "assets/OVERKILL",
        "assets/OVERKILL.EXE",
    ),
    generated_noncanonical_inputs=(
        "assets/OVERKILL.UNLZEXE.EXE",
        "assets/OVERKILL.OVERLAY.BIN",
    ),
    bootstrap_islands=(
        "outer launcher / text-mode adapter selector",
        "original OVERKILL MZ/container unpack path",
        "32FF:* inner unpack/self-relocation bootstrap",
        "optional AdLib/Roland driver load into 2032:*",
        "startup asset decoding and screen materialization",
    ),
    first_inner_transfer=RuntimeAddress(
        0x1010,
        0x95C9,
        role="first confirmed transfer into relocated inner runtime code",
        confidence="observed",
        notes=(
            "This is an archaeology/extraction milestone, not necessarily the "
            "final clean source-port entrypoint."
        ),
    ),
    canonical_runtime_entries=(
        RuntimeAddress(
            0x1010,
            0xD007,
            role="current high-level game/frame orchestration frontier",
            confidence="observed during current Tandy startup/gameplay runs",
            notes=(
                "Useful as a checkpoint for runtime exhaustion.  It does not mean "
                "menu, level-select, or boss-key paths are already semantically clean."
            ),
        ),
        RuntimeAddress(
            0x1010,
            0xD445,
            role="level-select input selector loop head",
            confidence="hooked regression frontier",
            notes="EDRAX is DS:BEDA == 0; selector zero is valid.",
        ),
    ),
    required_initial_state=(
        "PSP compact selector tail is seeded from build_command_tail(video, sound)",
        "CS:95BC holds the original video selector word: 0=CGA, 1=EGA, 2=Tandy/PCjr",
        "DS:0055 is set by the original sound-driver probe when AdLib/Roland is active",
        "2032:0000 may contain the loaded optional sound driver entry when selected",
        "registered runtime-code slots, such as 1010:5E42, must match accepted staticized byte variants",
    ),
    derived_asset_classes=(
        "text/splash screens from assets/OVERKILL.EXE",
        "startup/menu/level-select graphics materialized by original decoders",
        "fonts, tiles, sprites, and planar/pixel buffers",
        "planet/level metadata and object tables",
        "sound driver blobs and captured YM3812 register streams",
    ),
    source_port_rule=(
        "Original packed game files are the only canonical inputs.  The unpacker, "
        "outer shell, and bootstrap are an extraction/verification layer, not target "
        "gameplay source.  The clean source-port runtime should start from a "
        "canonical initialized inner-game image plus deterministic derived assets."
    ),
)


def bootstrap_boundary_manifest(*, video: str = "tandy", sound: str = "pc") -> dict[str, Any]:
    """Return the current static-runtime boundary manifest as plain JSON data."""

    return STATIC_RUNTIME_BOUNDARY.to_manifest(video=video, sound=sound)


def write_bootstrap_boundary_manifest(path: str | Path, *, video: str = "tandy", sound: str = "pc") -> None:
    """Write the boundary manifest without executing the original game."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = bootstrap_boundary_manifest(video=video, sound=sound)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
