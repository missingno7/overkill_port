"""Quantization coverage of the enemy behaviour zoo (docs/overkill/actor_model.md §5.2).

How close is the recovered zoo to a data-driven actor engine?  This statically decomposes every
recovered ``_step_*`` handler in ``behavior_walk.py`` into the CLOSED verb set (the shared workers) and
classifies each by how it quantizes:

  STUB     -- tiny body, no worker calls: trivially a `[SetSprite/Anim, guard?] + tail` step-list.
  PURE     -- all worker callees are known verbs + simple control flow: a step-list TODAY.
  CHAIN    -- also calls another _step_ handler (morph / fall-through): compose two step-lists.
  CONTROL  -- verbs are all known but the body has heavy inline control flow (a substate/mode
              sub-machine or a retry loop) the verb set does not NAME yet -- needs 1-2 control verbs.
  ESCAPE   -- calls a bespoke routine that is not a verb (boss/jump-table): keep behind a Call verb.

It prints the coverage split, the verb-reuse histogram, and -- most useful -- the ESCAPE callees
(the exact routines still outside the vocabulary) and the CONTROL handlers (where new verbs are owed).

Usage:  python scripts/actor_quantization_report.py
"""
from __future__ import annotations

import ast
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
WALK = ROOT / "overkill" / "recovered" / "adapters" / "behavior_walk.py"

#: the CLOSED verb vocabulary -- worker fn -> verb name (docs/overkill/actor_model.md §5.2).
VERB_OF = {
    "_postmove_bc45": "tail", "_bc45_postmove": "tail",
    "_afd8_step": "contact", "contact_probe_afd8": "contact", "_bdd0_contact_at": "contact",
    "_apply_seek": "seek", "_b729_seek": "seek",
    "object_delta_steer_5e42": "steer", "_steer_missile_tail_8744": "steer",
    "object_delta_5e1b": "steer", "step_operations_for_direction": "move",
    "_ground_follow_move_bbed": "move",
    "_spawn_enemy_shot_7476": "shoot", "_spawn_ground_crawler_shot": "shoot",
    "_spawn_child_c237": "spawn", "_alloc": "spawn", "enemy_spawn_stamp_8209": "spawn",
    "retarget_delta_toward_anchor_74e2": "retarget",
    "_bb03_bounce": "bounce",
    "_bfc7_touch_death": "death", "_bd17_deactivate": "death",
    "canned_random_next_4d95": "random",
    "object_tile_probe_deactivates_ad60": "tile-gate", "object_bounds_tile_decision_ad60": "tile-gate",
    "_planet_sprite_f225": "sprite", "_postmove_bc45_with_drift": "tail",
    "overlap_contact_box_contains": "contact", "object_update_af60": "update",
    # verbs under alternate names / aliases surfaced by the first coverage pass
    "enemy_shot_stamp_7476": "shoot", "_stamp_8209": "spawn", "afd8": "contact",
    "_steer_5e42_inplace": "steer", "_triple_afd8_or_die_f194": "contact", "_ad60_tail": "tile-gate",
    "_shot_hit_9e19": "death", "_jitter_axis_96ec": "move", "emit_bae1": "shoot",
    "_reflect_0686": "reflect", "ground_crawler_sprite_8b_8c": "sprite",
    "object_update_b86d": "update", "object_update_ae2c": "update", "object_update_ae7d": "update",
    # predicate GUARDS (a bool worker read as a step guard) -- part of the vocabulary
    "scenery_89_should_emit": "guard", "scenery_19_should_emit": "guard",
    "ground_crawler_should_spawn": "guard",
}
#: pure computation / helpers -- not verbs, not escapes (they carry no behaviour).
UTILITY = {
    "i16", "_s16", "tuple", "items", "range", "int", "len", "min", "max", "abs", "rw", "ww", "rb",
    "wb", "enumerate", "bool", "list", "dict", "set", "sorted", "any", "all", "SimpleNamespace",
    "replace", "get", "append", "bytes", "bytearray", "reversed", "sum", "ord", "chr",
}


def _handlers(tree):
    fns = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    handlers = {n: f for n, f in fns.items() if n.startswith("_step_") or n.startswith("step_")}
    return fns, handlers


