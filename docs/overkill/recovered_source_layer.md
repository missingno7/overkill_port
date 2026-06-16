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
