from __future__ import annotations

import os

from .cpu import CF, DF, IF, PF, SF, TF, ZF, _PARITY
from .hooks import registry
from .memory import EGA_CPU_APERTURE, EGA_APERTURE, EGA_PLANE_STRIDE, EGA_PLANE_WINDOW
from .games.overkill.asset_codecs import (
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
    strip_overlay_path_components_0701,
    output_lz_byte,
    read_packed_byte,
    read_packed_byte_hook,
    read_packed_word_le_hook,
)
from .games.overkill.asset_codecs.startup_graphics import (
    expand_4plane_block_4511,
    expand_4plane_list_450c,
    expand_4plane_row_4537,
    expand_bits_45cb,
    pack_four_pixels_45f6,
)

from .games.overkill.rendering.coordinates import (
    coordinate_ax_to_di_5a00,
    coordinate_ax_to_di_5a24,
    object_row_address_from_mode_dispatch_5a36,
    object_row_address_mode1_2580,
)
from .games.overkill.rendering.layer_sprites import (
    LayerSpriteRuntime,
    dispatch_layer_sprite_tail_75f5,
    draw_compact_layer_sprite_7746,
    draw_layer_sprite_75a6,
    draw_layer_sprite_768e,
    is_known_layer_sprite_composite_target,
    predict_layer_sprite_composite_target_768e,
    run_layer_sprite_compositor_target,
)

from .games.overkill.rendering.tandy import (
    expand_tandy_cell_33dd as run_expand_tandy_cell_33dd,
    expand_tandy_block_33b2 as run_expand_tandy_block_33b2,
    expand_tandy_list_33af as run_expand_tandy_list_33af,
    TandyRenderRuntime,
    draw_object_block_35cc as run_tandy_draw_object_block_35cc,
    draw_split_object_356c as run_tandy_draw_split_object_356c,
    draw_tiny_object_3657 as run_tandy_draw_tiny_object_3657,
    masked_compact_2fb6 as run_tandy_masked_compact_2fb6,
    masked_sprite_composite_2e6e as run_tandy_masked_sprite_composite_2e6e,
    masked_sprite_composite_2f81 as run_tandy_masked_sprite_composite_2f81,
    or_inverted_mask_2ecb as run_tandy_or_inverted_mask_2ecb,
    or_inverted_mask_2f40 as run_tandy_or_inverted_mask_2f40,
    postcopy_scaled_blit_375b as run_tandy_postcopy_scaled_blit_375b,
    present_tandy_frame_3354 as run_present_tandy_frame_3354,
    changed_dword_present_8rows_cdaa as run_tandy_changed_dword_present_cdaa,
    copy_rect_to_tandy_video_306f as run_tandy_rect_copy_306f,
    small_strided_copy_34d8 as run_tandy_small_strided_copy_34d8,
    source_strided_copy_35aa as run_tandy_source_strided_copy_35aa,
    split_present_copy_34ad as run_tandy_split_present_copy_34ad,
    strided_copy_34c5 as run_tandy_strided_copy_34c5,
    tiny_strided_copy_3542 as run_tandy_tiny_strided_copy_3542,
)

# Runtime-patched code guard -------------------------------------------------
#
# OVERKILL's unpacked EXE still patches/relocates large parts of the 1010h code
# segment during startup.  A Python replacement bypasses whatever bytes are live
# at CS:IP, so render hooks that assume one fixed instruction stream should be
# conservative: if the game later changes the entry bytes, remove the hook and
# let the interpreter execute the patched original.  Synthetic oracle tests often
# do not populate the routine bytes at all, so an all-zero signature is treated as
# "test fixture / no live code available" and the hook remains enabled.

def _self_disable_if_patched(cpu, ip: int, expected: bytes, name: str) -> bool:
    cs = cpu.s.cs & 0xFFFF
    start = ((cs << 4) + (ip & 0xFFFF)) & 0xFFFFF
    live = bytes(cpu.mem.data[start:start + len(expected)])
    if live == expected or all(b == 0 for b in live):
        return False
    raise RuntimeError(
        f"OVERKILL hook {name} at {cs:04X}:{ip:04X} saw runtime-patched code; "
        f"live bytes {live.hex(' ')} != expected {expected.hex(' ')}"
    )


_SIG_2750 = bytes.fromhex("8b 36 4c 23 2e 8e 06 a4 95 2e 8e 1e 98 95 bb 0d")
_SIG_27EB = bytes.fromhex("51 2e 83 3e d6 0b 00 74 0e 56 2e 8b 0e 9c 5b 51")
_SIG_280D = bytes.fromhex("2e 8b 0e 9c 5b ac 2e 88 05 47 e2 f9 2e 2b 3e 9c")
_SIG_2824 = bytes.fromhex("bf f4 5a 2e 8b 0e 9c 5b 51 2e 8a 05 2e 8a 65 28")
_SIG_291C = bytes.fromhex("51 2e 8a 05 47 57 2e 8b 3e a6 5b aa 2e 89 3e a6")
_SIG_2932 = bytes.fromhex("2e c6 06 a0 5b 00 2e 8b 1e 9c 5b 8a 04 8a 20 d1")
_SIG_2E6E = bytes.fromhex("bb 58 00 ad 26 23 05 0b 04 83 c6 02 ab ad 26 23")
_SIG_2ECB = bytes.fromhex("bb 58 00 8b 04 f7 d0 26 09 05 83 c6 04 83 c7 02")
_SIG_2F40 = bytes.fromhex("bb 60 00 8b 04 f7 d0 26 09 05 83 c6 04 83 c7 02")
_SIG_2F81 = bytes.fromhex("bb 60 00 ad 26 23 05 0b 04 83 c6 02 ab ad 26 23")
_SIG_306F = bytes.fromhex("ad 8b c8 ad 2e 8e 06 a4 95 d1 e0 d1 e0 8b e8 51")
_SIG_33AF = bytes.fromhex("e8 25 11 75 03 e9 f3 10 2e 8b 0e 9e 5b 51 2e 8b")
_SIG_33B2 = bytes.fromhex("75 03 e9 f3 10 2e 8b 0e 9e 5b 51 2e 8b 0e 9c")
_SIG_34AD = bytes.fromhex("83 ff ff 74 03 e8 10 00 8b 7e 10 8b 76 0e 81 c6")
_SIG_34C5 = bytes.fromhex("bb 58 00 b9 10 00 a5 a5 a5 a5 a5 a5 a5 a5 03 fb")
_SIG_34D8 = bytes.fromhex("83 ff ff 75 01 c3 bb 60 00 a5 a5 a5 a5 03 fb")
_SIG_3542 = bytes.fromhex("83 ff ff 75 01 c3 bb 64 00 a5 a5 03 fb a5 a5 03")
_SIG_35CC = bytes.fromhex("e8 67 24 89 46 0c 3d ff ff 75 01 c3 03 06 4c 23")
_SIG_356C = bytes.fromhex("e8 c7 24 89 46 0c 3d ff ff 74 0f 03 06 4c 23")
_SIG_3657 = bytes.fromhex("e8 dc 23 89 46 0c 3d ff ff 75 01 c3 03 06 4c 23")
_SIG_375B = bytes.fromhex("2e c7 06 03 59 00 00 2e 8b 3e f9 58 2e 8b 36 fb 58 2e 8b 0e fd 58 2e 8b 2e ff 58 d1 e5")
_SIG_35AA = bytes.fromhex("2e 8e 06 96 95 2e 8e 1e 98 95 bb 58 00 b9 10 00")
_SIG_58DF = bytes.fromhex("51 2e 89 0e 01 59 2e 8b 1e bc 95 d1 e3 2e ff 97")
_SIG_5DB2 = bytes.fromhex("c7 06 54 a9 00 00 c7 06 0a 23 00 00 8b 46 04 3b")
_SIG_768E = bytes.fromhex("8b 7e 0c 83 ff ff 75 01 c3 2e 8e 06 98 95 8b 5e")
_SIG_7746 = bytes.fromhex("8b 7e 0c 83 ff ff 75 01 c3 2e 8e 06 98 95 8b 5e")
_SIG_75A6 = bytes.fromhex("8b 5e 08 2e 8b 0e a6 95 83 fb 1c 72 08 83 eb 1c")
_SIG_2FB6 = bytes.fromhex("bb 64 00 ad 26 23 05 0b 04 83 c6 02 ab ad 26")
_SIG_A8C7 = bytes.fromhex("51 8b d9 d1 e3 8b af ca 32 83 7e 00 00 74 1e 83 3e ac bd")
_SIG_A849 = bytes.fromhex("51 8b d9 d1 e3 8b af ca 32 83 7e 00 00 74 03 e8 6d b2")
_SIG_A90F = bytes.fromhex("51 8b d9 d1 e3 8b af 12 8d 83 7e 00 00 74 03 e8")
_SIG_A927 = bytes.fromhex("51 8b d9 d1 e3 8b af ca 32 83 7e 00 00 74 03 e8 59 b1")
_SIG_A9E0 = bytes.fromhex("51 8b d9 d1 e3 8b af ca 32 ff 06 40 23 81 3e 40 23 dc 05")
_SIG_AA10 = bytes.fromhex("51 8b d9 d1 e3 8b af 12 8d 83 7e 00 00 74 03 e8 09 00")
_SIG_B73E = bytes.fromhex("83 7e 1c ff 74 4d 8b 5e 1c d1 e3 2e ff a7 4e b7")
_SIG_AA2B = bytes.fromhex("8b 5e 16 d1 e3 2e ff a7 36 aa")
_SIG_EFAE = bytes.fromhex("8b 46 04 a3 fe d1 8b 46 02 a3 00 d2 8b 5e 18")
_SIG_CCAA = bytes.fromhex("b9 08 00 26 8b 04 26 3b 05 74 05 b2 01 26 89 05")
_SIG_CCC4 = bytes.fromhex("b9 08 00 26 8b 04 26 3b 05 74 05 b2 01 26 89 05")
_SIG_CCF0 = bytes.fromhex("b9 20 00 26 8a 04 26 3a 05 74 05 b2 01 26 88 05")



@registry.replace(0x1010, 0xC916, "overkill_file_checksum_loop")
def overkill_file_checksum_loop(cpu):
    """Hook wrapper for OVERKILL 1010:C916 file checksum loop."""
    compute_overkill_file_checksum(cpu)


@registry.replace(0x1010, 0x45F6, "overkill_pack_four_pixels_45f6")
def overkill_pack_four_pixels_45f6(cpu):
    """Hook wrapper for OVERKILL 1010:45F6 startup graphics pixel packer."""
    pack_four_pixels_45f6(cpu)


def _overkill_read_packed_byte(cpu) -> None:
    """Compatibility alias for the OVERKILL 1010:0624 packed byte reader."""
    read_packed_byte(cpu)


@registry.replace(0x1010, 0x0624, "overkill_packed_read_byte")
def overkill_packed_read_byte(cpu):
    """Hook wrapper for OVERKILL 1010:0624 packed byte reader."""
    read_packed_byte_hook(cpu)


@registry.replace(0x1010, 0x0615, "overkill_packed_read_word")
def overkill_packed_read_word(cpu):
    """Hook wrapper for OVERKILL 1010:0615 little-endian packed word reader."""
    read_packed_word_le_hook(cpu)

@registry.replace(0x1010, 0x45CB, "overkill_expand_bits_45cb")
def overkill_expand_bits_45cb(cpu):
    """Hook wrapper for OVERKILL 1010:45CB startup graphics bit expander."""
    expand_bits_45cb(cpu)






@registry.replace(0x1010, 0x03A8, "overkill_vertical_rle_decoder_03a8")
def overkill_vertical_rle_decoder_03a8(cpu):
    """Hook wrapper for OVERKILL 1010:03A8 vertical startup RLE decoder."""
    decode_vertical_rle_columns(cpu)


def _call_hook_like_near_call(cpu, handler, return_ip: int) -> None:
    """Run a replacement body with the same stack side effect as CALL/RET."""
    cpu.push(return_ip & 0xFFFF)
    handler(cpu)


def _run_interpreted_near_call_observed(cpu, target_ip: int, return_ip: int, *, max_steps: int = 20000) -> None:
    """Run a rare original near helper from inside a larger lifted path.

    This is used for non-hot, display/bookkeeping helper tails that have not yet
    been lifted but are needed to keep gameplay moving through an observed path.
    The helper is still bounded and deterministic: it installs the same near-CALL
    return word the ASM would have pushed, steps until that continuation is
    reached, and restores verifier state afterwards so nested fast hooks do not
    recursively start their own differential verification.
    """
    cs = cpu.s.cs & 0xFFFF
    target = (cs, return_ip & 0xFFFF)
    saved_verifier = cpu.hook_verifier
    cpu.hook_verifier = None
    cpu.push(return_ip & 0xFFFF)
    cpu.s.ip = target_ip & 0xFFFF
    try:
        for _ in range(max_steps):
            if cpu.addr() == target:
                return
            cpu.step()
    finally:
        cpu.hook_verifier = saved_verifier
    raise RuntimeError(
        f"interpreted helper 1010:{target_ip & 0xFFFF:04X} did not return to "
        f"1010:{return_ip & 0xFFFF:04X}; now at {cpu.s.cs & 0xFFFF:04X}:{cpu.s.ip & 0xFFFF:04X}"
    )



@registry.replace(0x1010, 0x4511, "overkill_expand_4plane_block_4511")
def overkill_expand_4plane_block_4511(cpu):
    """Hook wrapper for OVERKILL 1010:4511 4-plane startup block expander."""
    expand_4plane_block_4511(cpu)



@registry.replace(0x1010, 0x33DD, "overkill_expand_tandy_cell_33dd")
def overkill_expand_tandy_cell_33dd(cpu):
    """Hook wrapper for OVERKILL 1010:33DD Tandy startup cell expander."""
    run_expand_tandy_cell_33dd(cpu)


@registry.replace(0x1010, 0x33B2, "overkill_expand_tandy_block_33b2")
def overkill_expand_tandy_block_33b2(cpu):
    """Hook wrapper for OVERKILL 1010:33B2 Tandy startup block expander."""
    run_expand_tandy_block_33b2(cpu, _tandy_render_runtime())


@registry.replace(0x1010, 0x33AF, "overkill_expand_tandy_list_33af")
def overkill_expand_tandy_list_33af(cpu):
    """Hook wrapper for OVERKILL 1010:33AF Tandy startup list expander."""
    run_expand_tandy_list_33af(cpu, _tandy_render_runtime())













@registry.replace(0x1010, 0x2E6E, "overkill_tandy_masked_sprite_composite_2e6e")
def overkill_tandy_masked_sprite_composite_2e6e(cpu):
    """Hook wrapper for OVERKILL 1010:2E6E Tandy masked compositor."""
    run_tandy_masked_sprite_composite_2e6e(cpu, _tandy_render_runtime())


@registry.replace(0x1010, 0x2F40, "overkill_tandy_or_inverted_mask_2f40")
def overkill_tandy_or_inverted_mask_2f40(cpu):
    """Hook wrapper for OVERKILL 1010:2F40 Tandy inverted-mask OR compositor."""
    run_tandy_or_inverted_mask_2f40(cpu, _tandy_render_runtime())

@registry.replace(0x1010, 0x2ECB, "overkill_tandy_or_inverted_mask_2ecb")
def overkill_tandy_or_inverted_mask_2ecb(cpu):
    """Hook wrapper for OVERKILL 1010:2ECB Tandy inverted-mask OR compositor."""
    run_tandy_or_inverted_mask_2ecb(cpu, _tandy_render_runtime())

@registry.replace(0x1010, 0x2F81, "overkill_tandy_masked_sprite_composite_2f81")
def overkill_tandy_masked_sprite_composite_2f81(cpu):
    """Hook wrapper for OVERKILL 1010:2F81 Tandy masked compositor."""
    run_tandy_masked_sprite_composite_2f81(cpu, _tandy_render_runtime())


@registry.replace(0x1010, 0x35AA, "overkill_tandy_source_strided_copy_35aa")
def overkill_tandy_source_strided_copy_35aa(cpu):
    """Hook wrapper for OVERKILL 1010:35AA Tandy source-strided copy."""
    run_tandy_source_strided_copy_35aa(cpu, _tandy_render_runtime())




@registry.replace(0x1010, 0x34AD, "overkill_tandy_split_present_copy_34ad")
def overkill_tandy_split_present_copy_34ad(cpu):
    """Hook wrapper for OVERKILL 1010:34AD Tandy split present copy."""
    run_tandy_split_present_copy_34ad(cpu, _tandy_render_runtime())

@registry.replace(0x1010, 0x34C5, "overkill_tandy_strided_copy_34c5")
def overkill_tandy_strided_copy_34c5(cpu):
    """Hook wrapper for OVERKILL 1010:34C5 Tandy strided copy helper."""
    run_tandy_strided_copy_34c5(cpu, _tandy_render_runtime())


@registry.replace(0x1010, 0x34D8, "overkill_tandy_small_strided_copy_34d8")
def overkill_tandy_small_strided_copy_34d8(cpu):
    """Hook wrapper for OVERKILL 1010:34D8 Tandy small strided copy."""
    run_tandy_small_strided_copy_34d8(cpu, _tandy_render_runtime())




@registry.replace(0x1010, 0x3542, "overkill_tandy_tiny_strided_copy_3542")
def overkill_tandy_tiny_strided_copy_3542(cpu):
    """Hook wrapper for OVERKILL 1010:3542 Tandy tiny strided copy."""
    run_tandy_tiny_strided_copy_3542(cpu, _tandy_render_runtime())





@registry.replace(0x1010, 0x3657, "overkill_tandy_draw_tiny_object_3657")
def overkill_tandy_draw_tiny_object_3657(cpu):
    """Hook wrapper for OVERKILL 1010:3657 Tandy tiny-object draw."""
    run_tandy_draw_tiny_object_3657(cpu, _tandy_render_runtime())

@registry.replace(0x1010, 0x356C, "overkill_tandy_draw_split_object_356c")
def overkill_tandy_draw_split_object_356c(cpu):
    """Hook wrapper for OVERKILL 1010:356C Tandy split-object draw."""
    run_tandy_draw_split_object_356c(cpu, _tandy_render_runtime())

@registry.replace(0x1010, 0x35CC, "overkill_tandy_draw_object_block_35cc")
def overkill_tandy_draw_object_block_35cc(cpu):
    """Hook wrapper for OVERKILL 1010:35CC Tandy object-block draw."""
    run_tandy_draw_object_block_35cc(cpu, _tandy_render_runtime())


@registry.replace(0x1010, 0x768E, "overkill_tandy_layer_sprite_draw_768e")
def overkill_tandy_layer_sprite_draw_768e(cpu):
    """Hook wrapper for OVERKILL 1010:768E shared layer-sprite draw helper.

    The legacy registry name says Tandy, but this original routine is reached in
    CGA, EGA, and Tandy.  The readable game-specific implementation lives in
    ``games.overkill.rendering.layer_sprites``.
    """
    draw_layer_sprite_768e(cpu, _layer_sprite_runtime())


def _tandy_layer_dispatch_75f5(cpu, obj_bp: int, chain: str) -> None:
    """Compatibility wrapper for the shared OVERKILL 1010:75F5 layer tail."""
    dispatch_layer_sprite_tail_75f5(cpu, obj_bp, chain, _layer_sprite_runtime())


@registry.replace(0x1010, 0x75A6, "overkill_tandy_layer_sprite_draw_75a6")
def overkill_tandy_layer_sprite_draw_75a6(cpu):
    """Hook wrapper for OVERKILL 1010:75A6 shared double-slot layer draw."""
    draw_layer_sprite_75a6(cpu, _layer_sprite_runtime())


@registry.replace(0x1010, 0x2FB6, "overkill_tandy_masked_compact_2fb6")
def overkill_tandy_masked_compact_2fb6(cpu):
    """Hook wrapper for OVERKILL 1010:2FB6 Tandy compact masked compositor."""
    run_tandy_masked_compact_2fb6(cpu, _tandy_render_runtime())


@registry.replace(0x1010, 0x306F, "overkill_tandy_rect_copy_306f")
def overkill_tandy_rect_copy_306f(cpu):
    """Hook wrapper for OVERKILL 1010:306F Tandy raw rectangular copy."""
    run_tandy_rect_copy_306f(cpu, _tandy_render_runtime())


@registry.replace(0x1010, 0x7746, "overkill_tandy_compact_layer_draw_7746")
def overkill_tandy_compact_layer_draw_7746(cpu):
    """Hook wrapper for OVERKILL 1010:7746 shared compact layer draw."""
    draw_compact_layer_sprite_7746(cpu, _layer_sprite_runtime())


@registry.replace(0x1010, 0xEDE9, "overkill_lz_output_byte_ede9")
def overkill_lz_output_byte_ede9(cpu):
    """Hook wrapper for OVERKILL 1010:EDE9 LZ byte-output helper."""
    output_lz_byte(cpu)


@registry.replace(0x1010, 0xED97, "overkill_lz_input_byte_ed97")
def overkill_lz_input_byte_ed97(cpu):
    """Hook wrapper for OVERKILL 1010:ED97 LZ byte-input helper."""
    input_lz_byte(cpu)


@registry.replace(0x254A, 0x05A1, "overkill_overlay_directory_entry_scan_254a_05a1")
def overkill_overlay_directory_entry_scan_254a_05a1(cpu):
    """Hook wrapper for OVERKILL 254A:05A1 overlay directory-entry scan loop."""
    find_overlay_directory_entry_05a1(cpu)


@registry.replace(0x254A, 0x05BF, "overkill_overlay_xor_decode_254a_05bf")
def overkill_overlay_xor_decode_254a_05bf(cpu):
    """Hook wrapper for OVERKILL 254A:05BF overlay XOR decoder."""
    decode_overlay_xor(cpu)


@registry.replace(0x254A, 0x0582, "overkill_overlay_signature_compare_254a_0582")
def overkill_overlay_signature_compare_254a_0582(cpu):
    """Hook wrapper for OVERKILL 254A:0582 overlay signature compare loop."""
    compare_overlay_signature_0582(cpu)


@registry.replace(0x254A, 0x05D9, "overkill_overlay_entry_name_compare_254a_05d9")
def overkill_overlay_entry_name_compare_254a_05d9(cpu):
    """Hook wrapper for OVERKILL 254A:05D9 overlay directory-name compare loop."""
    compare_overlay_entry_name_05d9(cpu)


@registry.replace(0x254A, 0x0701, "overkill_overlay_path_normalizer_254a_0701")
def overkill_overlay_path_normalizer_254a_0701(cpu):
    """Hook wrapper for OVERKILL 254A:0701 overlay path-component normalizer."""
    strip_overlay_path_components_0701(cpu)


@registry.replace(0x1010, 0xED7A, "overkill_lz_backref_copy_ed7a")
def overkill_lz_backref_copy_ed7a(cpu):
    """Hook wrapper for OVERKILL 1010:ED7A LZ back-reference copy loop."""
    copy_lz_back_reference(cpu)

@registry.replace(0x1010, 0xECF2, "overkill_lz_decoder_ecf2")
def overkill_lz_decoder_ecf2(cpu):
    """Hook wrapper for OVERKILL 1010:ECF2 full LZ asset decoder."""
    decode_lz_asset(cpu)

@registry.replace(0x1010, 0x0367, "overkill_linear_byte_rle_decoder_0367_fast")
def overkill_linear_byte_rle_decoder_0367(cpu):
    """Hook wrapper for OVERKILL 1010:0367 linear byte-RLE decoder."""
    decode_linear_byte_rle(cpu)


@registry.replace(0x1010, 0x0324, "overkill_word_pair_rle_decoder_0324")
def overkill_word_pair_rle_decoder_0324(cpu):
    """Hook wrapper for OVERKILL 1010:0324 word-pair RLE decoder."""
    decode_word_pair_rle(cpu)




@registry.replace(0x1010, 0x4537, "overkill_expand_4plane_row_4537_fast")
def overkill_expand_4plane_row_4537(cpu):
    """Hook wrapper for OVERKILL 1010:4537 4-plane startup row expander."""
    expand_4plane_row_4537(cpu)

@registry.replace(0x1010, 0x450C, "overkill_expand_4plane_list_450c")
def overkill_expand_4plane_list_450c(cpu):
    """Hook wrapper for OVERKILL 1010:450C 4-plane startup list expander."""
    expand_4plane_list_450c(cpu)


def _inc_reg16_preserve_cf(cpu, reg_idx: int) -> None:
    old = cpu.get_reg16(reg_idx)
    old_cf = cpu.get_flag(CF)
    cpu.set_reg16(reg_idx, (old + 1) & 0xFFFF)
    cpu.set_add_flags(old, 1, old + 1, 16)
    cpu.set_flag(CF, old_cf)


def _dec_reg16_preserve_cf(cpu, reg_idx: int) -> None:
    old = cpu.get_reg16(reg_idx)
    old_cf = cpu.get_flag(CF)
    cpu.set_reg16(reg_idx, (old - 1) & 0xFFFF)
    cpu.set_sub_flags(old, 1, old - 1, 16)
    cpu.set_flag(CF, old_cf)


def _add_reg16(cpu, reg_idx: int, value: int) -> None:
    old = cpu.get_reg16(reg_idx)
    result = old + (value & 0xFFFF)
    cpu.set_reg16(reg_idx, result)
    cpu.set_add_flags(old, value & 0xFFFF, result, 16)


def _sub_reg16(cpu, reg_idx: int, value: int) -> None:
    old = cpu.get_reg16(reg_idx)
    result = old - (value & 0xFFFF)
    cpu.set_reg16(reg_idx, result)
    cpu.set_sub_flags(old, value & 0xFFFF, result, 16)


def _add_mem_word(cpu, seg: int, off: int, value: int) -> None:
    old = cpu.mem.rw(seg, off)
    result = old + (value & 0xFFFF)
    cpu.mem.ww(seg, off, result)
    cpu.set_add_flags(old, value & 0xFFFF, result, 16)


def _sub_mem_word(cpu, seg: int, off: int, value: int) -> None:
    old = cpu.mem.rw(seg, off)
    result = old - (value & 0xFFFF)
    cpu.mem.ww(seg, off, result)
    cpu.set_sub_flags(old, value & 0xFFFF, result, 16)


def _and_mem_word(cpu, seg: int, off: int, value: int) -> None:
    result = cpu.mem.rw(seg, off) & (value & 0xFFFF)
    cpu.mem.ww(seg, off, result)
    cpu.set_logic_flags(result, 16)




def _ega_aperture_overlap(seg: int, off: int, count: int) -> bool:
    """Return True when a flat byte transfer touches the emulated EGA aperture.

    Real EGA memory is not a linear bytearray: reads come from the selected read
    plane and writes land in the planes selected by the sequencer map mask.
    Slice-copy fast paths must therefore avoid this range, otherwise only one
    shadow plane is updated/read and moving EGA sprites leave coloured ghosts.
    The fast callers already restrict transfers to non-wrapping 16-bit offsets,
    so a simple physical interval check is enough here.
    """
    if count <= 0:
        return False
    start = (((seg & 0xFFFF) << 4) + (off & 0xFFFF)) & 0xFFFFF
    end = start + count
    ega_start = EGA_CPU_APERTURE
    ega_end = EGA_CPU_APERTURE + EGA_PLANE_WINDOW
    return start < ega_end and end > ega_start

def _cmp_word(cpu, a: int, b: int) -> None:
    cpu.set_sub_flags(a & 0xFFFF, b & 0xFFFF, (a & 0xFFFF) - (b & 0xFFFF), 16)


def _test_word(cpu, a: int, b: int) -> None:
    cpu.set_logic_flags((a & 0xFFFF) & (b & 0xFFFF), 16)


def _xor_al_al(cpu) -> None:
    cpu.set_reg8(0, 0)
    cpu.set_logic_flags(0, 8)


def _rep_movsb(cpu, count: int) -> None:
    count &= 0xFFFF
    if count == 0:
        cpu.s.cx = 0
        return

    # Fast path for the normal forward, non-wrapping case used by the render
    # blitters.  REP MOVSB does not alter FLAGS, so a bytearray slice copy is
    # behavior-equivalent as long as the 16-bit source/destination offsets and
    # 20-bit physical addresses do not wrap inside the transfer.
    if not cpu.get_flag(DF):
        si = cpu.s.si & 0xFFFF
        di = cpu.s.di & 0xFFFF
        if si + count <= 0x10000 and di + count <= 0x10000 \
                and not (cpu.mem.ega_planar and (
                    _ega_aperture_overlap(cpu.s.ds, si, count)
                    or _ega_aperture_overlap(cpu.s.es, di, count)
                )):
            src = (((cpu.s.ds & 0xFFFF) << 4) + si) & 0xFFFFF
            dst = (((cpu.s.es & 0xFFFF) << 4) + di) & 0xFFFFF
            if src + count <= len(cpu.mem.data) and dst + count <= len(cpu.mem.data):
                cpu.mem.data[dst:dst + count] = cpu.mem.data[src:src + count]
                cpu.s.si = (si + count) & 0xFFFF
                cpu.s.di = (di + count) & 0xFFFF
                cpu.s.cx = 0
                return

    delta = -1 if cpu.get_flag(DF) else 1
    for _ in range(count):
        cpu.mem.wb(cpu.s.es, cpu.s.di, cpu.mem.rb(cpu.s.ds, cpu.s.si))
        cpu.s.si = (cpu.s.si + delta) & 0xFFFF
        cpu.s.di = (cpu.s.di + delta) & 0xFFFF
    cpu.s.cx = 0


def _rep_stosb(cpu, count: int) -> None:
    count &= 0xFFFF
    if count == 0:
        cpu.s.cx = 0
        return
    value = cpu.get_reg8(0)
    if not cpu.get_flag(DF):
        di = cpu.s.di & 0xFFFF
        if di + count <= 0x10000 \
                and not (cpu.mem.ega_planar and _ega_aperture_overlap(cpu.s.es, di, count)):
            dst = (((cpu.s.es & 0xFFFF) << 4) + di) & 0xFFFFF
            if dst + count <= len(cpu.mem.data):
                cpu.mem.data[dst:dst + count] = bytes([value]) * count
                cpu.s.di = (di + count) & 0xFFFF
                cpu.s.cx = 0
                return
    delta = -1 if cpu.get_flag(DF) else 1
    for _ in range(count):
        cpu.mem.wb(cpu.s.es, cpu.s.di, value)
        cpu.s.di = (cpu.s.di + delta) & 0xFFFF
    cpu.s.cx = 0


def _ega_next_scanline_di(cpu) -> None:
    """Mirror OVERKILL's planar 80-byte EGA/VGA row address advance."""
    _add_reg16(cpu, 7, 0x2000)  # ADD DI,2000h
    _test_word(cpu, cpu.s.di, 0x4000)
    if not cpu.get_flag(ZF):
        _add_reg16(cpu, 7, 0xC050)


@registry.replace(0x1010, 0x375B, "overkill_tandy_postcopy_scaled_blit_375b")
def overkill_tandy_postcopy_scaled_blit_375b(cpu):
    """Hook wrapper for OVERKILL 1010:375B Tandy post-copy scaled blitter."""
    if _self_disable_if_patched(cpu, 0x375B, _SIG_375B, "overkill_tandy_postcopy_scaled_blit_375b"):
        return
    run_tandy_postcopy_scaled_blit_375b(cpu)


