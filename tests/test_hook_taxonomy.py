"""The hook taxonomy must stay grounded in the real registry.

These tests guard the checkpoint model: curated checkpoint/env-wait/debug-probe
addresses must be actual registered hooks (no stale or typo'd entries), every
registered hook lands in exactly one category, and the curated boundary sets stay
small (they name real logical boundaries, not padded glue).
"""
import overkill.hooks  # noqa: F401 - registers all replacements
from dos_re.hooks import registry
from overkill.hook_taxonomy import (
    CHECKPOINT_HOOKS,
    DEBUG_PROBE_HOOKS,
    ENV_WAIT_HOOKS,
    classify_hook,
    classify_registry,
)


def test_curated_sets_are_real_registered_hooks():
    registered = set(registry.replacements.keys())
    for label, curated in (
        ("checkpoint", CHECKPOINT_HOOKS),
        ("env_wait", ENV_WAIT_HOOKS),
        ("debug_probe", DEBUG_PROBE_HOOKS),
    ):
        missing = [a for a in curated if a not in registered]
        assert not missing, f"{label} addresses not in the hook registry: " + ", ".join(
            f"{cs:04X}:{ip:04X}" for cs, ip in missing
        )


def test_every_hook_classified_exactly_once():
    buckets = classify_registry(registry.replacements.keys())
    total = sum(len(v) for v in buckets.values())
    assert total == len(registry.replacements)
    # Partition: each address appears in exactly one bucket.
    seen = [a for v in buckets.values() for a in v]
    assert len(seen) == len(set(seen))


def test_glue_is_the_majority_and_boundaries_stay_small():
    buckets = classify_registry(registry.replacements.keys())
    # Curated logical boundaries are deliberately a small, explicit set; the glue
    # majority is the collapse target.  If checkpoints balloon, someone is padding
    # the set instead of collapsing glue.
    assert len(buckets["checkpoint"]) <= 24
    assert len(buckets["glue"]) > len(buckets["checkpoint"]) + len(buckets["env_wait"])


def test_known_boundaries_classify_as_expected():
    assert classify_hook((0x1010, 0x3354)) == "checkpoint"   # Tandy present
    assert classify_hook((0x1010, 0x0679)) == "env_wait"     # timer wait
    assert classify_hook((0x1010, 0xB73E)) == "glue"         # an object behaviour
