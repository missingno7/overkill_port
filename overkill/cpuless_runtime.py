"""Game-specific host wiring for the standalone CPUless runtime (mirrors lemmings_port's runtime.py).

This holds the OVERKILL-specific HOST INPUTS the CPUless game needs -- the things the original read
through DOS/BIOS that a native host supplies instead -- kept OUT of the game-agnostic ``dos_re`` and,
critically, CARRIER-FREE: nothing here imports the interpreter, the VM runtime, or a VM-comparing
probe, so it is safe to import under the CPUless wall (``overkill.cpuless_host.install_import_guard``).

Today: the per-level asset bundle the gameplay frame reads on level load / death re-init (the original's
0B3E / 0E9C loaders do INT 21h file reads; the native port hands the decoded bytes in instead). The
decode itself lives in the pure ``overkill.asset_codecs`` package. As the front-end comes online this
module also gains the video-type selection and boot-key wiring, per the campaign blueprint.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Where the OVERKILL asset container and the static DGROUP bundle live (original-game bytes; never
#: packaged). A host that keeps them elsewhere overrides these before the first level load.
CONTAINER = ROOT / "assets" / "OVERKILL"
BUNDLE = ROOT / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"


def level_assets_for(planet: int, _cache: dict = {}):
    """The per-planet files ``advance_gameplay_frame_97b2`` reads on level load / death re-init /
    game-over / advance -- a HOST INPUT (the frame never emulates INT 21h). Decoded from the asset
    container via the pure ``asset_codecs`` package and cached per planet. Carrier-free."""
    if planet not in _cache:
        from overkill.asset_codecs.level_assets import (decode_level_blocks, decode_level_graphics,
                                                        decode_level_tile_map)
        from overkill.asset_codecs.native_level import (_read_class_override_pairs,
                                                        build_level_class_table)
        from overkill.native_frame import LevelAssets
        container = CONTAINER.read_bytes()
        exe = BUNDLE.read_bytes()
        _cache[planet] = LevelAssets(
            map_bytes=bytes(decode_level_tile_map(container, planet)),
            class_table=bytes(build_level_class_table(_read_class_override_pairs(exe, planet))),
            blocks=bytes(decode_level_blocks(container, planet)),
            graphics=bytes(decode_level_graphics(container, planet)),
        )
    return _cache[planet]


def assets_available() -> bool:
    """Whether the host data needed by :func:`level_assets_for` is present (both are original-game
    bytes, never committed) -- lets a caller SKIP asset-dependent paths with a clear message."""
    return CONTAINER.is_file() and BUNDLE.is_file()