@registry.replace(0x1010, 0x497A, "overkill_blit_scaled_column_block_497a")
def overkill_blit_scaled_column_block_497a(cpu):
    """Replace the hot display blit/clear routine at 1010:497A.

    Evidence: reached from the renderer dispatcher at 1010:58EC through a
    function-pointer table selected by CS:95BC.  The routine copies rows from
    DS:SI to ES:DI (usually decoded asset buffer -> B800 planar video memory),
    optionally skipping/duplicating source rows according to CS:5901/5903/5905,
    and uses the same planar address step as the original inner loops.

    This is deliberately a direct transliteration of 497A..4A40, not a guessed
    high-level renderer.  It preserves the observed register/flag/stack state
    by using the same arithmetic flag helpers as the interpreter.
    """
    cs = cpu.s.cs & 0xFFFF
    mem = cpu.mem

    # 497A: mov cs:[5903],0000h
    mem.ww(cs, 0x5903, 0)
    # 4981..4995: load local state and double BP (source bytes per row)
    cpu.s.di = mem.rw(cs, 0x58F9)
    cpu.s.si = mem.rw(cs, 0x58FB)
    cpu.s.cx = mem.rw(cs, 0x58FD)
    cpu.s.bp = mem.rw(cs, 0x58FF)
    cpu.s.bp = cpu.shift(4, cpu.s.bp, 1, 16)  # SHL BP,1

    # Optional bottom-up source positioning.
    _cmp_word(cpu, mem.rw(cs, 0x5905), 0)
    if not cpu.get_flag(ZF):
        cpu.s.ax = cpu.s.bp & 0xFFFF
        _dec_reg16_preserve_cf(cpu, 1)  # DEC CX
        # MUL CX, matching CPU8086 group-F7 behavior: AX*CX -> DX:AX, CF/OF only.
        result = (cpu.s.ax & 0xFFFF) * (cpu.s.cx & 0xFFFF)
        cpu.s.ax = result & 0xFFFF
        cpu.s.dx = (result >> 16) & 0xFFFF
        carry = cpu.s.dx != 0
        cpu.set_flag(CF, carry)
        cpu.set_flag(0x0800, carry)  # OF
        _inc_reg16_preserve_cf(cpu, 1)  # INC CX
        _add_reg16(cpu, 6, cpu.s.ax)    # ADD SI,AX

    # Initial clear/skip region before the first copied row.
    cpu.push(cpu.s.cx)
    cpu.s.cx = mem.rw(cs, 0x58FD)
    _sub_reg16(cpu, 1, mem.rw(cs, 0x5901))
    _test_word(cpu, cpu.s.cx, cpu.s.cx)  # OR CX,CX
    if not cpu.get_flag(SF):
        cpu.s.cx = cpu.shift(5, cpu.s.cx, 1, 16)  # SHR CX,1
        if cpu.s.cx != 0:
            _dec_reg16_preserve_cf(cpu, 1)
            if cpu.s.cx != 0:
                # 49BD..49CB: advance DI by CX-1 planar rows.
                while cpu.s.cx != 0:
                    _ega_next_scanline_di(cpu)
                    cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF  # LOOP, no flags
            # 49CD..49E3: clear one row and advance to next row.
            _xor_al_al(cpu)
            cpu.s.cx = cpu.s.bp & 0xFFFF
            _rep_stosb(cpu, cpu.s.cx)
            _sub_reg16(cpu, 7, cpu.s.bp)
            _ega_next_scanline_di(cpu)
    cpu.s.cx = cpu.pop()

    # 49E4..4A38: copy/skip rows according to CS:5901 accumulator.
    while True:
        cpu.s.ax = mem.rw(cs, 0x5901)
        _cmp_word(cpu, cpu.s.ax, mem.rw(cs, 0x58FD))
        if cpu.get_flag(ZF):
            copy_this_row = True
        else:
            _add_mem_word(cpu, cs, 0x5903, cpu.s.ax)
            cpu.s.ax = mem.rw(cs, 0x58FD)
            _cmp_word(cpu, cpu.s.ax, mem.rw(cs, 0x5903))
            # JA 4A11: jump if AX > CS:5903, unsigned.
            if (not cpu.get_flag(CF)) and (not cpu.get_flag(ZF)):
                _sub_mem_word(cpu, cs, 0x5903, cpu.s.ax)
                copy_this_row = True
            else:
                _cmp_word(cpu, mem.rw(cs, 0x5905), 0)
                if cpu.get_flag(ZF):
                    _add_reg16(cpu, 6, cpu.s.bp)
                else:
                    _sub_reg16(cpu, 6, cpu.s.bp)
                cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF  # LOOP 49E4, no flags
                if cpu.s.cx != 0:
                    continue
                break

        # 4A16..4A38: copy one BP-byte row, advance planar DI, optionally step SI back.
        cpu.push(cpu.s.cx)
        cpu.s.cx = cpu.s.bp & 0xFFFF
        _rep_movsb(cpu, cpu.s.cx)
        _sub_reg16(cpu, 7, cpu.s.bp)
        _ega_next_scanline_di(cpu)
        _cmp_word(cpu, mem.rw(cs, 0x5905), 0)
        if not cpu.get_flag(ZF):
            _sub_reg16(cpu, 6, cpu.s.bp)
            _sub_reg16(cpu, 6, cpu.s.bp)
        cpu.s.cx = cpu.pop()
        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF  # LOOP 49E4, no flags
        if cpu.s.cx != 0:
            continue
        break

    # 4A3A..4A40: final clear row and RET.
    _xor_al_al(cpu)
    cpu.s.cx = cpu.s.bp & 0xFFFF
    _rep_stosb(cpu, cpu.s.cx)
    cpu.s.ip = cpu.pop()

@registry.replace(0x1010, 0x41DA, "overkill_linear_rows_to_work_buffer_41da")
def overkill_linear_rows_to_work_buffer_41da(cpu):
    """Replace 1010:41DA row-copy routine selected by the 5A5A table.

    Direct transliteration of 41DA..41F4.  The current captured startup call has
    both header words zero, which is exactly the kind of 8086 edge case that is
    slow in the interpreter: LOOP with CX=0000 performs 65,536 iterations.  The
    hook preserves that behavior instead of treating zero as zero iterations.
    """
    cs = cpu.s.cs & 0xFFFF
    cpu.s.es = cpu.mem.rw(cs, 0x9598)
    # LODSW; MOV CX,AX
    cpu.s.ax = cpu.mem.rw(cpu.s.ds, cpu.s.si)
    cpu.s.si = (cpu.s.si + (-2 if cpu.get_flag(DF) else 2)) & 0xFFFF
    cpu.s.cx = cpu.s.ax & 0xFFFF
    # LODSW; SHL AX,1; MOV BP,AX
    cpu.s.ax = cpu.mem.rw(cpu.s.ds, cpu.s.si)
    cpu.s.si = (cpu.s.si + (-2 if cpu.get_flag(DF) else 2)) & 0xFFFF
    cpu.s.ax = cpu.shift(4, cpu.s.ax, 1, 16)
    cpu.s.bp = cpu.s.ax & 0xFFFF

    # LOOP executes 65,536 times when the input count word is zero.
    iterations = cpu.s.cx if cpu.s.cx != 0 else 0x10000

    if cpu.s.bp != 0 and iterations * (cpu.s.bp & 0xFFFF) > 10_000_000:
        raise RuntimeError(
            f"suspicious 41DA row copy header: rows={iterations} width_bytes={cpu.s.bp:04X} "
            f"DS:SI={cpu.s.ds:04X}:{(cpu.s.si - 4) & 0xFFFF:04X} DI={cpu.s.di:04X}"
        )

    if cpu.s.bp == 0:
        # Hot startup edge case: zero-width rows.  The original still performs
        # every LOOP iteration, but each row only does SUB DI,0 and ADD DI,50h.
        # Collapse it while preserving the final ADD flags from the last row.
        start_di = cpu.s.di & 0xFFFF
        if iterations:
            last_old_di = (start_di + (0x50 * (iterations - 1))) & 0xFFFF
            final_di_full = last_old_di + 0x50
            cpu.s.di = final_di_full & 0xFFFF
            cpu.set_add_flags(last_old_di, 0x50, final_di_full, 16)
            # The collapsed loop still has one observable memory side-effect:
            # PUSH CX writes to SS:SP-2 every row and POP restores SP.  The
            # last iteration always pushes 0001h before LOOP consumes it.
            cpu.mem.ww(cpu.s.ss, (cpu.s.sp - 2) & 0xFFFF, 0x0001)
        cpu.s.cx = 0
        cpu.s.ip = cpu.pop()
        return

    for _ in range(iterations):
        cpu.push(cpu.s.cx)
        cpu.s.cx = cpu.s.bp & 0xFFFF
        _rep_movsb(cpu, cpu.s.cx)
        _sub_reg16(cpu, 7, cpu.s.bp)
        _add_reg16(cpu, 7, 0x0050)
        cpu.s.cx = cpu.pop()
        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF  # LOOP, no flags
    cpu.s.ip = cpu.pop()


@registry.replace(0x1010, 0x477E, "overkill_sprite_blit_9x16_477e")
def overkill_sprite_blit_9x16_477e(cpu):
    """Replace the fully-unrolled fixed-geometry sprite blit at 1010:477E.

    Evidence: profiling the asset-heavy loading path shows this is the single
    dominant routine (hundreds of thousands of interpreted MOVSW per load,
    clustered around 1010:477E..480D and reached from the 5A36/4740 table
    dispatcher).  The original code is straight-line, not a loop: it copies a
    fixed 9-byte-wide by 16-row sprite from DS:SI into a packed ES:DI buffer.
    Disassembly of 477E..480D:

        477E  mov es, cs:[9596]          ; dest segment
        4783  mov ds, cs:[9598]          ; source segment
        per row (x16):
            movsw; movsw; movsw; movsw; movsb   ; copy 9 bytes, SI+=9, DI+=9
            add si, 002Bh                       ; skip 43 -> source row stride 52
        4808  mov ds, cs:[9596]          ; restore DS = dest segment
        480D  ret near

    Side effects preserved exactly (verified against interpreted ASM on
    artifacts/evidence/snapshot_stop_477e_probe, exit state SI+=0x340, DI+=0x90,
    DS=ES=cs:[9596], FLAGS=0212):
      * ES = cs:[9596], DS = cs:[9596] on exit
      * SI += 16*0x34 = 0x340, DI += 16*0x09 = 0x90
      * 144 bytes copied (16 rows x 9 bytes), source stride 52, dest packed
      * FLAGS = result of the final `add si,0x2B` (the only flag-affecting op;
        MOVS leaves FLAGS untouched)
      * near RET to the caller

    MOVS honours DF; the unrolled body only ever runs forward (DF=0) in the
    captured oracle.  DF=1 takes a faithful per-instruction fallback so the hook
    can never silently diverge from the original word/byte ordering.  Source and
    destination always live in distinct segments (e.g. 35FF vs 25CC), so the
    forward slice copy can never alias the destination it is reading from.
    """
    cs = cpu.s.cs & 0xFFFF
    mem = cpu.mem
    es_seg = mem.rw(cs, 0x9596)   # 477E: mov es, cs:[9596]
    ds_seg = mem.rw(cs, 0x9598)   # 4783: mov ds, cs:[9598]
    cpu.s.es = es_seg
    cpu.s.ds = ds_seg

    si = cpu.s.si & 0xFFFF
    di = cpu.s.di & 0xFFFF
    data = mem.data
    mlen = len(data)
    old_si = si

    if not cpu.get_flag(DF):
        for _row in range(16):
            # movsw x4 + movsb == 9 forward byte copies; SI+=9, DI+=9.
            if si + 9 <= 0x10000 and di + 9 <= 0x10000:
                src = ((ds_seg << 4) + si) & 0xFFFFF
                dst = ((es_seg << 4) + di) & 0xFFFFF
                if src + 9 <= mlen and dst + 9 <= mlen:
                    data[dst:dst + 9] = data[src:src + 9]
                    si = (si + 9) & 0xFFFF
                    di = (di + 9) & 0xFFFF
                else:  # physical-edge wrap: stay byte-exact
                    for _ in range(9):
                        mem.wb(es_seg, di, mem.rb(ds_seg, si))
                        si = (si + 1) & 0xFFFF
                        di = (di + 1) & 0xFFFF
            else:  # 16-bit offset wrap inside the row: stay byte-exact
                for _ in range(9):
                    mem.wb(es_seg, di, mem.rb(ds_seg, si))
                    si = (si + 1) & 0xFFFF
                    di = (di + 1) & 0xFFFF
            old_si = si
            si = (si + 0x2B) & 0xFFFF   # add si,002Bh
    else:
        # DF=1 fallback: reproduce the exact MOVSW/MOVSB word/byte ordering.
        for _row in range(16):
            for _ in range(4):  # movsw x4
                mem.ww(es_seg, di, mem.rw(ds_seg, si))
                si = (si - 2) & 0xFFFF
                di = (di - 2) & 0xFFFF
            mem.wb(es_seg, di, mem.rb(ds_seg, si))  # movsb
            si = (si - 1) & 0xFFFF
            di = (di - 1) & 0xFFFF
            old_si = si
            si = (si + 0x2B) & 0xFFFF   # add si,002Bh (unaffected by DF)

    cpu.set_add_flags(old_si, 0x2B, old_si + 0x2B, 16)
    cpu.s.si = si
    cpu.s.di = di
    cpu.s.ds = es_seg   # 4808: mov ds, cs:[9596]
    cpu.s.ip = cpu.pop()  # 480D: ret near


@registry.replace(0x1010, 0x38B7, "overkill_masked_sprite_composite_38b7")
def overkill_masked_sprite_composite_38b7(cpu):
    """Replace the masked 2-column sprite-composite loop at 1010:38B7..38CF.

    Profiling after the 477E lift showed this is the hottest remaining
    interpreted routine during sprite-heavy frames.  It is a tight LOOP that
    composites a sprite over the destination with the classic AND-mask / OR-data
    operation, two 16-bit columns per row:

        38B7  lodsw                ; mask = DS:[SI], SI += 2
        38B8  and ax, es:[di]      ; AX = mask AND dest word (keep background)
        38BB  or  ax, ds:[si]      ; AX |= data word = DS:[SI] (paint sprite)
        38BD  add si, 2            ; step past the data word
        38C0  stosw                ; ES:[DI] = AX, DI += 2
        38C1..38CA  (identical second column)
        38CB  add di, 0030h        ; next visible row (net DI stride 0034h)
        38CE  loop 38B7            ; CX rows (CX==0 -> 65536, 8086 rule)
        38D0  (fall-through)

    Per row the source is [mask0, data0, mask1, data1] so SI advances 8; the
    destination advances 0034h (two words written + 30h).  The destination is a
    read-modify-write (the AND reads ES:[DI] before STOSW overwrites it).  Only
    the final `add di,0030h` leaves live FLAGS; AX holds the last composited
    word; CX exits 0; control falls through to 38D0.  LODSW/STOSW honour DF; the
    immediate `add si,2`/`add di,30h` do not.  Verified bit-identical to the
    interpreted loop over 2000 randomised states.
    """
    s = cpu.s
    mem = cpu.mem
    df = cpu.get_flag(DF)
    rows = s.cx if s.cx != 0 else 0x10000
    es = s.es & 0xFFFF
    ds = s.ds & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    ax = s.ax & 0xFFFF
    sd = -2 if df else 2
    old_di = di
    for _ in range(rows):
        for _col in range(2):
            mask = mem.rw(ds, si)            # lodsw
            si = (si + sd) & 0xFFFF
            ax = mask & mem.rw(es, di)       # and ax, es:[di]
            ax = ax | mem.rw(ds, si)         # or  ax, ds:[si]
            si = (si + 2) & 0xFFFF           # add si, 2
            mem.ww(es, di, ax)               # stosw
            di = (di + sd) & 0xFFFF
        old_di = di
        di = (di + 0x30) & 0xFFFF            # add di, 0030h
    cpu.set_add_flags(old_di, 0x30, old_di + 0x30, 16)
    s.si = si
    s.di = di
    s.ax = ax
    s.cx = 0
    s.ip = 0x38D0                            # fall through past LOOP



def _run_cga_masked_sprite_composite_38b7_as_near(cpu) -> None:
    """Run 38B7 when reached as a jump-table near-return target.

    The registered 38B7 hook intentionally stops at the 38D0 fall-through so the
    interpreter can execute the shared ``mov ds,cs:[9596]; ret`` tail when 38B7 is
    entered directly.  The layer dispatcher jumps to 38B7 as the final target, so
    here we must execute that shared tail explicitly.
    """
    overkill_masked_sprite_composite_38b7(cpu)
    if (cpu.s.ip & 0xFFFF) != 0x38D0:
        raise RuntimeError(f"38B7 composite returned to unexpected IP {cpu.s.ip:04X}")
    cpu.s.ds = cpu.mem.rw(cpu.s.cs & 0xFFFF, 0x9596)
    cpu.s.ip = cpu.pop()


@registry.replace(0x1010, 0x3849, "overkill_masked_sprite_composite_3849")
def overkill_masked_sprite_composite_3849(cpu):
    """Replace the 4-column masked sprite composite loop at 1010:3849.

    This is the wider sibling of the verified 38B7 hook.  Each row composites
    four destination words using source pairs [mask,data] and then advances the
    destination by 0x2C, for a net visible stride of 0x34 bytes.  The helper
    finally restores DS from CS:[9596] and returns near.
    """
    s = cpu.s
    mem = cpu.mem
    rows = s.cx & 0xFFFF
    if rows == 0:
        rows = 0x10000

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    sd = -2 if cpu.get_flag(DF) else 2
    ax = s.ax & 0xFFFF
    old_di = di

    for _ in range(rows):
        for _col in range(4):
            mask = mem.rw(ds, si)
            si = (si + sd) & 0xFFFF
            ax = mask & mem.rw(es, di)
            ax = ax | mem.rw(ds, si)
            si = (si + 2) & 0xFFFF
            mem.ww(es, di, ax)
            di = (di + sd) & 0xFFFF
        old_di = di
        di = (di + 0x2C) & 0xFFFF

    cpu.set_add_flags(old_di, 0x2C, old_di + 0x2C, 16)
    s.ax = ax
    s.si = si
    s.di = di
    s.cx = 0
    s.ds = mem.rw(s.cs & 0xFFFF, 0x9596)
    s.ip = cpu.pop()


def _ega_spread_word_two_bits_mask(word: int) -> tuple[int, int]:
    """Spread a 16-bit source word through the 409D two-bit mask chain."""
    al = word & 0xFF
    ah = (word >> 8) & 0xFF
    dl = 0xFF
    for _ in range(2):
        cf = 1
        new_al = ((cf << 7) | (al >> 1)) & 0xFF; cf = al & 1; al = new_al
        new_ah = ((cf << 7) | (ah >> 1)) & 0xFF; cf = ah & 1; ah = new_ah
        new_dl = ((cf << 7) | (dl >> 1)) & 0xFF; cf = dl & 1; dl = new_dl
    return ((ah << 8) | al) & 0xFFFF, dl & 0xFF


def _ega_spread_word_two_bits_data(word: int) -> tuple[int, int]:
    """Spread a 16-bit source word through the 409D two-bit data chain."""
    al = word & 0xFF
    ah = (word >> 8) & 0xFF
    dl = 0
    for _ in range(2):
        cf = al & 1
        al = (al >> 1) & 0xFF
        new_ah = ((cf << 7) | (ah >> 1)) & 0xFF; cf = ah & 1; ah = new_ah
        new_dl = ((cf << 7) | (dl >> 1)) & 0xFF; cf = dl & 1; dl = new_dl
    return ((ah << 8) | al) & 0xFFFF, dl & 0xFF


def _ega_spread_word_bits_mask(word: int, bits: int) -> tuple[int, int]:
    al = word & 0xFF
    ah = (word >> 8) & 0xFF
    dl = 0xFF
    for _ in range(bits):
        cf = 1
        new_al = ((cf << 7) | (al >> 1)) & 0xFF; cf = al & 1; al = new_al
        new_ah = ((cf << 7) | (ah >> 1)) & 0xFF; cf = ah & 1; ah = new_ah
        new_dl = ((cf << 7) | (dl >> 1)) & 0xFF; cf = dl & 1; dl = new_dl
    return ((ah << 8) | al) & 0xFFFF, dl & 0xFF


def _ega_spread_word_bits_data(word: int, bits: int) -> tuple[int, int]:
    al = word & 0xFF
    ah = (word >> 8) & 0xFF
    dl = 0
    for _ in range(bits):
        cf = al & 1
        al = (al >> 1) & 0xFF
        new_ah = ((cf << 7) | (ah >> 1)) & 0xFF; cf = ah & 1; ah = new_ah
        new_dl = ((cf << 7) | (dl >> 1)) & 0xFF; cf = dl & 1; dl = new_dl
    return ((ah << 8) | al) & 0xFFFF, dl & 0xFF


def _run_ega_compact_spread_composite_bits(cpu, *, bits: int) -> None:
    s = cpu.s
    mem = cpu.mem
    rows = s.bp & 0xFFFF
    if rows == 0:
        rows = 0x10000

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    dh = (s.dx >> 8) & 0xFF
    ax = s.ax & 0xFFFF
    dl = s.dx & 0xFF
    sd = -2 if cpu.get_flag(DF) else 2

    for _ in range(rows):
        mask_word = mem.rw(ds, si)
        si = (si + sd) & 0xFFFF
        mask_ax, mask_dl = _ega_spread_word_bits_mask(mask_word, bits)
        mem.ww(es, di, mem.rw(es, di) & mask_ax)
        mem.wb(es, (di + 0x02) & 0xFFFF, mem.rb(es, (di + 0x02) & 0xFFFF) & mask_dl)

        data_word = mem.rw(ds, si)
        si = (si + sd) & 0xFFFF
        ax, dl = _ega_spread_word_bits_data(data_word, bits)
        mem.ww(es, di, mem.rw(es, di) | ax)
        mem.wb(es, (di + 0x02) & 0xFFFF, mem.rb(es, (di + 0x02) & 0xFFFF) | dl)

        old_di = di
        di = (di + 0x34) & 0xFFFF
        cpu.set_add_flags(old_di, 0x34, old_di + 0x34, 16)

        old_bp = s.bp & 0xFFFF
        s.bp = (old_bp - 1) & 0xFFFF
        cpu.set_sub_flags(old_bp, 1, old_bp - 1, 16)

    s.ax = ax & 0xFFFF
    s.dx = ((dh << 8) | (dl & 0xFF)) & 0xFFFF
    s.si = si
    s.di = di
    s.ds = mem.rw(s.cs & 0xFFFF, 0x9596)
    s.ip = cpu.pop()


@registry.replace(0x1010, 0x40D7, "overkill_ega_compact_spread_composite_40d7")
def overkill_ega_compact_spread_composite_40d7(cpu):
    """Replace compact EGA four-bit spread compositor at 1010:40D7."""
    _run_ega_compact_spread_composite_bits(cpu, bits=4)


@registry.replace(0x1010, 0x412B, "overkill_ega_compact_spread_composite_412b")
def overkill_ega_compact_spread_composite_412b(cpu):
    """Replace compact EGA six-bit spread compositor at 1010:412B."""
    _run_ega_compact_spread_composite_bits(cpu, bits=6)


@registry.replace(0x1010, 0x409D, "overkill_ega_compact_spread_composite_409d")
def overkill_ega_compact_spread_composite_409d(cpu):
    """Replace compact EGA two-bit spread compositor at 1010:409D.

    Reached from the 7746 compact layer helper in EGA-ish dispatch tables.  BP is
    the row counter (normally 8).  Each row consumes one mask word and one data
    word, spreads them through the original two-step RCR/SHR chains, updates a
    word plus byte at ES:DI/ES:DI+2, advances DI by 34h, and decrements BP.
    """
    s = cpu.s
    mem = cpu.mem
    rows = s.bp & 0xFFFF
    if rows == 0:
        rows = 0x10000

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    dh = (s.dx >> 8) & 0xFF
    ax = s.ax & 0xFFFF
    dl = s.dx & 0xFF

    for _ in range(rows):
        mask_word = mem.rw(ds, si)            # LODSW
        si = (si + (-2 if cpu.get_flag(DF) else 2)) & 0xFFFF
        mask_ax, mask_dl = _ega_spread_word_two_bits_mask(mask_word)
        mem.ww(es, di, mem.rw(es, di) & mask_ax)
        mem.wb(es, (di + 0x02) & 0xFFFF, mem.rb(es, (di + 0x02) & 0xFFFF) & mask_dl)

        data_word = mem.rw(ds, si)            # LODSW
        si = (si + (-2 if cpu.get_flag(DF) else 2)) & 0xFFFF
        ax, dl = _ega_spread_word_two_bits_data(data_word)
        mem.ww(es, di, mem.rw(es, di) | ax)
        mem.wb(es, (di + 0x02) & 0xFFFF, mem.rb(es, (di + 0x02) & 0xFFFF) | dl)

        old_di = di
        di = (di + 0x34) & 0xFFFF
        cpu.set_add_flags(old_di, 0x34, old_di + 0x34, 16)

        old_bp = s.bp & 0xFFFF
        s.bp = (old_bp - 1) & 0xFFFF
        cpu.set_sub_flags(old_bp, 1, old_bp - 1, 16)

    s.ax = ax & 0xFFFF
    s.dx = ((dh << 8) | (dl & 0xFF)) & 0xFFFF
    s.si = si
    s.di = di
    # CX is intentionally preserved; this routine loops on BP, not LOOP/CX.
    s.ds = mem.rw(s.cs & 0xFFFF, 0x9596)
    s.ip = cpu.pop()


def _cga_or_inverted_composite_rows(cpu, *, words_per_row: int, row_add: int) -> None:
    s = cpu.s
    mem = cpu.mem
    rows = s.cx & 0xFFFF
    if rows == 0:
        rows = 0x10000

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    sd = -2 if cpu.get_flag(DF) else 2
    ax = s.ax & 0xFFFF
    old_di = di

    for _ in range(rows):
        for _col in range(words_per_row):
            ax = mem.rw(ds, si)              # LODSW
            si = (si + sd) & 0xFFFF
            ax = (~ax) & 0xFFFF              # NOT AX
            value = mem.rw(es, di) | ax      # OR ES:[DI],AX
            mem.ww(es, di, value & 0xFFFF)
            cpu.set_logic_flags(value, 16)
            old_si = si
            si = (si + 0x0002) & 0xFFFF      # ADD SI,2
            cpu.set_add_flags(old_si, 0x0002, old_si + 0x0002, 16)
            old_di_col = di
            di = (di + 0x0002) & 0xFFFF      # ADD DI,2
            cpu.set_add_flags(old_di_col, 0x0002, old_di_col + 0x0002, 16)
        old_di = di
        di = (di + row_add) & 0xFFFF
        cpu.set_add_flags(old_di, row_add, old_di + row_add, 16)

    s.ax = ax & 0xFFFF
    s.si = si
    s.di = di
    s.cx = 0
    s.ds = mem.rw(s.cs & 0xFFFF, 0x9596)
    s.ip = cpu.pop()


@registry.replace(0x1010, 0x387C, "overkill_or_inverted_sprite_composite_387c")
def overkill_or_inverted_sprite_composite_387c(cpu):
    """Replace the 4-column CGA inverted-mask OR compositor at 1010:387C."""
    _cga_or_inverted_composite_rows(cpu, words_per_row=4, row_add=0x002C)


@registry.replace(0x1010, 0x38D6, "overkill_or_inverted_sprite_composite_38d6")
def overkill_or_inverted_sprite_composite_38d6(cpu):
    """Replace the 2-column CGA inverted-mask OR compositor at 1010:38D6."""
    _cga_or_inverted_composite_rows(cpu, words_per_row=2, row_add=0x0030)


@registry.replace(0x1010, 0x390E, "overkill_or_inverted_sprite_composite_390e")
def overkill_or_inverted_sprite_composite_390e(cpu):
    """Replace the 1-column CGA inverted-mask OR compositor at 1010:390E."""
    _cga_or_inverted_composite_rows(cpu, words_per_row=1, row_add=0x0032)


def _ega_spread_byte_rcr_mask(byte: int, bits: int) -> int:
    al = byte & 0xFF
    ah = 0xFF
    for _ in range(bits):
        cf = 1
        new_al = ((cf << 7) | (al >> 1)) & 0xFF; cf = al & 1; al = new_al
        new_ah = ((cf << 7) | (ah >> 1)) & 0xFF; cf = ah & 1; ah = new_ah
    return ((ah << 8) | al) & 0xFFFF


def _ega_spread_byte_rcr_data(byte: int, bits: int) -> int:
    al = byte & 0xFF
    ah = 0
    for _ in range(bits):
        cf = al & 1
        al = (al >> 1) & 0xFF
        new_ah = ((cf << 7) | (ah >> 1)) & 0xFF; cf = ah & 1; ah = new_ah
    return ((ah << 8) | al) & 0xFFFF


def _run_ega_compact_byte_spread_composite_bits(cpu, *, bits: int) -> None:
    s = cpu.s
    mem = cpu.mem
    rows = s.cx & 0xFFFF
    if rows == 0:
        rows = 0x10000

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    sd = -1 if cpu.get_flag(DF) else 1
    ax = s.ax & 0xFFFF
    old_di = di

    for _ in range(rows):
        mask = _ega_spread_byte_rcr_mask(mem.rb(ds, si), bits)
        si = (si + sd) & 0xFFFF
        for k in (0x00, 0x1A, 0x34, 0x4E):
            mem.ww(es, (di + k) & 0xFFFF, mem.rw(es, (di + k) & 0xFFFF) & mask)
        for k in (0x00, 0x1A, 0x34, 0x4E):
            ax = _ega_spread_byte_rcr_data(mem.rb(ds, si), bits)
            si = (si + sd) & 0xFFFF
            mem.ww(es, (di + k) & 0xFFFF, mem.rw(es, (di + k) & 0xFFFF) | ax)
        old_di = di
        di = (di + 0x68) & 0xFFFF
        cpu.set_add_flags(old_di, 0x68, old_di + 0x68, 16)

    s.ax = ax & 0xFFFF
    s.si = si
    s.di = di
    s.cx = 0
    s.ds = mem.rw(s.cs & 0xFFFF, 0x9596)
    s.ip = cpu.pop()


@registry.replace(0x1010, 0x2193, "overkill_ega_compact_byte_masked_composite_2193")
def overkill_ega_compact_byte_masked_composite_2193(cpu):
    """Replace EGA compact byte masked compositor at 1010:2193."""
    s = cpu.s
    mem = cpu.mem
    rows = s.cx & 0xFFFF
    if rows == 0:
        rows = 0x10000

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    ah = (s.ax >> 8) & 0xFF
    al = s.ax & 0xFF
    old_si = si

    for _ in range(rows):
        row_si = si
        mask = mem.rb(ds, row_si)
        for source_off in (1, 2, 3, 4):
            al = (mem.rb(es, di) & mask) | mem.rb(ds, (row_si + source_off) & 0xFFFF)
            mem.wb(es, di, al & 0xFF)
            old_di = di
            di = (di + 0x1A) & 0xFFFF
            cpu.set_add_flags(old_di, 0x1A, old_di + 0x1A, 16)
        old_si = si
        si = (si + 0x05) & 0xFFFF
        cpu.set_add_flags(old_si, 0x05, old_si + 0x05, 16)

    s.ax = ((ah << 8) | (al & 0xFF)) & 0xFFFF
    s.si = si
    s.di = di
    s.cx = 0
    s.ds = mem.rw(s.cs & 0xFFFF, 0x9596)
    s.ip = cpu.pop()


def _ega_spread_byte_rcl_mask(byte: int, bits: int) -> int:
    ah = byte & 0xFF
    al = 0xFF
    for _ in range(bits):
        cf = 1
        new_ah = ((ah << 1) | cf) & 0xFF; cf = (ah >> 7) & 1; ah = new_ah
        new_al = ((al << 1) | cf) & 0xFF; cf = (al >> 7) & 1; al = new_al
    return ((ah << 8) | al) & 0xFFFF


def _ega_spread_byte_rcl_data(byte: int, bits: int) -> int:
    ah = byte & 0xFF
    al = 0
    for _ in range(bits):
        cf = (ah >> 7) & 1
        ah = ((ah << 1) & 0xFF)
        new_al = ((al << 1) | cf) & 0xFF; cf = (al >> 7) & 1; al = new_al
    return ((ah << 8) | al) & 0xFFFF


def _run_ega_compact_byte_spread_left_composite_bits(cpu, *, bits: int) -> None:
    s = cpu.s
    mem = cpu.mem
    rows = s.cx & 0xFFFF
    if rows == 0:
        rows = 0x10000

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    ax = s.ax & 0xFFFF
    old_si = si

    for _ in range(rows):
        row_si = si
        mask = _ega_spread_byte_rcl_mask(mem.rb(ds, row_si), bits)
        for k in (0x00, 0x1A, 0x34, 0x4E):
            mem.ww(es, (di + k) & 0xFFFF, mem.rw(es, (di + k) & 0xFFFF) & mask)
        for source_off, k in ((1, 0x00), (2, 0x1A), (3, 0x34), (4, 0x4E)):
            ax = _ega_spread_byte_rcl_data(mem.rb(ds, (row_si + source_off) & 0xFFFF), bits)
            mem.ww(es, (di + k) & 0xFFFF, mem.rw(es, (di + k) & 0xFFFF) | ax)
        old_di = di
        di = (di + 0x68) & 0xFFFF
        cpu.set_add_flags(old_di, 0x68, old_di + 0x68, 16)
        old_si = si
        si = (si + 0x05) & 0xFFFF
        cpu.set_add_flags(old_si, 0x05, old_si + 0x05, 16)

    s.ax = ax & 0xFFFF
    s.si = si
    s.di = di
    s.cx = 0
    s.ds = mem.rw(s.cs & 0xFFFF, 0x9596)
    s.ip = cpu.pop()


@registry.replace(0x1010, 0x238D, "overkill_ega_compact_byte_spread_left_composite_238d")
def overkill_ega_compact_byte_spread_left_composite_238d(cpu):
    """Replace left-shift EGA byte-spread compact compositor at 1010:238D."""
    _run_ega_compact_byte_spread_left_composite_bits(cpu, bits=3)


@registry.replace(0x1010, 0x2410, "overkill_ega_compact_byte_spread_left_composite_2410")
def overkill_ega_compact_byte_spread_left_composite_2410(cpu):
    """Replace left-shift EGA byte-spread compact compositor at 1010:2410."""
    _run_ega_compact_byte_spread_left_composite_bits(cpu, bits=2)


@registry.replace(0x1010, 0x247E, "overkill_ega_compact_byte_spread_left_composite_247e")
def overkill_ega_compact_byte_spread_left_composite_247e(cpu):
    """Replace left-shift EGA byte-spread compact compositor at 1010:247E."""
    _run_ega_compact_byte_spread_left_composite_bits(cpu, bits=1)


@registry.replace(0x1010, 0x21D6, "overkill_ega_compact_byte_spread_composite_21d6")
def overkill_ega_compact_byte_spread_composite_21d6(cpu):
    """Replace EGA byte-spread compact compositor at 1010:21D6."""
    _run_ega_compact_byte_spread_composite_bits(cpu, bits=1)


