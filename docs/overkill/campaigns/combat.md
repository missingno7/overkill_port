# Campaign: COMBAT RESOLUTION (tier: byte-exact)

**Scope.** Player shots kill enemies, enemy contact/shots hurt the player, scoring, drops: the 62F6
object-overlap scan, the C037 death transition (recovered), 5F0D scoring (recovered), the 2078
completion-drop counters (recovered).

**Done when:** in play_native, shooting an enemy kills it (explosion + score + possible drop) and
enemies hurt the player — byte-exact vs the VM at the walk boundary (extend the shadow corpus to a
firing demo).

**State (2026-07-05):** player-shot behavior 0x02 handled in the walk; the anchor-touch (BCCB→BFC7)
+ damage chains native; **the 62F6 combat chain is COMPOSED into the walk's postmove** (62F6 overlap
→ BEC5 reaction → BF25 damage → the full BFC7 death; variant-2 candidate clear; survival's `+24h :=
5` hit-react — "bp+36" in the old docstrings is DECIMAL). Proven by `verify_native_combat`: a
planted solid player shot vs the live L1 wave — kill / no-hit / survive, all full-DGROUP zero-diff,
with fired-assertions so the oracle can't regress to a no-op. The whole-walk shadow stays 200/0.
Unit-tested in `test_behavior_walk_combat.py`. Unrecovered remainder fail-louds: the BEC5
owner-link/unclassified candidate reaction (`+30h` owner pointer).

**Next:** a firing-demo shadow gate (a demo corpus where the player actually fires, so the chain is
witnessed under real inputs end-to-end), then the done-condition check in play_native.
