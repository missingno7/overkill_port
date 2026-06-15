# Island Truth Tables

Each island should keep a small truth table so future work does not lose track of
what is known, what is verified, what is guessed, and what remains staged in
`overkill/hooks.py`.

This file is intentionally lightweight. It is not a replacement for
`docs/overkill/runtime_findings.md`; it is the index that tells an agent where confidence
comes from and where not to invent meaning.

## Template

```text
Island: <name>
Layer range: <pyramid layers, e.g. 2-5>
Purpose: <one sentence>

What we know:
- ...

What is verified:
- routine/address -> test/snapshot/verifier evidence

What is guessed / candidate only:
- ...

Still unknown / frontier:
- ...

Belongs here:
- address/name/status

Still staged in overkill/hooks.py:
- address/name/reason

Do not import:
- higher-layer modules that this island must not know about

Coverage / tests / snapshots:
- ...
```

## Current OVERKILL Island Summary

### `asset_codecs`

Layer range: 2-5. Deterministic asset stream helpers, checksum, RLE/LZ, and
decoded asset table search.

What we know:
- This island is about bytes becoming decoded asset data, not about semantic
  entities that use the assets.
- It must not know about enemies, projectiles, bosses, levels, or modern UI.

Status:
- Closed candidate for known non-overlay asset codecs.
- Overlay sub-decoders, file orchestration, startup graphics materialization, and
  gameplay counters are separate islands, not hidden asset-codec work.


### `overlay`

Layer range: 2-5. Overlay segment helpers for signature checks, directory entry
scan, entry-name/path normalization, and XOR block decode.

What we know:
- Overlay segment residence does not automatically mean the routine is an
  overlay loader. `1F8F:0960` was moved to `game_state` because its behavior is
  per-frame counter update.
- `254A:*` directory/path/XOR helpers remain overlay-specific.

Status:
- Closed candidate for known overlay decode/directory helper paths.

### `startup_graphics`

Layer range: 2-5. Startup renderer lookup tables and graphics materialization.

What we know:
- These routines prepare renderer-visible tables or transient graphics buffers.
- They are not asset codecs merely because they run during loading/startup.

Status:
- Closed candidate for the known startup table/graphics materialization hooks.

### `file_io`

Layer range: 2-5. Original DOS/file/container orchestration used by asset and
overlay loading.

What we know:
- File offsets, handles, carry flag, and far-return stack shape are part of the
  oracle-visible contract.
- This island may call lower-level DOS/runtime services and asset/overlay helper
  routines, but it must not interpret gameplay meaning.

Status:
- Closed candidate for the known overlay/container parent loader path.

### `rendering`

Layer range: 2-5. Video-mode addressing, dirty-cell presenters, Tandy/CGA/EGA
primitives, startup lookup tables, layer/presence helpers.

What we know:
- Some historically `cga_*` names were really shared video-mode dispatch helpers.
- Rendering may know sprites, cells, planes, dirty rectangles, and video buffers.
- Rendering must not know `Enemy`, `Boss`, concrete level story, or modern UI.

Status:
- Tandy/shared rendering is increasingly mature.
- EGA-specific correctness remains an active frontier and needs frame verifier
  evidence.

### `gameplay`

Layer range: 2-5 today; layers 6-7 later. Object slots, movement, collision,
postmove tails, behavior dispatch, and runtime object evidence.

2026-06-14 verified update:
- `1010:7524 overkill_find_free_effect_slot_7524` and
  `1010:7573 overkill_find_free_object_slot_7573` cover the compact effect and
  main gameplay object 38h-byte slot allocators.  The tests pin found-slot,
  sentinel-wrap, and exhausted-pool behavior against interpreted original ASM.
- `1010:B24D overkill_object_behavior_b24d` covers the observed EFAE-selected
  object-family steering/overlap prelude from
  `snapshot_stop_1010_b24d_behavior`. It composes the runtime-patched `5E42`
  steering helper and lands on the already-owned `AD5A`/`ADC9` motion tails.
- `1010:9E19` remains a bounded-original child from the rare overlap side-effect
  branch; do not promote that side effect semantically until it has its own
  oracle-backed lift.