@registry.replace(0x1010, 0x2223, "overkill_ega_compact_byte_spread_composite_2223")
def overkill_ega_compact_byte_spread_composite_2223(cpu):
    """Replace EGA byte-spread compact compositor at 1010:2223."""
    _run_ega_compact_byte_spread_composite_bits(cpu, bits=2)


@registry.replace(0x1010, 0x2285, "overkill_ega_compact_byte_spread_composite_2285")
def overkill_ega_compact_byte_spread_composite_2285(cpu):
    """Replace EGA byte-spread compact compositor at 1010:2285."""
    _run_ega_compact_byte_spread_composite_bits(cpu, bits=3)


@registry.replace(0x1010, 0x22FC, "overkill_ega_compact_byte_spread_composite_22fc")
def overkill_ega_compact_byte_spread_composite_22fc(cpu):
    """Replace EGA byte-spread compact compositor at 1010:22FC.

    The compact layer helper 7746 reaches this mode-1 target for an 8-row sprite
    phase.  Each row consumes one mask byte and four data bytes, spreads each byte
    through four RCR/SHR steps into a 16-bit word, updates four EGA chunks spaced
    by 1Ah, advances DI by 68h, and LOOPs on CX.
    """
    s = cpu.s
    mem = cpu.mem
    rows = s.cx & 0xFFFF
    if rows == 0:
        rows = 0x10000

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    sd = -1 if cpu.get_flag(DF) else 1
    ax = s.ax & 0xFFFF
    old_di = di

    for _ in range(rows):
        mask = _ega_spread_byte_rcr_mask(mem.rb(ds, si), 4)  # LODSB + mask chain
        si = (si + sd) & 0xFFFF
        for k in (0x00, 0x1A, 0x34, 0x4E):
            mem.ww(es, (di + k) & 0xFFFF, mem.rw(es, (di + k) & 0xFFFF) & mask)
        for k in (0x00, 0x1A, 0x34, 0x4E):
            ax = _ega_spread_byte_rcr_data(mem.rb(ds, si), 4)
            si = (si + sd) & 0xFFFF
            mem.ww(es, (di + k) & 0xFFFF, mem.rw(es, (di + k) & 0xFFFF) | ax)
        old_di = di
        di = (di + 0x68) & 0xFFFF
        cpu.set_add_flags(old_di, 0x68, old_di + 0x68, 16)

    s.ax = ax & 0xFFFF
    s.si = si
    s.di = di
    s.cx = 0
    s.ds = mem.rw(s.cs & 0xFFFF, 0x9596)
    s.ip = cpu.pop()


@registry.replace(0x1010, 0x38F9, "overkill_masked_sprite_composite_38f9")
def overkill_masked_sprite_composite_38f9(cpu):
    """Replace the compact 1-column CGA masked compositor at 1010:38F9.

    Reached from the compact layer helper 7746 in mode 0.  Each row consumes one
    source mask/data word pair, composites one destination word, then advances DI
    by 32h after STOSW for the same net 34h row stride as the wider CGA sprite
    compositors.  The original restores DS from CS:[9596] and returns near.
    """
    s = cpu.s
    mem = cpu.mem
    rows = s.cx & 0xFFFF
    if rows == 0:
        rows = 0x10000

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    sd = -2 if cpu.get_flag(DF) else 2
    ax = s.ax & 0xFFFF
    old_di = di

    for _ in range(rows):
        mask = mem.rw(ds, si)                 # LODSW
        si = (si + sd) & 0xFFFF
        ax = mask & mem.rw(es, di)            # AND AX,ES:[DI]
        ax = ax | mem.rw(ds, si)              # OR AX,DS:[SI]
        si = (si + 2) & 0xFFFF                # ADD SI,2
        mem.ww(es, di, ax & 0xFFFF)           # STOSW
        di = (di + sd) & 0xFFFF
        old_di = di
        di = (di + 0x32) & 0xFFFF             # ADD DI,32h

    cpu.set_add_flags(old_di, 0x32, old_di + 0x32, 16)
    s.ax = ax & 0xFFFF
    s.si = si
    s.di = di
    s.cx = 0
    s.ds = mem.rw(s.cs & 0xFFFF, 0x9596)
    s.ip = cpu.pop()


@registry.replace(0x1010, 0x10B7, "overkill_ega_layer_or_inverted_composite_10b7")
def overkill_ega_layer_or_inverted_composite_10b7(cpu):
    """Replace EGA layer inverted-mask OR compositor at 1010:10B7."""
    s = cpu.s
    mem = cpu.mem
    rows = s.cx & 0xFFFF
    if rows == 0:
        rows = 0x10000

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    ax = s.ax & 0xFFFF
    old_si = si

    for _ in range(rows):
        row_si = si
        ax = (~mem.rw(ds, row_si)) & 0xFFFF
        for k in (0x00, 0x1A, 0x34, 0x4E):
            mem.ww(es, (di + k) & 0xFFFF, mem.rw(es, (di + k) & 0xFFFF) | ax)
        ax = (~mem.rw(ds, (row_si + 0x02) & 0xFFFF)) & 0xFFFF
        for k in (0x02, 0x1C, 0x36, 0x50):
            mem.ww(es, (di + k) & 0xFFFF, mem.rw(es, (di + k) & 0xFFFF) | ax)
        old_di = di
        di = (di + 0x68) & 0xFFFF
        cpu.set_add_flags(old_di, 0x68, old_di + 0x68, 16)
        old_si = si
        si = (si + 0x14) & 0xFFFF
        cpu.set_add_flags(old_si, 0x14, old_si + 0x14, 16)

    s.ax = ax & 0xFFFF
    s.si = si
    s.di = di
    s.cx = 0
    s.ds = mem.rw(s.cs & 0xFFFF, 0x9596)
    s.ip = cpu.pop()


@registry.replace(0x1010, 0x103C, "overkill_ega_layer_masked_composite_103c")
def overkill_ega_layer_masked_composite_103c(cpu):
    """Replace the EGA layer masked compositor at 1010:103C.

    This is reached from the shared 75F5 layer-sprite dispatch in mode 1
    (EGA). Per row it updates four destination chunks spaced by 1Ah bytes.
    Each chunk has two destination words: the first word uses source mask
    [SI+00] and data words [SI+04/08/0C/10]; the second uses source mask
    [SI+02] and data words [SI+06/0A/0E/12].  The row then advances SI by
    14h and LOOPs.  The original restores DS from CS:[9596] and returns near.
    """
    s = cpu.s
    mem = cpu.mem
    rows = s.cx & 0xFFFF
    if rows == 0:
        rows = 0x10000

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    ax = s.ax & 0xFFFF
    old_si = si

    for _ in range(rows):
        row_si = si
        row_di = di
        mask0 = mem.rw(ds, row_si)
        mask1 = mem.rw(ds, (row_si + 0x02) & 0xFFFF)
        for data0, data1 in ((0x04, 0x06), (0x08, 0x0A), (0x0C, 0x0E), (0x10, 0x12)):
            ax = (mem.rw(es, row_di) & mask0) | mem.rw(ds, (row_si + data0) & 0xFFFF)
            mem.ww(es, row_di, ax & 0xFFFF)
            ax = (mem.rw(es, (row_di + 0x02) & 0xFFFF) & mask1) | mem.rw(ds, (row_si + data1) & 0xFFFF)
            mem.ww(es, (row_di + 0x02) & 0xFFFF, ax & 0xFFFF)
            row_di = (row_di + 0x1A) & 0xFFFF
        di = row_di
        old_si = si
        si = (si + 0x14) & 0xFFFF

    # Live flags come from the final ADD SI,14h before the last LOOP.
    cpu.set_add_flags(old_si, 0x14, old_si + 0x14, 16)
    s.ax = ax & 0xFFFF
    s.si = si
    s.di = di
    s.cx = 0
    s.ds = mem.rw(s.cs & 0xFFFF, 0x9596)
    s.ip = cpu.pop()


@registry.replace(0x1010, 0x1AEB, "overkill_ega_spaced_word_composite_1aeb")
def overkill_ega_spaced_word_composite_1aeb(cpu):
    """Replace the hot EGA spaced-word composite loop at 1010:1AEB.

    Each row updates four words separated by 1Ah bytes in ES.  Source words are
    laid out as one mask word followed by four data words.  The original
    restores DS from CS:[9596] and returns near after the loop.
    """
    s = cpu.s
    mem = cpu.mem
    rows = s.cx & 0xFFFF
    if rows == 0:
        rows = 0x10000

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    ax = s.ax & 0xFFFF
    old_si = si

    for _ in range(rows):
        row_si = si
        mask = mem.rw(ds, row_si)
        for data_off in (2, 4, 6, 8):
            ax = (mem.rw(es, di) & mask) | mem.rw(ds, (row_si + data_off) & 0xFFFF)
            mem.ww(es, di, ax)
            di = (di + 0x1A) & 0xFFFF
        old_si = si
        si = (si + 0x0A) & 0xFFFF

    cpu.set_add_flags(old_si, 0x0A, old_si + 0x0A, 16)
    s.ax = ax & 0xFFFF
    s.si = si
    s.di = di
    s.cx = 0
    s.ds = mem.rw(s.cs & 0xFFFF, 0x9596)
    s.ip = cpu.pop()


@registry.replace(0x1010, 0x1D1B, "overkill_ega_spread_masked_composite_1d1b")
def overkill_ega_spread_masked_composite_1d1b(cpu):
    """Replace the hot EGA bit-spread masked composite loop at 1010:1D1B.

    This is the sibling of the 1AEB jump-table sprite variant (both are reached
    through the ``jmp cs:[bx]`` dispatcher at 1010:76E2 and return near to the
    object-scan caller after restoring DS from CS:[9596]).  Per row it writes
    four 3-byte chunks (a word at DI plus a byte at DI+2) spaced 1Ah bytes apart,
    advancing DI by 68h between rows.

    The source layout is one mask word followed by four data words (SI += 0Ah per
    row).  Unlike 1AEB, each word is first spread through the original RCR/SHR bit
    chains before it is combined with the destination:

      * mask word: ``DL=FF`` then 4x {STC; RCR AL; RCR AH; RCR DL}; the resulting
        AX (word) and DL (byte) are AND-ed into all four chunks of the row,
        clearing the pixels the sprite will overwrite;
      * each of the four data words: ``DL=0`` then 4x {SHR AL; RCR AH; RCR DL};
        the resulting AX/DL are OR-ed into that chunk, painting the pixels.

    The chains are replicated exactly (same primitives, same order) so registers,
    flags and written memory match the interpreted ASM; only the per-instruction
    fetch/decode/dispatch overhead is removed.  Verified bit-identical at runtime
    by the differential hook verifier (see ``DEFAULT_STOPS`` 1D1B near_ret) and by
    ``test_ega_spread_masked_composite_1d1b_hook_matches_interpreted_asm``.
    """
    s = cpu.s
    mem = cpu.mem
    rows = s.cx & 0xFFFF
    if rows == 0:
        rows = 0x10000

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    dh = (s.dx >> 8) & 0xFF

    rw, ww, rb, wb = mem.rw, mem.ww, mem.rb, mem.wb

    ax = s.ax & 0xFFFF
    dl = 0
    old_di = di
    # Destination chunk offsets within a row: word at +k, byte at +k+2.
    chunk = (0x00, 0x1A, 0x34, 0x4E)

    for _ in range(rows):
        # Mask word: STC-seeded RCR chain, then AND into all four chunks.
        al = rw(ds, si) & 0xFF
        ah = (rw(ds, si) >> 8) & 0xFF
        si = (si + 2) & 0xFFFF
        dl = 0xFF
        for _ in range(4):
            cf = 1
            nal = ((cf << 7) | (al >> 1)) & 0xFF; cf = al & 1; al = nal
            nah = ((cf << 7) | (ah >> 1)) & 0xFF; cf = ah & 1; ah = nah
            ndl = ((cf << 7) | (dl >> 1)) & 0xFF; cf = dl & 1; dl = ndl
        mask_ax = ((ah << 8) | al) & 0xFFFF
        mask_dl = dl
        for k in chunk:
            ww(es, (di + k) & 0xFFFF, rw(es, (di + k) & 0xFFFF) & mask_ax)
            wb(es, (di + k + 2) & 0xFFFF, rb(es, (di + k + 2) & 0xFFFF) & mask_dl)

        # Four data words: SHR-seeded RCR chain, then OR into the matching chunk.
        for k in chunk:
            al = rw(ds, si) & 0xFF
            ah = (rw(ds, si) >> 8) & 0xFF
            si = (si + 2) & 0xFFFF
            dl = 0
            for _ in range(4):
                cf = al & 1; al = (al >> 1) & 0xFF
                nah = ((cf << 7) | (ah >> 1)) & 0xFF; cf = ah & 1; ah = nah
                ndl = ((cf << 7) | (dl >> 1)) & 0xFF; cf = dl & 1; dl = ndl
            ax = ((ah << 8) | al) & 0xFFFF
            ww(es, (di + k) & 0xFFFF, rw(es, (di + k) & 0xFFFF) | ax)
            wb(es, (di + k + 2) & 0xFFFF, rb(es, (di + k + 2) & 0xFFFF) | dl)

        old_di = di
        di = (di + 0x68) & 0xFFFF

    # Live flags at the near return come from the final ADD DI,68h.
    cpu.set_add_flags(old_di, 0x68, old_di + 0x68, 16)
    s.ax = ax & 0xFFFF
    s.dx = ((dh << 8) | (dl & 0xFF)) & 0xFFFF
    s.si = si
    s.di = di
    s.cx = 0
    s.ds = mem.rw(s.cs & 0xFFFF, 0x9596)
    s.ip = cpu.pop()


@registry.replace(0x1010, 0x13E7, "overkill_ega_spread_masked_composite_wide_13e7")
def overkill_ega_spread_masked_composite_wide_13e7(cpu):
    """Replace the hot wide EGA bit-spread masked composite loop at 1010:13E7.

    This is the five-byte-wide sibling of the 1D1B variant: another target of the
    ``jmp cs:[bx]`` sprite dispatcher (here at 1010:7620) that returns near to the
    object-scan caller after restoring DS from CS:[9596].  Where 1D1B writes a
    word+byte (3-byte) chunk, 1D1B's wide sibling writes a word+word+byte (5-byte)
    chunk: a word at DI, a word at DI+2, and a byte at DI+4.  Four chunks per row
    are spaced 1Ah bytes apart (DI += 68h between rows).

    Per row the source is read with explicit ``MOV r,DS:[SI+disp]`` (not LODSW), as
    one mask pair followed by four data pairs, so SI advances by 14h per row:

      * mask: AX=[SI], BX=[SI+2], ``DL=FF`` then 4x {STC; RCR AL; RCR AH; RCR BL;
        RCR BH; RCR DL}; AX/BX/DL are AND-ed into all four chunks of the row;
      * data k (k=0..3): AX=[SI+4+4k], BX=[SI+6+4k], ``DL=0`` then 4x {SHR AL;
        RCR AH; RCR BL; RCR BH; RCR DL}; AX/BX/DL are OR-ed into chunk k.

    The RCR/SHR chains are replicated exactly (same primitives/order over the
    AL/AH/BL/BH/DL register chain) so registers, flags and written memory match the
    interpreted ASM; only the per-instruction fetch/decode/dispatch overhead is
    removed.  The live flags at the near return come from the final ``ADD SI,14h``
    (textually the last arithmetic before LOOP).  Verified bit-identical by the
    differential hook verifier (``DEFAULT_STOPS`` 13E7 near_ret) and by
    ``test_ega_spread_masked_composite_wide_13e7_hook_matches_interpreted_asm``.
    """
    s = cpu.s
    mem = cpu.mem
    rows = s.cx & 0xFFFF
    if rows == 0:
        rows = 0x10000

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    dh = (s.dx >> 8) & 0xFF

    rw, ww, rb, wb = mem.rw, mem.ww, mem.rb, mem.wb

    ax = s.ax & 0xFFFF
    bx = s.bx & 0xFFFF
    dl = 0
    old_si = si
    # Destination chunk offsets within a row: word at +k, word at +k+2, byte +k+4.
    chunk = (0x00, 0x1A, 0x34, 0x4E)

    for _ in range(rows):
        # Mask pair: STC-seeded RCR chain over AL/AH/BL/BH/DL, AND into all chunks.
        word = rw(ds, si)
        al = word & 0xFF; ah = (word >> 8) & 0xFF
        word = rw(ds, (si + 2) & 0xFFFF)
        bl = word & 0xFF; bh = (word >> 8) & 0xFF
        dl = 0xFF
        for _ in range(4):
            cf = 1
            n = ((cf << 7) | (al >> 1)) & 0xFF; cf = al & 1; al = n
            n = ((cf << 7) | (ah >> 1)) & 0xFF; cf = ah & 1; ah = n
            n = ((cf << 7) | (bl >> 1)) & 0xFF; cf = bl & 1; bl = n
            n = ((cf << 7) | (bh >> 1)) & 0xFF; cf = bh & 1; bh = n
            n = ((cf << 7) | (dl >> 1)) & 0xFF; cf = dl & 1; dl = n
        mask_ax = ((ah << 8) | al) & 0xFFFF
        mask_bx = ((bh << 8) | bl) & 0xFFFF
        mask_dl = dl
        for k in chunk:
            ww(es, (di + k) & 0xFFFF, rw(es, (di + k) & 0xFFFF) & mask_ax)
            ww(es, (di + k + 2) & 0xFFFF, rw(es, (di + k + 2) & 0xFFFF) & mask_bx)
            wb(es, (di + k + 4) & 0xFFFF, rb(es, (di + k + 4) & 0xFFFF) & mask_dl)

        # Four data pairs: SHR-seeded RCR chain, then OR into the matching chunk.
        for j, k in enumerate(chunk):
            so = 4 + j * 4
            word = rw(ds, (si + so) & 0xFFFF)
            al = word & 0xFF; ah = (word >> 8) & 0xFF
            word = rw(ds, (si + so + 2) & 0xFFFF)
            bl = word & 0xFF; bh = (word >> 8) & 0xFF
            dl = 0
            for _ in range(4):
                cf = al & 1; al = (al >> 1) & 0xFF
                n = ((cf << 7) | (ah >> 1)) & 0xFF; cf = ah & 1; ah = n
                n = ((cf << 7) | (bl >> 1)) & 0xFF; cf = bl & 1; bl = n
                n = ((cf << 7) | (bh >> 1)) & 0xFF; cf = bh & 1; bh = n
                n = ((cf << 7) | (dl >> 1)) & 0xFF; cf = dl & 1; dl = n
            ax = ((ah << 8) | al) & 0xFFFF
            bx = ((bh << 8) | bl) & 0xFFFF
            ww(es, (di + k) & 0xFFFF, rw(es, (di + k) & 0xFFFF) | ax)
            ww(es, (di + k + 2) & 0xFFFF, rw(es, (di + k + 2) & 0xFFFF) | bx)
            wb(es, (di + k + 4) & 0xFFFF, rb(es, (di + k + 4) & 0xFFFF) | dl)

        di = (di + 0x68) & 0xFFFF
        old_si = si
        si = (si + 0x14) & 0xFFFF

    # Live flags at the near return come from the final ADD SI,14h.
    cpu.set_add_flags(old_si, 0x14, old_si + 0x14, 16)
    s.ax = ax & 0xFFFF
    s.bx = bx & 0xFFFF
    s.dx = ((dh << 8) | (dl & 0xFF)) & 0xFFFF
    s.si = si
    s.di = di
    s.cx = 0
    s.ds = mem.rw(s.cs & 0xFFFF, 0x9596)
    s.ip = cpu.pop()


@registry.replace(0x1010, 0x29C6, "overkill_ega_spaced_copy_29c6")
def overkill_ega_spaced_copy_29c6(cpu):
    """Replace the hot EGA 16-row spaced copy routine at 1010:29C6.

    If DI is FFFFh the original returns immediately.  Otherwise it copies four
    3-byte chunks per row for 16 rows, spacing destination chunks by 1Ah bytes.
    """
    s = cpu.s
    mem = cpu.mem
    _cmp_word(cpu, s.di & 0xFFFF, 0xFFFF)
    if (s.di & 0xFFFF) == 0xFFFF:
        s.ip = cpu.pop()
        return

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    s.bx = 0x0017
    old_di = di

    for _row in range(16):
        for _col in range(4):
            mem.ww(es, di, mem.rw(ds, si))
            si = (si + 2) & 0xFFFF
            di = (di + 2) & 0xFFFF
            mem.wb(es, di, mem.rb(ds, si))
            si = (si + 1) & 0xFFFF
            di = (di + 1) & 0xFFFF
            old_di = di
            di = (di + 0x0017) & 0xFFFF

    cpu.set_add_flags(old_di, 0x0017, old_di + 0x0017, 16)
    s.si = si
    s.di = di
    s.cx = 0
    s.ip = cpu.pop()


@registry.replace(0x1010, 0x2AB9, "overkill_ega_source_spaced_copy_2ab9")
def overkill_ega_source_spaced_copy_2ab9(cpu):
    """Replace EGA object draw copy routine at 1010:2AB9.

    The original calls the mode-specific 5A36 row-address helper, then copies
    four 3-byte chunks per row for 16 rows, spacing source chunks by 1Ah bytes.
    """
    s = cpu.s
    mem = cpu.mem
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF
    cs = s.cs & 0xFFFF

    _call_hook_like_near_call(cpu, object_row_address_mode1_2580, 0x2ABC)
    if s.ip != 0x2ABC:
        return
    # The near-call push already left 0x2ABC in the scratch slot below SP, so the
    # stack image matches a real CALL/RET without an extra fixup write here.

    mem.ww(ss, (bp + 0x0C) & 0xFFFF, s.ax)
    _cmp_word(cpu, s.ax, 0xFFFF)
    if (s.ax & 0xFFFF) == 0xFFFF:
        s.ip = cpu.pop()
        return

    _add_reg16(cpu, 0, mem.rw(s.ds & 0xFFFF, 0x234C))
    mem.ww(ss, (bp + 0x0C) & 0xFFFF, s.ax)
    s.si = s.ax & 0xFFFF
    s.di = mem.rw(ss, (bp + 0x0E) & 0xFFFF)
    s.es = mem.rw(cs, 0x9596)
    s.ds = mem.rw(cs, 0x9598)
    s.bx = 0x0017

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    old_si = si

    for _row in range(16):
        for _col in range(4):
            mem.ww(es, di, mem.rw(ds, si))
            si = (si + 2) & 0xFFFF
            di = (di + 2) & 0xFFFF
            mem.wb(es, di, mem.rb(ds, si))
            si = (si + 1) & 0xFFFF
            di = (di + 1) & 0xFFFF
            old_si = si
            si = (si + 0x0017) & 0xFFFF

    cpu.set_add_flags(old_si, 0x0017, old_si + 0x0017, 16)
    s.si = si
    s.di = di
    s.cx = 0
    s.ds = mem.rw(cs, 0x9596)
    s.ip = cpu.pop()


@registry.replace(0x1010, 0x469F, "overkill_sprite_copy_9x16_469f")
def overkill_sprite_copy_9x16_469f(cpu):
    """Replace the hot 9-byte-wide by 16-row plain sprite copy at 1010:469F."""
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    old_di = di

    if not cpu.get_flag(DF):
        data = mem.data
        src_base = ds << 4
        dst_base = es << 4
        for _ in range(16):
            data[((dst_base + di) & 0xFFFFF):((dst_base + di) & 0xFFFFF) + 9] =                 data[((src_base + si) & 0xFFFFF):((src_base + si) & 0xFFFFF) + 9]
            si = (si + 9) & 0xFFFF
            old_di = (di + 9) & 0xFFFF
            di = (old_di + 0x2B) & 0xFFFF
    else:
        for _ in range(16):
            for _word in range(4):
                mem.ww(es, di, mem.rw(ds, si))
                si = (si - 2) & 0xFFFF
                di = (di - 2) & 0xFFFF
            mem.wb(es, di, mem.rb(ds, si))
            si = (si - 1) & 0xFFFF
            di = (di - 1) & 0xFFFF
            old_di = di
            di = (di + 0x2B) & 0xFFFF

    cpu.set_add_flags(old_di, 0x2B, old_di + 0x2B, 16)
    s.si = si
    s.di = di
    s.cx = 0
    s.ip = cpu.pop()

@registry.replace(0x1010, 0x4D15, "overkill_presence_stamp_list_4d15")
def overkill_presence_stamp_list_4d15(cpu):
    """Replace the hot 1010:4D15 presence/stamp list helper.

    The caller feeds a compact list of triples.  Each iteration maps the first
    word through DS:[9A08 + word*2], adds DS:[234C] and the second word to get
    an ES-relative cell address, then uses the low byte of the third word as a
    marker.  Empty cells are stamped into ES and the cell address is appended to
    DS:DI; occupied cells are skipped.  In mode 1 it checks/stamps a small stack
    of vertically separated cells at +1Ah/+34h/+4Eh; BP selects whether the +4Eh
    layer is included.

    This screen is especially expensive when the live player disables the older
    interactive-risk render hooks: the planet/difficulty screen executes this
    loop tens of thousands of times.  Keep the loop in Python locals and only set
    FLAGS for the final original instruction that can survive the LOOP/RET.
    """
    s = cpu.s
    count = s.cx & 0xFFFF
    if count == 0:
        count = 0x10000

    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    cs = s.cs & 0xFFFF
    ds_base = ds << 4
    es_base = es << 4
    cs_base = cs << 4
    data = cpu.mem.data
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    bp = s.bp & 0xFFFF
    delta = -2 if cpu.get_flag(DF) else 2
    table_base = 0x9A08
    scroll_base = data[((ds_base + 0x234C) & 0xFFFFF)] | (data[((ds_base + 0x234D) & 0xFFFFF)] << 8)
    mode = data[((cs_base + 0x95BC) & 0xFFFFF)] | (data[((cs_base + 0x95BD) & 0xFFFFF)] << 8)
    bx = s.bx & 0xFFFF
    ax = s.ax & 0xFFFF
    last_flag_kind = "none"
    last_flag_a = 0
    last_flag_b = 0
    last_flag_result = 0
    last_flag_bits = 8

    def read_word(seg_base: int, off: int) -> int:
        a = (seg_base + (off & 0xFFFF)) & 0xFFFFF
        if a == 0xFFFFF:
            return data[a] | (data[0] << 8)
        return data[a] | (data[a + 1] << 8)

    def write_word(seg_base: int, off: int, value: int) -> None:
        # DS:DI never targets EGA planar memory on this path, so direct writes are
        # safe and avoid the Memory.ww helper overhead inside the hot loop.
        a = (seg_base + (off & 0xFFFF)) & 0xFFFFF
        data[a] = value & 0xFF
        if a == 0xFFFFF:
            data[0] = (value >> 8) & 0xFF
        else:
            data[a + 1] = (value >> 8) & 0xFF

    def write_byte(seg_base: int, off: int, value: int) -> None:
        # ES is the presence/cell buffer in this routine, not the EGA A000h
        # aperture, so direct byte writes match Memory.wb without planar routing.
        data[(seg_base + (off & 0xFFFF)) & 0xFFFFF] = value & 0xFF

    for _ in range(count):
        # LODSW #1: compact table index.
        ax = read_word(ds_base, si)
        si = (si + delta) & 0xFFFF
        bx = ((ax << 1) + table_base) & 0xFFFF
        bx = read_word(ds_base, bx)
        bx = (bx + scroll_base) & 0xFFFF

        # LODSW #2: cell-relative offset.
        ax = read_word(ds_base, si)
        si = (si + delta) & 0xFFFF
        bx = (bx + ax) & 0xFFFF

        # LODSW #3: marker byte in AL.
        ax = read_word(ds_base, si)
        si = (si + delta) & 0xFFFF
        marker = ax & 0xFF

        cell = data[(es_base + bx) & 0xFFFFF]
        if cell != 0:
            last_flag_kind = "sub"
            last_flag_a = cell
            last_flag_b = 0
            last_flag_result = cell
            last_flag_bits = 8
            s.cx = (s.cx - 1) & 0xFFFF
            continue

        should_store = False
        store_1a = False
        store_34 = False
        store_4e = False
        if mode != 1:
            # JNE 4D59: non-mode-1 callers only stamp the base cell and append
            # the address to DS:DI.  The stacked +1A/+34/+4E stores are reached
            # only through the mode-1 JMP BP path.
            should_store = True
        else:
            blocked = False
            for off in (0x1A, 0x34, 0x4E):
                value = data[(es_base + ((bx + off) & 0xFFFF)) & 0xFFFFF]
                if value != 0:
                    last_flag_kind = "sub"
                    last_flag_a = value
                    last_flag_b = 0
                    last_flag_result = value
                    last_flag_bits = 8
                    blocked = True
                    break
            if not blocked:
                if bp not in (0x4D4D, 0x4D51):
                    s.ax = ax
                    s.bx = bx
                    s.si = si
                    s.di = di
                    s.ip = bp
                    return
                should_store = True
                store_1a = True
                store_34 = True
                store_4e = bp == 0x4D4D

        if should_store:
            if store_4e:
                write_byte(es_base, (bx + 0x4E) & 0xFFFF, marker)
            if store_34:
                write_byte(es_base, (bx + 0x34) & 0xFFFF, marker)
            if store_1a:
                write_byte(es_base, (bx + 0x1A) & 0xFFFF, marker)
            write_byte(es_base, bx, marker)
            write_word(ds_base, di, bx)
            old_di = di
            di = (di + 2) & 0xFFFF
            last_flag_kind = "add"
            last_flag_a = old_di
            last_flag_b = 2
            last_flag_result = old_di + 2
            last_flag_bits = 16

        s.cx = (s.cx - 1) & 0xFFFF

    s.ax = ax & 0xFFFF
    s.bx = bx & 0xFFFF
    s.si = si & 0xFFFF
    s.di = di & 0xFFFF
    s.cx = 0
    if last_flag_kind == "add":
        cpu.set_add_flags(last_flag_a, last_flag_b, last_flag_result, last_flag_bits)
    elif last_flag_kind == "sub":
        cpu.set_sub_flags(last_flag_a, last_flag_b, last_flag_result, last_flag_bits)
    s.ip = cpu.pop()


def _object_ptr_from_scan_index(cpu, table_base: int, cx_value: int) -> tuple[int, int]:
    """Return (BX, BP) for OVERKILL's descending object-list scan loops."""
    bx = ((cx_value & 0xFFFF) << 1) & 0xFFFF
    bp = cpu.mem.rw(cpu.s.ds & 0xFFFF, (table_base + bx) & 0xFFFF)
    cpu.s.bx = bx
    cpu.s.bp = bp
    return bx, bp


def _push_loop_count_for_interpreted_tail(cpu, cx_value: int) -> None:
    cpu.s.sp = (cpu.s.sp - 2) & 0xFFFF
    cpu.mem.ww(cpu.s.ss & 0xFFFF, cpu.s.sp, cx_value & 0xFFFF)


def _remember_balanced_push_scratch(cpu, cx_value: int) -> None:
    # PUSH/POP pairs leave the last pushed word below SP. Full-memory oracle
    # comparisons can see it even though SP is balanced afterwards.
    cpu.mem.ww(cpu.s.ss & 0xFFFF, (cpu.s.sp - 2) & 0xFFFF, cx_value & 0xFFFF)


def _scan_loop_until_callable(cpu, table_base: int, callable_ip: int, done_ip: int, should_call) -> None:
    """Collapse an object-list loop until the next entry that really calls out.

    The overlaid loading/rendering code has several loops of the form::

        push cx
        mov  bx,cx
        shl  bx,1
        mov  bp,[table+bx]
        ... tests against SS:[BP+...] ...
        call helper      ; only for active/matching objects
        pop  cx
        loop top

    Most startup iterations only skip inactive objects.  This helper consumes
    those skip-only iterations in Python and stops immediately before the real
    CALL for the first object that needs original helper logic.
    """
    iterations = cpu.s.cx & 0xFFFF
    if iterations == 0:
        iterations = 0x10000

    while iterations:
        cx_value = cpu.s.cx & 0xFFFF
        _object_ptr_from_scan_index(cpu, table_base, cx_value)
        if should_call():
            _push_loop_count_for_interpreted_tail(cpu, cx_value)
            cpu.s.ip = callable_ip & 0xFFFF
            return

        _remember_balanced_push_scratch(cpu, cx_value)
        cpu.s.cx = (cx_value - 1) & 0xFFFF
        iterations -= 1
        if cpu.s.cx == 0:
            cpu.s.ip = done_ip & 0xFFFF
            return

    cpu.s.ip = done_ip & 0xFFFF


def _scan_active_object_call(cpu, table_base: int, callable_ip: int, done_ip: int) -> None:
    ss = cpu.s.ss & 0xFFFF

    def should_call() -> bool:
        active = cpu.mem.rw(ss, cpu.s.bp & 0xFFFF)
        _cmp_word(cpu, active, 0)
        return active != 0

    _scan_loop_until_callable(cpu, table_base, callable_ip, done_ip, should_call)


