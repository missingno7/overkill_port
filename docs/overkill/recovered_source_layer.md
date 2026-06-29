# Recovered source layer

See also: `semantic_crystallization_plan.md` for the durable promotion plan
and anti-duplication rules.

This layer is the first deliberately source-like crystallisation pass.  It is not
an attempt to build a new engine.  It is a narrow place for structures and helper
primitives whose meaning is already constrained by verified hooks and repeated
memory-layout evidence.

## Layer boundary

The recovered package is split so the future source-port candidate code is kept
separate from the DOS/ASM compatibility glue:

```text
overkill/recovered/
    views/       DOS-memory overlays; may know original offsets and segments
    adapters/    CPU/memory <-> pure record projection; may set flags/registers
    domain/      pure copied source-like records; no CPU/memory dependency
    systems/     pure gameplay/system functions over domain records only
```

Compatibility modules still exist at the package root (`coords.py`,
`object_slots.py`, `collision_primitives.py`) for older imports, but new code
should target the split packages directly.

## Hard rule for portable layers

`overkill.recovered.domain` and `overkill.recovered.systems` must not import or
refer to:

```text
cpu, mem, memory, dos_re, overkill.hooks, overkill.gameplay,
overkill.recovered.views, overkill.recovered.adapters
```

This is enforced by:

```text
python scripts/audit_recovered_layers.py
python scripts/lint.py
```

The intended source-port path is:

```text
DOS-compatible path:
    DOS memory -> views/adapters -> domain records -> systems -> adapters -> DOS memory

Future native path:
    native world records -> systems -> native world records
```

## ObjectSlotView vs ObjectSlotRecord

`ObjectSlotView` lives in `overkill.recovered.views.object_slots`.  It is a typed
overlay over existing emulated memory.  It does not own copied object state.  It
is equivalent to recovering a C pointer such as:

```c
ObjectSlot *obj = (ObjectSlot *)&memory[slot_base];
```

`ObjectSlotRecord` lives in `overkill.recovered.domain.object_slots`.  It is a
pure copied record with no reference to DOS memory.  Systems can use it without
knowing how the data was stored in the original executable.

Currently crystallised offsets in the view/adapter path:

```text
+00 active_word
+02 x_word / signed x
+04 y_word / signed y
+0A gate_or_layer      conservative name; used by BDD0/BDE3/AC81 scan logic
+0E link_key           conservative name; used to reject same-linked objects
+14 scan_flag          BDE3 scan candidate gate
+16 hazard_class       BDE3 requires value 4
+18 logic_id           repeatedly used by object/collision/dispatch logic
```

The observed table shape used by the scan families is:

```text
DS:23B4, 0x23 records, stride 0x38
```

## First pure system

The first portable recovered system is:

```text
overkill.recovered.systems.collision.view_contact_rect_test
```

It is the pure source-like form of `1010:8331`, operating only on
`ObjectSlotRecord` and `ViewContactCenter`.  The ASM-compatible adapter still
replays the original `SI`/FLAGS sequence for hook verification, but validates
that the pure system agrees with the instruction-shaped path.

Wired existing collision hooks through the recovered split where the evidence is
already strong:

- `1010:8331 overkill_view_contact_rect_test_8331`
- `1010:BDD0 overkill_player_hazard_scan_guard_bdd0`
- `1010:BDE3 overkill_player_hazard_object_scan_bde3`
- `1010:B032 overkill_object_tile_sweep_blocked_b032`
- `1010:835B overkill_collision_clc_ret_835b`

## Promotion rule

A name may move into the pure recovered layers only when it can point back to
exact ASM addresses, verified hooks, or repeated independent memory-layout
evidence.  Hypotheses stay in docs until the traces converge.

Validation used for the split-layer seed:

```text
python -m pytest tests/test_recovered_semantics.py \
  tests/test_overkill_hooks.py::test_view_contact_rect_test_8331_matches_interpreted_asm_inside_and_miss \
  tests/test_overkill_hooks.py::test_player_hazard_scan_guard_bdd0_matches_interpreted_asm_gate_and_empty_scan \
  tests/test_overkill_hooks.py::test_object_tile_sweep_blocked_b032_matches_interpreted_asm -q
# 9 passed

python scripts/audit_recovered_layers.py
# Recovered layer audit passed for 6 pure files

python scripts/audit_hook_oracle.py
# Hook-oracle audit passed: 320 registered hooks, 320 metadata entries, no direct registered child calls detected.

python scripts/audit_islands.py --all-hooks
# unclassified unknown hooks: 0

python scripts/lint.py
# Lint passed for 99 Python files

python scripts/run_tests.py --no-lint --scope dos-re --timeout 20
# 7 passed, 0 failed, 0 timed out

SDL_VIDEODRIVER=dummy python scripts/play.py \
  --demo artifacts/demos/demo_play_tandy_20260615_235831 \
  --verify-hooks --sound adlib --verify-max 5000 --verify-step-budget 600000
# OK HOOK VERIFY LIMIT REACHED verified=5000
```