def _callees(fn) -> set:
    out = set()
    for c in ast.walk(fn):
        if isinstance(c, ast.Call):
            if isinstance(c.func, ast.Name):
                out.add(c.func.id)
            elif isinstance(c.func, ast.Attribute):
                out.add(c.func.attr)
    return out


def _control_weight(fn) -> int:
    return sum(isinstance(n, (ast.If, ast.For, ast.While)) for n in ast.walk(fn))


def _is_handler_name(n: str) -> bool:
    return n.startswith("_step_") or n.startswith("step_")


def classify(name, fn, handler_names):
    callees = _callees(fn)
    verbs = {VERB_OF[c] for c in callees if c in VERB_OF}
    # a CHAIN calls another behaviour handler (local OR imported) -- morph / fall-through
    chains = {c for c in callees if c != name and (c in handler_names or _is_handler_name(c))}
    unknown = {c for c in callees
               if c not in VERB_OF and c not in UTILITY and c not in handler_names
               and not _is_handler_name(c) and c != "RecoveryGap"}  # a gap raise is not an escape verb
    ctrl = _control_weight(fn)
    body = sum(1 for _ in ast.walk(fn))
    if unknown:
        return "ESCAPE", verbs, chains, unknown, ctrl
    if chains:
        return "CHAIN", verbs, chains, unknown, ctrl
    if ctrl >= 5:                      # heavy inline control flow the verb set doesn't name yet
        return "CONTROL", verbs, chains, unknown, ctrl
    if not verbs and body < 60:
        return "STUB", verbs, chains, unknown, ctrl
    return "PURE", verbs, chains, unknown, ctrl


def main() -> int:
    tree = ast.parse(WALK.read_text())
    fns, handlers = _handlers(tree)
    rows = {n: classify(n, f, handlers) for n, f in handlers.items()}

    buckets = Counter(v[0] for v in rows.values())
    verb_use = Counter()
    escape_callees = Counter()
    for kind, verbs, chains, unknown, ctrl in rows.values():
        verb_use.update(verbs)
        escape_callees.update(unknown)

    # behaviours ALREADY expressed as verified (shadow-gated) step-lists in the interpreter
    from overkill.recovered.adapters import actor_steps
    done_ids = set()
    for attr in ("BOUNCE_BEHAVIORS", "CONTROLLER_BEHAVIORS", "SHOOTER_BEHAVIORS", "SPAWNER_BEHAVIORS"):
        done_ids |= set(getattr(actor_steps, attr, {}))

    total = len(rows)
    quantizable = buckets["STUB"] + buckets["PURE"] + buckets["CHAIN"]
    print(f"=== ACTOR QUANTIZATION COVERAGE: {total} recovered handlers ===\n")
    for k in ("STUB", "PURE", "CHAIN", "CONTROL", "ESCAPE"):
        print(f"  {k:8} {buckets[k]:3d}  ({100*buckets[k]/total:4.1f}%)")
    with_control = quantizable + buckets["CONTROL"]
    print(f"\n  ALREADY EXPRESSED as verified (shadow-gated) step-lists: {len(done_ids)} behaviour ids "
          f"-> {', '.join(f'{i:#04x}' for i in sorted(done_ids))}")
    print(f"  QUANTIZABLE TODAY (STUB+PURE+CHAIN): {quantizable}/{total} = "
          f"{100*quantizable/total:.1f}%")
    print(f"  QUANTIZABLE after 1-2 CONTROL verbs (+substate/mode/loop): {with_control}/{total} = "
          f"{100*with_control/total:.1f}%")
    print(f"  genuine Call ESCAPE floor (bosses/pods/pickups/morph): {buckets['ESCAPE']}/{total} = "
          f"{100*buckets['ESCAPE']/total:.1f}%")

    print("\n=== verb reuse across handlers ===")
    for verb, cnt in verb_use.most_common():
        print(f"  {cnt:3d}  {verb}")

    print("\n=== ESCAPE: bespoke callees still outside the vocabulary (candidate Call targets) ===")
    for c, cnt in escape_callees.most_common():
        print(f"  {cnt:3d}  {c}")

    print("\n=== CONTROL handlers (owe a substate/mode/loop verb) ===")
    print("  " + ", ".join(n for n, v in rows.items() if v[0] == "CONTROL"))
    print("\n=== ESCAPE handlers ===")
    print("  " + ", ".join(n for n, v in rows.items() if v[0] == "ESCAPE"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