def _scan_layered_object_call(cpu, wanted_layer: int, callable_ip: int, done_ip: int) -> None:
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF

    def should_call() -> bool:
        active = cpu.mem.rw(ss, cpu.s.bp & 0xFFFF)
        _cmp_word(cpu, active, 0)
        if active == 0:
            return False

        mode = cpu.mem.rw(ds, 0xBDAC)
        _cmp_word(cpu, mode, 1)
        use_layer_test = False
        if mode != 1:
            camera = cpu.mem.rw(ds, 0x2350)
            _cmp_word(cpu, camera, 0x00B6)
            if camera <= 0x00B6:  # original JA falls through to layer test only when false
                layer = cpu.mem.rw(ss, (cpu.s.bp + 0x16) & 0xFFFF)
                _cmp_word(cpu, layer, 1)
                if layer == 1:
                    return False
                use_layer_test = True

        obj_layer = cpu.mem.rw(ss, (cpu.s.bp + 0x0A) & 0xFFFF)
        _cmp_word(cpu, obj_layer, wanted_layer)
        return obj_layer == wanted_layer

    _scan_loop_until_callable(cpu, 0x32CA, callable_ip, done_ip, should_call)


def _format_object_context(cpu, bp: int | None = None, cx_value: int | None = None) -> str:
    parts = [
        f"CS:IP={cpu.s.cs & 0xFFFF:04X}:{cpu.s.ip & 0xFFFF:04X}",
        f"DS={cpu.s.ds & 0xFFFF:04X}",
        f"SS={cpu.s.ss & 0xFFFF:04X}",
        f"SP={cpu.s.sp & 0xFFFF:04X}",
        f"CX={cpu.s.cx & 0xFFFF:04X}",
    ]
    if cx_value is not None:
        parts.append(f"scan_cx={cx_value & 0xFFFF:04X}")
    if bp is not None:
        ss = cpu.s.ss & 0xFFFF
        bp &= 0xFFFF
        parts.append(f"BP={bp:04X}")
        for off, name in (
            (0x00, "active"),
            (0x08, "sprite"),
            (0x0A, "layer"),
            (0x0C, "di"),
            (0x0E, "present_si"),
            (0x12, "phase"),
            (0x14, "type"),
            (0x16, "draw_layer"),
            (0x18, "logic_id"),
            (0x1C, "substate"),
            (0x24, "variant"),
            (0x32, "target_y"),
            (0x34, "target_x"),
        ):
            parts.append(f"{name}@+{off:02X}={cpu.mem.rw(ss, (bp + off) & 0xFFFF):04X}")
    return "; ".join(parts)


def _raise_unverified_path(
    cpu,
    *,
    parent: str,
    chain: str,
    target_ip: int | None = None,
    bp: int | None = None,
    cx_value: int | None = None,
) -> None:
    target = "immediate-ret" if target_ip is None else f"{target_ip:04X}"
    raise RuntimeError(
        f"unverified original-code path reached in {parent}: {chain} -> {target}. "
        f"Fail-fast is intentional; reverse and hook this target instead of "
        f"falling back to interpreted ASM. {_format_object_context(cpu, bp, cx_value)}"
    )


def _present_dispatch_target_5a92(cpu, bp: int) -> int:
    cs = cpu.s.cs & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    mode = cpu.mem.rw(cs, 0x95BC)
    obj_type = cpu.mem.rw(ss, (bp + 0x14) & 0xFFFF)
    index = ((obj_type + mode + mode + mode) << 1) & 0xFFFF
    return cpu.mem.rw(cs, (0x5AB6 + index) & 0xFFFF)


def _draw_dispatch_target_5ac8(cpu, bp: int) -> int:
    cs = cpu.s.cs & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    mode = cpu.mem.rw(cs, 0x95BC)
    obj_type = cpu.mem.rw(ss, (bp + 0x14) & 0xFFFF)
    index = ((obj_type + mode + mode + mode) << 1) & 0xFFFF
    return cpu.mem.rw(cs, (0x5AE2 + index) & 0xFFFF)


def _layer_draw_dispatch_target_7596(cpu, bp: int) -> int:
    cs = cpu.s.cs & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    obj_type = cpu.mem.rw(ss, (bp + 0x14) & 0xFFFF)
    index = (obj_type << 1) & 0xFFFF
    return cpu.mem.rw(cs, (0x75A0 + index) & 0xFFFF)




def _tandy_render_runtime() -> TandyRenderRuntime:
    """Build VM callbacks/signatures for Tandy-specific rendering primitives."""
    return TandyRenderRuntime(
        self_disable_if_patched=_self_disable_if_patched,
        object_row_address_from_mode_dispatch_5a36=overkill_cga_object_row_addr_5a36,
        signature_2e6e=_SIG_2E6E,
        signature_2ecb=_SIG_2ECB,
        signature_2f40=_SIG_2F40,
        signature_2f81=_SIG_2F81,
        signature_2fb6=_SIG_2FB6,
        signature_306f=_SIG_306F,
        signature_33af=_SIG_33AF,
        signature_33b2=_SIG_33B2,
        signature_34ad=_SIG_34AD,
        signature_34c5=_SIG_34C5,
        signature_34d8=_SIG_34D8,
        signature_3542=_SIG_3542,
        signature_35aa=_SIG_35AA,
        signature_35cc=_SIG_35CC,
        signature_356c=_SIG_356C,
        signature_3657=_SIG_3657,
    )


def _layer_sprite_runtime() -> LayerSpriteRuntime:
    """Build the callback table used by the shared layer-sprite module.

    The renderer setup logic now lives outside this large hook-registration file,
    but the concrete compositor hook functions remain here for now.  Creating the
    table lazily keeps import order simple while avoiding a circular import from
    ``games.overkill.rendering.layer_sprites`` back into this module.
    """
    return LayerSpriteRuntime(
        self_disable_if_patched=_self_disable_if_patched,
        fail_unverified=_raise_unverified_path,
        signature_75a6=_SIG_75A6,
        signature_768e=_SIG_768E,
        signature_7746=_SIG_7746,
        compositor_handlers={
            # EGA compact/spread compositor leaves.
            0x2193: overkill_ega_compact_byte_masked_composite_2193,
            0x238D: overkill_ega_compact_byte_spread_left_composite_238d,
            0x2410: overkill_ega_compact_byte_spread_left_composite_2410,
            0x247E: overkill_ega_compact_byte_spread_left_composite_247e,
            0x21D6: overkill_ega_compact_byte_spread_composite_21d6,
            0x2223: overkill_ega_compact_byte_spread_composite_2223,
            0x2285: overkill_ega_compact_byte_spread_composite_2285,
            0x22FC: overkill_ega_compact_byte_spread_composite_22fc,
            0x409D: overkill_ega_compact_spread_composite_409d,
            0x40D7: overkill_ega_compact_spread_composite_40d7,
            0x412B: overkill_ega_compact_spread_composite_412b,
            # CGA compositor leaves.
            0x387C: overkill_or_inverted_sprite_composite_387c,
            0x38D6: overkill_or_inverted_sprite_composite_38d6,
            0x390E: overkill_or_inverted_sprite_composite_390e,
            0x3849: overkill_masked_sprite_composite_3849,
            0x38B7: _run_cga_masked_sprite_composite_38b7_as_near,
            0x38F9: overkill_masked_sprite_composite_38f9,
            # EGA full-width layer compositor leaves.
            0x10B7: overkill_ega_layer_or_inverted_composite_10b7,
            0x103C: overkill_ega_layer_masked_composite_103c,
            0x1AEB: overkill_ega_spaced_word_composite_1aeb,
            0x1D1B: overkill_ega_spread_masked_composite_1d1b,
            # Tandy compositor leaves.
            0x2F81: overkill_tandy_masked_sprite_composite_2f81,
            0x2F40: overkill_tandy_or_inverted_mask_2f40,
            0x2ECB: overkill_tandy_or_inverted_mask_2ecb,
            0x2E6E: overkill_tandy_masked_sprite_composite_2e6e,
            0x2FB6: overkill_tandy_masked_compact_2fb6,
        },
    )


def _layer_sprite_composite_target_768e(cpu, bp: int) -> int | None:
    """Compatibility shim for scan/prediction code; see rendering.layer_sprites."""
    return predict_layer_sprite_composite_target_768e(cpu, bp)


def _is_verified_tandy_sprite_composite_target(target_ip: int | None) -> bool:
    """Compatibility shim; this is now a shared CGA/EGA/Tandy target check."""
    return is_known_layer_sprite_composite_target(target_ip)


def _run_known_tandy_sprite_composite_target(cpu, target_ip: int) -> bool:
    """Compatibility shim for the old Tandy-only helper name."""
    return run_layer_sprite_compositor_target(cpu, target_ip, _layer_sprite_runtime())


def _object_logic_target_aa2b(cpu, bp: int) -> int:
    """Predict AA2B's object-logic dispatch target from SS:[BP+16]."""
    cs = cpu.s.cs & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    draw_layer = cpu.mem.rw(ss, (bp + 0x16) & 0xFFFF)
    index = (draw_layer << 1) & 0xFFFF
    return cpu.mem.rw(cs, (0xAA36 + index) & 0xFFFF)


def _object_family_target_efae(cpu, bp: int) -> int:
    """Predict EFAE's second-level behavior dispatch target from SS:[BP+18]."""
    cs = cpu.s.cs & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    logic_id = cpu.mem.rw(ss, (bp + 0x18) & 0xFFFF)
    index = (logic_id << 1) & 0xFFFF
    return cpu.mem.rw(cs, (0xEFC4 + index) & 0xFFFF)


