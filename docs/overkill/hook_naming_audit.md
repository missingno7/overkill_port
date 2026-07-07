> **SUPERSEDED (2026-07-07).** This document is a historical plan/report from an earlier phase.
> It is NOT the current direction and may contradict the present state.  The live authorities:
> [`campaigns/README.md`](campaigns/README.md) (the operating model) →
> [`campaigns/demo_lockstep.md`](campaigns/demo_lockstep.md) (THE active campaign) →
> the TOP HEADER of [`run_status.md`](run_status.md) (the current frontier).

# OVERKILL hook naming audit

Current state after the hook-wrapper refactor pass:

- Registered hooks: **222**.
- Every registry label now includes its exact entry address suffix (`_<ip>` or
  `_<seg>_<ip>` for overlay/far hooks).  This keeps coverage, verifier output,
  and crash reports searchable by address without having to cross-reference
  `symbols.json`.
- Tiny address-bound wrappers for the asset/loading codec island were moved out
  of `overkill/hooks.py` into
  `overkill/hook_wrappers/asset_codecs.py`.
- Text-rendering wrappers now live in
  `overkill/hook_wrappers/text.py`.
- Timer/PC-speaker wrappers now live in
  `overkill/hook_wrappers/sounds.py`.
- Shared hook-wrapper mechanics now live in
  `overkill/hook_wrappers/common.py`.
- `overkill.hooks` remains the aggregate hook-registration import
  surface, but stale pre-rename aliases have been removed.

## Names normalized in this pass

| Address | Previous registry label | New registry label | Reason |
| --- | --- | --- | --- |
| `1010:C916` | `overkill_file_checksum_loop` | `overkill_file_checksum_loop_c916` | Added missing address suffix. |
| `1010:0624` | `overkill_packed_read_byte` | `overkill_packed_read_byte_0624` | Added missing address suffix. |
| `1010:0615` | `overkill_packed_read_word` | `overkill_packed_read_word_le_0615` | Added address and clarified little-endian word read. |
| `1010:0367` | `overkill_linear_byte_rle_decoder_0367_fast` | `overkill_linear_byte_rle_decoder_0367` | Removed performance adjective from semantic registry label. |
| `1010:4537` | `overkill_expand_4plane_row_4537_fast` | `overkill_expand_4plane_row_4537` | Removed performance adjective from semantic registry label. |

`overkill_fast_timer_isr_06e5` is intentionally unchanged: `fast` is part of the
routine's role, not a performance-quality marker.

## Names normalized in the second pass

| Address | Previous registry label | New registry label | Reason |
| --- | --- | --- | --- |
| `1010:768E` | `overkill_tandy_layer_sprite_draw_768e` | `overkill_layer_sprite_draw_768e` | The routine is a shared layer-sprite draw helper reached outside Tandy-only code paths. The stale Python alias has been removed; use the new address-suffixed/shared name. |
| `1010:75A6` | `overkill_tandy_layer_sprite_draw_75a6` | `overkill_layer_sprite_draw_75a6` | Same shared layer-sprite island; not Tandy-only. The stale Python alias has been removed; use the new address-suffixed/shared name. |
| `1010:7746` | `overkill_tandy_compact_layer_draw_7746` | `overkill_compact_layer_sprite_draw_7746` | Shared compact layer-sprite draw helper; clarified `sprite` and removed misleading Tandy ownership. The stale Python alias has been removed; use the new address-suffixed/shared name. |

Cleanup note: tests and scripts now import the canonical names directly; the old `overkill_tandy_*` aliases are gone.

## Naming quality by group

Good enough / precise:

- Asset codecs and loader hooks: `packed_read`, `rle`, `lz`, overlay directory,
  checksum, startup 4-plane expansion.
- Direct renderer leaves: Tandy masked compositors, strided row copies, present
  blits, dirty-cell copy modes.
- Hardware/timing hooks: timer ISR, wait loops, retrace gates, PC speaker tick.

Acceptable but deliberately low-level:

- Scan glue names such as `*_scan_setup_*`, `*_call_*`, and `*_scan_tail_*`.
  These are not gameplay concepts; they are faithful fragments of loop bodies.
  The phase word (`setup`, `call`, `tail`) is useful while the verifier is still
  comparing stack/register side effects at glue boundaries.
- Object behavior labels such as `overkill_object_behavior_ae09` and
  `overkill_object_behavior_b73e`.  These should not be renamed to semantic
  names until the object type and in-game role are proven by traces, not guessed.
- Dispatch labels such as `overkill_object_logic_dispatch_aa2b` and
  `overkill_object_family_dispatch_efae`.  These are precise structural names;
  later source-port code can sit above them with nicer gameplay names.

## Next safe extraction targets

1. `hook_wrappers/rendering_tandy.py`: Tandy row-copy/compositor/present wrappers.
   This is mechanically similar to the asset-codec/text/sound extraction, but
   the wrappers need the `_tandy_render_runtime()` factory and runtime-patched-code
   guard.
2. `hook_wrappers/layer_scan.py`: A8xx/A9xx scan setup/call/tail glue.  Keep the
   current low-level names until the loops are fully collapsed into one higher
   layer scan routine.
3. `hook_wrappers/object_logic.py`: AAxx/ABxx/ADxx/BCxx behavior wrappers.  Move
   wrappers only; do not rename `object_behavior_*` entries unless a trace-backed
   role is documented.

## Rule going forward

Use this registry-label pattern:

```text
overkill_<island>_<proven_behavior>_<entry_ip>
overkill_<island>_<proven_behavior>_<segment>_<entry_ip>   # only for far/overlay hooks
```

Avoid names based on guesses (`enemy`, `bonus`, `explosion`, etc.) until the
object table fields, script selector, and visible behavior all agree.  It is
better to keep an address-level name than to encode a false semantic abstraction.

## 2026-06-13 cleanup pass: duplicates and wrapper-label alignment

- `overkill_file_checksum_loop_c916`, `overkill_packed_read_byte_0624`, and
  `overkill_packed_read_word_le_0615` now use the same Python function name as
  their registry label.  The older unsuffixed aliases were removed in the zombie-cleanup pass so tests and diagnostics do not keep two names for the same hook.
- `asset_codecs/startup_graphics.py` was first reduced from a stale exact copy to a shim; the shim has now been removed.  Startup graphics helpers live only in `rendering/startup_graphics.py`.
- Remaining duplicated micro-helpers (`_add_reg16`, `_add_mem_word`,
  `_cmp_byte`, etc.) are intentionally left alone in this pass.  Some local
  copies differ in return value or EGA/Tandy-specific fast-path constraints, so
  they should be collapsed only after a dedicated ASM-helper audit.