2026-06-14 collision-system update:
- `1010:4FF9 overkill_tile_contact_probe_4ff9` is now verified as a raw
  tile/contact probe. It combines the offset table at `DS:214E`, the coordinate
  probe `5073`, and tile lookup `505B`, restoring probe coordinates and returning
  contact state in `CF`. This is evidence for a future collision-system layer,
  not a semantic object archetype.

What we know:
- Current facts are mostly layer-4 runtime facts: active flag, coordinates,
  sprite refs, logic ids, owner/link fields, collision side effects.
- Do not promote to `Enemy`, `Projectile`, `Pickup`, or `Boss` without evidence
  across multiple systems.

Status:
- Active frontier. Many useful helpers are verified, but semantic archetypes are
  still candidates.

### `input_menu`

Layer range: 2-5. Keyboard polling, key-state packing, menu/input wait/yield
points.

What we know:
- Interactive pacing/yield boundaries can be behaviorally important even when
  pure CPU state matches.
- Hooks that compose wait loops must preserve installed wait/publish hooks when
  they represent external runtime boundaries.

Status:
- Keyboard polling is partially lifted; UI/menu wait loops remain a frontier.

### `sound`

Layer range: 2-5. Timer ISR, PC speaker state, PIT ports, cadence, and backend
publication.

What we know:
- Sound timing is tied to the original timer ISR and PIT cadence.
- This island should not invent music/sound semantics until the command and
  driver paths are better understood.

Status:
- PC speaker hardware path and timer cadence are partially verified.

### `bootstrap`

Layer range: 1-2 oracle/extraction classification only. Transient launcher,
unpack, relocation, driver-load, and startup materialization code.

What we know:
- `32FF:*` cold-start code is classified as bootstrap, not unknown gameplay.
- `assets/OVERKILL` and `assets/OVERKILL.EXE` are the only canonical inputs.
- Generated convenience files such as `OVERKILL.UNLZEXE.EXE` and
  `OVERKILL.OVERLAY.BIN` are noncanonical artifacts only.
- Bootstrap may produce code bodies, screens, tables, and driver blobs; these
  should become deterministic derived assets or staticized Python, not permanent
  runtime architecture.
- The current boundary manifest is in
  `overkill/bootstrap_boundary.py`.

Status:
- Classified-do-not-hook for final gameplay.  Run/trace it only as oracle,
  extraction, or startup-correctness evidence.

## Promotion Rule Reminder

A semantic name is only allowed when it can point back to evidence:

```text
semantic name -> runtime slot/fields -> verified lifted routine -> original ASM trace/snapshot
```

If that chain is missing, keep the name as a candidate with evidence and
confidence instead of a final game entity.

### `game_state`

Layer range: 2-5. Per-frame/game-loop counters, global state handoff, frame
orchestration, and low-level update loops that are above individual object
helpers but below semantic game systems.

What we know:
- `1010:A940` is a per-frame game-state update cluster, not an object archetype.
- `1F8F:0922` is a gameplay counter tick even though it lives in an overlay
  segment.
- `1F8F:0960` is the nested gameplay counter stride loop used by `0922`; it is
  game-state, not overlay/file/asset decode.
- `1010:D007..D04C` is the main gameplay frame-loop dispatcher.

What is verified:
- `1F8F:0922 overkill_gameplay_counter_tick_1f8f_0922` verified against the
  original through hook verifier and regression smoke.
- `1F8F:0960 overkill_gameplay_counter_stride_loop_1f8f_0960` remains verified
  through the existing oracle test and is now owned by `game_state`.

What is guessed / candidate only:
- No semantic gameplay entities are inferred from this island yet.

Still unknown / frontier:
- `1010:A940` parent cluster should only be hooked after its child calls are
  understood or safely composable.
- `1010:D007` main loop is classified, but intentionally not lifted as one large
  hook yet.

Still staged in overkill/hooks.py:
- Address wrappers only; game-state logic lives in `gameplay/game_state.py`.

Do not import:
- Semantic entity/archetype layers or modern frontend/UI modules.

### `sound` update

What is verified:
- `1010:0672` clears the timer tick flag `CS:[066B]` and returns.
- `1010:0679` waits for that flag by explicitly delivering the original IRQ0
  handler, then models the final CMP/JZ/RET iteration.

Still unknown / frontier:
- Higher-level sound-command semantics remain candidates only; this island still
  works mainly at timer/PC-speaker bytecode level.

