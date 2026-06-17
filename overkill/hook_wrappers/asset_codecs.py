"""Address-bound hook wrappers for OVERKILL asset/loading codecs.

The implementation bodies live in :mod:`overkill.asset_codecs`
and related startup-rendering modules.  This file only owns the CS:IP registration
names and tiny adapter functions, so the global replacements shim does not keep
accreting loader-specific wrappers.
"""

from __future__ import annotations

from dos_re.hooks import registry
from ..asset_codecs import (
    compare_overlay_entry_name_05d9,
    compare_overlay_signature_0582,
    compute_overkill_file_checksum,
    copy_lz_back_reference,
    decode_linear_byte_rle,
    decode_lz_asset,
    decode_overlay_xor,
    decode_vertical_rle_columns,
    decode_word_pair_rle,
    find_overlay_directory_entry_05a1,
    input_lz_byte,
    output_lz_byte,
    read_packed_byte_hook,
    read_packed_word_le_hook,
    search_decoded_asset_table_c713,
    strip_overlay_path_components_0701,
)
from ..file_io import open_overlay_container_entry_254a_04d7
from ..rendering.startup_graphics import (
    expand_4plane_block_4511,
    expand_4plane_list_450c,
    expand_4plane_row_4537,
    expand_bits_45cb,
    pack_four_pixels_45f6,
)


@registry.replace(0x1010, 0xC916, "overkill_file_checksum_loop_c916")
def overkill_file_checksum_loop_c916(cpu):
    """OVERKILL 1010:C916 file checksum loop."""
    compute_overkill_file_checksum(cpu)


@registry.replace(0x1010, 0x45F6, "overkill_pack_four_pixels_45f6")
def overkill_pack_four_pixels_45f6(cpu):
    """OVERKILL 1010:45F6 startup graphics pixel packer."""
    pack_four_pixels_45f6(cpu)


@registry.replace(0x1010, 0x0624, "overkill_packed_read_byte_0624")
def overkill_packed_read_byte_0624(cpu):
    """OVERKILL 1010:0624 packed byte reader."""
    read_packed_byte_hook(cpu)


@registry.replace(0x1010, 0x0615, "overkill_packed_read_word_le_0615")
def overkill_packed_read_word_le_0615(cpu):
    """OVERKILL 1010:0615 little-endian packed word reader."""
    read_packed_word_le_hook(cpu)


@registry.replace(0x1010, 0x45CB, "overkill_expand_bits_45cb")
def overkill_expand_bits_45cb(cpu):
    """OVERKILL 1010:45CB startup graphics bit expander."""
    expand_bits_45cb(cpu)


@registry.replace(0x1010, 0xC713, "overkill_decoded_asset_table_search_c713")
def overkill_decoded_asset_table_search_c713(cpu):
    """OVERKILL 1010:C713 decoded-asset table search loop."""
    search_decoded_asset_table_c713(cpu)


@registry.replace(0x1010, 0x03A8, "overkill_vertical_rle_decoder_03a8")
def overkill_vertical_rle_decoder_03a8(cpu):
    """OVERKILL 1010:03A8 vertical startup RLE decoder."""
    decode_vertical_rle_columns(cpu)


@registry.replace(0x1010, 0x4511, "overkill_expand_4plane_block_4511")
def overkill_expand_4plane_block_4511(cpu):
    """OVERKILL 1010:4511 4-plane startup block expander."""
    expand_4plane_block_4511(cpu)


@registry.replace(0x1010, 0xEDE9, "overkill_lz_output_byte_ede9")
def overkill_lz_output_byte_ede9(cpu):
    """OVERKILL 1010:EDE9 LZ byte-output helper."""
    output_lz_byte(cpu)


@registry.replace(0x1010, 0xED97, "overkill_lz_input_byte_ed97")
def overkill_lz_input_byte_ed97(cpu):
    """OVERKILL 1010:ED97 LZ byte-input helper."""
    input_lz_byte(cpu)


@registry.replace(0x254A, 0x04D7, "overkill_overlay_container_open_entry_254a_04d7")
def overkill_overlay_container_open_entry_254a_04d7(cpu):
    """OVERKILL 254A:04D7 overlay/container file-open parent."""
    open_overlay_container_entry_254a_04d7(cpu)


@registry.replace(0x254A, 0x05A1, "overkill_overlay_directory_entry_scan_254a_05a1")
def overkill_overlay_directory_entry_scan_254a_05a1(cpu):
    """OVERKILL 254A:05A1 overlay directory-entry scan loop."""
    find_overlay_directory_entry_05a1(cpu)


@registry.replace(0x254A, 0x05BF, "overkill_overlay_xor_decode_254a_05bf")
def overkill_overlay_xor_decode_254a_05bf(cpu):
    """OVERKILL 254A:05BF overlay XOR decoder."""
    decode_overlay_xor(cpu)


@registry.replace(0x254A, 0x0582, "overkill_overlay_signature_compare_254a_0582")
def overkill_overlay_signature_compare_254a_0582(cpu):
    """OVERKILL 254A:0582 overlay signature compare loop."""
    compare_overlay_signature_0582(cpu)


@registry.replace(0x254A, 0x05D9, "overkill_overlay_entry_name_compare_254a_05d9")
def overkill_overlay_entry_name_compare_254a_05d9(cpu):
    """OVERKILL 254A:05D9 overlay directory-name compare loop."""
    compare_overlay_entry_name_05d9(cpu)


@registry.replace(0x254A, 0x0701, "overkill_overlay_path_normalizer_254a_0701")
def overkill_overlay_path_normalizer_254a_0701(cpu):
    """OVERKILL 254A:0701 overlay path-component normalizer."""
    strip_overlay_path_components_0701(cpu)


@registry.replace(0x1010, 0xED7A, "overkill_lz_backref_copy_ed7a")
def overkill_lz_backref_copy_ed7a(cpu):
    """OVERKILL 1010:ED7A LZ back-reference copy loop."""
    copy_lz_back_reference(cpu)


@registry.replace(0x1010, 0xECF2, "overkill_lz_decoder_ecf2")
def overkill_lz_decoder_ecf2(cpu):
    """OVERKILL 1010:ECF2 full LZ asset decoder."""
    decode_lz_asset(cpu)


@registry.replace(0x1010, 0x0367, "overkill_linear_byte_rle_decoder_0367")
def overkill_linear_byte_rle_decoder_0367(cpu):
    """OVERKILL 1010:0367 linear byte-RLE decoder."""
    decode_linear_byte_rle(cpu)


@registry.replace(0x1010, 0x0324, "overkill_word_pair_rle_decoder_0324")
def overkill_word_pair_rle_decoder_0324(cpu):
    """OVERKILL 1010:0324 word-pair RLE decoder."""
    decode_word_pair_rle(cpu)


@registry.replace(0x1010, 0x4537, "overkill_expand_4plane_row_4537")
def overkill_expand_4plane_row_4537(cpu):
    """OVERKILL 1010:4537 4-plane startup row expander."""
    expand_4plane_row_4537(cpu)


@registry.replace(0x1010, 0x450C, "overkill_expand_4plane_list_450c")
def overkill_expand_4plane_list_450c(cpu):
    """OVERKILL 1010:450C 4-plane startup list expander."""
    expand_4plane_list_450c(cpu)

__all__ = [name for name in globals() if name.startswith("overkill_")]