## Anti-duplication rule

When a behavior has been promoted into a pure system, that pure function becomes
the canonical gameplay decision.  Hooks should not keep a second copy of the
decision.  Adapters may replay the original instruction-shaped compare/flag
sequence only to preserve verifier-visible CPU state, and should assert that the
instruction-shaped path agrees with the pure system.

This is what makes the refactor a gradual upward migration instead of a pile of
parallel implementations.

## Hazard scan promoted to pure collision semantics

The next promoted gameplay slice is the BDD0/BDE3 player-hazard object scan.
The scan shell is still ASM-compatible, but the candidate/hit decision now has a
portable source-like form:

```text
overkill.recovered.systems.collision.is_player_hazard_scan_candidate
overkill.recovered.systems.collision.slot_contains_probe_point
overkill.recovered.systems.collision.player_hazard_scan_hit
```

Evidence root:

```text
1010:BDD0  scan guard and probe setup
1010:BDE3  object-table scan body
1010:5059  STC/RET hit continuation
```

The pure system knows only `ObjectSlotRecord` and `ProbePoint`.  The adapter
`run_player_hazard_candidate_checks_bde3` performs the original compare sequence
and verifies that the pure result agrees with the instruction-shaped path before
the hook jumps to `5059` or advances to the next table slot.

This keeps the gradual promotion rule intact:

```text
DOS object table -> ObjectSlotView -> ObjectSlotRecord -> pure collision system -> ASM adapter glue
```

No separate duplicated gameplay decision should be reintroduced in the hook.  If
a later refactor changes the BDE3 semantics, change the pure system first and let
the adapter/hook preserve only CPU-visible register and flag effects.

## Movement clamp and edge-scroll bias promoted to pure movement semantics

The A5xx/A6xx movement edge helpers now have a portable recovered core while
keeping the lifted hook path byte-compatible with the original ASM:

```text
overkill.recovered.systems.movement.two_pass_axis_clamp_step
overkill.recovered.systems.movement.one_pixel_axis_step
overkill.recovered.systems.movement.recover_top_scroll_bias_a662
overkill.recovered.systems.movement.decay_bottom_scroll_bias_a63c
overkill.recovered.systems.movement.top_scroll_edge_response_a648
overkill.recovered.systems.movement.bottom_scroll_edge_response_a63c
overkill.recovered.systems.movement.vertical_scroll_edge_response_a616
```

Evidence root:

```text
1010:A5D1  left X clamp/unclamped one-pixel step
1010:A5EA  right X two-pass clamp step
1010:A5F9  upward Y two-pass clamp step
1010:A607  downward Y unsigned-below two-pass clamp step
1010:A616  vertical edge-scroll parent
1010:A648  top-edge bias response
1010:A63C  bottom-bias decay
1010:A662  top-bias recovery
```

The pure layer owns only final source-level values: object X/Y after a two-pass
axis clamp and the `DS:A39A/A39C` top/bottom scroll-bias words after the edge
response.  The lifted hook layer still replays the original compare/INC/DEC,
CALL-next scratch, nested return, and flag-producing instruction order, then
asserts that the pure system agrees.  These helpers are still low-level movement
/ scroll-bias primitives, not semantic player/enemy intent.

Validation for this crystallisation pass:

```text
python -m pytest tests/test_recovered_semantics.py::test_recovered_axis_clamp_and_vertical_scroll_bias_are_pure_source_port_helpers -q
# 1 passed

python scripts/run_tests.py tests/test_overkill_hooks.py --name '*vertical_scroll*' --timeout 80 --fail-fast --no-lint --verbose
# 1 passed

python scripts/run_tests.py tests/test_overkill_hooks.py --name '*clamp_step*' --timeout 80 --fail-fast --no-lint --verbose
# 1 passed
```

## Runtime-world projection and level-editor evidence

The recovered layer now has a non-gameplay probe for turning a live snapshot into
source-like data:

