# Semantic crystallization plan

This document is the durable project brief for the gradual upward refactor from
verified ASM-compatible hooks into recovered source-port code.  It exists so a
new AI agent can understand the target architecture without needing chat
history.

The goal is not to build a new engine from intuition.  The goal is to let the
original source-code shape crystallize from evidence until the upper layers can
be reused by a future native source port.

## North star

The project should move in this direction:

```text
original binary oracle
  -> interpreted ASM / exact traces
  -> ASM-compatible hooks
  -> lifted game-specific modules
  -> recovered memory views and adapters
  -> pure domain records and systems
  -> native source-port runtime
```

The important long-term boundary is:

```text
DOS-compatible path:
    DOS memory -> views/adapters -> domain records -> pure systems -> adapters -> DOS memory

Future native path:
    native world records -> pure systems -> native world records
```

Everything below `domain/` and `systems/` may still know about the original DOS
execution world.  Everything in `domain/` and `systems/` must be portable game
logic/data and must not know about CPU registers, segment:offset memory, hook
addresses, or verifier continuations.

## Repository layers

The recovered source-port path is intentionally split by dependency direction:

```text
overkill/hooks.py
    Exact CS:IP registration and thin address-facing wrappers.

    May know: cpu, registers, flags, continuations, original addresses.
    Should not own durable gameplay decisions once a pure layer exists.

overkill/gameplay/, overkill/rendering/, overkill/sounds/, ...
    Verified lifted routines and island modules.

    May still be ASM-shaped.  Good place for code immediately after it moves out
    of overkill/hooks.py.  Over time, stable decisions should be promoted into
    overkill/recovered/ when they become portable.

overkill/recovered/views/
    Typed overlays over original DOS memory.

    May know: original offsets, table bases, stride, segment choice.
    Must stay thin.  No high-level gameplay decisions.

    Example: ObjectSlotView is equivalent to a recovered C pointer such as
    `ObjectSlot *obj = (ObjectSlot *)&memory[slot_base]`.

overkill/recovered/adapters/
    Bridges between DOS/ASM execution and pure recovered code.

    May know: cpu, memory, registers, flags, continuations, views, domain
    records, and pure systems.
    Should contain only projection and ASM-compatibility glue.  If gameplay
    decision logic appears here, it should be a temporary staging point and then
    promoted upward.

overkill/recovered/domain/
    Pure copied source-like records.

    Must not know: cpu, mem, memory, dos_re, hooks, views, adapters, or original
    addresses as execution dependencies.
    Example: ObjectSlotRecord.

overkill/recovered/systems/
    Pure recovered gameplay/system functions over domain records and ordinary
    values.

    Must not know: cpu, mem, memory, dos_re, hooks, views, adapters, segment
    offsets, or continuation addresses.
    Example: collision.view_contact_rect_test.
```

The import boundary for `domain/` and `systems/` is enforced by:

```bash
python scripts/audit_recovered_layers.py
python scripts/lint.py
```

## The promotion pipeline

Use this ladder for every subsystem:

```text
1. Unknown ASM
   Only classify as far as evidence supports.

2. Verified hook
   Replace one exact boundary.  Preserve registers, flags, memory, stack, and
   continuation behavior.

3. Lifted island helper
   Move implementation out of overkill/hooks.py when it has a stable island and
   tests.  The hook remains an address-facing wrapper.

4. Recovered view
   If repeated routines prove a memory layout, create or extend a typed memory
   overlay such as ObjectSlotView.

5. Domain record
   If a stable slice can be copied away from DOS memory, create a pure record
   such as ObjectSlotRecord.

6. Pure system
   If the decision can be expressed without CPU/memory/registers/flags, move it
   into overkill.recovered.systems.

7. Native-ready use
   Once enough pure systems exist, a native source-port runtime can use them
   directly without loading the DOS runtime.
```

A higher layer is allowed only when the lower layer proves it.  Do not skip the
view/adapter/domain split just because a high-level name feels obvious.

## Deduplication rule

Gameplay decision logic should live at the highest proven portable layer.

Once a pure system exists, do not reimplement the same decision in the hook or
adapter.  The desired shape is:

```text
hook:
    exact address wrapper and continuation glue

adapter:
    read DOS state -> build domain records -> call pure system
    replay original CMP/ADD/SUB/RET/flag choreography for verifier compatibility

system:
    one canonical portable gameplay decision
```

If the adapter must replay the original compare sequence, it may do so only to
preserve CPU-visible side effects.  It should assert that the instruction-shaped
path agrees with the pure system.  This prevents the codebase from growing two
competing versions of the same game rule.

Good pattern:

```text
pure collision system decides whether a probe hits an object
adapter replays 8086 comparisons so SI/FLAGS match the original ASM
hook only jumps/returns exactly as the original boundary requires
```

Bad pattern:

```text
hook has one collision rule
adapter has a second collision rule
pure system has a third collision rule
```

## Evidence standard

A semantic name or pure system is earned when multiple independent traces point
to the same representation.  Useful evidence includes:

```text
- exact ASM addresses and known continuations
- hook-verifier tests that match registers/flags/memory/stack
- repeated use of the same object/table offsets by independent routines
- coverage across demos, snapshots, or different levels
- frame-verifier evidence when a visual subsystem is involved
- documented edge cases that still fit the proposed representation
```

Use conservative names until the evidence converges.  For example:

```text
logic_id       better than enemy_type
ObjectSlot     before Enemy
hazard_class   before damage_type
candidate      before definitive archetype
```

Hypotheses belong in documentation or truth tables, not in executable pure
systems.

## Current crystallized seed

The current stable seed is deliberately small:

```text
ObjectSlotView
    DOS-memory overlay for the DS:23B4 object table and SS:BP current slot.

ObjectSlotRecord
    Pure copied record for the fields repeatedly constrained so far.

collision.view_contact_rect_test
    Pure source-like form of 1010:8331.

collision.player_hazard_scan_hit and helpers
    Pure source-like decision extracted from BDD0/BDE3, with the adapter still
    preserving the exact ASM compare/flag behavior.
```

Current proven object-table shape:

```text
DS:23B4
0x23 records
stride 0x38
```

Current conservative object-slot fields:

```text
+00 active_word
+02 x_word / signed x
+04 y_word / signed y
+0A gate_or_layer
+0E link_key
+14 scan_flag
+16 hazard_class
+18 logic_id
```

Do not expand this list by guessing.  Expand it when another verified routine
constrains the field.

## Refactoring checklist

Before promoting code upward, answer these questions:

```text
1. Which exact ASM address range or hook proves this behavior?
2. Which tests or replay commands verify it?
3. What are the inputs, outputs, and side effects?
4. Can the core decision be expressed without cpu/memory/registers/flags?
5. Which part must remain in the adapter only for ASM-visible flags/registers?
6. Is there already a pure helper that should be reused instead of duplicated?
7. Does the name stay conservative enough for all observed object types?
8. Have docs and truth tables been updated with the evidence root?
```

If the answer to question 4 is no, keep the code in an ASM-compatible lifted
module for now.  Do not force it into `systems/`.

## Anti-patterns

Avoid these shapes:

```text
- Introducing Enemy/Projectile/Pickup classes before object-slot evidence proves
  stable archetypes.
- Passing cpu or mem into overkill.recovered.domain or overkill.recovered.systems.
- Letting a pure system import views or adapters.
- Keeping a gameplay decision duplicated in both hook and pure system.
- Replacing flag-sensitive ASM with a clean boolean while forgetting the adapter
  must preserve flags for verification.
- Moving code upward just because it looks cleaner, without a test or trace root.
- Adding silent fallbacks when a recovered assumption fails.  Fail loudly and
  create a repro snapshot/demo instead.
```

## Documentation duties

When crystallizing a new piece, update the nearest durable documents:

```text
docs/overkill/recovered_source_layer.md
    Current recovered layer structures and promoted systems.

docs/overkill/island_truth_tables.md
    Confidence/evidence/frontiers by island.

docs/overkill/runtime_findings.md
    Address-level findings and pitfalls.

docs/overkill/run_status.md
    Latest checkpoint and exact commands run.

symbols.json
    Address names, confidence, and replacement status.
```

For long-lived architecture rules, update this document and `AGENTS.md` so the
next AI agent sees the rules immediately.