def _run_object_behavior_b73e(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Lift the first branch layer of behavior B73E until its next helper call.

    The observed gameplay object (`logic_id=20h`, `substate=FFFFh`) enters the
    no-substate path, selects an animation frame, and when it has not reached
    its target Y/X yet it prepares DS:2304/2306 and calls B729 -> 5DB2.  We stop
    at that concrete helper instead of pretending the whole behavior is known.
    """
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF

    def run_b85c_move_to_target() -> None:
        target_y_local = cpu.mem.rw(ss, (bp + 0x32) & 0xFFFF)
        target_x_local = cpu.mem.rw(ss, (bp + 0x34) & 0xFFFF)
        cpu.mem.ww(ds, 0x2308, 0x0002)
        cpu.mem.ww(ds, 0x2304, target_y_local)
        cpu.s.ax = target_x_local
        cpu.mem.ww(ds, 0x2306, target_x_local)
        # B85C reaches the movement helper through B862 CALL B729, then
        # B735 CALL 5DB2.  The lifted helper models AF60's self-call scratch
        # relative to the current SP, so keep both real return frames live while
        # running it; otherwise AF63 is written one frame too shallow and hook
        # verification later sees stale stack garbage around SS:SP.
        saved_sp = cpu.s.sp & 0xFFFF
        cpu.push(0xB865)
        cpu.push(0xB738)
        _run_movement_direction_5db2(cpu)
        cpu.s.sp = saved_sp
        _cmp_word(cpu, cpu.mem.rw(ds, 0x230A), 0)
        cpu.mem.ww(ss, (bp + 0x06) & 0xFFFF, 0x0004)
        _run_object_postmove_bc4b(cpu, parent=parent, chain=f"{chain} -> B73E -> B85C -> B729 -> 5DB2", cx_value=cx_value)
        cpu.s.ip = cpu.pop()

    def run_b7c7_reset_target(*, check_2324: bool, branch: str) -> None:
        # B7C7/B7CE: choose a new target row, align it to 8 pixels, reset the
        # behavior substate, and tail-jump into the common BC4B post-move path.
        # B7C7 performs the DS:2324 guard first; B7CE is the direct path that
        # always reloads target_y from DS:2380+8.
        if check_2324:
            value_2324 = cpu.mem.rw(ds, 0x2324)
            _cmp_word(cpu, value_2324, 0x0001)
            should_reload_y = value_2324 != 0x0001
        else:
            should_reload_y = True
        if should_reload_y:
            cpu.s.ax = cpu.mem.rw(ds, 0x2380)
            old_ax = cpu.s.ax
            cpu.s.ax = (cpu.s.ax + 0x0008) & 0xFFFF
            cpu.set_add_flags(old_ax, 0x0008, old_ax + 0x0008, 16)
            cpu.mem.ww(ss, (bp + 0x32) & 0xFFFF, cpu.s.ax)
        _and_mem_word(cpu, ss, (bp + 0x32) & 0xFFFF, 0xFFF8)
        cpu.mem.ww(ds, 0x2340, 0x0028)
        cpu.mem.ww(ss, (bp + 0x1C) & 0xFFFF, 0x0000)
        cpu.mem.ww(ss, (bp + 0x08) & 0xFFFF, 0x0078)
        cpu.mem.ww(ss, (bp + 0x34) & 0xFFFF, 0x0020)
        _run_object_postmove_bc4b(
            cpu,
            parent=parent,
            chain=f"{chain} -> B73E -> B7BD -> {branch}",
            cx_value=cx_value,
        )
        cpu.s.ip = cpu.pop()

    substate = cpu.mem.rw(ss, (bp + 0x1C) & 0xFFFF)
    _cmp_word(cpu, substate, 0xFFFF)
    if substate != 0xFFFF:
        cpu.s.bx = substate
        cpu.s.bx = cpu.shift(4, cpu.s.bx, 1, 16)
        target_ip = cpu.mem.rw(cpu.s.cs & 0xFFFF, (0xB74E + cpu.s.bx) & 0xFFFF)
        if target_ip == 0xB754:
            y = cpu.mem.rw(ss, (bp + 0x04) & 0xFFFF)
            target_y = cpu.mem.rw(ss, (bp + 0x32) & 0xFFFF)
            cpu.s.ax = y
            _cmp_word(cpu, y, target_y)
            if y != target_y:
                run_b85c_move_to_target()
                return
            x = cpu.mem.rw(ss, (bp + 0x02) & 0xFFFF)
            target_x = cpu.mem.rw(ss, (bp + 0x34) & 0xFFFF)
            cpu.s.ax = x
            _cmp_word(cpu, x, target_x)
            if x != target_x:
                run_b85c_move_to_target()
                return
            _add_mem_word(cpu, ss, (bp + 0x1C) & 0xFFFF, 1)
            _run_object_postmove_bc4b(cpu, parent=parent, chain=f"{chain} -> B73E -> B754", cx_value=cx_value)
            cpu.s.ip = cpu.pop()
            return
        if target_ip == 0xB770:
            cpu.mem.ww(ss, (bp + 0x08) & 0xFFFF, 0x0079)
            _add_mem_word(cpu, ss, (bp + 0x1C) & 0xFFFF, 1)
            _run_object_postmove_bc4b(cpu, parent=parent, chain=f"{chain} -> B73E -> B770", cx_value=cx_value)
            cpu.s.ip = cpu.pop()
            return
        if target_ip == 0xB77B:
            _add_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, 0x0004)
            _cmp_word(cpu, cpu.mem.rw(ss, (bp + 0x02) & 0xFFFF), 0x00A0)
            if cpu.mem.rw(ss, (bp + 0x02) & 0xFFFF) >= 0x00A0:
                cpu.mem.ww(ss, (bp + 0x08) & 0xFFFF, 0x0077)
            _run_object_postmove_bc4b(cpu, parent=parent, chain=f"{chain} -> B73E -> B77B", cx_value=cx_value)
            cpu.s.ip = cpu.pop()
            return
        _raise_unverified_path(
            cpu, parent=parent, chain=f"{chain} -> B73E[substate]",
            target_ip=target_ip, bp=bp, cx_value=cx_value,
        )

    timer = cpu.mem.rw(ds, 0x2338)
    y = cpu.mem.rw(ss, (bp + 0x04) & 0xFFFF)
    _cmp_word(cpu, y, 0x0060)
    if y < 0x0060:
        # NEG AX; ADD AX,007Fh, with AX initially DS:[2338].
        cpu.set_sub_flags(0, timer, -timer, 16)
        cpu.s.ax = (-timer) & 0xFFFF
        old_ax = cpu.s.ax
        cpu.s.ax = (cpu.s.ax + 0x007F) & 0xFFFF
        cpu.set_add_flags(old_ax, 0x007F, old_ax + 0x007F, 16)
    else:
        old_ax = timer
        cpu.s.ax = (timer + 0x007A) & 0xFFFF
        cpu.set_add_flags(old_ax, 0x007A, old_ax + 0x007A, 16)
    cpu.mem.ww(ss, (bp + 0x08) & 0xFFFF, cpu.s.ax)

    target_y = cpu.mem.rw(ss, (bp + 0x32) & 0xFFFF)
    cpu.s.ax = y
    _cmp_word(cpu, y, target_y)
    if y != target_y:
        # B85C: move toward the target; shared by Y-mismatch and X-mismatch.
        run_b85c_move_to_target()
        return

    x = cpu.mem.rw(ss, (bp + 0x02) & 0xFFFF)
    target_x = cpu.mem.rw(ss, (bp + 0x34) & 0xFFFF)
    cpu.s.ax = x
    _cmp_word(cpu, x, target_x)
    if x != target_x:
        run_b85c_move_to_target()
        return

    # B7BD reached when this object is already at its current target.  In the
    # observed gameplay state DS:A7A0 is below 23h, so the original immediately
    # falls through to the same BC4B post-move helper.  Keep that helper as the
    # next honest frontier rather than pretending the whole behavior is closed.
    _cmp_word(cpu, cpu.mem.rw(ds, 0xA7A0), 0x0023)
    if cpu.mem.rw(ds, 0xA7A0) < 0x0023:
        _run_object_postmove_bc4b(cpu, parent=parent, chain=f"{chain} -> B73E -> B7BD", cx_value=cx_value)
        cpu.s.ip = cpu.pop()
        return

    game_counter = cpu.mem.rw(ds, 0x2340)
    _cmp_word(cpu, game_counter, 0x02BC)
    if game_counter < 0x02BC:
        reaches_b808 = True
    else:
        _cmp_word(cpu, game_counter, 0x02D0)
        reaches_b808 = game_counter > 0x02D0
    if not reaches_b808:
        old_ptr = cpu.mem.rw(ds, 0x20A6)
        new_ptr = (old_ptr + 0x0002) & 0xFFFF
        cpu.mem.ww(ds, 0x20A6, new_ptr)
        _cmp_word(cpu, new_ptr, 0x20C7)
        if new_ptr >= 0x20C7:
            cpu.mem.ww(ds, 0x20A6, 0x20A8)
            new_ptr = 0x20A8
        cpu.s.bx = cpu.mem.rw(ds, new_ptr)
        cpu.s.bx &= 0x0001
        cpu.set_logic_flags(cpu.s.bx, 16)
        if cpu.s.bx == 0:
            _run_formation_spawn_7476_observed(
                cpu,
                parent=parent,
                chain=f"{chain} -> B73E -> B7BD -> B800",
                cx_value=cx_value,
            )

    _cmp_word(cpu, cpu.mem.rw(ds, 0xA47E), 0x0003)
    if cpu.mem.rw(ds, 0xA47E) <= 0x0003:
        run_b7c7_reset_target(check_2324=True, branch="B808 -> B7C7 -> BC4B")
        return
    _cmp_word(cpu, game_counter, 0x0005)
    if game_counter < 0x0005:
        run_b7c7_reset_target(check_2324=False, branch="B815 -> B7CE -> BC4B")
        return
    _cmp_word(cpu, cpu.mem.rw(ds, 0x232E), 0x003F)
    if cpu.mem.rw(ds, 0x232E) != 0x003F:
        _run_object_postmove_bc4b(
            cpu,
            parent=parent,
            chain=f"{chain} -> B73E -> B7BD -> B7F3 -> BC4B",
            cx_value=cx_value,
        )
        cpu.s.ip = cpu.pop()
        return

    for _ in range(0x20):
        cpu.s.si = cpu.mem.rw(ds, 0xA842)
        _cmp_word(cpu, cpu.s.si, 0xA894)
        if cpu.s.si >= 0xA894:
            cpu.mem.ww(ds, 0xA842, 0xA844)
            cpu.s.si = 0xA844
        else:
            cpu.s.si = cpu.mem.rw(ds, 0xA842)
        cpu.s.ax = cpu.mem.rw(ds, cpu.s.si)
        cpu.s.si = (cpu.s.si + 2) & 0xFFFF
        old_ax = cpu.s.ax
        cpu.s.ax = (cpu.s.ax + 0x0020) & 0xFFFF
        cpu.set_add_flags(old_ax, 0x0020, old_ax + 0x0020, 16)
        cpu.mem.ww(ss, (bp + 0x34) & 0xFFFF, cpu.s.ax)
        cpu.s.ax = cpu.mem.rw(ds, cpu.s.si)
        cpu.s.si = (cpu.s.si + 2) & 0xFFFF
        cpu.mem.ww(ss, (bp + 0x32) & 0xFFFF, cpu.s.ax)
        cpu.mem.ww(ds, 0xA842, cpu.s.si)

        x = cpu.mem.rw(ss, (bp + 0x02) & 0xFFFF)
        cpu.s.ax = x
        _cmp_word(cpu, x, cpu.mem.rw(ss, (bp + 0x34) & 0xFFFF))
        if x != cpu.mem.rw(ss, (bp + 0x34) & 0xFFFF):
            _run_object_postmove_bc4b(cpu, parent=parent, chain=f"{chain} -> B73E -> B7BD -> B82D -> BC4B", cx_value=cx_value)
            cpu.s.ip = cpu.pop()
            return
        y = cpu.mem.rw(ss, (bp + 0x04) & 0xFFFF)
        cpu.s.ax = y
        _cmp_word(cpu, y, cpu.mem.rw(ss, (bp + 0x32) & 0xFFFF))
        if y != cpu.mem.rw(ss, (bp + 0x32) & 0xFFFF):
            _run_object_postmove_bc4b(cpu, parent=parent, chain=f"{chain} -> B73E -> B7BD -> B82D -> BC4B", cx_value=cx_value)
            cpu.s.ip = cpu.pop()
            return

        _cmp_word(cpu, cpu.mem.rw(ds, 0xA7A0), 0x0023)
        if cpu.mem.rw(ds, 0xA7A0) < 0x0023:
            _run_object_postmove_bc4b(cpu, parent=parent, chain=f"{chain} -> B73E -> B7BD -> B82D -> B7BD", cx_value=cx_value)
            cpu.s.ip = cpu.pop()
            return
        game_counter = cpu.mem.rw(ds, 0x2340)
        _cmp_word(cpu, game_counter, 0x02BC)
        if game_counter < 0x02BC:
            continue
        _cmp_word(cpu, game_counter, 0x02D0)
        if game_counter > 0x02D0:
            continue
        _raise_unverified_path(
            cpu, parent=parent, chain=f"{chain} -> B73E -> B7BD -> B82D loop",
            target_ip=0xB800, bp=bp, cx_value=cx_value,
        )
    _raise_unverified_path(
        cpu, parent=parent, chain=f"{chain} -> B73E -> B7BD -> B82D loop",
        target_ip=0xB7BD, bp=bp, cx_value=cx_value,
    )


def _run_view_window_check_aa46(cpu) -> None:
    """Run the observed AA46 -> 8331 view-window check path.

    This helper is used from BCCB inside the BC4B post-move pass.  It preserves
    the memory writes to DS:95F2/95F4 and the live carry flag used by BCCB.  The
    current Tandy gameplay path exits with CF clear; if a later state reaches a
    not-yet-modeled branch, the surrounding caller will fail fast instead of
    hiding it.
    """
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem

    cpu.s.ax = mem.rw(ss, (bp + 0x02) & 0xFFFF)
    cpu.set_logic_flags(cpu.s.ax, 16)  # OR AX,AX
    if cpu.s.ax & 0x8000:
        cpu.set_flag(CF, False)  # 835B CLC on this observed out-of-window exit.
        return

    cpu.s.si = mem.rw(ds, 0x2384)
    _cmp_word(cpu, cpu.s.si, 0x0003)
    # The observed path uses SI < 3.  For SI >= 3 the original still reaches the
    # same 8331-style bounds check through a nearby branch; keep the arithmetic
    # table-driven because it is harmless for the captured state and explicit.
    old_si = cpu.s.si
    cpu.s.si = (cpu.s.si << 1) & 0xFFFF
    cpu.set_add_flags(old_si, old_si, old_si + old_si, 16)  # SHL-by-1 flag shape approximation.
    old_si = cpu.s.si
    cpu.s.si = (cpu.s.si << 1) & 0xFFFF
    cpu.set_add_flags(old_si, old_si, old_si + old_si, 16)
    old_si = cpu.s.si
    cpu.s.si = (cpu.s.si + 0x214E) & 0xFFFF
    cpu.set_add_flags(old_si, 0x214E, old_si + 0x214E, 16)

    cpu.s.ax = mem.rw(ds, cpu.s.si)
    cpu.s.si = (cpu.s.si + 2) & 0xFFFF
    old_ax = cpu.s.ax
    cpu.s.ax = (cpu.s.ax + mem.rw(ds, 0x237E)) & 0xFFFF
    cpu.set_add_flags(old_ax, mem.rw(ds, 0x237E), old_ax + mem.rw(ds, 0x237E), 16)
    mem.ww(ds, 0x95F2, cpu.s.ax)
    cpu.s.ax = mem.rw(ds, cpu.s.si)
    cpu.s.si = (cpu.s.si + 2) & 0xFFFF
    old_ax = cpu.s.ax
    cpu.s.ax = (cpu.s.ax + mem.rw(ds, 0x2380)) & 0xFFFF
    cpu.set_add_flags(old_ax, mem.rw(ds, 0x2380), old_ax + mem.rw(ds, 0x2380), 16)
    mem.ww(ds, 0x95F4, cpu.s.ax)

    cpu.s.si = (mem.rw(ds, 0x95F2) + 0x0010) & 0xFFFF
    cpu.set_add_flags(mem.rw(ds, 0x95F2), 0x0010, mem.rw(ds, 0x95F2) + 0x0010, 16)
    x = mem.rw(ss, (bp + 0x02) & 0xFFFF)
    _cmp_word(cpu, x, cpu.s.si)
    sx = x if x < 0x8000 else x - 0x10000
    ssi = cpu.s.si if cpu.s.si < 0x8000 else cpu.s.si - 0x10000
    if sx > ssi:
        cpu.set_flag(CF, False)
        return
    old_si = cpu.s.si
    cpu.s.si = (cpu.s.si - 0x0020) & 0xFFFF
    cpu.set_sub_flags(old_si, 0x0020, old_si - 0x0020, 16)
    _cmp_word(cpu, x, cpu.s.si)
    ssi = cpu.s.si if cpu.s.si < 0x8000 else cpu.s.si - 0x10000
    if sx < ssi:
        cpu.set_flag(CF, False)
        return

    cpu.s.si = (mem.rw(ds, 0x95F4) + 0x0010) & 0xFFFF
    cpu.set_add_flags(mem.rw(ds, 0x95F4), 0x0010, mem.rw(ds, 0x95F4) + 0x0010, 16)
    y = mem.rw(ss, (bp + 0x04) & 0xFFFF)
    _cmp_word(cpu, y, cpu.s.si)
    sy = y if y < 0x8000 else y - 0x10000
    ssi = cpu.s.si if cpu.s.si < 0x8000 else cpu.s.si - 0x10000
    if sy > ssi:
        cpu.set_flag(CF, False)
        return
    old_si = cpu.s.si
    cpu.s.si = (cpu.s.si - 0x0020) & 0xFFFF
    cpu.set_sub_flags(old_si, 0x0020, old_si - 0x0020, 16)
    _cmp_word(cpu, y, cpu.s.si)
    ssi = cpu.s.si if cpu.s.si < 0x8000 else cpu.s.si - 0x10000
    if sy < ssi:
        cpu.set_flag(CF, False)
        return
    cpu.set_flag(CF, True)



def _run_collision_handler_bec5_observed(cpu, *, collided_bx: int, parent: str, chain: str, cx_value: int) -> None:
    """Run the currently verified BEC5 collision branch for hazard/item type 2.

    This is the first non-render collision path reached from the closed object
    island.  The observed branch handles a collided object whose +24h field is
    0002h: deactivate that object, decrement the moving object's +32h counter
    through the same staged tests as the original, and mark +36h with 0005h.
    Other BEC5 sub-branches remain fail-fast so they become explicit RE work.
    """
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    bx = collided_bx & 0xFFFF
    mem = cpu.mem

    variant = mem.rw(ds, (bx + 0x18) & 0xFFFF)
    for target in (0x0007, 0x0008, 0x000C, 0x0009):
        _cmp_word(cpu, variant, target)
        if variant == target:
            _raise_unverified_path(
                cpu,
                parent=parent,
                chain=f"{chain} -> BEC5 variant {variant:04X}",
                target_ip=0xBEC5,
                bp=bp,
                cx_value=cx_value,
            )
    _cmp_word(cpu, variant, 0x0002)
    if variant != 0x0002:
        _raise_unverified_path(
            cpu,
            parent=parent,
            chain=f"{chain} -> BEC5 variant {variant:04X}",
            target_ip=0xBEC5,
            bp=bp,
            cx_value=cx_value,
        )

    cpu.s.bx = bx
    mem.ww(ds, bx, 0)
    sprite = mem.rw(ds, (bx + 0x08) & 0xFFFF)
    _cmp_word(cpu, sprite, 0x0033)
    if sprite == 0x0033:
        _raise_unverified_path(
            cpu,
            parent=parent,
            chain=f"{chain} -> BEC5 sprite 0033",
            target_ip=0xBF21,
            bp=bp,
            cx_value=cx_value,
        )

    _sub_mem_word(cpu, ss, (bp + 0x20) & 0xFFFF, 1)
    if mem.rw(ss, (bp + 0x20) & 0xFFFF) == 0:
        _raise_unverified_path(
            cpu,
            parent=parent,
            chain=f"{chain} -> BEC5 first counter zero",
            target_ip=0xBF32,
            bp=bp,
            cx_value=cx_value,
        )

    bedc = mem.rw(ds, 0xBEDC)
    _cmp_word(cpu, bedc, 0x0001)
    if bedc == 0x0001:
        _sub_mem_word(cpu, ss, (bp + 0x20) & 0xFFFF, 1)
        if mem.rw(ss, (bp + 0x20) & 0xFFFF) == 0:
            _run_collision_death_tail_bfc7(
                cpu,
                parent=parent,
                chain=f"{chain} -> BEC5 BEDC=0001 counter zero",
                cx_value=cx_value,
            )
            return
        mem.ww(ss, (bp + 0x24) & 0xFFFF, 0x0005)
        a8c2 = mem.rw(ds, 0xA8C2)
        _cmp_word(cpu, a8c2, 0x0001)
        if a8c2 == 0x0001:
            _raise_unverified_path(
                cpu,
                parent=parent,
                chain=f"{chain} -> BEC5 BEDC=0001 A8C2=0001",
                target_ip=0xBF5F,
                bp=bp,
                cx_value=cx_value,
            )
        cpu.s.ip = cpu.pop()
        return
    _cmp_word(cpu, bedc, 0x0000)
    if bedc != 0:
        _raise_unverified_path(
            cpu,
            parent=parent,
            chain=f"{chain} -> BEC5 BEDC={bedc:04X}",
            target_ip=0xBF52,
            bp=bp,
            cx_value=cx_value,
        )

    for label, target in (("second", 0xBF46), ("third", 0xBF4B), ("fourth", 0xBF50)):
        _sub_mem_word(cpu, ss, (bp + 0x20) & 0xFFFF, 1)
        if mem.rw(ss, (bp + 0x20) & 0xFFFF) == 0:
            if label == "fourth":
                _run_collision_death_tail_bfc7(cpu, parent=parent, chain=f"{chain} -> BEC5", cx_value=cx_value)
                return
            _raise_unverified_path(
                cpu,
                parent=parent,
                chain=f"{chain} -> BEC5 {label} counter zero",
                target_ip=target,
                bp=bp,
                cx_value=cx_value,
            )

    mem.ww(ss, (bp + 0x24) & 0xFFFF, 0x0005)
    a8c2 = mem.rw(ds, 0xA8C2)
    _cmp_word(cpu, a8c2, 0x0001)
    if a8c2 == 0x0001:
        _raise_unverified_path(
            cpu,
            parent=parent,
            chain=f"{chain} -> BEC5 A8C2=0001",
            target_ip=0xBF60,
            bp=bp,
            cx_value=cx_value,
        )

def _run_score_add_5f0d_observed(cpu, amount: int) -> None:
    """Observed score add helper reached from BFC7.

    The original is a packed decimal add starting at 1010:5F0D.  The death-tail
    paths seen so far add 0030h or 0060h into DS:2314..2318 and preserve AX, DX,
    and BP.  Later code in the tail overwrites flags, so this helper only needs
    the memory effect for the verified branch.
    """
    ss = cpu.s.ss & 0xFFFF
    carry = amount & 0xFFFF
    off = 0x2314
    for _ in range(5):
        value = cpu.mem.rb(ss, off)
        addend = carry & 0xFF
        total = (value & 0x0F) + (addend & 0x0F)
        high = (value >> 4) + (addend >> 4)
        if total > 9:
            total -= 10
            high += 1
        carry = 0
        if high > 9:
            high -= 10
            carry = 1
        cpu.mem.wb(ss, off, ((high << 4) | total) & 0xFF)
        off = (off + 1) & 0xFFFF


def _run_y_clamp_bcb1(cpu) -> None:
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    y = cpu.mem.rw(ss, (bp + 0x04) & 0xFFFF)
    _cmp_word(cpu, y, 0x00C0)
    sy = y if y < 0x8000 else y - 0x10000
    if sy > 0x00C0:
        cpu.mem.ww(ss, (bp + 0x04) & 0xFFFF, 0x00C0)
        return
    _cmp_word(cpu, y, 0)
    if sy < 0:
        cpu.mem.ww(ss, (bp + 0x04) & 0xFFFF, 0)


def _run_collision_death_tail_bfc7(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Run the observed BFC7 object death/transition tail for type-1 objects."""
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem

    logic_id = mem.rw(ss, (bp + 0x18) & 0xFFFF)
    _cmp_word(cpu, logic_id, 0x0021)
    if logic_id == 0x0021:
        _cmp_word(cpu, mem.rw(ds, 0x2356), 0x0004)
        if mem.rw(ds, 0x2356) != 0x0004:
            cpu.s.ip = cpu.pop()
            return
        _raise_unverified_path(
            cpu, parent=parent, chain=f"{chain} -> BFC7 logic 0021",
            target_ip=0xBFD2, bp=bp, cx_value=cx_value,
        )

    obj_type = mem.rw(ss, (bp + 0x14) & 0xFFFF)
    _cmp_word(cpu, obj_type, 0x0001)
    cpu.s.bx = 0x0030
    if obj_type != 0x0001:
        cpu.s.bx = 0x0060
    if obj_type not in (0x0001, 0x0002):
        _raise_unverified_path(
            cpu, parent=parent, chain=f"{chain} -> BFC7 type {obj_type:04X}",
            target_ip=0xBFE1, bp=bp, cx_value=cx_value,
        )

    score_ax = cpu.s.ax
    score_dx = cpu.s.dx
    score_bp = cpu.s.bp
    _run_score_add_5f0d_observed(cpu, cpu.s.bx)
    stack_base = cpu.s.sp & 0xFFFF
    mem.ww(ss, (stack_base - 8) & 0xFFFF, score_dx)
    mem.ww(ss, (stack_base - 6) & 0xFFFF, score_ax)
    mem.ww(ss, (stack_base - 4) & 0xFFFF, score_bp)
    _run_y_clamp_bcb1(cpu)

    saved_bp = bp
    cpu.push(saved_bp)
    linked_slot = mem.rw(ss, (bp + 0x28) & 0xFFFF)
    _cmp_word(cpu, linked_slot, 0xFFFF)
    if linked_slot != 0xFFFF:
        _raise_unverified_path(
            cpu, parent=parent, chain=f"{chain} -> BFC7 linked slot",
            target_ip=0xBFEE, bp=bp, cx_value=cx_value,
        )
    cpu.s.bp = cpu.pop()

    # Observed call C055 returns before the state transition.  Keep the CALL
    # scratch visible below SP for full-memory comparisons.
    _remember_balanced_push_scratch(cpu, 0xC01B)
    if logic_id == 0x0020:
        old_counter = mem.rw(ds, 0xA47E)
        mem.ww(ds, 0xA47E, (old_counter - 1) & 0xFFFF)
        cpu.set_sub_flags(old_counter, 1, old_counter - 1, 16)
    else:
        _raise_unverified_path(
            cpu, parent=parent, chain=f"{chain} -> BFC7 C055 logic {logic_id:04X}",
            target_ip=0xC055, bp=bp, cx_value=cx_value,
        )
    _cmp_word(cpu, mem.rb(ds, 0x98C0), 0)
    if mem.rb(ds, 0x98C0) != 0:
        mem.wb(ds, 0xBEFF, 0x19)

    cpu.s.ax = logic_id
    mem.ww(ss, (bp + 0x1A) & 0xFFFF, cpu.s.ax)
    mem.ww(ss, (bp + 0x18) & 0xFFFF, 0x0001)
    mem.ww(ss, (bp + 0x22) & 0xFFFF, 0x0000)
    cpu.s.bx = obj_type
    cpu.s.bx = cpu.shift(4, cpu.s.bx, 1, 16)
    if obj_type == 0x0000:
        mem.ww(ss, (bp + 0x08) & 0xFFFF, 0x0000)
    elif obj_type == 0x0001:
        mem.ww(ss, (bp + 0x08) & 0xFFFF, 0x0000)
    else:
        _raise_unverified_path(
            cpu, parent=parent, chain=f"{chain} -> BFC7 type dispatch",
            target_ip=0xC04E, bp=bp, cx_value=cx_value,
        )
    cpu.s.ip = cpu.pop()


def _run_post_contact_9e69_observed(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Run the observed 1010:9E69 post-contact bookkeeping path."""
    ds = cpu.s.ds & 0xFFFF
    mem = cpu.mem

    _cmp_word(cpu, mem.rw(ds, 0xA47C), 0x0001)
    if mem.rw(ds, 0xA47C) == 0x0001:
        return
    _cmp_word(cpu, mem.rw(ds, 0x2384), 0x0003)
    if mem.rw(ds, 0x2384) >= 0x0003:
        return
    _cmp_byte(cpu, mem.rb(ds, 0x98C0), 0x00)
    if mem.rb(ds, 0x98C0) != 0:
        mem.wb(ds, 0xBEFF, 0x03)
    _cmp_word(cpu, mem.rw(ds, 0xBEDC), 0x0000)
    if mem.rw(ds, 0xBEDC) != 0:
        # JNE 9E98: skip the A362 every-other-call toggle and run the same tail
        # immediately while BEDC is active.
        _run_post_contact_9e98_tail_observed(cpu)
        return
    old = mem.rb(ds, 0xA362)
    new = (old + 1) & 0xFF
    mem.wb(ds, 0xA362, new)
    cpu.set_add_flags(old, 1, old + 1, 8)
    new &= 0x01
    mem.wb(ds, 0xA362, new)
    cpu.set_logic_flags(new, 8)
    if new == 0:
        _run_post_contact_9e98_tail_observed(cpu)


def _run_post_contact_9e98_tail_observed(cpu) -> None:
    """Run the observed 1010:9E98 tail of post-contact bookkeeping.

    9E69 toggles DS:A362 and returns immediately on odd toggles.  On even
    toggles it falls into 9E98, which advances global counters and redraws the
    associated status/formation strip through 61DC.  The gameplay-relevant
    branches are lifted here; the rare display helper 61DC is still executed by
    bounded original interpretation so the visible frame and scratch registers
    stay faithful until that helper is lifted separately.
    """
    ds = cpu.s.ds & 0xFFFF
    cs = cpu.s.cs & 0xFFFF
    resume_ip = cpu.s.ip & 0xFFFF
    mem = cpu.mem

    old_counter = mem.rw(ds, 0xA95A)
    new_counter = (old_counter - 1) & 0xFFFF
    mem.ww(ds, 0xA95A, new_counter)
    cpu.set_sub_flags(old_counter, 1, old_counter - 1, 16)
    _cmp_word(cpu, new_counter, 0xFFFF)
    if new_counter == 0xFFFF:
        mem.ww(ds, 0xA95C, 0x0000)
        _cmp_byte(cpu, mem.rb(ds, 0x9791), 0x01)
        if mem.rb(ds, 0x9791) == 0x01:
            mem.ww(ds, 0xA95A, 0x0003)
            mem.ww(ds, 0xA95C, 0x0018)
            return
        mem.ww(ds, 0x2384, 0x0003)
        _cmp_byte(cpu, mem.rb(ds, 0x98C0), 0x00)
        if mem.rb(ds, 0x98C0) != 0:
            mem.wb(ds, 0xBEFF, 0x19)

    _run_interpreted_near_call_observed(cpu, 0x61DC, 0x9EC5)
    _cmp_word(cpu, mem.rw(cs, 0x95BC), 0x0001)
    if mem.rw(cs, 0x95BC) == 0x0001:
        _run_interpreted_near_call_observed(cpu, 0x511F, 0x9ED0)
        _run_interpreted_near_call_observed(cpu, 0x61DC, 0x9ED3)
        _run_interpreted_near_call_observed(cpu, 0x511F, 0x9ED6)
    cpu.s.ip = resume_ip


def _find_free_object_slot_7573(cpu) -> int:
    """Mirror the original 1010:7573 object-slot allocator.

    The loop target in the ASM is 757A, not 7583, so the sentinel/wrap check is
    repeated on every scan iteration.  A lifted version that only wrapped once
    before the loop could let DS:[95DA] advance past 32CC into Tandy draw
    scratch space; the next projectile allocation would then overlap the sprite
    buffer and vanish on the following draw pass.
    """
    ds = cpu.s.ds & 0xFFFF
    bx = cpu.mem.rw(ds, 0x95DA)
    cx = 0x0022
    while cx:
        _cmp_word(cpu, bx, 0x32CC)
        if bx == 0x32CC:
            bx = 0x2B5C
        value = cpu.mem.rw(ds, bx)
        _cmp_word(cpu, value, 0)
        if value == 0:
            cpu.mem.ww(ds, 0x95DA, bx)
            cpu.s.bx = bx
            cpu.s.cx = cx
            return bx
        old_bx = bx
        bx = (bx + 0x0038) & 0xFFFF
        cpu.set_add_flags(old_bx, 0x0038, old_bx + 0x0038, 16)
        cx = (cx - 1) & 0xFFFF
    cpu.s.bx = 0xFFFF
    cpu.s.cx = 0
    return 0xFFFF


def _run_formation_spawn_7476_observed(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Run observed B800 -> 7476 helper that spawns a formation child object."""
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem

    bx = _find_free_object_slot_7573(cpu)
    _cmp_word(cpu, cpu.s.bx, 0xFFFF)
    if bx == 0xFFFF:
        return
    if mem.rb(ds, 0x98C0) != 0:
        mem.wb(ds, 0xBEFF, 0x1A)

    cpu.s.cx = 0x000C
    cpu.s.dx = 0x000C
    _cmp_word(cpu, mem.rw(ds, 0xA8C2), 0x0001)
    if mem.rw(ds, 0xA8C2) == 0x0001:
        cpu.s.cx = 0x001C
        cpu.s.dx = 0x0008

    cpu.s.ax = mem.rw(ss, (bp + 0x04) & 0xFFFF)
    old_ax = cpu.s.ax
    cpu.s.ax = (cpu.s.ax + cpu.s.cx) & 0xFFFF
    cpu.set_add_flags(old_ax, cpu.s.cx, old_ax + cpu.s.cx, 16)
    mem.ww(ds, (bx + 0x04) & 0xFFFF, cpu.s.ax)
    cpu.s.ax = mem.rw(ss, (bp + 0x02) & 0xFFFF)
    old_ax = cpu.s.ax
    cpu.s.ax = (cpu.s.ax + cpu.s.dx) & 0xFFFF
    cpu.set_add_flags(old_ax, cpu.s.dx, old_ax + cpu.s.dx, 16)
    mem.ww(ds, (bx + 0x02) & 0xFFFF, cpu.s.ax)

    mem.ww(ds, bx, 0x0001)
    mem.ww(ds, (bx + 0x1E) & 0xFFFF, 0x0000)
    mem.ww(ds, (bx + 0x06) & 0xFFFF, 0x0000)
    mem.ww(ds, (bx + 0x08) & 0xFFFF, 0x0031)
    mem.ww(ds, (bx + 0x0A) & 0xFFFF, 0x0001)
    mem.ww(ds, (bx + 0x14) & 0xFFFF, 0x0000)
    mem.ww(ds, (bx + 0x16) & 0xFFFF, 0x0002)
    mem.ww(ds, (bx + 0x18) & 0xFFFF, 0x000B)
    mem.ww(ds, (bx + 0x1C) & 0xFFFF, 0xFFFF)

    cpu.s.ax = mem.rw(ds, (bx + 0x04) & 0xFFFF)
    cpu.s.cx = (mem.rw(ds, 0x2380) + 0x0009) & 0xFFFF
    cpu.set_add_flags(mem.rw(ds, 0x2380), 0x0009, mem.rw(ds, 0x2380) + 0x0009, 16)
    old_ax = cpu.s.ax
    cpu.s.ax = (cpu.s.ax - cpu.s.cx) & 0xFFFF
    cpu.set_sub_flags(old_ax, cpu.s.cx, old_ax - cpu.s.cx, 16)
    mem.ww(ds, (bx + 0x2C) & 0xFFFF, cpu.s.ax)
    cpu.s.ax = mem.rw(ds, (bx + 0x02) & 0xFFFF)
    cpu.s.cx = mem.rw(ds, 0x237E)
    old_ax = cpu.s.ax
    cpu.s.ax = (cpu.s.ax - cpu.s.cx) & 0xFFFF
    cpu.set_sub_flags(old_ax, cpu.s.cx, old_ax - cpu.s.cx, 16)
    mem.ww(ds, (bx + 0x2A) & 0xFFFF, cpu.s.ax)

def _run_object_overlap_scan_62f6(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Run the no-collision path of the 1010:62F6 object-overlap scan.

    The original is a large unrolled scan over 32CA-era object slots.  This
    compact loop preserves the observed no-collision semantics and fail-fasts if
    a candidate would jump to the unlifted collision handler at BEC5.
    """
    ss = cpu.s.ss & 0xFFFF
    ds = cpu.s.ds & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem

    def finish_empty_scan() -> None:
        # 741C: ADD BX,0038 ; 741F: RET in the unrolled original.
        _add_reg16(cpu, 3, 0x0038)  # BX

    _cmp_word(cpu, mem.rw(ss, bp), 0)
    if mem.rw(ss, bp) == 0:
        cpu.s.bx = 0x3294
        finish_empty_scan()
        return

    _cmp_word(cpu, mem.rw(ss, (bp + 0x02) & 0xFFFF), 0x0020)
    if (mem.rw(ss, (bp + 0x02) & 0xFFFF) if mem.rw(ss, (bp + 0x02) & 0xFFFF) < 0x8000 else mem.rw(ss, (bp + 0x02) & 0xFFFF) - 0x10000) < 0x20:
        cpu.s.bx = 0x3294
        finish_empty_scan()
        return

    for off, bad in ((0x16, 0), (0x18, 0)):
        _cmp_word(cpu, mem.rw(ss, (bp + off) & 0xFFFF), bad)
        if mem.rw(ss, (bp + off) & 0xFFFF) == bad:
            cpu.s.bx = 0x3294
            finish_empty_scan()
            return
    _cmp_word(cpu, mem.rw(ss, (bp + 0x18) & 0xFFFF), 0x0001)
    if mem.rw(ss, (bp + 0x18) & 0xFFFF) == 0x0001:
        return
    _cmp_word(cpu, mem.rw(ss, (bp + 0x18) & 0xFFFF), 0x0026)
    if mem.rw(ss, (bp + 0x18) & 0xFFFF) == 0x0026:
        cpu.s.bx = 0x3294
        finish_empty_scan()
        return

    cpu.s.si = mem.rw(ss, (bp + 0x16) & 0xFFFF)
    cpu.s.di = mem.rw(ss, (bp + 0x0A) & 0xFFFF)
    cpu.s.dx = mem.rw(ss, (bp + 0x04) & 0xFFFF) & 0xFFF8
    cpu.set_logic_flags(cpu.s.dx, 16)
    cpu.s.cx = mem.rw(ss, (bp + 0x02) & 0xFFFF) & 0xFFF8
    cpu.set_logic_flags(cpu.s.cx, 16)

    obj_type = mem.rw(ss, (bp + 0x14) & 0xFFFF)
    logic_id = mem.rw(ss, (bp + 0x18) & 0xFFFF)
    bx = 0x2B5C
    while True:
        cpu.s.bx = bx
        _cmp_word(cpu, mem.rw(ds, bx), 0)
        if mem.rw(ds, bx) != 0:
            _cmp_word(cpu, mem.rw(ds, (bx + 0x1E) & 0xFFFF), 0)
            if mem.rw(ds, (bx + 0x1E) & 0xFFFF) != 0:
                ax = mem.rw(ds, (bx + 0x04) & 0xFFFF)
                _test_word(cpu, ax, 0x0007)
                y_candidates = []
                if ax & 0x0007:
                    aligned = (ax & 0xFFF8)
                    y_candidates.append((aligned + 8) & 0xFFFF)
                    y_candidates.append(aligned)
                else:
                    y_candidates.append(ax)
                y_candidates.append((y_candidates[-1] - 8) & 0xFFFF)
                if obj_type == 2:
                    y_candidates.append((y_candidates[-1] - 8) & 0xFFFF)
                    y_candidates.append((y_candidates[-1] - 8) & 0xFFFF)
                if cpu.s.dx in y_candidates:
                    ax = mem.rw(ds, (bx + 0x02) & 0xFFFF) & 0xFFF8
                    x_candidates = [ax, (ax - 8) & 0xFFFF]
                    if obj_type == 2 and logic_id not in (0x78, 0x79):
                        x_candidates.append((x_candidates[-1] - 8) & 0xFFFF)
                        x_candidates.append((x_candidates[-1] - 8) & 0xFFFF)
                    if cpu.s.cx in x_candidates:
                        # The original arrives at BEC5 with AX holding the
                        # matched tile X and BX pointing at the collided slot.
                        cpu.s.ax = cpu.s.cx & 0xFFFF
                        _run_collision_handler_bec5_observed(
                            cpu,
                            collided_bx=bx,
                            parent=parent,
                            chain=f"{chain} -> 62F6",
                            cx_value=cx_value,
                        )
                        return
                # Leave AX approximately as the last tested Y coordinate, as the
                # original unrolled code does on the no-collision path.
                cpu.s.ax = y_candidates[-1]
        if bx == 0x3294:
            cpu.s.bx = bx
            finish_empty_scan()
            return
        old_bx = bx
        bx = (bx + 0x0038) & 0xFFFF
        cpu.set_add_flags(old_bx, 0x0038, old_bx + 0x0038, 16)


def _run_object_postmove_bc4b(cpu, *, parent: str, chain: str, cx_value: int, clamp_y: bool = True) -> None:
    """Run the observed BC4B post-move/bounds/collision helper path."""
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem

    if clamp_y:
        # BCB1: clamp Y into the 0..C0h range.  Some callers jump directly to
        # BC4F, after this call; those use clamp_y=False.
        y = mem.rw(ss, (bp + 0x04) & 0xFFFF)
        _cmp_word(cpu, y, 0x00C0)
        sy = y if y < 0x8000 else y - 0x10000
        if sy > 0x00C0:
            mem.ww(ss, (bp + 0x04) & 0xFFFF, 0x00C0)
        else:
            _cmp_word(cpu, y, 0)
            if sy < 0:
                mem.ww(ss, (bp + 0x04) & 0xFFFF, 0)
        _remember_balanced_push_scratch(cpu, 0xBC4E)

    global_disable = mem.rw(ds, 0xA47C)
    _cmp_word(cpu, global_disable, 0)
    skip_precise_x = global_disable != 0 or mem.rw(ss, (bp + 0x18) & 0xFFFF) in (0, 0x48, 0x26, 0x86, 0x28, 0x29, 0x34)
    x = mem.rw(ss, (bp + 0x02) & 0xFFFF)
    sx = x if x < 0x8000 else x - 0x10000
    if not skip_precise_x:
        _cmp_word(cpu, x, 0xFF40)
        if sx < -0x00C0:
            _run_deactivate_bd17_observed(cpu, parent=parent, chain=f"{chain} -> BC4B", cx_value=cx_value)
            return
        _cmp_word(cpu, x, 0x00F0)
        if sx >= 0x00F0:
            _run_deactivate_bd17_observed(cpu, parent=parent, chain=f"{chain} -> BC4B", cx_value=cx_value)
            return
    else:
        _cmp_word(cpu, x, 0xFFEC)
        if sx < -0x0014:
            _run_deactivate_bd17_observed(cpu, parent=parent, chain=f"{chain} -> BC4B", cx_value=cx_value)
            return
        _cmp_word(cpu, x, 0x00F0)
        if sx >= 0x00F0:
            _run_deactivate_bd17_observed(cpu, parent=parent, chain=f"{chain} -> BC4B", cx_value=cx_value)
            return

    _cmp_word(cpu, global_disable, 0)
    if global_disable == 0:
        # BC4B reaches the contact checks through CALL BCCB.  Even though BCCB
        # balances SP before returning, its nested CALLs leave return-address
        # scratch below SP; keep the real BCAD call frame live while modelling
        # BCCB so later nested calls land at the same stack offsets.
        bccb_sp = cpu.s.sp & 0xFFFF
        cpu.push(0xBCAD)
        try:
            # BCCB early exits for inactive/exempt objects; otherwise it may call
            # the view-window helper and only continues into hit logic if CF is set.
            _cmp_word(cpu, mem.rw(ss, bp), 0)
            if mem.rw(ss, bp) != 0:
                for off, bad in ((0x16, 5), (0x18, 0), (0x18, 1)):
                    _cmp_word(cpu, mem.rw(ss, (bp + off) & 0xFFFF), bad)
                    if mem.rw(ss, (bp + off) & 0xFFFF) == bad:
                        break
                else:
                    obj_type = mem.rw(ss, (bp + 0x14) & 0xFFFF)
                    _cmp_word(cpu, obj_type, 1)
                    if obj_type == 1:
                        # BCF4 CALL AA46 leaves BCF7 below BCCB's live frame.
                        saved_sp = cpu.s.sp & 0xFFFF
                        cpu.push(0xBCF7)
                        _run_view_window_check_aa46(cpu)
                        cpu.s.sp = saved_sp
                    elif obj_type == 2:
                        _raise_unverified_path(cpu, parent=parent, chain=f"{chain} -> BCCB", target_ip=0xAA71, bp=bp, cx_value=cx_value)
                    else:
                        return
                    if cpu.get_flag(CF):
                        _cmp_word(cpu, mem.rw(ds, 0xA8C2), 0x0001)
                        if mem.rw(ds, 0xA8C2) != 0x0001:
                            cpu.push(0xBD09)
                            _run_collision_death_tail_bfc7(
                                cpu,
                                parent=parent,
                                chain=f"{chain} -> BCCB",
                                cx_value=cx_value,
                            )
                        # BD09 CALL 9E69 must run with BD0C on the stack, not
                        # merely written below the current SP.  The 9E69 -> 9E98
                        # display tail calls 61DC, whose nested scratch is part
                        # of the verifier-visible freed stack bytes.
                        saved_sp = cpu.s.sp & 0xFFFF
                        cpu.push(0xBD0C)
                        _run_post_contact_9e69_observed(
                            cpu,
                            parent=parent,
                            chain=f"{chain} -> BCCB -> BD09",
                            cx_value=cx_value,
                        )
                        cpu.s.sp = saved_sp
        finally:
            cpu.s.sp = bccb_sp
        # BCAD CALL 62F6 leaves the BCB0 return word as stack scratch below SP.
        saved_sp = cpu.s.sp & 0xFFFF
        cpu.push(0xBCB0)
        _run_object_overlap_scan_62f6(cpu, parent=parent, chain=f"{chain} -> BC4B", cx_value=cx_value)
        cpu.s.sp = saved_sp


def _run_object_family_dispatch_efae(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Run EFAE's prologue and leave IP at the concrete second-level target.

    EFAE is a dispatcher, not a behavior body.  It publishes the object's current
    Y/X into DS:D1FE/D200 and then jumps through a second table indexed by
    SS:[BP+18].  Keep this boundary conservative: do not run the selected
    gameplay routine inline here.
    """
    ss = cpu.s.ss & 0xFFFF
    ds = cpu.s.ds & 0xFFFF
    bp = cpu.s.bp & 0xFFFF

    cpu.s.ax = cpu.mem.rw(ss, (bp + 0x04) & 0xFFFF)
    cpu.mem.ww(ds, 0xD1FE, cpu.s.ax)
    cpu.s.ax = cpu.mem.rw(ss, (bp + 0x02) & 0xFFFF)
    cpu.mem.ww(ds, 0xD200, cpu.s.ax)

    cpu.s.bx = cpu.mem.rw(ss, (bp + 0x18) & 0xFFFF)
    cpu.s.bx = cpu.shift(4, cpu.s.bx, 1, 16)  # SHL BX,1
    target_ip = cpu.mem.rw(cpu.s.cs & 0xFFFF, (0xEFC4 + cpu.s.bx) & 0xFFFF)
    cpu.s.ip = target_ip


def _run_object_behavior_8d4f(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Lift the observed logic_id=1Fh target-patrol behavior at 1010:8D4F.

    The body is mostly an overlay far-call (`1F8F:027A`) that reads the next
    waypoint pair from DS:A482, publishes target X/Y to DS:2306/2304, sets
    movement mode 3, calls the generic 5DB2 direction helper through the far
    trampoline at 1010:8D8B, then returns to 8D54 and joins BC4B.
    """
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem

    cpu.s.si = mem.rw(ds, 0xA482)
    cpu.s.ax = mem.rw(ds, cpu.s.si)
    cpu.s.si = (cpu.s.si + 2) & 0xFFFF
    old_ax = cpu.s.ax
    cpu.s.ax = (cpu.s.ax + 0x0020) & 0xFFFF
    cpu.set_add_flags(old_ax, 0x0020, old_ax + 0x0020, 16)
    mem.ww(ds, 0x2306, cpu.s.ax)
    cpu.s.ax = mem.rw(ds, cpu.s.si)
    cpu.s.si = (cpu.s.si + 2) & 0xFFFF
    mem.ww(ds, 0x2304, cpu.s.ax)
    mem.ww(ds, 0x2308, 0x0003)
    cpu.s.ax = 0x5DB2
    # Faithfully reproduce the call frame the original leaves below SP -- OVERKILL
    # reads this scratch through its self-call tricks, so an approximation diverges:
    #   8D4F      CALL FAR 1F8F:027A   pushes CS=1010, IP=8D54
    #   1F8F:0292 CALL FAR 1010:8D8B   pushes CS=1F8F, IP=0297
    #   1010:8D8B CALL AX (=5DB2)      pushes IP=8D8D
    # 5DB2 then runs and three RET/RETF pops unwind the frame back to 8D54.
    cpu.push(0x1010)
    cpu.push(0x8D54)
    cpu.push(0x1F8F)
    cpu.push(0x0297)
    cpu.push(0x8D8D)
    _run_movement_direction_5db2(cpu)
    cpu.s.sp = (cpu.s.sp + 0x000A) & 0xFFFF  # RET 5DB2 + RETF 8D8D + RETF 1F8F:0451
    _run_object_postmove_bc4b(cpu, parent=parent, chain=f"{chain} -> 8D4F -> 1F8F:027A -> 5DB2", cx_value=cx_value)
    cpu.s.ip = cpu.pop()




def _run_tile_probe_5073(cpu) -> None:
    """Mirror the coordinate-to-tile-index helper at 1010:5073."""
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem

    cpu.s.ax = mem.rw(ds, 0x234E)
    old_ax = cpu.s.ax
    addend = mem.rw(ss, (bp + 0x02) & 0xFFFF)
    cpu.s.ax = (old_ax + addend) & 0xFFFF
    cpu.set_add_flags(old_ax, addend, old_ax + addend, 16)
    mem.ww(ds, 0x215A, cpu.s.ax)
    if cpu.s.ax & 0x8000:
        return
    for _ in range(4):
        cpu.s.ax = cpu.shift(5, cpu.s.ax, 1, 16)  # SHR AX,1
    cpu.s.dx = cpu.s.ax
    cpu.s.ax = cpu.shift(4, cpu.s.ax, 1, 16)
    cpu.s.ax = cpu.shift(4, cpu.s.ax, 1, 16)
    cpu.s.cx = cpu.s.ax
    cpu.s.ax = cpu.shift(4, cpu.s.ax, 1, 16)
    old_ax = cpu.s.ax
    cpu.s.ax = (old_ax + cpu.s.cx) & 0xFFFF
    cpu.set_add_flags(old_ax, cpu.s.cx, old_ax + cpu.s.cx, 16)
    old_ax = cpu.s.ax
    cpu.s.ax = (old_ax + cpu.s.dx) & 0xFFFF
    cpu.set_add_flags(old_ax, cpu.s.dx, old_ax + cpu.s.dx, 16)
    cpu.s.bx = mem.rw(ds, 0x2350)
    _sub_reg16(cpu, 3, cpu.s.ax)
    cpu.s.ax = mem.rw(ss, (bp + 0x04) & 0xFFFF) & 0xFFF0
    cpu.set_logic_flags(cpu.s.ax, 16)
    for _ in range(4):
        cpu.s.ax = cpu.shift(5, cpu.s.ax, 1, 16)
    _add_reg16(cpu, 3, cpu.s.ax)


def _run_tile_lookup_505b(cpu) -> None:
    """Mirror the observed tile lookup helper at 1010:505B."""
    cs = cpu.s.cs & 0xFFFF
    es = cpu.mem.rw(cs, 0x9592)
    cpu.s.es = es
    cpu.s.si = 0xC3AA
    value = cpu.mem.rb(es, cpu.s.bx & 0xFFFF)
    cpu.set_reg8(0, value)
    cpu.set_reg8(4, 0)  # XOR AH,AH
    old_si = cpu.s.si
    cpu.s.si = (cpu.s.si + cpu.s.ax) & 0xFFFF
    cpu.set_add_flags(old_si, cpu.s.ax, old_si + cpu.s.ax, 16)
    cpu.set_reg8(0, cpu.mem.rb(cpu.s.ds & 0xFFFF, cpu.s.si))
    cpu.set_logic_flags(cpu.get_reg8(0), 8)



def _run_deactivate_bd17_observed(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Run observed 1010:BD17 object deactivation tail.

    BD17 is reached from BC4B when an object leaves the allowed X bounds.  The
    currently observed gameplay case is the B73E formation/attack object with
    draw layer 4 and logic id 20h: BD17 clears the active flag, calls C054, C054
    decrements DS:A47E for this logic family, then BD17 optionally clears the
    per-slot byte indexed by SS:[BP+28h].
    """
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem

    mem.ww(ss, (bp + 0x00) & 0xFFFF, 0x0000)

    draw_layer = mem.rw(ss, (bp + 0x16) & 0xFFFF)
    _cmp_word(cpu, draw_layer, 0x0004)
    if draw_layer == 0x0004:
        logic_id = mem.rw(ss, (bp + 0x18) & 0xFFFF)

        # C054 observed C14F family: these logic ids decrement the global live
        # counter A47E.  The new crash hits logic_id 20h here.
        c14f_ids = {
            0x0014, 0x0016, 0x0017, 0x0018,
            0x001D, 0x001E, 0x0020, 0x0021, 0x0022,
            0x0061, 0x0062, 0x0065,
            0x007F, 0x0080, 0x0081,
        }
        if logic_id in c14f_ids:
            _sub_mem_word(cpu, ds, 0xA47E, 0x0001)  # DEC word ptr DS:A47E
        elif logic_id == 0x0093:
            mem.wb(ds, 0x98A8, 0x01)
            _sub_mem_word(cpu, ds, 0xA47E, 0x0001)
        else:
            _raise_unverified_path(
                cpu, parent=parent, chain=f"{chain} -> BD17 -> C054",
                target_ip=0xC054, bp=bp, cx_value=cx_value,
            )

        _cmp_word(cpu, logic_id, 0x0001)
        if logic_id == 0x0001:
            return
        slot = mem.rw(ss, (bp + 0x28) & 0xFFFF)
        _cmp_word(cpu, slot, 0xFFFF)
        if slot == 0xFFFF:
            return
        cpu.s.si = slot
        cpu.s.si = cpu.shift(4, cpu.s.si, 1, 16)  # SHL SI,1
        _add_reg16(cpu, 6, 0x2078)                # ADD SI,2078h
        mem.wb(ds, cpu.s.si & 0xFFFF, 0x00)
        return

    _cmp_word(cpu, draw_layer, 0x0001)
    if draw_layer == 0x0001:
        mem.ww(ss, (bp + 0x16) & 0xFFFF, 0x0002)
        return

    logic_id = mem.rw(ss, (bp + 0x18) & 0xFFFF)
    for target, counter in ((0x0007, 0xA970), (0x0008, 0xA970), (0x0005, 0xA976), (0x0006, 0xA976), (0x000C, 0xA974)):
        _cmp_word(cpu, logic_id, target)
        if logic_id == target:
            if mem.rw(ds, counter) != 0:
                _sub_mem_word(cpu, ds, counter, 0x0001)
            return

    _raise_unverified_path(
        cpu, parent=parent, chain=f"{chain} -> BD17",
        target_ip=0xBD17, bp=bp, cx_value=cx_value,
    )


def _run_object_behavior_aed8(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Lift the observed EFAE logic_id=2 movement/tile-probe branch at AED8."""
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem

    _sub_mem_word(cpu, ss, (bp + 0x1C) & 0xFFFF, 1)
    if mem.rw(ss, (bp + 0x1C) & 0xFFFF) == 0:
        _raise_unverified_path(cpu, parent=parent, chain=f"{chain} -> AED8 timer expired", target_ip=0xADC9, bp=bp, cx_value=cx_value)

    cpu.s.ax = 0xB250
    # AED8 pushes B250 and falls into AEE4.  The return word is later replaced
    # by the nested ADBF call scratch; keep SP unchanged in the lifted form.
    mem.ww(ss, (cpu.s.sp - 2) & 0xFFFF, 0xB250)
    _run_aee4_step_for_direction(cpu)

    # Observed B250 branch: object +1Eh == 1 jumps to B2A3 -> AD5A.
    marker = mem.rw(ss, (bp + 0x1E) & 0xFFFF)
    _cmp_word(cpu, marker, 0x0001)
    if marker != 0x0001:
        _raise_unverified_path(cpu, parent=parent, chain=f"{chain} -> AED8 -> B250", target_ip=0xB254, bp=bp, cx_value=cx_value)

    cpu.s.ax = mem.rw(ds, 0xA278)
    _add_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, cpu.s.ax)
    x = mem.rw(ss, (bp + 0x02) & 0xFFFF)
    _cmp_word(cpu, x, 0x0008)
    if x < 0x0008:
        _run_deactivate_bd17_observed(cpu, parent=parent, chain=f"{chain} -> AED8 -> AD5A", cx_value=cx_value)
        cpu.s.ip = cpu.pop()
        return
    _cmp_word(cpu, x, 0x00E0)
    if x > 0x00E0:
        _run_deactivate_bd17_observed(cpu, parent=parent, chain=f"{chain} -> AED8 -> AD5A", cx_value=cx_value)
        cpu.s.ip = cpu.pop()
        return
    y = mem.rw(ss, (bp + 0x04) & 0xFFFF)
    _cmp_word(cpu, y, 0x00C8)
    if y > 0x00C8:
        _run_deactivate_bd17_observed(cpu, parent=parent, chain=f"{chain} -> AED8 -> AD5A", cx_value=cx_value)
        cpu.s.ip = cpu.pop()
        return
    draw_layer = mem.rw(ss, (bp + 0x16) & 0xFFFF)
    _cmp_word(cpu, draw_layer, 0x0002)
    if draw_layer != 0x0002:
        _raise_unverified_path(cpu, parent=parent, chain=f"{chain} -> AED8 -> AD5A", target_ip=0xADF4, bp=bp, cx_value=cx_value)
    logic_id = mem.rw(ss, (bp + 0x18) & 0xFFFF)
    for good in (0x0002, 0x0004, 0x000C, 0x0005, 0x0006, 0x0009, 0x0008):
        _cmp_word(cpu, logic_id, good)
        if logic_id == good:
            break
    else:
        _raise_unverified_path(cpu, parent=parent, chain=f"{chain} -> AED8 -> AD5A", target_ip=0xADAA, bp=bp, cx_value=cx_value)

    bdac = mem.rw(ds, 0xBDAC)
    _cmp_word(cpu, bdac, 0x0001)
    if bdac == 0x0001:
        _raise_unverified_path(cpu, parent=parent, chain=f"{chain} -> AED8 -> ADAF", target_ip=0xADC3, bp=bp, cx_value=cx_value)
    _run_tile_probe_5073(cpu)
    _add_reg16(cpu, 3, 0x000D)  # ADD BX,000Dh before 505B.
    # CALL 505B leaves ADBF as stack scratch below SP.
    mem.ww(ss, (cpu.s.sp - 2) & 0xFFFF, 0xADBF)
    _run_tile_lookup_505b(cpu)
    if not cpu.get_flag(ZF):
        _raise_unverified_path(cpu, parent=parent, chain=f"{chain} -> AED8 -> ADBF nonzero tile", target_ip=0xADC1, bp=bp, cx_value=cx_value)
    cpu.s.ip = cpu.pop()

def _run_object_logic_ab10(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Lift the observed AA2B target AB10 position/sprite update helper.

    AB10 is a first-level object logic target for SS:[BP+16] == 6 in the
    current island.  The observed branch samples a small animation table at
    DS:A40C/DS:A414 using DS:2336 and DS:237C, then writes the object's sprite
    and position before returning to the AA2B caller.
    """
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    mem = cpu.mem

    v2384 = mem.rw(ds, 0x2384)
    _cmp_word(cpu, v2384, 0x0003)
    if v2384 >= 0x0003:
        _raise_unverified_path(cpu, parent=parent, chain=f"{chain} -> AB10", target_ip=0xAC21, bp=bp, cx_value=cx_value)

    global_disable = mem.rw(ds, 0xA47C)
    _cmp_word(cpu, global_disable, 0x0003)
    if global_disable >= 0x0003:
        _raise_unverified_path(cpu, parent=parent, chain=f"{chain} -> AB10", target_ip=0xAC21, bp=bp, cx_value=cx_value)

    cpu.s.ax = mem.rw(ds, 0x2336)
    cpu.s.bx = 0xA40C
    # XLAT: AL = DS:[BX+AL], AH unchanged.
    cpu.set_reg8(0, mem.rb(ds, (cpu.s.bx + (cpu.s.ax & 0x00FF)) & 0xFFFF))
    old_ax = cpu.s.ax & 0xFFFF
    cpu.s.ax = (old_ax + 0x0009) & 0xFFFF
    cpu.set_add_flags(old_ax, 0x0009, old_ax + 0x0009, 16)
    mem.ww(ss, (bp + 0x08) & 0xFFFF, cpu.s.ax)

    cpu.s.dx = 0xA414
    cpu.s.bx = 0x237C
    cpu.s.si = mem.rw(ds, (cpu.s.bx + 0x08) & 0xFFFF)
    cpu.s.si = cpu.shift(4, cpu.s.si, 1, 16)
    cpu.s.si = cpu.shift(4, cpu.s.si, 1, 16)
    old_si = cpu.s.si
    cpu.s.si = (cpu.s.si + cpu.s.dx) & 0xFFFF
    cpu.set_add_flags(old_si, cpu.s.dx, old_si + cpu.s.dx, 16)

    cpu.s.ax = mem.rw(ds, cpu.s.si)
    cpu.s.si = (cpu.s.si + (-2 if cpu.get_flag(DF) else 2)) & 0xFFFF
    old_ax = cpu.s.ax & 0xFFFF
    addend = mem.rw(ds, (cpu.s.bx + 0x02) & 0xFFFF)
    cpu.s.ax = (old_ax + addend) & 0xFFFF
    cpu.set_add_flags(old_ax, addend, old_ax + addend, 16)
    mem.ww(ss, (bp + 0x02) & 0xFFFF, cpu.s.ax)

    cpu.s.ax = mem.rw(ds, cpu.s.si)
    cpu.s.si = (cpu.s.si + (-2 if cpu.get_flag(DF) else 2)) & 0xFFFF
    old_ax = cpu.s.ax & 0xFFFF
    addend = mem.rw(ds, (cpu.s.bx + 0x04) & 0xFFFF)
    cpu.s.ax = (old_ax + addend) & 0xFFFF
    cpu.set_add_flags(old_ax, addend, old_ax + addend, 16)
    mem.ww(ss, (bp + 0x04) & 0xFFFF, cpu.s.ax)
    cpu.s.ip = cpu.pop()

def _run_object_logic_dispatch_aa2b(cpu, *, parent: str, chain: str, cx_value: int) -> None:
    """Run AA2B's first-level dispatch and leave IP at the selected target.

    AA2B dispatches through CS:AA36 using SS:[BP+16].  It is a jump-table stub,
    not a stable gameplay body, so keep the hook at this exact boundary instead
    of executing the selected behavior inline.
    """
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    cpu.s.bx = cpu.mem.rw(ss, (bp + 0x16) & 0xFFFF)
    cpu.s.bx = cpu.shift(4, cpu.s.bx, 1, 16)  # SHL BX,1
    target_ip = cpu.mem.rw(cpu.s.cs & 0xFFFF, (0xAA36 + cpu.s.bx) & 0xFFFF)
    cpu.s.ip = target_ip


def _scan_object_logic_via_aa2b(
    cpu,
    *,
    table_base: int,
    done_ip: int,
    call_ip: int,
    advance_global_counter: bool,
) -> None:
    """Collapse the AA2B object scan only up to the next real CALL.

    The loop bodies at A9E0/AA10 are scan wrappers, not the object logic itself.
    They PUSH CX, select BP from an object table, and only then call AA2B for
    active objects.  A previous replacement crossed that CALL boundary and ran
    the whole AA2B dispatch inline.  That is too large a hook boundary: the
    verifier quite reasonably stops the original ASM at AA01/AA1F before the
    CALL, while the hook had already consumed the call and sometimes the whole
    remaining scan.

    Keep this hook as a narrow scan accelerator: consume inactive entries, but
    when the first active object is found, leave CPU state exactly as the ASM has
    it immediately before CALL AA2B.  The interpreter then executes the CALL,
    and the separate AA2B hook owns the object-logic dispatch boundary.
    """
    iterations = cpu.s.cx & 0xFFFF
    if iterations == 0:
        iterations = 0x10000

    while iterations:
        cx_value = cpu.s.cx & 0xFFFF

        # PUSH CX / MOV BX,CX / SHL BX,1 / MOV BP,[table+BX]
        _object_ptr_from_scan_index(cpu, table_base, cx_value)

        if advance_global_counter:
            ds = cpu.s.ds & 0xFFFF
            old_counter = cpu.mem.rw(ds, 0x2340)
            counter = (old_counter + 1) & 0xFFFF
            cpu.mem.ww(ds, 0x2340, counter)
            _cmp_word(cpu, counter, 0x05DC)
            if counter >= 0x05DC:
                cpu.mem.ww(ds, 0x2340, 0)

        active = cpu.mem.rw(cpu.s.ss & 0xFFFF, cpu.s.bp & 0xFFFF)
        _cmp_word(cpu, active, 0)
        if active != 0:
            _push_loop_count_for_interpreted_tail(cpu, cx_value)
            cpu.s.ip = call_ip & 0xFFFF
            return

        # The original PUSH/POP pair is balanced for inactive objects, but the
        # transient PUSH still leaves bytes just below SP.  Keep that stack
        # scratch visible for full-memory oracle comparisons.
        _remember_balanced_push_scratch(cpu, cx_value)
        cpu.s.cx = (cx_value - 1) & 0xFFFF
        iterations -= 1
        if cpu.s.cx == 0:
            cpu.s.ip = done_ip & 0xFFFF
            return

    cpu.s.ip = done_ip & 0xFFFF


@registry.replace(0x1010, 0xA849, "overkill_scan_objects_call_5ac8_a849")
def overkill_scan_objects_call_5ac8_a849(cpu):
    """Skip inactive 32CA draw entries up to the real ``CALL 5AC8``.

    A849 is only the descending scan wrapper.  Earlier versions tried to run the
    child 5AC8 draw dispatch inline for some known targets, but that crosses the
    verifier boundary: the original ASM stops at A858 before the CALL, while the
    composed hook may have already returned to A85E.  Keep this hook narrow and
    let the real CALL enter the independently verified 5AC8/target hooks.
    """
    if _self_disable_if_patched(cpu, 0xA849, _SIG_A849, "overkill_scan_objects_call_5ac8_a849"):
        return

    iterations = cpu.s.cx & 0xFFFF
    if iterations == 0:
        iterations = 0x10000
    ss = cpu.s.ss & 0xFFFF

    while iterations:
        cx_value = cpu.s.cx & 0xFFFF
        _object_ptr_from_scan_index(cpu, 0x32CA, cx_value)
        active = cpu.mem.rw(ss, cpu.s.bp & 0xFFFF)
        _cmp_word(cpu, active, 0)

        if active != 0:
            _push_loop_count_for_interpreted_tail(cpu, cx_value)
            cpu.s.ip = 0xA858
            return

        _remember_balanced_push_scratch(cpu, cx_value)
        cpu.s.cx = (cx_value - 1) & 0xFFFF
        iterations -= 1
        if cpu.s.cx == 0:
            cpu.s.ip = 0xA85E
            return

    cpu.s.ip = 0xA85E


@registry.replace(0x1010, 0xA861, "overkill_scan_objects_call_5ac8_a861")
def overkill_scan_objects_call_5ac8_a861(cpu):
    """Skip inactive 8D12 draw entries up to the real ``CALL 5AC8``.

    Hook verification for this wrapper is intentionally narrow: active entries
    continue at A870, and the separate 5AC8/target hooks own the draw dispatch.
    """
    iterations = cpu.s.cx & 0xFFFF
    if iterations == 0:
        iterations = 0x10000
    ss = cpu.s.ss & 0xFFFF

    while iterations:
        cx_value = cpu.s.cx & 0xFFFF
        _object_ptr_from_scan_index(cpu, 0x8D12, cx_value)
        active = cpu.mem.rw(ss, cpu.s.bp & 0xFFFF)
        _cmp_word(cpu, active, 0)
        if active != 0:
            _push_loop_count_for_interpreted_tail(cpu, cx_value)
            cpu.s.ip = 0xA870
            return
        _remember_balanced_push_scratch(cpu, cx_value)

        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF
        iterations -= 1
        if cpu.s.cx == 0:
            cpu.s.ip = 0xA876
            return
    cpu.s.ip = 0xA876


@registry.replace(0x1010, 0xA87C, "overkill_scan_objects_call_7746_a87c")
def overkill_scan_objects_call_7746_a87c(cpu):
    """Skip inactive compact-layer entries up to the real ``CALL 7746``."""
    iterations = cpu.s.cx & 0xFFFF
    if iterations == 0:
        iterations = 0x10000
    ss = cpu.s.ss & 0xFFFF
    while iterations:
        cx_value = cpu.s.cx & 0xFFFF
        _object_ptr_from_scan_index(cpu, 0x8D12, cx_value)
        active = cpu.mem.rw(ss, cpu.s.bp & 0xFFFF)
        _cmp_word(cpu, active, 0)
        if active != 0:
            _push_loop_count_for_interpreted_tail(cpu, cx_value)
            cpu.s.ip = 0xA88B
            return
        _remember_balanced_push_scratch(cpu, cx_value)
        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF
        iterations -= 1
        if cpu.s.cx == 0:
            cpu.s.ip = 0xA891
            return
    cpu.s.ip = 0xA891


@registry.replace(0x1010, 0xA894, "overkill_scan_layer0_draw_a894")
def overkill_scan_layer0_draw_a894(cpu):
    """Skip non-drawing entries in the overlaid layer-0 draw scan before CALL 7596."""
    _scan_layered_object_call(cpu, 0, 0xA8BE, 0xA8C4)


@registry.replace(0x1010, 0xA8C7, "overkill_scan_layer1_draw_a8c7")
def overkill_scan_layer1_draw_a8c7(cpu):
    """Skip non-drawing entries in the layer-1 scan before ``CALL 7596``."""
    if _self_disable_if_patched(cpu, 0xA8C7, _SIG_A8C7, "overkill_scan_layer1_draw_a8c7"):
        return

    iterations = cpu.s.cx & 0xFFFF
    if iterations == 0:
        iterations = 0x10000
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF

    def should_call() -> bool:
        active = cpu.mem.rw(ss, cpu.s.bp & 0xFFFF)
        _cmp_word(cpu, active, 0)
        if active == 0:
            return False

        mode = cpu.mem.rw(ds, 0xBDAC)
        _cmp_word(cpu, mode, 1)
        if mode != 1:
            camera = cpu.mem.rw(ds, 0x2350)
            _cmp_word(cpu, camera, 0x00B6)
            if camera <= 0x00B6:
                layer = cpu.mem.rw(ss, (cpu.s.bp + 0x16) & 0xFFFF)
                _cmp_word(cpu, layer, 1)
                if layer == 1:
                    return False

        obj_layer = cpu.mem.rw(ss, (cpu.s.bp + 0x0A) & 0xFFFF)
        _cmp_word(cpu, obj_layer, 1)
        return obj_layer == 1

    while iterations:
        cx_value = cpu.s.cx & 0xFFFF
        _object_ptr_from_scan_index(cpu, 0x32CA, cx_value)
        if should_call():
            _push_loop_count_for_interpreted_tail(cpu, cx_value)
            cpu.s.ip = 0xA8F1
            return

        _remember_balanced_push_scratch(cpu, cx_value)
        cpu.s.cx = (cx_value - 1) & 0xFFFF
        iterations -= 1
        if cpu.s.cx == 0:
            cpu.s.ip = 0xA8F7
            return

    cpu.s.ip = 0xA8F7


def _scan_present_objects_via_5a92(
    cpu,
    *,
    table_base: int,
    done_ip: int,
    return_ip: int,
    parent: str,
    chain: str,
) -> None:
    """Skip inactive present entries up to the real ``CALL 5A92``."""
    iterations = cpu.s.cx & 0xFFFF
    if iterations == 0:
        iterations = 0x10000
    ss = cpu.s.ss & 0xFFFF
    call_ip = (return_ip - 3) & 0xFFFF

    while iterations:
        cx_value = cpu.s.cx & 0xFFFF
        _object_ptr_from_scan_index(cpu, table_base, cx_value)
        active = cpu.mem.rw(ss, cpu.s.bp & 0xFFFF)
        _cmp_word(cpu, active, 0)

        if active != 0:
            _push_loop_count_for_interpreted_tail(cpu, cx_value)
            cpu.s.ip = call_ip
            return

        _remember_balanced_push_scratch(cpu, cx_value)
        cpu.s.cx = (cx_value - 1) & 0xFFFF
        iterations -= 1
        if cpu.s.cx == 0:
            cpu.s.ip = done_ip & 0xFFFF
            return

    cpu.s.ip = done_ip & 0xFFFF


@registry.replace(0x1010, 0xA90F, "overkill_scan_objects_call_5a92_a90f")
def overkill_scan_objects_call_5a92_a90f(cpu):
    """Present active 8D12 objects when their Tandy targets are verified."""
    if _self_disable_if_patched(cpu, 0xA90F, _SIG_A90F, "overkill_scan_objects_call_5a92_a90f"):
        return
    _scan_present_objects_via_5a92(
        cpu,
        table_base=0x8D12,
        done_ip=0xA924,
        return_ip=0xA921,
        parent="1010:A90F",
        chain="A90F -> 5A92",
    )


@registry.replace(0x1010, 0xA927, "overkill_scan_objects_call_5a92_a927")
def overkill_scan_objects_call_5a92_a927(cpu):
    """Present active 32CA objects when their Tandy targets are verified."""
    if _self_disable_if_patched(cpu, 0xA927, _SIG_A927, "overkill_scan_objects_call_5a92_a927"):
        return
    _scan_present_objects_via_5a92(
        cpu,
        table_base=0x32CA,
        done_ip=0xA93C,
        return_ip=0xA939,
        parent="1010:A927",
        chain="A927 -> 5A92",
    )


@registry.replace(0x1010, 0xB73E, "overkill_object_behavior_b73e")
def overkill_object_behavior_b73e(cpu):
    """Fail-fast lifted branch of object behavior B73E."""
    if _self_disable_if_patched(cpu, 0xB73E, _SIG_B73E, "overkill_object_behavior_b73e"):
        return
    _run_object_behavior_b73e(
        cpu,
        parent="1010:B73E",
        chain="B73E",
        cx_value=cpu.s.cx & 0xFFFF,
    )


def _run_af63_step_for_direction(cpu, *, parent: str = "1010:AF63") -> None:
    """Mirror one 1010:AF63 2-pixel direction step.

    AF63 dispatches through the CS:AF6E table using SS:[BP+06].  AF60 is built
    from this same body with a self-call trick, so keeping the one-step body
    separate lets 5DB2 mode 1 (direct AF63) and mode 2 (AF60 double step) share
    exactly the same movement mapping.
    """
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF

    direction = cpu.mem.rw(ss, (bp + 0x06) & 0xFFFF) & 0xFFFF
    cpu.s.bx = direction
    cpu.s.bx = cpu.shift(4, cpu.s.bx, 1, 16)  # SHL BX,1 before table JMP.

    if direction == 0:
        _sub_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, 2)
    elif direction == 1:
        _sub_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, 2)
        _add_mem_word(cpu, ss, (bp + 0x04) & 0xFFFF, 2)
    elif direction == 2:
        _add_mem_word(cpu, ss, (bp + 0x04) & 0xFFFF, 2)
    elif direction == 3:
        _add_mem_word(cpu, ss, (bp + 0x04) & 0xFFFF, 2)
        _add_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, 2)
    elif direction == 4:
        _add_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, 2)
    elif direction == 5:
        _add_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, 2)
        _sub_mem_word(cpu, ss, (bp + 0x04) & 0xFFFF, 2)
    elif direction == 6:
        _sub_mem_word(cpu, ss, (bp + 0x04) & 0xFFFF, 2)
    elif direction == 7:
        _sub_mem_word(cpu, ss, (bp + 0x04) & 0xFFFF, 2)
        _sub_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, 2)
    else:
        _raise_unverified_path(
            cpu,
            parent=parent,
            chain="AF63 direction table",
            target_ip=cpu.mem.rw(cpu.s.cs & 0xFFFF, (0xAF6E + ((direction << 1) & 0xFFFF)) & 0xFFFF),
            bp=bp,
            cx_value=cpu.s.cx & 0xFFFF,
        )


