# Campaign: PLAYER (tier: byte-exact)

**Scope.** Ship movement, the fire fan-out, damage intake (energy A95C / lives A95A), player death.

**Done when:** all player behavior runs natively over the image (ADR-1), including fired shots
entering the image pools, the damage chain (9E19/9E69 — already in the walk), and the death
transition handing off to the Spine's death edge. Hooks retired to verify-only.

**State (2026-07-05):** movement + scroll + fire fan-out native (dataclass-side); the damage beats
are native in the walk; shots now flow into the image (the dual-state fix). Player death edge =
Spine's work.

**Next:** migrate the player step to read/write the image (removes the last dataclass authority).