### `layer_sprites` update

What is verified:
- `1010:5A6C` is a shared source-cell mode dispatch stub.
- `1010:511F` is a shared per-frame video-page stub; only mode 1 mutates page
  state, so Tandy calls are expected no-op returns.

Still unknown / frontier:
- `1010:A846/A85E/A876` layer-scan parents and `1010:4CED..4D14` presence-list
  parent are classified but not yet hooked.  They should be composed from
  existing scan/presence helpers to avoid duplicate code.

### `layer_sprites` update: A90C present parent

What is verified:
- `1010:A90C overkill_present_object_scan_pair_a90c` composes existing `A90F`
  and `A927` present scans, then routes to the `A93C/4D64/4D6F` presence-list
  clear chain.
- `1010:A93C` is only `CALL 4D64 ; RET`.
- `1010:4D64` is only the setup parent for the existing `4D6F` clear loop.

What is intentionally not duplicated:
- The `A90F/A927` scan bodies remain the single source of truth for present-list
  scanning.
- The `4D6F` clear loop remains the single source of truth for presence-list
  clearing.
- `5A92` present-object dispatch remains its own boundary.

Still unknown / frontier:
- `1010:4CED` presence stamping parent and `1010:A846/A85E/A876` scan parents
  are still candidates for composition-only hooks.

### `game_state` update: D04D frontier

What is classified:
- `1010:D04D..D072` is part of the per-frame state/UI update path reached from
  the `D007` main-frame dispatcher.

What is guessed / candidate only:
- No object archetype or semantic game entity should be inferred from this block
  yet.

Still unknown / frontier:
- Child calls and side effects under `D04D` need to be separated before any parent
  hook is attempted.

### `input_menu` update: 96C5/96C8 intro delay

What is verified:
- `1010:96C5 overkill_intro_retrace_delay_loop_96c5` is the intro/menu
  fixed-count retrace delay loop.
- `1010:96C8 overkill_intro_retrace_delay_loop_tail_96c8` is the resume tail
  after a pacing boundary.

What is intentionally preserved:
- The hook calls the installed `50C9` hook so UI/frame publication remains an
  observable runtime boundary during interactive play.

### `collision` update: BC45 postmove prelude

What is verified:
- `1010:BC45 overkill_object_postmove_prelude_bc45` adds the global delta at
  `DS:[A278]` into `SS:[BP+02]`, then reuses the shared `BC4B` postmove chain.

What is intentionally not duplicated:
- The `BC4B` collision/postmove implementation remains the single source of
  truth for the chain after the prelude.


### `collision` update: BFC7 logic-0021 gate

What is verified:
- In `1010:BFC7`, object logic id `0021h` is not a separate behavior body.
  It checks `DS:2356` first.
- If `DS:2356 != 0004h`, the original returns immediately.
- If `DS:2356 == 0004h`, the original jumps to `BFD7` and reuses the ordinary
  type-based score/death/transition tail.

What is intentionally preserved:
- The BFD7 tail still owns score updates, Y clamping, optional linked-counter
  effects, `C054` selector dispatch, and the final object state transition.

Still unknown / frontier:
- This fix does not classify the semantic object represented by logic id
  `0021h`; it only proves the low-level branch contract.

### `tandy_renderer` update: 4E0D loading scroll parent

What is verified:
- `1010:4E0D overkill_tandy_loading_scroll_until_4e0d` is the parent loop around
  the already-lifted `A781` loading-scroll step.
- The original call pushes return IP `4E12`; preserving that scratch value matters
  for full-memory oracle comparison.

What is intentionally not duplicated:
- The actual scroll step remains `_loading_scroll_step_a781`.

### `game_state` update: 61C5/61CA countdown scan

What is verified:
- `1010:61C5 overkill_decrement_first_active_counter_61c5` sets up the counter
  scan with `DI=2368`.
- `1010:61CA overkill_decrement_first_active_counter_scan_61ca` is the hot inner
  scan used by direct gameplay callers.

Still unknown / frontier:
- `1010:9FEA` appears related to object/table coordinate updates, but should not
  be promoted without an oracle.
- `1010:5EF9`, `1010:4D95`, `1010:780E`, and `1010:8A7E` remain meaningful
  classified frontiers for future small-hook passes.