```text
overkill/recovered/domain/world.py      pure records, no VM dependency
overkill/recovered/adapters/world_adapter.py
scripts/dump_world.py
scripts/trace_world_writes.py
```

This is not a level-file parser yet.  It is a bridge from a verified runtime
state to a stable editor/source-port data model.  The first confirmed split is:

```text
DS:23B4  effect/contact slots, 0x23 records, stride 0x38
DS:2B5C  gameplay object slots, 0x22 records, stride 0x38
DS:32CA  update/draw/present pointer table
DS:8D12  compact/effect pointer table
```

Use `dump_world.py` to compare snapshots/levels and `trace_world_writes.py` to
find routines that populate or mutate these tables.  Those traces should guide
the next semantic-crystallisation steps; do not guess a level format from one
snapshot alone.

## World-write trace summaries

`trace_world_writes.py` now enriches each write event with:

```text
writer cs:ip, coverage island, exact symbol when known
target kind: object slot field, pointer-table entry, runtime global, boss pointer
resolved object-slot table/index and field offset
resolved old/new pointer values when a 16-bit pointer is written
```

`scripts/summarize_world_writes.py` turns that raw trace into a materialisation
map.  This is useful for deciding which fields are gameplay state and which are
renderer scratch.

Example:

```text
python scripts/trace_world_writes.py \
  --demo artifacts/demos/demo_play_tandy_20260616_000527 \
  --max-steps 20000 --max-events 2000 \
  -o artifacts/world_write_trace_demo_20260616_000527_enriched_20000.json

python scripts/summarize_world_writes.py \
  artifacts/world_write_trace_demo_20260616_000527_enriched_20000.json \
  -o artifacts/world_write_summary_demo_20260616_000527_enriched_20000.json \
  --text
```

The current demo-start trace already separates several kinds of writes:

```text
1010:35CF tandy_renderer     writes +0C heavily: likely draw/address scratch, not level materialisation
1010:5A36 coordinates        writes +12 heavily: row/address/dispatch helper evidence
1010:5DB2 movement           writes +06 plus x/y: movement-direction helper evidence
1010:AB10 gameplay_objects   writes +08 plus x/y: object-logic/sprite-table evidence
1010:B86D gameplay_objects   writes x/y, +08, target_x/y: object behavior state/movement evidence
1010:7524 gameplay_objects   advances DS:95D8 effect allocator cursor
```

Do not promote these unknown offsets directly to semantic names yet.  The trace
summary is evidence pressure: repeated writes from one subsystem suggest the next
field candidates, while writes from renderer interiors warn us not to mistake
render scratch for source-port gameplay state.

## Action-spawn fan-out gates promoted to pure systems

The per-frame action/spawn fan-out `1010:A067` had two pure boolean decisions
living in the lifted layer (`overkill/gameplay/action_spawns.py`).  They are now
canonical pure systems:

```text
overkill.recovered.systems.action_spawns.action_trigger_is_pressed
overkill.recovered.systems.action_spawns.action_latch_allows_repeat
```

Evidence root: `1010:A067` `SIG_FRAME_ACTION_SPAWN_FANOUT_A067`
(`TEST [98BE],10h` trigger bit; `CMP [A980],0` / `CMP [9790],1` / `CMP [232A],0Fh`
held-repeat chain).  The lifted A067 hook now only projects DS state and replays
the `TEST`/`CMP` flag effects, calling these predicates as the decision.  Verified
by `tests/test_action_spawn_gates.py`, the existing A067 hook tests, and the
demo-replay equivalence suite (0 divergence).  Names stay conservative (`action`,
not weapon/projectile/player) — the A958 dispatch target `44AF` is still the
unresolved action-spawn frontier.

## Strengthened pure-layer audit

`scripts/audit_recovered_layers.py` now also fails on, in `recovered/{domain,
systems}`:

- capitalised VM/CPU **types** (`CPU`, `CPUState`, `Memory`, `Mem`, `Registers`,
  `Register`, `DosRuntime`) in annotations or bare names;
- original **memory-layout / segment constants** (`0x1010`, `0x23B4`, `0x2B5C`,
  `0x32CA`, `0x8D12`, `0x95D8`) as bare literals — with a `# layout-justified`
  line-comment escape hatch so genuine domain values are never blocked.

Negative tests in `tests/test_audit_recovered_layers.py` prove these are not
vacuous.  See `high_level_refactor_audit.md` and
`artifacts/high_level_refactor_gaps.json` for the full coupling/duplication/
promotion audit.