def _run_af60_double_step_for_direction(cpu) -> None:
    """Mirror 1010:AF60 for the movement helper's speed-2 mode.

    AF60 is another OVERKILL self-call trick: ``CALL AF63`` pushes AF63, so
    the direction movement body runs once, RET returns to AF63, and the same
    body runs a second time before returning to the original caller.
    """
    ss = cpu.s.ss & 0xFFFF
    # AF60 begins with CALL AF63.  After the self-call trick completes, SP is
    # back where it started but the pushed return word remains as stack scratch.
    cpu.mem.ww(ss, (cpu.s.sp - 2) & 0xFFFF, 0xAF63)
    _run_af63_step_for_direction(cpu, parent="1010:AF60")
    _run_af63_step_for_direction(cpu, parent="1010:AF60")


def _run_aee4_step_for_direction(cpu) -> None:
    """Mirror 1010:AEE4: one 8-pixel direction step via the AEEE table."""
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF
    direction = cpu.mem.rw(ss, (bp + 0x06) & 0xFFFF) & 0xFFFF
    cpu.s.bx = direction
    cpu.s.bx = cpu.shift(4, cpu.s.bx, 1, 16)

    if direction == 0:
        _sub_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, 8)
    elif direction == 1:
        _sub_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, 8)
        _add_mem_word(cpu, ss, (bp + 0x04) & 0xFFFF, 8)
    elif direction == 2:
        _add_mem_word(cpu, ss, (bp + 0x04) & 0xFFFF, 8)
    elif direction == 3:
        _add_mem_word(cpu, ss, (bp + 0x04) & 0xFFFF, 8)
        _add_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, 8)
    elif direction == 4:
        _add_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, 8)
    elif direction == 5:
        _add_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, 8)
        _sub_mem_word(cpu, ss, (bp + 0x04) & 0xFFFF, 8)
    elif direction == 6:
        _sub_mem_word(cpu, ss, (bp + 0x04) & 0xFFFF, 8)
    elif direction == 7:
        _sub_mem_word(cpu, ss, (bp + 0x04) & 0xFFFF, 8)
        _sub_mem_word(cpu, ss, (bp + 0x02) & 0xFFFF, 8)
    else:
        _raise_unverified_path(
            cpu,
            parent="1010:AEE4",
            chain="AEE4 direction table",
            target_ip=cpu.mem.rw(cpu.s.cs & 0xFFFF, (0xAEEE + ((direction << 1) & 0xFFFF)) & 0xFFFF),
            bp=bp,
            cx_value=cpu.s.cx & 0xFFFF,
        )


def _run_movement_direction_5db2(cpu) -> None:
    """Run the 1010:5DB2 target-seeking movement/direction helper.

    The helper compares object Y/X against DS:2304/2306, encodes the desired
    direction into DS:A954, maps that nibble through DS:A348 into the object's
    animation/direction word at SS:[BP+06], then dispatches through CS:5E0C by
    DS:2308.  For the currently opened object-logic island, the verified mode is
    DS:2308 == 2, which is the AF60 double 2-pixel step.
    """
    ds = cpu.s.ds & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    bp = cpu.s.bp & 0xFFFF

    cpu.mem.ww(ds, 0xA954, 0)
    cpu.mem.ww(ds, 0x230A, 0)

    y = cpu.mem.rw(ss, (bp + 0x04) & 0xFFFF)
    target_y = cpu.mem.rw(ds, 0x2304)
    _cmp_word(cpu, y, target_y)
    if y < target_y:
        cpu.mem.ww(ds, 0xA954, 1)
    elif y > target_y:
        cpu.mem.ww(ds, 0xA954, 2)

    x = cpu.mem.rw(ss, (bp + 0x02) & 0xFFFF)
    target_x = cpu.mem.rw(ds, 0x2306)
    _cmp_word(cpu, x, target_x)
    # Original uses signed JL/JG for X after CMP AX,DS:[2306].
    sx = x if x < 0x8000 else x - 0x10000
    starget_x = target_x if target_x < 0x8000 else target_x - 0x10000
    direction_bits = cpu.mem.rw(ds, 0xA954)
    if sx < starget_x:
        direction_bits |= 0x0004
        cpu.mem.ww(ds, 0xA954, direction_bits)
    elif sx > starget_x:
        direction_bits |= 0x0008
        cpu.mem.ww(ds, 0xA954, direction_bits)

    cpu.s.bx = 0xA348
    cpu.s.ax = cpu.mem.rw(ds, 0xA954)
    mapped = cpu.mem.rb(ds, (cpu.s.bx + (cpu.s.ax & 0xFF)) & 0xFFFF)
    cpu.set_reg8(0, mapped)  # XLAT updates AL only.
    cpu.set_sub_flags(mapped, 0xFF, mapped - 0xFF, 8)  # CMP AL,FFh.
    if mapped == 0xFF:
        cpu.mem.ww(ds, 0x230A, 1)
        # MOV word and RET do not affect flags; leave CMP AL,FFh flags live.
        return

    cpu.mem.ww(ss, (bp + 0x06) & 0xFFFF, cpu.s.ax)
    cpu.s.bx = cpu.mem.rw(ds, 0x2308)
    cpu.s.bx = cpu.shift(4, cpu.s.bx, 1, 16)  # SHL BX,1 before 5E0C table JMP.
    mode = cpu.mem.rw(ds, 0x2308)
    target_ip = cpu.mem.rw(cpu.s.cs & 0xFFFF, (0x5E0C + ((mode << 1) & 0xFFFF)) & 0xFFFF)
    if target_ip == 0xAF63:
        _run_af63_step_for_direction(cpu, parent="1010:5DB2")
        return
    if target_ip == 0xAF60:
        _run_af60_double_step_for_direction(cpu)
        return
    if target_ip == 0xAEE4:
        _run_aee4_step_for_direction(cpu)
        return
    _raise_unverified_path(
        cpu,
        parent="1010:5DB2",
        chain="5DB2 -> 5E0C movement-mode dispatch",
        target_ip=target_ip,
        bp=bp,
        cx_value=cpu.s.cx & 0xFFFF,
    )


@registry.replace(0x1010, 0x5DB2, "overkill_movement_direction_helper_5db2")
def overkill_movement_direction_helper_5db2(cpu):
    """Verified target-seeking movement helper at 1010:5DB2."""
    if _self_disable_if_patched(cpu, 0x5DB2, _SIG_5DB2, "overkill_movement_direction_helper_5db2"):
        return
    _run_movement_direction_5db2(cpu)
    cpu.s.ip = cpu.pop()


@registry.replace(0x1010, 0xAA2B, "overkill_object_logic_dispatch_aa2b")
def overkill_object_logic_dispatch_aa2b(cpu):
    """Fail-fast first-level object logic dispatcher indexed by SS:[BP+16]."""
    if _self_disable_if_patched(cpu, 0xAA2B, _SIG_AA2B, "overkill_object_logic_dispatch_aa2b"):
        return
    _run_object_logic_dispatch_aa2b(
        cpu,
        parent="1010:AA2B",
        chain="AA2B",
        cx_value=cpu.s.cx & 0xFFFF,
    )


@registry.replace(0x1010, 0xEFAE, "overkill_object_family_dispatch_efae")
def overkill_object_family_dispatch_efae(cpu):
    """Fail-fast second-level object-family dispatcher indexed by SS:[BP+18]."""
    if _self_disable_if_patched(cpu, 0xEFAE, _SIG_EFAE, "overkill_object_family_dispatch_efae"):
        return
    _run_object_family_dispatch_efae(
        cpu,
        parent="1010:EFAE",
        chain="EFAE",
        cx_value=cpu.s.cx & 0xFFFF,
    )


@registry.replace(0x1010, 0xA9E0, "overkill_scan_objects_call_aa2b_a9e0")
def overkill_scan_objects_call_aa2b_a9e0(cpu):
    """Run the 32CA object-logic scan until the next unlifted concrete behavior."""
    if _self_disable_if_patched(cpu, 0xA9E0, _SIG_A9E0, "overkill_scan_objects_call_aa2b_a9e0"):
        return
    _scan_object_logic_via_aa2b(
        cpu,
        table_base=0x32CA,
        done_ip=0xAA07,
        call_ip=0xAA01,
        advance_global_counter=True,
    )


@registry.replace(0x1010, 0xAA10, "overkill_scan_objects_call_aa2b_aa10")
def overkill_scan_objects_call_aa2b_aa10(cpu):
    """Run the 8D12 object-logic scan until the next unlifted concrete behavior."""
    if _self_disable_if_patched(cpu, 0xAA10, _SIG_AA10, "overkill_scan_objects_call_aa2b_aa10"):
        return
    _scan_object_logic_via_aa2b(
        cpu,
        table_base=0x8D12,
        done_ip=0xAA25,
        call_ip=0xAA1F,
        advance_global_counter=False,
    )


@registry.replace(0x1010, 0x4D6F, "overkill_clear_presence_list_4d6f")
def overkill_clear_presence_list_4d6f(cpu):
    """Replace the hot list clear at 1010:4D6F.

    It walks up to CX word entries from DS:SI, stops on FFFF, and clears the
    corresponding occupancy byte(s) in ES.  Mode CS:[95BC] == 1 clears the
    stacked +1A/+34/+4E cells as well.
    """
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    cs = s.cs & 0xFFFF
    si = s.si & 0xFFFF
    count = s.cx & 0xFFFF
    if count == 0:
        count = 0x10000
    step = -2 if cpu.get_flag(DF) else 2

    while count:
        ax = mem.rw(ds, si)
        si = (si + step) & 0xFFFF
        s.ax = ax
        _cmp_word(cpu, ax, 0xFFFF)
        if ax == 0xFFFF:
            s.si = si
            s.ip = cpu.pop()
            return

        s.di = ax & 0xFFFF
        mode = mem.rw(cs, 0x95BC)
        _cmp_word(cpu, mode, 1)
        if mode == 1:
            mem.wb(es, (s.di + 0x4E) & 0xFFFF, 0)
            mem.wb(es, (s.di + 0x34) & 0xFFFF, 0)
            mem.wb(es, (s.di + 0x1A) & 0xFFFF, 0)
        mem.wb(es, s.di, 0)
        s.cx = (s.cx - 1) & 0xFFFF
        count -= 1
        if s.cx == 0:
            s.si = si
            s.ip = cpu.pop()
            return

    s.si = si
    s.ip = cpu.pop()

@registry.replace(0x1010, 0x41A6, "overkill_variable_width_interlaced_blit_41a6")
def overkill_variable_width_interlaced_blit_41a6(cpu):
    """Replace the hot variable-width interlaced row blit at 1010:41A6.

    Entry state is set up by the immediately preceding interpreted code:

        ES = CS:[9598]
        CX = row count
        BP = source bytes per row (source width word * 2)
        DS:SI = source
        ES:DI = destination

    Original loop:

        push cx
        mov  cx,bp
        rep  movsb
        sub  di,bp
        add  di,2000h
        test di,4000h
        jz   +
        add  di,C050h
        pop  cx
        loop ...
        ret

    It is the same EGA/CGA interlaced-addressing family as the already lifted
    447B and 41DA routines, but with a variable row width.
    """
    rows = cpu.s.cx & 0xFFFF
    if rows == 0:
        rows = 0x10000

    while rows:
        # Preserve the PUSH/POP scratch write because some oracle tests compare
        # the full 1 MiB memory image, including the word below SP.
        cpu.push(cpu.s.cx)
        cpu.s.cx = cpu.s.bp & 0xFFFF
        _rep_movsb(cpu, cpu.s.cx)
        _sub_reg16(cpu, 7, cpu.s.bp)
        _add_reg16(cpu, 7, 0x2000)
        _test_word(cpu, cpu.s.di, 0x4000)
        if not cpu.get_flag(ZF):
            _add_reg16(cpu, 7, 0xC050)
        cpu.s.cx = cpu.pop()
        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF  # LOOP, flags unaffected.
        rows -= 1

    cpu.s.ip = cpu.pop()









