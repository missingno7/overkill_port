"""Address-bound hook wrappers for OVERKILL text rendering helpers."""

from __future__ import annotations

from ....hooks import registry
from ..rendering.text import (
    TextRenderRuntime,
    run_score_byte_text_5ef9,
    run_score_status_text_block_5edb,
    run_score_nibble_text_5f06,
    run_tandy_text_glyph_3153,
    run_text_dispatch_519a,
    run_text_string_loop_518c,
)
from .common import self_disable_if_patched


def _text_render_runtime() -> TextRenderRuntime:
    return TextRenderRuntime(self_disable_if_patched=self_disable_if_patched)


@registry.replace(0x1010, 0x518C, "overkill_text_string_loop_518c")
def overkill_text_string_loop_518c(cpu):
    """OVERKILL 1010:518C text string loop."""
    run_text_string_loop_518c(cpu, _text_render_runtime())


@registry.replace(0x1010, 0x519A, "overkill_text_dispatch_519a")
def overkill_text_dispatch_519a(cpu):
    """OVERKILL 1010:519A text-character dispatcher."""
    run_text_dispatch_519a(cpu, _text_render_runtime())


@registry.replace(0x1010, 0x5EDB, "overkill_score_status_text_block_5edb")
def overkill_score_status_text_block_5edb(cpu):
    """OVERKILL 1010:5EDB HUD/status text block helper."""
    run_score_status_text_block_5edb(cpu, _text_render_runtime())


@registry.replace(0x1010, 0x5F06, "overkill_score_nibble_text_5f06")
def overkill_score_nibble_text_5f06(cpu):
    """OVERKILL 1010:5F06 score nibble text helper."""
    run_score_nibble_text_5f06(cpu, _text_render_runtime())


@registry.replace(0x1010, 0x5EF9, "overkill_score_byte_text_5ef9")
def overkill_score_byte_text_5ef9(cpu):
    """OVERKILL 1010:5EF9 two-nibble score/text helper."""
    run_score_byte_text_5ef9(cpu, _text_render_runtime())


@registry.replace(0x1010, 0x3153, "overkill_tandy_text_glyph_3153")
def overkill_tandy_text_glyph_3153(cpu):
    """OVERKILL 1010:3153 Tandy text/glyph renderer."""
    run_tandy_text_glyph_3153(cpu, _text_render_runtime())
