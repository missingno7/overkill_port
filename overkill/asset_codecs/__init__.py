"""Game-specific OVERKILL asset decoding/loading codecs."""
from .asset_table import search_decoded_asset_table_c713
from .checksum import compute_overkill_file_checksum
from .container import (
    OverkillContainerEntry,
    load_container_asset,
    parse_overkill_container,
    read_container_asset,
)
from .level_assets import (
    LEVEL_COUNT,
    TILE_MAP_SIZE,
    LevelAsset,
    LevelData,
    build_level_class_table,
    decode_level_blocks,
    decode_level_graphics,
    decode_level_tile_map,
    finalize_level_tile_plane,
    load_level_data,
    overkill_level_assets,
)
from .loader import decode_asset
from .lz import copy_lz_back_reference, decode_lz_asset, decode_lz_bytes, input_lz_byte, output_lz_byte
from .planar import deplanarize_tandy, pack_planes_344b
from .overlay import (
    compare_overlay_entry_name_05d9,
    compare_overlay_signature_0582,
    decode_overlay_xor,
    find_overlay_directory_entry_05a1,
    strip_overlay_path_components_0701,
)
from .packed_stream import read_packed_byte, read_packed_byte_hook, read_packed_word_le, read_packed_word_le_hook
from .rle import (
    decode_byte_single_marker_rle,
    decode_linear_byte_rle,
    decode_linear_byte_rle_bytes,
    decode_vertical_rle_columns,
    decode_vertical_rle_columns_writes,
    decode_word_pair_rle,
    decode_word_pair_rle_words,
    decode_word_single_marker_rle_words,
)

__all__ = [
    "compute_overkill_file_checksum",
    "search_decoded_asset_table_c713",
    "copy_lz_back_reference",
    "OverkillContainerEntry",
    "parse_overkill_container",
    "read_container_asset",
    "load_container_asset",
    "LEVEL_COUNT",
    "TILE_MAP_SIZE",
    "LevelAsset",
    "LevelData",
    "overkill_level_assets",
    "decode_level_tile_map",
    "decode_level_blocks",
    "decode_level_graphics",
    "finalize_level_tile_plane",
    "build_level_class_table",
    "load_level_data",
    "decode_asset",
    "decode_byte_single_marker_rle",
    "decode_linear_byte_rle",
    "decode_linear_byte_rle_bytes",
    "decode_lz_bytes",
    "pack_planes_344b",
    "deplanarize_tandy",
    "decode_level_blocks",
    "decode_level_graphics",
    "decode_word_single_marker_rle_words",
    "decode_lz_asset",
    "decode_word_pair_rle",
    "decode_word_pair_rle_words",
    "compare_overlay_entry_name_05d9",
    "compare_overlay_signature_0582",
    "decode_overlay_xor",
    "find_overlay_directory_entry_05a1",
    "decode_vertical_rle_columns",
    "decode_vertical_rle_columns_writes",
    "input_lz_byte",
    "strip_overlay_path_components_0701",
    "output_lz_byte",
    "read_packed_byte",
    "read_packed_byte_hook",
    "read_packed_word_le",
    "read_packed_word_le_hook",
]