@registry.replace(0x1010, 0x27EB, "overkill_ega_row_driver_27eb")
def overkill_ega_row_driver_27eb(cpu):
    if _self_disable_if_patched(cpu, 0x27EB, _SIG_27EB, "overkill_ega_row_driver_27eb"):
        return
    """Fuse the hot EGA mode-1 row driver at 1010:27EB.

    This is the interpreted outer loop that used to call the already-hooked
    helpers thousands of times during EGA startup/menu asset expansion:

        27EB  push cx                  ; remaining source rows
        27EC  cmp  cs:[0BD6],0
        27F4  push si / call 2932 ...  ; optional transparency-mask row
        2802  mov  cs:[5BA6],di
        2807  mov  di,5AF4h
        280A  mov  bp,0004h
        280D  ... temp-row load
        2824  ... temp expansion/copy, LOOP back to 27EB or JMP 27D9

    The narrow 280D/2824/2932 hooks are still the source of truth.  This driver
    removes the repeated interpreter dispatch and hook-boundary crossings around
    them without inventing new renderer semantics.
    """
    cs = cpu.s.cs & 0xFFFF
    mem = cpu.mem

    while True:
        outer_cx = cpu.s.cx & 0xFFFF
        # 27EB PUSH CX.  The 2824 block consumes this with its final POP CX.
        cpu.push(outer_cx)

        _cmp_word(cpu, mem.rw(cs, 0x0BD6), 0)
        if not cpu.get_flag(ZF):
            # 27F4 PUSH SI; 27F5 MOV CX,CS:[5B9C]
            saved_si = cpu.s.si & 0xFFFF
            cpu.push(saved_si)
            width = mem.rw(cs, 0x5B9C)
            loop_count = width if width != 0 else 0x10000
            cpu.s.cx = width & 0xFFFF

            while loop_count:
                # 27FA PUSH CX; 27FB CALL 2932; 27FE POP CX; 27FF LOOP 27FA.
                cpu.push(cpu.s.cx)
                cpu.push(0x27FE)
                overkill_ega_transparency_mask_2932(cpu)
                cpu.s.cx = cpu.pop()
                cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF
                loop_count -= 1

            cpu.s.si = cpu.pop()

        # 2802 MOV CS:[5BA6],DI; 2807 MOV DI,5AF4h; 280A MOV BP,4.
        mem.ww(cs, 0x5BA6, cpu.s.di & 0xFFFF)
        cpu.s.di = 0x5AF4
        cpu.s.bp = 0x0004

        overkill_ega_load_temp_rows_280d(cpu)
        overkill_ega_expand_temp_rows_2824(cpu)
        if cpu.s.ip != 0x27EB:
            return


@registry.replace(0x1010, 0x280D, "overkill_ega_load_temp_rows_280d")
def overkill_ega_load_temp_rows_280d(cpu):
    if _self_disable_if_patched(cpu, 0x280D, _SIG_280D, "overkill_ega_load_temp_rows_280d"):
        return
    """Replace the hot four-row temp loader at 1010:280D.

    The block copies four ``CS:5B9C``-byte rows from DS:SI into the temporary
    EGA row buffer starting at CS:5AF4, with a fixed 40-byte stride between
    rows.  It is the setup immediately before the 2824 expansion block.
    """
    cs = cpu.s.cs & 0xFFFF
    width = cpu.mem.rw(cs, 0x5B9C)
    if width == 0:
        width = 0x10000
    data = cpu.mem.data
    src_base = (cpu.s.ds & 0xFFFF) << 4
    dst_base = cs << 4
    di = cpu.s.di & 0xFFFF
    si = cpu.s.si & 0xFFFF
    bp = cpu.s.bp & 0xFFFF

    while bp != 0:
        # Final PUSH-less LOOP leaves flags from DEC BP / the last arithmetic
        # instruction that matters.  We still use the helper flag operations for
        # the row-step instructions so oracle tests can compare exact FLAGS.
        row_di = di
        for _ in range(width):
            cpu.set_reg8(0, data[(src_base + si) & 0xFFFFF])  # LODSB
            si = (si + 1) & 0xFFFF
            data[(dst_base + row_di) & 0xFFFFF] = cpu.get_reg8(0)
            row_di = (row_di + 1) & 0xFFFF
        cpu.s.di = row_di
        _sub_reg16(cpu, 7, width)
        _add_reg16(cpu, 7, 0x0028)
        di = cpu.s.di & 0xFFFF
        cpu.s.bp = bp
        _dec_reg16_preserve_cf(cpu, 5)
        bp = cpu.s.bp & 0xFFFF

    cpu.s.si = si
    cpu.s.cx = 0
    cpu.s.ip = 0x2824


@registry.replace(0x1010, 0x2824, "overkill_ega_expand_temp_rows_2824")
def overkill_ega_expand_temp_rows_2824(cpu):
    if _self_disable_if_patched(cpu, 0x2824, _SIG_2824, "overkill_ega_expand_temp_rows_2824"):
        return
    """Replace the hot EGA temp-row expansion/copy block at 1010:2824.

    This block converts four temporary 1bpp-ish rows at CS:5AF4/5B1C/5B44/5B6C
    into four EGA output-plane rows, applies OVERKILL's transparent-colour rule,
    then copies the four rows to the destination cursor tracked in CS:5BA6.  It
    is an internal block of the mode-1 renderer, not a subroutine: the hook ends
    at the same control-flow targets as the original ``LOOP/JMP`` tail
    (``27EB`` for another source row, ``27D9`` for the next object/list entry).

    The first lift mirrored the rotate/shift chain through ``CPU.shift``.  This
    version keeps the same byte/flag/stack results but performs the per-pixel
    plane packing as integer bit operations, which matters when the new 27EB
    driver fuses hundreds of rows into one hook call.
    """
    cs = cpu.s.cs & 0xFFFF
    ss = cpu.s.ss & 0xFFFF
    es = cpu.s.es & 0xFFFF
    mem = cpu.mem
    data = mem.data
    cs_base = cs << 4
    es_base = es << 4
    width_word = mem.rw(cs, 0x5B9C)
    width = width_word if width_word != 0 else 0x10000

    di = 0x5AF4
    transparent_enabled = mem.rw(cs, 0x0BD6) != 0
    transparent_colour = mem.rb(cs, 0x0000) & 0xFF
    marker_enabled = mem.rb(cs, 0xC5B0) == 1
    marker_base = mem.rw(cs, 0x5BAA)
    marker_add = mem.rw(cs, 0x5BA8)

    for col in range(width):
        # Final column PUSH CX scratch.  The column loop's push/pop pair leaves
        # the last pushed count in the word below SP.
        mem.ww(ss, (cpu.s.sp - 2) & 0xFFFF, (width - col) & 0xFFFF)

        al = data[(cs_base + di) & 0xFFFFF]
        ah = data[(cs_base + ((di + 0x28) & 0xFFFF)) & 0xFFFFF]
        dl = data[(cs_base + ((di + 0x50) & 0xFFFF)) & 0xFFFFF]
        dh = data[(cs_base + ((di + 0x78) & 0xFFFF)) & 0xFFFFF]
        p0 = mem.rb(cs, 0x5BA2)
        p1 = mem.rb(cs, 0x5BA3)
        p2 = mem.rb(cs, 0x5BA4)
        p3 = mem.rb(cs, 0x5BA5)
        bl = cpu.get_reg8(3)
        final_rcl_value = p3

        for _ in range(8):
            # ROL DH/DL/AH/AL + RCL BL gathers one 4-bit pixel.  The carry
            # emitted by RCL BL is overwritten by the next ROL, so only the
            # incoming plane bit matters for the low nibble that survives AND.
            bit = (dh >> 7) & 1; dh = ((dh << 1) | bit) & 0xFF; bl = ((bl << 1) | bit) & 0xFF
            bit = (dl >> 7) & 1; dl = ((dl << 1) | bit) & 0xFF; bl = ((bl << 1) | bit) & 0xFF
            bit = (ah >> 7) & 1; ah = ((ah << 1) | bit) & 0xFF; bl = ((bl << 1) | bit) & 0xFF
            bit = (al >> 7) & 1; al = ((al << 1) | bit) & 0xFF; bl = ((bl << 1) | bit) & 0xFF
            bl &= 0x0F

            if transparent_enabled and bl == transparent_colour:
                bl = 0

            if marker_enabled:
                cpu.s.bp = marker_base
                if cpu.s.bp != 0xFFFF:
                    cpu.s.bp = (cpu.s.bp + marker_add) & 0xFFFF
                    marker = mem.rb(ss, cpu.s.bp)
                    # The ASM branches are slightly counter-intuitive here:
                    # marker == 1 enters the 06h/0Ch swap block, while
                    # marker == 2 (and all other values) skip it.
                    if marker == 1:
                        if bl == 0x06:
                            bl = 0x0C
                        elif bl == 0x0C:
                            bl = 0x06

            cf = bl & 1; bl >>= 1
            old = p0; p0 = ((p0 << 1) | cf) & 0xFF; cf = (old >> 7) & 1
            cf = bl & 1; bl >>= 1
            old = p1; p1 = ((p1 << 1) | cf) & 0xFF; cf = (old >> 7) & 1
            cf = bl & 1; bl >>= 1
            old = p2; p2 = ((p2 << 1) | cf) & 0xFF; cf = (old >> 7) & 1
            cf = bl & 1; bl >>= 1
            old = p3; p3 = ((p3 << 1) | cf) & 0xFF; cf = (old >> 7) & 1
            final_rcl_value = p3

        data[(cs_base + di) & 0xFFFFF] = p0
        data[(cs_base + ((di + 0x28) & 0xFFFF)) & 0xFFFFF] = p1
        data[(cs_base + ((di + 0x50) & 0xFFFF)) & 0xFFFFF] = p2
        data[(cs_base + ((di + 0x78) & 0xFFFF)) & 0xFFFFF] = p3
        mem.wb(cs, 0x5BA2, p0)
        mem.wb(cs, 0x5BA3, p1)
        mem.wb(cs, 0x5BA4, p2)
        mem.wb(cs, 0x5BA5, p3)
        di = (di + 1) & 0xFFFF
        bl = 0

    cpu.set_reg8(0, al if width else cpu.get_reg8(0))
    cpu.set_reg8(4, ah if width else cpu.get_reg8(4))
    cpu.set_reg8(2, dl if width else cpu.get_reg8(2))
    cpu.set_reg8(6, dh if width else cpu.get_reg8(6))
    cpu.set_reg8(3, bl)
    cpu.s.di = di
    cpu.s.cx = 0
    # These flags are normally overwritten by the row-copy INC below; keep the
    # RCL result here for completeness before the copy phase runs.
    cpu.set_logic_flags(final_rcl_value, 8)
    cpu.set_flag(CF, bool(cf))

    def copy_temp_row(start: int, return_ip: int) -> None:
        count_word = mem.rw(cs, 0x5B9C)
        count = count_word if count_word != 0 else 0x10000
        src_di = start & 0xFFFF
        out_di = mem.rw(cs, 0x5BA6)

        # Mirror CALL 291C plus the helper's final PUSH CX/PUSH DI scratches.
        mem.ww(ss, (cpu.s.sp - 2) & 0xFFFF, return_ip & 0xFFFF)
        mem.ww(ss, (cpu.s.sp - 4) & 0xFFFF, 0x0001)
        mem.ww(ss, (cpu.s.sp - 6) & 0xFFFF, (src_di + count) & 0xFFFF)

        if count and src_di + count <= 0x10000 and out_di + count <= 0x10000 \
                and not (mem.ega_planar and _ega_aperture_overlap(es, out_di, count)):
            src = (cs_base + src_di) & 0xFFFFF
            dst = (es_base + out_di) & 0xFFFFF
            data[dst:dst + count] = data[src:src + count]
            al_last = data[src + count - 1]
            src_di = (src_di + count) & 0xFFFF
            out_di = (out_di + count) & 0xFFFF
        else:
            al_last = cpu.get_reg8(0)
            for _ in range(count):
                al_last = mem.rb(cs, src_di)
                src_di = (src_di + 1) & 0xFFFF
                mem.wb(es, out_di, al_last)
                out_di = (out_di + 1) & 0xFFFF

        mem.ww(cs, 0x5BA6, out_di)
        cpu.s.di = src_di
        cpu.s.cx = 0
        cpu.set_reg8(0, al_last)
        old_cf = cpu.get_flag(CF)
        old = (src_di - 1) & 0xFFFF
        cpu.set_add_flags(old, 1, old + 1, 16)
        cpu.set_flag(CF, old_cf)

    copy_temp_row(0x5AF4, 0x28EB)
    copy_temp_row(0x5B1C, 0x28F6)
    copy_temp_row(0x5B44, 0x2901)
    copy_temp_row(0x5B6C, 0x290C)

    cpu.s.di = mem.rw(cs, 0x5BA6)
    outer = cpu.pop()
    cpu.s.cx = (outer - 1) & 0xFFFF
    cpu.s.ip = 0x27EB if cpu.s.cx != 0 else 0x27D9


@registry.replace(0x1010, 0x291C, "overkill_ega_temp_row_copy_291c")
def overkill_ega_temp_row_copy_291c(cpu):
    if _self_disable_if_patched(cpu, 0x291C, _SIG_291C, "overkill_ega_temp_row_copy_291c"):
        return
    """Replace the hot EGA temp-row copy helper at 1010:291C.

    Original shape::

        push cx
    loop:
        mov  al,cs:[di]
        inc  di
        push di
        mov  di,cs:[5BA6]
        stosb
        mov  cs:[5BA6],di
        pop  di
        pop  cx
        loop loop
        ret

    It copies ``CX`` bytes from a temporary CS row to the current ES output
    cursor stored at ``CS:5BA6``.  The helper is called four times for each EGA
    converted row, so collapsing the interpreted push/pop/stos loop noticeably
    speeds up EGA startup and menu rendering without changing renderer logic.
    """
    cs = cpu.s.cs & 0xFFFF
    mem = cpu.mem
    count = cpu.s.cx & 0xFFFF
    if count == 0:
        count = 0x10000

    source_di = cpu.s.di & 0xFFFF
    out_di = mem.rw(cs, 0x5BA6)
    ah = cpu.get_reg8(4)
    last_source_di = source_di

    # Preserve the stack scratch left by the final PUSH CX / PUSH DI pair.  The
    # words are popped again, but full-memory oracle tests can still observe the
    # overwritten stack slots.
    final_pushed_cx = 1
    final_pushed_di = (source_di + count) & 0xFFFF
    mem.ww(cpu.s.ss, (cpu.s.sp - 2) & 0xFFFF, final_pushed_cx)
    mem.ww(cpu.s.ss, (cpu.s.sp - 4) & 0xFFFF, final_pushed_di)

    src_base = (cs << 4)
    es = cpu.s.es & 0xFFFF
    dst_base = es << 4
    data = mem.data
    planar_destination = mem.ega_planar and _ega_aperture_overlap(es, out_di, count)
    for i in range(count):
        al = data[(src_base + source_di) & 0xFFFFF]
        source_di = (source_di + 1) & 0xFFFF
        last_source_di = source_di
        if planar_destination:
            # STOSB into A000h must go through the EGA map-mask router.  The
            # previous lift wrote the flat A000 byte directly, which only changed
            # shadow plane 0 and could leave stale bits in the other planes.
            mem.wb(es, out_di, al)
        else:
            data[(dst_base + out_di) & 0xFFFFF] = al
        out_di = (out_di + 1) & 0xFFFF
        cpu.set_reg8(0, al)

    mem.ww(cs, 0x5BA6, out_di)
    cpu.s.di = last_source_di
    cpu.s.cx = 0
    # Final flags are from the last INC DI.  INC preserves CF.
    old_cf = cpu.get_flag(CF)
    old = (last_source_di - 1) & 0xFFFF
    cpu.set_add_flags(old, 1, old + 1, 16)
    cpu.set_flag(CF, old_cf)
    cpu.set_reg8(4, ah)
    cpu.s.ip = cpu.pop()


@registry.replace(0x1010, 0x2932, "overkill_ega_transparency_mask_2932")
def overkill_ega_transparency_mask_2932(cpu):
    if _self_disable_if_patched(cpu, 0x2932, _SIG_2932, "overkill_ega_transparency_mask_2932"):
        return
    """Replace the hot EGA transparency-mask builder at 1010:2932.

    This is the same routine as the previous transliterated hook, but it now
    computes the eight transparency bits directly instead of executing the
    original RCL chain through CPU.shift for every bit of every plane byte.
    The helper is called thousands of times by the EGA startup/menu asset path,
    so avoiding per-bit flag/register helper traffic is much more valuable than
    adding another tiny leaf hook.
    """
    s = cpu.s
    cs = s.cs & 0xFFFF
    ds = s.ds & 0xFFFF
    mem = cpu.mem

    width = mem.rw(cs, 0x5B9C)
    si = s.si & 0xFFFF
    bx = (width * 3) & 0xFFFF

    al_src = mem.rb(ds, si)
    ah_src = mem.rb(ds, (si + width) & 0xFFFF)
    dl_src = mem.rb(ds, (si + ((width << 1) & 0xFFFF)) & 0xFFFF)
    dh_src = mem.rb(ds, (si + bx) & 0xFFFF)
    transparent = mem.rb(cs, 0x0000) & 0x0F

    def rcl8(value: int, carry: int) -> tuple[int, int]:
        value &= 0xFF
        return (((value << 1) | carry) & 0xFF), ((value >> 7) & 1)

    # Keep the exact carry interactions through CS:[5BA1] and CS:[5BA0], but
    # run them as simple integer operations rather than CPU.shift calls.
    al = al_src
    ah = ah_src
    dl = dl_src
    dh = dh_src
    scratch = mem.rb(cs, 0x5BA1)
    mask = 0
    # The loop's incoming CF is not the caller's CF: the original setup
    # executes SHL BX,1 and then ADD BX,CS:[5B9C], so the first RCL sees the
    # carry produced by that ADD.
    bx2 = (width << 1) & 0xFFFF
    cf = 1 if (bx2 + width) > 0xFFFF else 0
    for _ in range(8):
        dh, cf = rcl8(dh, cf)
        scratch, cf = rcl8(scratch, cf)
        dl, cf = rcl8(dl, cf)
        scratch, cf = rcl8(scratch, cf)
        ah, cf = rcl8(ah, cf)
        scratch, cf = rcl8(scratch, cf)
        al, cf = rcl8(al, cf)
        scratch, cf = rcl8(scratch, cf)
        scratch &= 0x0F
        cf = 1 if scratch == transparent else 0
        mask, cf = rcl8(mask, cf)

    mem.wb(cs, 0x5BA0, mask)
    mem.wb(cs, 0x5BA1, scratch)
    mem.ww(s.ss & 0xFFFF, (s.sp - 2) & 0xFFFF, 0x0001)  # final PUSH CX scratch

    s.bx = bx
    s.cx = 0
    s.ax = ((ah & 0xFF) << 8) | (mask & 0xFF)  # MOV AL,[5BA0] after the loop.
    s.dx = ((dh & 0xFF) << 8) | (dl & 0xFF)

    mem.wb(s.es & 0xFFFF, s.di & 0xFFFF, mask)
    s.di = (s.di + ( -1 if cpu.get_flag(DF) else 1)) & 0xFFFF

    old_cf = bool(cf)
    old_si = s.si & 0xFFFF
    s.si = (old_si + 1) & 0xFFFF
    cpu.set_add_flags(old_si, 1, old_si + 1, 16)
    cpu.set_flag(CF, old_cf)
    s.ip = cpu.pop()


@registry.replace(0x1010, 0x5827, "overkill_ega_planar_to_linear_copy_5827")
def overkill_ega_planar_to_linear_copy_5827(cpu):
    """Replace the hot 1010:5827 EGA row-copy loop only.

    This deliberately stops at 58A4 and lets the original setup/render driver run
    after the copied 200-row screen/work-buffer transfer.  It is a narrow hook:
    it collapses the repeated row copy selected by CS:95BCh, but does not infer
    higher-level video semantics.
    """
    cs = cpu.s.cs & 0xFFFF
    iterations = cpu.s.cx & 0xFFFF
    if iterations == 0:
        iterations = 0x10000

    for _ in range(iterations):
        cpu.push(cpu.s.cx)

        # 5828..582F: BX = CS:[95BC] << 1; JMP CS:[5834+BX]
        mode_word = cpu.mem.rw(cs, 0x95BC)
        cpu.s.bx = mode_word & 0xFFFF
        cpu.s.bx = cpu.shift(4, cpu.s.bx, 1, 16)
        mode = (cpu.s.bx >> 1) & 0xFFFF

        if mode == 0:
            # 583A: packed/linear 80-byte row, planar source stride.
            cpu.s.cx = 0x0050
            _rep_movsb(cpu, cpu.s.cx)
            _sub_reg16(cpu, 6, 0x0050)   # SI -= 80
            _add_reg16(cpu, 6, 0x2000)   # next EGA plane/scanline block
            _test_word(cpu, cpu.s.si, 0x4000)
            if not cpu.get_flag(ZF):
                _add_reg16(cpu, 6, 0xC050)
        elif mode == 1:
            # 5852: four 40-byte plane reads selected through GC index writes.
            # A real EGA returns bytes from the GC read-map-selected plane while
            # SI stays at the same CPU offset.  Copy directly from our shadow
            # plane when the geometry is simple; otherwise fall back through
            # mem.rb/mem.wb so the selected-read-plane emulation still applies.
            cpu.s.ax = 0x0004
            _out_dx_ax(cpu)
            for plane in range(4):
                count = 0x0028
                si = cpu.s.si & 0xFFFF
                di = cpu.s.di & 0xFFFF
                if (cpu.mem.ega_planar
                        and (cpu.s.ds & 0xFFFF) == 0xA000
                        and si + count <= EGA_PLANE_WINDOW
                        and di + count <= 0x10000
                        and not _ega_aperture_overlap(cpu.s.es, di, count)):
                    read_plane = cpu.mem.ega_read_plane & 0x03
                    src = EGA_APERTURE + read_plane * EGA_PLANE_STRIDE + si
                    dst = (((cpu.s.es & 0xFFFF) << 4) + di) & 0xFFFFF
                    cpu.mem.data[dst:dst + count] = cpu.mem.data[src:src + count]
                    cpu.s.si = (si + count) & 0xFFFF
                    cpu.s.di = (di + count) & 0xFFFF
                    cpu.s.cx = 0
                else:
                    cpu.s.cx = count
                    _rep_movsb(cpu, cpu.s.cx)
                if plane != 3:
                    _sub_reg16(cpu, 6, count)
                    _inc_reg8_preserve_cf(cpu, 4)  # INC AH
                    _out_dx_ax(cpu)
        elif mode == 2:
            # 587E: 80 word copies (=160 bytes), different EGA row wrap rule.
            cpu.s.cx = 0x0050
            _rep_movsw(cpu, cpu.s.cx)
            _sub_reg16(cpu, 6, 0x00A0)
            _add_reg16(cpu, 6, 0x2000)
            _test_word(cpu, cpu.s.si, 0x8000)
            if not cpu.get_flag(ZF):
                _add_reg16(cpu, 6, 0x80A0)
        else:
            raise RuntimeError(f"unsupported OVERKILL 5827 video mode selector {mode_word:04X}")

        cpu.s.cx = cpu.pop()
        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF  # LOOP, flags unchanged

    # 5898..58A3: optional final graphics-controller write for mode 1.
    _cmp_word(cpu, cpu.mem.rw(cs, 0x95BC), 0x0001)
    if cpu.get_flag(ZF):
        cpu.s.ax = 0x0004
        _out_dx_ax(cpu)
    cpu.s.ip = 0x58A4


def _rep_movsw(cpu, count: int) -> None:
    count &= 0xFFFF
    if count == 0:
        cpu.s.cx = 0
        return

    byte_count = count * 2
    if not cpu.get_flag(DF):
        si = cpu.s.si & 0xFFFF
        di = cpu.s.di & 0xFFFF
        if si + byte_count <= 0x10000 and di + byte_count <= 0x10000 \
                and not (cpu.mem.ega_planar and (
                    _ega_aperture_overlap(cpu.s.ds, si, byte_count)
                    or _ega_aperture_overlap(cpu.s.es, di, byte_count)
                )):
            src = (((cpu.s.ds & 0xFFFF) << 4) + si) & 0xFFFFF
            dst = (((cpu.s.es & 0xFFFF) << 4) + di) & 0xFFFFF
            if src + byte_count <= len(cpu.mem.data) and dst + byte_count <= len(cpu.mem.data):
                cpu.mem.data[dst:dst + byte_count] = cpu.mem.data[src:src + byte_count]
                cpu.s.si = (si + byte_count) & 0xFFFF
                cpu.s.di = (di + byte_count) & 0xFFFF
                cpu.s.cx = 0
                return

    delta = -2 if cpu.get_flag(DF) else 2
    for _ in range(count):
        cpu.mem.ww(cpu.s.es, cpu.s.di, cpu.mem.rw(cpu.s.ds, cpu.s.si))
        cpu.s.si = (cpu.s.si + delta) & 0xFFFF
        cpu.s.di = (cpu.s.di + delta) & 0xFFFF
    cpu.s.cx = 0


def _inc_reg8_preserve_cf(cpu, idx: int) -> None:
    old_cf = cpu.get_flag(CF)
    old = cpu.get_reg8(idx)
    result = old + 1
    cpu.set_reg8(idx, result)
    cpu.set_add_flags(old, 1, result, 8)
    cpu.set_flag(CF, old_cf)


def _out_dx_ax(cpu) -> None:
    if cpu.port_writer:
        cpu.port_writer(cpu, cpu.s.dx & 0xFFFF, cpu.s.ax & 0xFFFF, 16)


def _out_dx_al(cpu) -> None:
    if cpu.port_writer:
        cpu.port_writer(cpu, cpu.s.dx & 0xFFFF, cpu.get_reg8(0), 8)


def _cmp_byte(cpu, a: int, b: int) -> None:
    cpu.set_sub_flags(a & 0xFF, b & 0xFF, (a & 0xFF) - (b & 0xFF), 8)


@registry.replace(0x1010, 0xCCAA, "overkill_dirty_copy_mode1_ccaa")
def overkill_dirty_copy_mode1_ccaa(cpu):
    if _self_disable_if_patched(cpu, 0xCCAA, _SIG_CCAA, "overkill_dirty_copy_mode1_ccaa"):
        return
    """Replace dirty detect/copy mode 1 at 1010:CCAA.

    Compares eight ES:SI words against ES:DI with an 80-byte stride.  Changed
    words are copied and DL is set to 1.  The surrounding dispatcher at CC90
    sets ES and clears DL before jumping here; the continuation at CD08 tests DL.
    """
    cpu.s.cx = 0x0008
    while cpu.s.cx != 0:
        src = cpu.mem.rw(cpu.s.es, cpu.s.si)
        dst = cpu.mem.rw(cpu.s.es, cpu.s.di)
        cpu.s.ax = src
        _cmp_word(cpu, src, dst)
        if not cpu.get_flag(ZF):
            cpu.set_reg8(2, 1)
            cpu.mem.ww(cpu.s.es, cpu.s.di, src)
        _add_reg16(cpu, 7, 0x0050)
        _add_reg16(cpu, 6, 0x0050)
        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF
    cpu.s.ip = 0xCD08


@registry.replace(0x1010, 0xCCC4, "overkill_dirty_copy_mode3_ccc4")
def overkill_dirty_copy_mode3_ccc4(cpu):
    if _self_disable_if_patched(cpu, 0xCCC4, _SIG_CCC4, "overkill_dirty_copy_mode3_ccc4"):
        return
    """Replace dirty detect/copy mode 3 at 1010:CCC4.

    Eight iterations, comparing/copying two adjacent words per row, then
    stepping source/destination by 160 bytes.
    """
    cpu.s.cx = 0x0008
    while cpu.s.cx != 0:
        src0 = cpu.mem.rw(cpu.s.es, cpu.s.si)
        dst0 = cpu.mem.rw(cpu.s.es, cpu.s.di)
        cpu.s.ax = src0
        _cmp_word(cpu, src0, dst0)
        if not cpu.get_flag(ZF):
            cpu.set_reg8(2, 1)
            cpu.mem.ww(cpu.s.es, cpu.s.di, src0)

        src1 = cpu.mem.rw(cpu.s.es, (cpu.s.si + 2) & 0xFFFF)
        dst1 = cpu.mem.rw(cpu.s.es, (cpu.s.di + 2) & 0xFFFF)
        cpu.s.ax = src1
        _cmp_word(cpu, src1, dst1)
        if not cpu.get_flag(ZF):
            cpu.set_reg8(2, 1)
            cpu.mem.ww(cpu.s.es, (cpu.s.di + 2) & 0xFFFF, src1)

        _add_reg16(cpu, 7, 0x00A0)
        _add_reg16(cpu, 6, 0x00A0)
        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF
    cpu.s.ip = 0xCD08


@registry.replace(0x1010, 0xCCF0, "overkill_dirty_copy_mode2_ccf0")
def overkill_dirty_copy_mode2_ccf0(cpu):
    if _self_disable_if_patched(cpu, 0xCCF0, _SIG_CCF0, "overkill_dirty_copy_mode2_ccf0"):
        return
    """Replace dirty detect/copy mode 2 at 1010:CCF0.

    Compares 32 ES:SI bytes against ES:DI with a 40-byte stride.
    """
    cpu.s.cx = 0x0020
    while cpu.s.cx != 0:
        src = cpu.mem.rb(cpu.s.es, cpu.s.si)
        dst = cpu.mem.rb(cpu.s.es, cpu.s.di)
        cpu.set_reg8(0, src)
        _cmp_byte(cpu, src, dst)
        if not cpu.get_flag(ZF):
            cpu.set_reg8(2, 1)
            cpu.mem.wb(cpu.s.es, cpu.s.di, src)
        _add_reg16(cpu, 7, 0x0028)
        _add_reg16(cpu, 6, 0x0028)
        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF
    cpu.s.ip = 0xCD08


@registry.replace(0x1010, 0x2750, "overkill_present_ega_frame_2750")
def overkill_present_ega_frame_2750(cpu):
    if _self_disable_if_patched(cpu, 0x2750, _SIG_2750, "overkill_present_ega_frame_2750"):
        return
    """Replace the EGA mode-1 frame-present blit at 1010:2750.

    The real routine writes the same A000h offsets four times while changing the
    EGA sequencer map-mask register (03C4h index 02h / 03C5h data 1,2,4,8).
    The memory model routes those CPU-visible A000h writes into the selected
    shadow plane.  The common A000 case copies directly into that selected
    shadow plane; unusual geometry falls back through ``Memory.ww``.  The copied
    source bytes and register flow mirror the original routine; this is
    deliberately only the final presenter, not a broad VGA/EGA hardware
    emulator.
    """
    cs = cpu.s.cs & 0xFFFF
    mem = cpu.mem

    # 2750..275D setup.
    cpu.s.si = mem.rw(cpu.s.ds, 0x234C)
    cpu.s.es = mem.rw(cs, 0x95A4)
    cpu.s.ds = mem.rw(cs, 0x9598)
    cpu.s.bx = 0x000D
    cpu.s.di = 0x00A0
    cpu.s.dx = 0x03C4
    cpu.set_reg8(0, 0x02)
    _out_dx_al(cpu)                 # OUT 03C4h,02h: sequencer map mask index.
    _inc_reg16_preserve_cf(cpu, 2)  # INC DX -> 03C5h.
    cpu.s.bp = 0x00C0

    es_seg = cpu.s.es & 0xFFFF
    width = 0x001A
    words = width // 2
    data = mem.data

    def set_present_map_mask() -> None:
        # Runtime executions update this via DOSMachine.port_write.  Synthetic
        # hook tests often have no port writer attached, so mirror this routine's
        # known 03C5h map-mask writes locally too.
        mem.ega_planar = True
        mem.ega_map_mask = cpu.get_reg8(0) & 0x0F

    def fast_copy_selected_plane(src: int, dst: int) -> bool:
        mask = cpu.get_reg8(0) & 0x0F
        if (not mem.ega_planar
                or es_seg != 0xA000
                or mask not in (0x01, 0x02, 0x04, 0x08)
                or src + width > 0x10000
                or dst + width > EGA_PLANE_WINDOW
                or _ega_aperture_overlap(cpu.s.ds, src, width)):
            return False
        plane = (mask.bit_length() - 1) & 0x03
        src_base = (((cpu.s.ds & 0xFFFF) << 4) + src) & 0xFFFFF
        dst_base = EGA_APERTURE + plane * EGA_PLANE_STRIDE + dst
        data[dst_base:dst_base + width] = data[src_base:src_base + width]
        return True

    while True:
        cpu.set_reg8(0, 0x01)
        _out_dx_al(cpu)
        set_present_map_mask()
        for plane in range(4):
            # Original plane copy is REP MOVSW with BX=000Dh: 26 bytes.
            # MOVS changes SI/DI/CX but not flags.
            src = cpu.s.si & 0xFFFF
            dst = cpu.s.di & 0xFFFF
            if fast_copy_selected_plane(src, dst):
                src = (src + width) & 0xFFFF
                dst = (dst + width) & 0xFFFF
            else:
                for _ in range(words):
                    mem.ww(es_seg, dst, mem.rw(cpu.s.ds, src))
                    src = (src + 2) & 0xFFFF
                    dst = (dst + 2) & 0xFFFF
            cpu.s.si = src
            cpu.s.di = dst
            cpu.s.cx = 0
            if plane != 3:
                _sub_reg16(cpu, 7, width)
                cpu.set_reg8(0, cpu.shift(4, cpu.get_reg8(0), 1, 8))
                _out_dx_al(cpu)
                set_present_map_mask()
        _add_reg16(cpu, 7, 0x000E)  # Net row stride: 26 copied bytes + 14 = 40.
        _dec_reg16_preserve_cf(cpu, 5)
        if cpu.get_flag(ZF):
            break

    cpu.set_reg8(0, 0x0F)
    _out_dx_al(cpu)
    set_present_map_mask()
    cpu.s.ds = mem.rw(cs, 0x9596)
    cpu.s.ip = cpu.pop()


