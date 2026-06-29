# High-level refactor audit (VM-coupling / duplication / promotion)

Goal of this pass: identify and collapse VM-shaped glue, remove duplicated
gameplay decisions, and expose missing-evidence boundaries so the native
source-port core can keep crystallising from verified behaviour.  This is **not**
an intuition rewrite — every promotion points back to an exact `CS:IP` oracle.

Method: AST scans for VM-coupled / pure-shaped functions, grep sweeps for
memory-layout constants and gap markers, and a structural read of the suspected
files (`frame_orchestration`, `object_runtime`, `object_behaviors`,
`object_movement`, `hooks.py`, `recovered/adapters/*`).  Machine-readable form:
`artifacts/high_level_refactor_gaps.json`.

## Headline finding

The lifted / adapter / pure split is already **healthy and well-policed**. The
discipline asked for by this task is largely in place:

- **Pure layers are clean.** 25 pure modules; `audit_recovered_layers.py` and
  `audit_architecture.py` pass. Zero memory-layout/segment constants leak into
  `recovered/{domain,systems}`; the hex literals there are *named gameplay
  constants* (`POSTMOVE_CONTACT_Y_SPAN = 0x002C`, logic-id sets) — the good kind.
- **Adapters follow the cross-check pattern.** `collision_adapter.py` (37),
  `object_behavior_adapter.py` (11) and `movement_adapter.py` (1) carry **49
  `... disagrees ...` assertions** — each reads DOS state, calls the canonical
  pure system, replays the instruction-shaped path, and asserts agreement. That
  is exactly the desired adapter shape, not duplication to remove.
- **Almost nothing pure is stranded in the lifted layer.** A full AST scan of
  `overkill/gameplay/*.py` for top-level functions that touch no `cpu`/`mem`
  returned only the two A067 action gates (now promoted, below), one glue helper
  (`_no_patch_guard`), and one slot-stamp that correctly writes an
  `ObjectSlotView` (already delegating its pure part to `object_spawn_seed_a4ea`).

So the opportunity here is **not** a large cleanup. It is (1) one clean pure
promotion, (2) closing mechanical-audit gaps so the clean state cannot regress,
and (3) recording the genuine evidence frontier loudly.

## Promotions

| file / function | current → desired | reason | evidence root | pure now? | action | risk |
|---|---|---|---|---|---|---|
| `gameplay/action_spawns.py::action_trigger_is_pressed` | lifted → **source_pure** | pure bool predicate (`input & 10h`) stranded in lifted | `1010:A067` `SIG_FRAME_ACTION_SPAWN_FANOUT_A067` (`f6 06 be 98 10` = `TEST [98BE],10h`) | yes | **DONE** → `systems/action_spawns.py`, imported back | low |
| `gameplay/action_spawns.py::action_latch_allows_repeat` | lifted → **source_pure** | pure repeat gate stranded in lifted | `1010:A067` (`CMP [A980],0` / `CMP [9790],1` / `CMP [232A],0Fh`) | yes | **DONE** → `systems/action_spawns.py` | low |

Verification of the promotion: `tests/test_action_spawn_gates.py` (3), the 5
existing A067 tests, both layer audits, lint (216 files), and the bounded
demo-replay equivalence suite (`23 passed, 23 skipped`, 0 divergence) — behaviour
preserved.

### Examined and intentionally left in place

| file / function | layer | why it stays |
|---|---|---|
| `gameplay/object_spawns.py::_stamp_object_spawn_seed_a4ea` | lifted | writes an `ObjectSlotView` (DOS memory); already calls the pure `object_spawn_seed_a4ea()` for the values — correct adapter shape |
| `gameplay/object_runtime_common.py::_no_patch_guard` | lifted | 2-line continuation glue, no gameplay decision |
| `recovered/adapters/world_adapter.py::object_slot_*_for_offset`, `describe_world_write_target` | bridge | map raw memory offsets → field meaning; inherently layout-aware (bridge), not portable domain |
| `recovered/adapters/collision_adapter.py` (whole) | bridge | exemplar cross-check adapters (37 agreement asserts); the decision already lives in `systems/collision.py` |

## Duplicate decisions

No *unguarded* duplicate gameplay decisions were found. The instruction-shaped
logic that mirrors a pure system always sits behind a `... disagrees ...`
assertion in an adapter (the sanctioned verifier-compatibility replay). This is
the anti-duplication rule working as intended; do not "deduplicate" these by
deleting the replay — the replay is what keeps the VM an exact oracle.

## VM coupling

`overkill/gameplay/*` is the **lifted** layer and is *expected* to take
`cpu`/`mem` — that is not a violation. The audit confirms coupling does **not**
leak downward into `recovered/{domain,systems}`. The one structural smell is
`overkill/hooks.py` at **3203 lines** (flagged by `source_port_status.py` as an
oversized hook_boundary file); it is registration glue + nested runtime
factories, not gameplay decisions, so it is a *thinning/splitting* candidate, not
a promotion one. Left for a dedicated slice.

## Tooling gaps (mechanical regression prevention)

`audit_recovered_layers.py` previously checked forbidden imports + lowercase
`cpu`/`mem`/`memory` names only. **Closed this pass** (with negative tests in
`tests/test_audit_recovered_layers.py`):

- forbidden **capitalised VM/CPU types** (`CPU`, `CPUState`, `Memory`, `Mem`,
  `Registers`, `Register`, `DosRuntime`) in annotations or bare names;
- forbidden **memory-layout/segment constants** (`0x1010`, `0x23B4`, `0x2B5C`,
  `0x32CA`, `0x8D12`, `0x95D8`) as bare literals, with a `# layout-justified`
  line-comment escape hatch so genuine domain values are never blocked.

**Still open** (recorded in the gaps JSON as advisory, deliberately *not* made
hard checks to avoid brittleness):

- a reporting check for pure-shaped functions stranded in lifted/adapter layers
  (this pass found them by ad-hoc AST scan; worth a standing advisory in
  `source_port_status.py`);
- heuristics for "hook wrapper too large" / "adapter does more than projection".

## Evidence gaps (the genuine frontier — exposed loudly, not hidden)

Behaviour that **cannot** be promoted yet stays in lifted/adapter and fails loud
on unverified paths (`_raise_unverified_path`) or runs as an explicit
`bounded_original` / `_run_interpreted_near_call_observed` child. Concentrations:

- `object_behaviors.py` — 17 interpreted-near-call/bounded seams (the per-logic
  handler family; still cpu-hooks, not pure slot transforms);
- `object_movement.py` — 12 (e.g. the `A7EB` display copy, the `D2A4+` tail);
- `contact_side_effects.py` — 5; `object_runtime_common.py` — 5;
  `object_deactivation.py` / `object_runtime.py` — 3 each.

These are the missing-evidence boundaries that block further promotion; see the
JSON `missing_evidence` list. None should be papered over with a clean
abstraction — each needs a trace/oracle before it can become a pure system.

## Recommended next slices (smaller-proven-first)

1. Advisory "stranded pure-shaped function" report in `source_port_status.py`.
2. Thin/split `overkill/hooks.py` (registration-only; move nested runtime
   factories out) — structural, behaviour-preserving, demo-replay gated.
3. Continue the `object_behaviors.py` handler frontier: per-logic movement
   halves are separable pure transforms (the established producer pattern), but
   each needs its produced-vs-VM probe before promotion.
