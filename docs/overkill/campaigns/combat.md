# Campaign: COMBAT RESOLUTION (tier: byte-exact)

**Scope.** Player shots kill enemies, enemy contact/shots hurt the player, scoring, drops: the 62F6
object-overlap scan, the C037 death transition (recovered), 5F0D scoring (recovered), the 2078
completion-drop counters (recovered).

**Done when:** in play_native, shooting an enemy kills it (explosion + score + possible drop) and
enemies hurt the player — byte-exact vs the VM at the walk boundary (extend the shadow corpus to a
firing demo).

**State (2026-07-05):** player-shot behavior 0x02 handled in the walk; the anchor-touch (BCCB→BFC7)
+ damage chains native; **the 62F6 scan is the gap** (the walk currently skips it; no candidates in
the free-run corpus). Player shots reach the image as of the dual-state fix.

**Next:** recover/compose 62F6 into the walk's postmove (the pure object_overlap_scan_62f6 family
exists in systems/collision) + a firing-demo shadow gate.