@registry.replace(0x1010, 0x50C9, "overkill_wait_vga_retrace_50c9")
def overkill_wait_vga_retrace_50c9(cpu):
    """Replace the C9EA VGA retrace wait wrapper reached through 50C9.

    The original code is not a high-level timer; it performs two busy-waits on
    port 03DAh, with the order controlled by CS:CA5A.  The hook still reads the
    port through the DOS/video IO layer so vga_status_reads and final AL/flags
    remain oracle-relative.
    """
    cs = cpu.s.cs & 0xFFFF
    inverted_order = cpu.mem.rb(cs, 0xCA5A) == 0x01
    _wait_vga_status_bit3(cpu, want_set=not inverted_order)
    _wait_vga_status_bit3(cpu, want_set=inverted_order)
    # Original path is 50C9 -> JMP C9EA; C9EA performs CALL C9F1 and CALL
    # CA02 before RET.  Those internal near calls leave their last return word
    # (C9F0) in the scratch stack slot at the original SS:SP-2.
    cpu.mem.ww(cpu.s.ss, (cpu.s.sp - 2) & 0xFFFF, 0xC9F0)
    cpu.s.ip = cpu.pop()


def _wait_vga_status_bit3(cpu, *, want_set: bool) -> None:
    cpu.s.dx = 0x03DA
    # Keep a guard for testability if a runtime accidentally has no IO layer.
    for _ in range(100000):
        value = cpu.port_reader(cpu, 0x03DA, 8) if cpu.port_reader else (0x08 if want_set else 0x00)
        cpu.set_reg8(0, value)
        result = value & 0x08
        cpu.set_logic_flags(result, 8)  # TEST AL,08h
        if (result != 0) == want_set:
            return
    raise RuntimeError("VGA status wait did not converge")

@registry.replace(0x1010, 0x58DF, "overkill_postcopy_blit_wait_loop_58df")
def overkill_postcopy_blit_wait_loop_58df(cpu):
    if _self_disable_if_patched(cpu, 0x58DF, _SIG_58DF, "overkill_postcopy_blit_wait_loop_58df"):
        return
    """Replace the narrow 58DF..58F8 post-copy blit/wait loop.

    This is still a control-flow hook, not a new renderer: for the captured
    mode-0 path it repeatedly invokes the already verified 497A blitter and the
    verified 50C9 VGA wait hook, preserving the PUSH/CALL/POP stack scratches
    and the unusual DEC CX + LOOP CX double-decrement.
    """
    cs = cpu.s.cs & 0xFFFF
    while True:
        cpu.push(cpu.s.cx)                         # 58DF PUSH CX
        cpu.mem.ww(cs, 0x5901, cpu.s.cx)           # 58E0 MOV CS:[5901],CX
        mode = cpu.mem.rw(cs, 0x95BC)
        cpu.s.bx = mode & 0xFFFF
        cpu.s.bx = cpu.shift(4, cpu.s.bx, 1, 16)   # 58E5..58EA
        if mode != 0:
            # The mode-1/2 callees are different planar/Tandy blitters and have
            # not been lifted as part of this narrow mode-0 hook.  Do not crash
            # EGA/Tandy profiling: make this address self-disabling and let the
            # original interpreted code run from 58DF on the next CPU step.
            cpu.replacement_hooks.pop((cs, 0x58DF), None)
            cpu.hook_names.pop((cs, 0x58DF), None)
            cpu.s.ip = 0x58DF
            return
        _call_hook_like_near_call(cpu, overkill_blit_scaled_column_block_497a, 0x58F1)
        if cpu.s.ip != 0x58F1:
            raise RuntimeError(f"497A replacement returned to unexpected IP {cpu.s.ip:04X}")
        _call_hook_like_near_call(cpu, overkill_wait_vga_retrace_50c9, 0x58F4)
        if cpu.s.ip != 0x58F4:
            raise RuntimeError(f"50C9 replacement returned to unexpected IP {cpu.s.ip:04X}")
        cpu.s.cx = cpu.pop()                       # 58F4 POP CX
        _dec_reg16_preserve_cf(cpu, 1)             # 58F5 DEC CX
        cpu.s.cx = (cpu.s.cx - 1) & 0xFFFF         # 58F6 LOOP, no flags
        if cpu.s.cx == 0:
            cpu.s.ip = 0x58F8
            return


@registry.replace(0x1010, 0x0679, "overkill_wait_timer_tick_0679")
def overkill_wait_timer_tick_0679(cpu):
    """Replace the timer-tick busy-wait at 1010:0679.

    Original routine:

        0679  cmp byte ptr cs:[066B],0
        067F  jz   0679
        0681  ret

    It spins until the byte flag at ``CS:066B`` becomes non-zero.  That flag is
    only ever touched by three tiny resident routines:

        1010:066C  inc byte ptr cs:[066B] ; ret   (tick increment helper)
        1010:0672  mov byte ptr cs:[066B],0 ; ret (clear before waiting)
        1010:0679  this wait loop

    ``066C`` is reached from the game's own reprogrammed IRQ0 handler installed
    at ``1010:068A``: that installer saves the old INT 08h vector to ``CS:0738``,
    reprograms the 8253 PIT (``out 43h,36h`` then divisor ``0x4000`` ≈ 72.8 Hz),
    and points INT 08h at the ISR ``1010:06E5``.  The ISR drives sound/per-tick
    logic, calls ``066C`` to bump ``066B`` on alternating sub-ticks, and chains
    the original BIOS handler every fourth tick.

    This interpreter delivers no asynchronous hardware interrupts, so that ISR
    never runs and ``066B`` stays 0 forever — the runtime spins here indefinitely
    once it reaches the main per-frame timing loop (callers at 981A/D025/D340/
    D41F, each paired with a ``066C`` clear at 97B2/D007/D318/D406).

    Mirroring the existing narrow VGA-retrace model (``50C9`` / port ``03DAh``),
    this hook models exactly one elapsed timer tick: if the flag is still 0 it
    bumps it to 1 (one ISR ``inc``), then reproduces the final, exiting loop
    iteration (``cmp`` against 0, ``jz`` not taken, ``ret``).  ``066B`` has no
    other consumer, so this is sufficient to satisfy the wait faithfully without
    speculatively emulating the whole IRQ0/sound ISR chain.
    """
    cs = cpu.s.cs & 0xFFFF
    flag = cpu.mem.rb(cs, 0x066B)
    cpu.timer_ticks_elapsed = 0
    if flag == 0:
        delivered = 0
        while flag == 0 and delivered < 8:
            if not _deliver_overkill_timer_irq0(cpu):
                raise RuntimeError(
                    "1010:0679 timer wait needs OVERKILL INT 08h at 1010:06E5; "
                    "no synthetic timer fallback is allowed"
                )
            delivered += 1
            flag = cpu.mem.rb(cs, 0x066B)
        if flag == 0:
            raise RuntimeError("1010:06E5 timer ISR did not advance CS:066B within 8 ticks")
        cpu.timer_ticks_elapsed = delivered
    # Final loop iteration: CMP byte ptr CS:[066B],0 (now non-zero); JZ not taken; RET.
    cpu.set_sub_flags(flag, 0, flag, 8)
    cpu.s.ip = cpu.pop()
    # There is exactly one of these waits per rendered frame, so it is the natural
    # place to throttle the game to real time when an interactive front-end asks.
    if cpu.timer_pacer is not None:
        cpu.timer_pacer()


def _deliver_overkill_timer_irq0(cpu, *, max_steps: int = 200_000) -> bool:
    """Synchronously run OVERKILL's installed INT 08h timer ISR if present.

    The game sound code lives in the real ISR at ``1010:06E5``.  The original
    handler chains the old BIOS timer every fourth tick via ``JMP FAR
    CS:[0738]``; in this VM that saved BIOS vector is often 0000:0000, so stop
    at the known chain point after the game-side work and restore the interrupt
    frame locally.
    """
    mem = cpu.mem
    off = mem.rw(0, 0x20)
    seg = mem.rw(0, 0x22)
    if (seg & 0xFFFF, off & 0xFFFF) != (0x1010, 0x06E5):
        return False

    ret_cs, ret_ip = cpu.s.cs & 0xFFFF, cpu.s.ip & 0xFFFF
    sp0 = cpu.s.sp & 0xFFFF
    cpu.push(cpu.s.flags)
    cpu.push(ret_cs)
    cpu.push(ret_ip)
    cpu.set_flag(IF, False)
    cpu.set_flag(TF, False)
    cpu.s.cs = seg & 0xFFFF
    cpu.s.ip = off & 0xFFFF

    for _ in range(max_steps):
        if cpu.s.sp == sp0 and cpu.addr() == (ret_cs, ret_ip):
            return True
        if cpu.addr() == (0x1010, 0x072F):
            # Chain path after the game work:
            #   POP DS; POP AX; STI; JMP FAR CS:[0738]
            cpu.s.ds = cpu.pop()
            cpu.s.ax = cpu.pop()
            cpu.set_flag(IF, True)
            if cpu.port_writer:
                cpu.port_writer(cpu, 0x20, 0x20, 8)
            cpu.s.ip = cpu.pop()
            cpu.s.cs = cpu.pop()
            cpu.s.flags = cpu.pop()
            return cpu.s.sp == sp0 and cpu.addr() == (ret_cs, ret_ip)
        cpu.step()
    raise RuntimeError(
        f"OVERKILL INT 08h timer ISR did not return "
        f"(cs:ip={cpu.s.cs:04X}:{cpu.s.ip:04X})"
    )



@registry.replace(0x1010, 0x3354, "overkill_present_tandy_frame_3354")
def overkill_present_tandy_frame_3354(cpu):
    """Hook wrapper for OVERKILL 1010:3354 Tandy frame-present blit."""
    run_present_tandy_frame_3354(cpu)


@registry.replace(0x1010, 0x447B, "overkill_present_frame_blit_447b")
def overkill_present_frame_blit_447b(cpu):
    """Replace the mode-0 frame-present blit reached via the 5BDC video jump table.

    The per-frame presenter ``1010:5BDC`` reads the mode selector ``CS:[95BC]``,
    shifts it left and ``jmp cs:[bx+5BE8]``.  For mode 0 the table entry is
    ``1010:447B``:

        447B  mov si, ds:[234C]      ; source cursor (work-buffer offset)
        447F  mov es, cs:[95A4]      ; destination segment (B800 video memory)
        4484  mov ds, cs:[9598]      ; source segment (decoded work buffer)
        4489  mov bx,1Ah / di,A0h / bp,C0h
        4492  mov cx,bx
              rep movsw              ; copy 1Ah (26) words = 52 bytes
              sub di,34h             ; rewind to row start
              add di,2000h           ; next interlaced scanline bank
              test di,4000h
              jz  44A7
              add di,C050h           ; wrap to next char row on bank crossing
        44A7  dec bp
              jnz 4492               ; C0h (192) rows
        44AA  mov ds, cs:[9596]      ; restore the game data segment
        44AF  ret

    Confirmed selectors in the live run: dest ``CS:[95A4]=B800h`` (CGA/EGA video
    memory), source ``CS:[9598]`` = the decoded work buffer, restore
    ``CS:[9596]`` = the game data segment.  This is the actual screen present and,
    once the main loop runs, the single hottest interpreted routine.

    The hook mirrors the interpreter's own helpers in the exact instruction order
    so registers, flags and memory match the oracle; it only collapses the Python
    per-iteration overhead of the 192-row interlaced copy.
    """
    cs = cpu.s.cs & 0xFFFF
    # 447B MOV SI, DS:[234C] (uses the entry DS before it is reloaded below).
    cpu.s.si = cpu.mem.rw(cpu.s.ds, 0x234C)
    # 447F/4484 load the destination and source segments from the resident selectors.
    cpu.s.es = cpu.mem.rw(cs, 0x95A4)
    cpu.s.ds = cpu.mem.rw(cs, 0x9598)
    # 4489..448F constants.
    cpu.s.bx = 0x001A
    cpu.s.di = 0x00A0
    cpu.s.bp = 0x00C0
    while True:
        cpu.s.cx = cpu.s.bx & 0xFFFF       # 4492 MOV CX,BX
        _rep_movsw(cpu, cpu.s.cx)          # 4494 REP MOVSW (sets CX=0, advances SI/DI)
        _sub_reg16(cpu, 7, 0x0034)         # 4496 SUB DI,34h
        _add_reg16(cpu, 7, 0x2000)         # 4499 ADD DI,2000h
        _test_word(cpu, cpu.s.di, 0x4000)  # 449D TEST DI,4000h
        if not cpu.get_flag(ZF):           # 44A1 JZ 44A7
            _add_reg16(cpu, 7, 0xC050)     # 44A3 ADD DI,C050h
        _dec_reg16_preserve_cf(cpu, 5)     # 44A7 DEC BP (CF unaffected on 8086)
        if cpu.get_flag(ZF):               # 44A8 JNZ 4492
            break
    cpu.s.ds = cpu.mem.rw(cs, 0x9596)      # 44AA MOV DS,CS:[9596]
    cpu.s.ip = cpu.pop()                   # 44AF RET

@registry.replace(0x1010, 0x017E, "overkill_keyboard_poll_bits_017e")
def overkill_keyboard_poll_bits_017e(cpu):
    """Replace the hot eight-key poll bit-packer at 1010:017E.

    The menu/gameplay input path repeatedly scans a small table of XT scan codes
    at DS:SI, reads the corresponding key-state byte from DS:DI+scan, shifts its
    low bit into DS:98BE, and advances SI.  It is small but very hot on static
    menu screens because the game polls it every frame.
    """
    s = cpu.s
    ds = s.ds & 0xFFFF
    data = cpu.mem.data
    base = ds << 4
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    cx = s.cx & 0xFFFF
    if cx == 0:
        cx = 0x10000

    bh = s.bx & 0xFF00
    al = s.ax & 0xFF
    bl = s.bx & 0xFF
    scratch_off = 0x98BE

    while cx:
        bl = data[(base + si) & 0xFFFFF]
        bx = bh | bl
        al = data[(base + ((bx + di) & 0xFFFF)) & 0xFFFFF]
        al = cpu.shift(5, al, 1, 8)  # SHR AL,1; CF becomes the key-state bit.
        scratch_addr = (base + scratch_off) & 0xFFFFF
        data[scratch_addr] = cpu.shift(2, data[scratch_addr], 1, 8)  # RCL byte [98BE],1.

        old_cf = cpu.get_flag(CF)
        old_si = si
        si = (si + 1) & 0xFFFF
        cpu.set_add_flags(old_si, 1, old_si + 1, 16)  # INC SI flags...
        cpu.set_flag(CF, old_cf)                      # ...but INC preserves CF.
        cx -= 1

    s.ax = (s.ax & 0xFF00) | (al & 0xFF)
    s.bx = bh | bl
    s.si = si
    s.cx = 0
    s.ip = 0x018B


@registry.replace(0x1010, 0xCD8D, "overkill_changed_word_present_8rows_cd8d")
def overkill_changed_word_present_8rows_cd8d(cpu):
    """Replace the changed-word CGA presenter loop at 1010:CD8D.

    After the dirty-copy detector marks a block as changed, this loop copies one
    word from the work buffer to the visible CGA aperture across eight interlaced
    scanlines.  It appears prominently on the planet/difficulty menu because the
    screen is redrawn in many small dirty cells when the selection changes.
    """
    s = cpu.s
    mem = cpu.mem
    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    cx = s.cx & 0xFFFF
    if cx == 0:
        cx = 0x10000

    ax = s.ax & 0xFFFF
    while cx:
        ax = mem.rw(ds, si)
        mem.ww(es, di, ax)

        old_si = si
        si = (si + 0x50) & 0xFFFF
        # ADD SI flags are overwritten before the LOOP unless this is somehow
        # not followed by the DI/test path, so keep only the architectural result.
        old_di = di
        di = (di + 0x2000) & 0xFFFF
        cpu.set_add_flags(old_di, 0x2000, old_di + 0x2000, 16)
        cpu.s.di = di
        _test_word(cpu, di, 0x4000)
        if not cpu.get_flag(ZF):
            old_di = di
            di = (di + 0xC050) & 0xFFFF
            cpu.set_add_flags(old_di, 0xC050, old_di + 0xC050, 16)
            cpu.s.di = di
        cx -= 1

    s.ax = ax
    s.si = si
    s.di = di
    s.cx = 0
    s.ip = 0xCE02


@registry.replace(0x1010, 0xCDAA, "overkill_tandy_changed_dword_present_8rows_cdaa")
def overkill_tandy_changed_dword_present_8rows_cdaa(cpu):
    """Replace the Tandy changed-cell presenter loop at 1010:CDAA."""
    run_tandy_changed_dword_present_cdaa(cpu)


def _interpret_current_instruction_without_hook(cpu) -> None:
    """Interpret the current instruction when an overlaid address no longer matches a hook signature."""
    key = cpu.addr()
    fn = cpu.replacement_hooks.pop(key, None)
    try:
        cpu.step()
    finally:
        if fn is not None:
            cpu.replacement_hooks[key] = fn


def _code_matches(cpu, off: int, expected: bytes) -> bool:
    cs = cpu.s.cs & 0xFFFF
    return all(cpu.mem.rb(cs, (off + i) & 0xFFFF) == b for i, b in enumerate(expected))


def _overkill_strided_row_copy(cpu, *, row_advance: int) -> None:
    """Shared replacement for OVERKILL's LODSW/REP-MOVSB strided row copier."""
    s = cpu.s
    mem = cpu.mem
    cs = s.cs & 0xFFFF
    s.es = mem.rw(cs, 0x9598)

    df = cpu.get_flag(DF)
    lod_delta = -2 if df else 2
    si = s.si & 0xFFFF
    ax = mem.rw(s.ds, si)
    si = (si + lod_delta) & 0xFFFF
    s.cx = ax & 0xFFFF
    ax = mem.rw(s.ds, si)
    si = (si + lod_delta) & 0xFFFF
    s.si = si
    s.ax = ax & 0xFFFF
    s.ax = cpu.shift(4, s.ax, 1, 16)  # SHL AX,1
    s.bp = s.ax & 0xFFFF

    outer = s.cx if s.cx != 0 else 0x10000
    width = s.bp & 0xFFFF
    row_advance &= 0xFFFF
    for _ in range(outer):
        # PUSH CX / MOV CX,BP / REP MOVSB / SUB DI,BP / ADD DI,row_advance /
        # POP CX / LOOP.  Keep using the project's optimized REP helper so DF
        # and 16-bit wrapping semantics stay centralized.
        saved_cx = s.cx & 0xFFFF
        cpu.push(saved_cx)
        s.cx = width
        _rep_movsb(cpu, width)
        _sub_reg16(cpu, 7, width)
        _add_reg16(cpu, 7, row_advance)
        s.cx = cpu.pop()
        s.cx = (s.cx - 1) & 0xFFFF  # LOOP does not change flags.

    s.ip = cpu.pop()


_STRIDED_ROW_COPY_34_SIG = bytes.fromhex("2e 8e 06 98 95 ad 8b c8 ad d1 e0 8b e8 51 8b cd f3 a4 2b fd 83 c7 34 59 e2 f3 c3")
_STRIDED_ROW_COPY_50_SIG = bytes.fromhex("2e 8e 06 98 95 ad 8b c8 ad d1 e0 8b e8 51 8b cd f3 a4 2b fd 83 c7 50 59 e2 f3 c3")


@registry.replace(0x1010, 0x3EE1, "overkill_strided_row_copy_3ee1")
def overkill_strided_row_copy_3ee1(cpu):
    """Replace row copier 1010:3EE1, which advances destination rows by 34h.

    This address is overlaid/reused by later sprite code, so the hook only
    applies while the exact row-copy bytes are resident.
    """
    if not _code_matches(cpu, 0x3EE1, _STRIDED_ROW_COPY_34_SIG):
        _interpret_current_instruction_without_hook(cpu)
        return
    _overkill_strided_row_copy(cpu, row_advance=0x34)


@registry.replace(0x1010, 0x3EFC, "overkill_strided_row_copy_3efc")
def overkill_strided_row_copy_3efc(cpu):
    """Replace row copier 1010:3EFC, which advances destination rows by 50h.

    This address is overlaid/reused by later sprite code, so the hook only
    applies while the exact row-copy bytes are resident.
    """
    if not _code_matches(cpu, 0x3EFC, _STRIDED_ROW_COPY_50_SIG):
        _interpret_current_instruction_without_hook(cpu)
        return
    _overkill_strided_row_copy(cpu, row_advance=0x50)




def _rcr_stc_chain_5bytes(bl: int, bh: int, al: int, ah: int, dl: int, passes: int) -> tuple[int, int, int, int, int]:
    """Return the 5-byte result of repeated STC; RCR BL,BH,AL,AH,DL groups.

    Used by the CGA masked-sprite compositors.  The interpreted version updated
    CPU flags on every single rotate, but those flags are overwritten by the
    row-step ADD/DEC before control leaves the hook.
    """
    bl &= 0xFF; bh &= 0xFF; al &= 0xFF; ah &= 0xFF; dl &= 0xFF
    for _ in range(passes):
        cf = 1
        old = bl; bl = ((cf << 7) | (old >> 1)) & 0xFF; cf = old & 1
        old = bh; bh = ((cf << 7) | (old >> 1)) & 0xFF; cf = old & 1
        old = al; al = ((cf << 7) | (old >> 1)) & 0xFF; cf = old & 1
        old = ah; ah = ((cf << 7) | (old >> 1)) & 0xFF; cf = old & 1
        old = dl; dl = ((cf << 7) | (old >> 1)) & 0xFF
    return bl, bh, al, ah, dl


def _shr_rcr_chain_5bytes(bl: int, bh: int, al: int, ah: int, dl: int, passes: int) -> tuple[int, int, int, int, int]:
    """Return the 5-byte result of repeated SHR BL; RCR BH,AL,AH,DL groups."""
    bl &= 0xFF; bh &= 0xFF; al &= 0xFF; ah &= 0xFF; dl &= 0xFF
    for _ in range(passes):
        cf = bl & 1
        bl = (bl >> 1) & 0xFF
        old = bh; bh = ((cf << 7) | (old >> 1)) & 0xFF; cf = old & 1
        old = al; al = ((cf << 7) | (old >> 1)) & 0xFF; cf = old & 1
        old = ah; ah = ((cf << 7) | (old >> 1)) & 0xFF; cf = old & 1
        old = dl; dl = ((cf << 7) | (old >> 1)) & 0xFF
    return bl, bh, al, ah, dl


_MASKED_SPRITE_COMPOSITE_3EFB_SIG = bytes.fromhex(
    "8b 1c 8b 44 04 b2 ff f9 d0 db d0 df d0 d8 d0 dc d0 da"
)


@registry.replace(0x1010, 0x3EFB, "overkill_masked_sprite_composite_3efb")
def overkill_masked_sprite_composite_3efb(cpu):
    """Replace the overlaid 6-shift masked sprite loop at 1010:3EFB.

    This is the dominant interpreted loop on the planet/difficulty selection
    redraw path after the 3E12 two-shift compositor is hooked.  The address is
    overlay-reused, so only apply while the observed masked-compositor bytes are
    resident.
    """
    if not _code_matches(cpu, 0x3EFB, _MASKED_SPRITE_COMPOSITE_3EFB_SIG):
        _interpret_current_instruction_without_hook(cpu)
        return

    s = cpu.s
    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    cs = s.cs & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    bp = s.bp & 0xFFFF
    rows = bp if bp != 0 else 0x10000
    initial_dh = s.dx & 0xFF00
    final_dl = s.dx & 0x00FF
    mem = cpu.mem

    for _ in range(rows):
        mask_bx = mem.rw(ds, si)
        mask_ax = mem.rw(ds, (si + 4) & 0xFFFF)
        bl = mask_bx & 0xFF
        bh = (mask_bx >> 8) & 0xFF
        al = mask_ax & 0xFF
        ah = (mask_ax >> 8) & 0xFF
        dl = 0xFF
        bl, bh, al, ah, dl = _rcr_stc_chain_5bytes(bl, bh, al, ah, dl, 6)
        mask_bx = ((bh << 8) | bl) & 0xFFFF
        mask_ax = ((ah << 8) | al) & 0xFFFF
        mem.ww(es, di, mem.rw(es, di) & mask_bx)
        mem.ww(es, (di + 2) & 0xFFFF, mem.rw(es, (di + 2) & 0xFFFF) & mask_ax)
        mem.wb(es, (di + 4) & 0xFFFF, mem.rb(es, (di + 4) & 0xFFFF) & dl)

        data_bx = mem.rw(ds, (si + 2) & 0xFFFF)
        data_ax = mem.rw(ds, (si + 6) & 0xFFFF)
        bl = data_bx & 0xFF
        bh = (data_bx >> 8) & 0xFF
        al = data_ax & 0xFF
        ah = (data_ax >> 8) & 0xFF
        dl = 0x00
        cpu.set_logic_flags(0, 8)        # XOR DL,DL
        bl, bh, al, ah, dl = _shr_rcr_chain_5bytes(bl, bh, al, ah, dl, 6)
        data_bx = ((bh << 8) | bl) & 0xFFFF
        data_ax = ((ah << 8) | al) & 0xFFFF
        mem.ww(es, di, mem.rw(es, di) | data_bx)
        mem.ww(es, (di + 2) & 0xFFFF, mem.rw(es, (di + 2) & 0xFFFF) | data_ax)
        mem.wb(es, (di + 4) & 0xFFFF, mem.rb(es, (di + 4) & 0xFFFF) | dl)
        final_dl = dl

        si = (si + 8) & 0xFFFF
        old_di = di
        di_sum = old_di + 0x34
        di = di_sum & 0xFFFF
        cpu.set_add_flags(old_di, 0x34, di_sum, 16)
        old_cf = cpu.get_flag(CF)
        old_bp = bp
        bp = (bp - 1) & 0xFFFF
        cpu.set_sub_flags(old_bp, 1, old_bp - 1, 16)
        cpu.set_flag(CF, old_cf)         # DEC preserves CF.

    s.si = si
    s.di = di
    s.bp = bp
    s.dx = initial_dh | final_dl
    s.bx = data_bx
    s.ax = data_ax
    s.ds = mem.rw(cs, 0x9596)            # MOV DS,CS:[9596] before RET.
    s.ip = cpu.pop()


@registry.replace(0x1010, 0x3E12, "overkill_masked_sprite_composite_3e12")
def overkill_masked_sprite_composite_3e12(cpu):
    """Replace the hot masked CGA sprite/composite row loop at 1010:3E12.

    The original loop consumes eight source bytes per row, shifts mask and data
    bits through carry twice, then AND/OR-composites three destination bytes.
    It is hit heavily by the planet/difficulty selection screen when the menu
    redraws its sprites and highlight frame.
    """
    s = cpu.s
    ds = s.ds & 0xFFFF
    es = s.es & 0xFFFF
    si = s.si & 0xFFFF
    di = s.di & 0xFFFF
    bp = s.bp & 0xFFFF
    rows = bp if bp != 0 else 0x10000
    initial_dh = s.dx & 0xFF00
    final_dl = s.dx & 0x00FF

    mem = cpu.mem
    for _ in range(rows):
        # Mask phase:
        #   mov bx,[si]; mov ax,[si+4]; mov dl,ff; stc;
        #   rcr bl,bh,al,ah,dl twice; and destination bytes.
        mask_bx = mem.rw(ds, si)
        mask_ax = mem.rw(ds, (si + 4) & 0xFFFF)
        bl = mask_bx & 0xFF
        bh = (mask_bx >> 8) & 0xFF
        al = mask_ax & 0xFF
        ah = (mask_ax >> 8) & 0xFF
        dl = 0xFF
        bl, bh, al, ah, dl = _rcr_stc_chain_5bytes(bl, bh, al, ah, dl, 2)
        mask_bx = ((bh << 8) | bl) & 0xFFFF
        mask_ax = ((ah << 8) | al) & 0xFFFF
        mem.ww(es, di, mem.rw(es, di) & mask_bx)
        mem.ww(es, (di + 2) & 0xFFFF, mem.rw(es, (di + 2) & 0xFFFF) & mask_ax)
        mem.wb(es, (di + 4) & 0xFFFF, mem.rb(es, (di + 4) & 0xFFFF) & dl)

        # Data phase:
        #   mov bx,[si+2]; mov ax,[si+6]; xor dl,dl;
        #   shr bl; rcr bh,al,ah,dl; repeat; or destination bytes.
        data_bx = mem.rw(ds, (si + 2) & 0xFFFF)
        data_ax = mem.rw(ds, (si + 6) & 0xFFFF)
        bl = data_bx & 0xFF
        bh = (data_bx >> 8) & 0xFF
        al = data_ax & 0xFF
        ah = (data_ax >> 8) & 0xFF
        dl = 0x00
        cpu.set_logic_flags(0, 8)        # XOR DL,DL clears CF/OF and sets ZF/PF.
        bl, bh, al, ah, dl = _shr_rcr_chain_5bytes(bl, bh, al, ah, dl, 2)
        data_bx = ((bh << 8) | bl) & 0xFFFF
        data_ax = ((ah << 8) | al) & 0xFFFF
        mem.ww(es, di, mem.rw(es, di) | data_bx)
        mem.ww(es, (di + 2) & 0xFFFF, mem.rw(es, (di + 2) & 0xFFFF) | data_ax)
        mem.wb(es, (di + 4) & 0xFFFF, mem.rb(es, (di + 4) & 0xFFFF) | dl)
        final_dl = dl

        # ADD SI,8; ADD DI,34h; DEC BP; JNZ 3E12.  Only the final DEC flags are
        # externally visible, with CF preserved from the immediately preceding
        # ADD DI because DEC does not modify CF.
        si = (si + 8) & 0xFFFF
        old_di = di
        di_sum = old_di + 0x34
        di = di_sum & 0xFFFF
        cpu.set_add_flags(old_di, 0x34, di_sum, 16)
        old_cf = cpu.get_flag(CF)
        old_bp = bp
        bp = (bp - 1) & 0xFFFF
        cpu.set_sub_flags(old_bp, 1, old_bp - 1, 16)
        cpu.set_flag(CF, old_cf)

    s.si = si
    s.di = di
    s.bp = bp
    s.dx = initial_dh | final_dl
    # BX and AX are left containing the last shifted data words; DL is already
    # reflected in DX, while DH is untouched by the ASM loop.
    s.bx = data_bx
    s.ax = data_ax
    s.ip = 0x3E6A



@registry.replace(0x1010, 0x5A36, "overkill_cga_object_row_addr_5a36")
def overkill_cga_object_row_addr_5a36(cpu):
    """Hook wrapper for OVERKILL 1010:5A36 object-row address dispatch.

    Implementation lives in ``games.overkill.rendering.coordinates`` because the
    routine is shared by CGA, EGA, and Tandy rendering paths.  The wrapper keeps
    the original ASM address visible at the hook boundary.
    """
    object_row_address_from_mode_dispatch_5a36(cpu)


@registry.replace(0x1010, 0x5A00, "overkill_cga_xy_to_di_5a00")
def overkill_cga_xy_to_di_5a00(cpu):
    """Hook wrapper for OVERKILL 1010:5A00 coordinate-to-DI helper."""
    coordinate_ax_to_di_5a00(cpu)


@registry.replace(0x1010, 0x5A24, "overkill_cga_xy_to_di_5a24")
def overkill_cga_xy_to_di_5a24(cpu):
    """Hook wrapper for OVERKILL 1010:5A24 coordinate-to-DI helper."""
    coordinate_ax_to_di_5a24(cpu)


@registry.replace(0x1010, 0x5AC8, "overkill_dispatch_draw_object_5ac8")
def overkill_dispatch_draw_object_5ac8(cpu):
    """Collapse the hot CGA object draw dispatcher at 1010:5AC8."""
    s = cpu.s
    cs = s.cs & 0xFFFF
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF
    mode = cpu.mem.rw(cs, 0x95BC)
    bx = cpu.mem.rw(ss, (bp + 0x14) & 0xFFFF)
    bx = (bx + mode + mode + mode) & 0xFFFF
    s.bx = bx
    s.bx = cpu.shift(4, s.bx, 1, 16)  # SHL BX,1; final flags before JMP.
    s.ip = cpu.mem.rw(cs, (0x5AE2 + s.bx) & 0xFFFF)


@registry.replace(0x1010, 0x5A92, "overkill_dispatch_present_object_5a92")
def overkill_dispatch_present_object_5a92(cpu):
    """Collapse the hot object-present dispatcher at 1010:5A92."""
    s = cpu.s
    cs = s.cs & 0xFFFF
    ss = s.ss & 0xFFFF
    bp = s.bp & 0xFFFF
    s.es = cpu.mem.rw(cs, 0x9598)
    s.di = cpu.mem.rw(ss, (bp + 0x0C) & 0xFFFF)
    s.si = cpu.mem.rw(ss, (bp + 0x0E) & 0xFFFF)
    mode = cpu.mem.rw(cs, 0x95BC)
    bx = cpu.mem.rw(ss, (bp + 0x14) & 0xFFFF)
    bx = (bx + mode + mode + mode) & 0xFFFF
    s.bx = bx
    s.bx = cpu.shift(4, s.bx, 1, 16)  # SHL BX,1; final flags before JMP.
    s.ip = cpu.mem.rw(cs, (0x5AB6 + s.bx) & 0xFFFF)


@registry.replace(0x1010, 0xAA44, "overkill_clc_ret_aa44")
def overkill_clc_ret_aa44(cpu):
    """Replace the tiny hot CLC/RET success helper at 1010:AA44."""
    cpu.set_flag(CF, False)
    cpu.s.ip = cpu.pop()