### `gameplay` update: B86D object-family behavior

What is verified:
- `1010:B86D overkill_object_behavior_b86d` covers the observed logic-id `001Dh`
  object-slot behavior through the `B885/B729` and `B8B0` paths, verified
  against full-memory original ASM oracles from
  `artifacts/evidence/snapshot_stop_1010_b86d_behavior` and
  `artifacts/evidence/snapshot_stop_1010_b8b0_behavior`.

What is intentionally preserved:
- `B86D` stops at the shared `1010:BC4B` postmove/collision boundary; the BC4B
  helper remains the single owner of that tail.

Additional covered path:
- `B86D -> B8F8` is now covered from `snapshot_stop_1010_b86d_b8f8_edge`: it
  runs the lifted `5E1B` delta helper, reuses the verified runtime-patched
  `5E42` steering helper, forces sprite `0076h`, and lands on `BC4B`.

### `game_state` update: status compositor and frame-controller count leaves

What is verified:
- `1010:85D5 overkill_status_cell_composite_85d5` is a low-level status/HUD
  cell compositor parent.  It composes the verified cursor leaves `613E` and
  `615A` and the existing `5A6C` source-cell dispatch.  This is still a raw
  compositor, not a semantic HUD widget.
- `1010:99CD overkill_status_coord_list_fill_99cd` fills a coordinate list in
  `ES:DI` from `SS:[BP+2]` and `SS:[BP+4]` with fixed `+8/+9` offsets.
- `1010:9BFB` and `1010:9BFE` are verified tiny `INC AH/AL; RET` leaves inside
  the `9C01` child of the `9B2E` frame controller.

What is guessed / candidate only:
- `85D5` likely belongs to status/HUD composition, but no higher-level widget
  names are assigned.
- `9C01-9C6B` looks like an axis/side condition counter feeding a jump table at
  `CS:9C70`; this is structural only, not semantic gameplay classification.

Still unknown / frontier:
- The caller region around `859E-8653` should be classified next; `8517-8545` is now covered as a raw four-entry status/list descriptor seed.
- `9C01-9C6B` should get a frontier manifest before any parent lift of `9B2E`.


### `game_state` update: interstitial frame script and raw status-list seeds

What is verified:
- `1010:D318 overkill_interstitial_timed_input_loop_d318` is a repeated frame-script/timed-input gate.  It composes existing frame children, increments `DS:BED8`, loops at `D318`, or waits for `DS:98BE & 10h` to clear before returning.
- `1010:D367 overkill_interstitial_status_cell_d367` is the small cell-blit helper inside that script, switching to the `CS:95B6` source segment for `5A6C` and restoring `DS` afterward.
- `1010:852B overkill_status_cell_seed_852b` seeds one raw descriptor at `SS:BP`.
- `1010:8517 overkill_status_cell_list_seed_8517` seeds four such descriptors and preserves the original same-IP `CALL 852B`/fall-through shape.

What is guessed / candidate only:
- These descriptors likely feed a status/interstitial list, but no concrete HUD/menu widget identity is assigned.

Still unknown / frontier:
- `859E-8653` appears to be the sibling consumer/compositor around these descriptor records and should be classified next.

### `movement` update - 2026-06-15 AF60 direct entry

What is verified:
- `1010:AF60` is a self-call double 2-pixel movement entry: `CALL AF63`, then
  the `AF63` 2-pixel direction table body runs twice before returning to the
  original caller.
- The direct-entry hook is signature-guarded by the `AF60` call plus the full
  `AF63` entry/table/handler bytes.

Still unknown / frontier:
- `1010:89FF-8A20` remains a movement setup/controller around direct `AF63`
  traffic; it should be investigated as a separate parent, not folded into the
  primitive step table hooks.

### Hook-oracle audit update - 2026-06-15

What is verified:
- Complete child routines that are also registered hooks should be composed via
  `call_installed_hook_like_near_call`, not by calling their Python wrapper
  directly.
- The current static audit reports no direct registered child calls in
  `overkill/hooks.py` and no direct Tandy `5A36` calls.

Still unknown / frontier:
- Metadata-only entries without installed hooks should be reviewed: either
  promote complete routines to registered hooks, or document them as partial
  tails/bounded-original frontiers.
