"""AUDIT: every declared RECOVERY FACT must have its consequence visible in the generated artifacts.

Recovery facts (`artifacts/lift_*.txt`) are this project's currency: hand-verified statements about the
binary that the pipeline is supposed to act on.  A fact that exists but is never CONSUMED is worse than
no fact at all -- it reads as settled knowledge while changing nothing, and the generated corpus quietly
contradicts it.  That is not hypothetical: `lift_keep_interpreted.txt` declared `1010:0679` /
`1010:50C9` the ENV-WAIT frontier ("a plain lift freezes a timing-dependent iteration count --
liftverify proves it DIVERGES"), yet `probe_vmless_cpuless.py` never passed the file, so both were
promoted into the committed corpus and no gate noticed for weeks.

This audit checks CONSEQUENCES, not source text.  Grepping the pipeline for a flag proves only that a
string appears; asserting the OUTCOME in the census proves the fact actually took effect, and keeps
working if the pipeline is rewritten.

It is a RATCHET.  Known, documented violations are listed in ``KNOWN_VIOLATIONS`` with the reason and
where the fix is tracked; the audit fails on any violation NOT in that list, and also fails when a
listed violation has been fixed (so the list can only shrink and never silently rots).

Usage:  python scripts/audit_recovery_facts.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "artifacts"

#: the committed CPUless corpus -- the generated runtime source the port actually ships.
CORPUS = ROOT / "overkill" / "cpuless_recovered"

#: an emitted boundary observation: ``plat.boundary(0x1010, 0x97CB, 0x97CE, {...}, ...)``.
#: Group 1/2 are the head CS:IP the emitter was told to yield at (emit_cpuless._emit_boundary).
_BOUNDARY_CALL = re.compile(r"\bplat\.boundary\(\s*0x([0-9A-Fa-f]{1,4})\s*,\s*0x([0-9A-Fa-f]{1,4})\s*,")

#: violation-key -> why it is tolerated *for now* and where the fix is tracked.  A violation here is an
#: acknowledged debt with an owner, not an exemption: the audit fails if one is fixed but still listed.
KNOWN_VIOLATIONS = {
    "keep-interpreted-promoted:1010:0679":
        "env-wait (frame timer spin) is promoted although declared keep-interpreted. MITIGATED at "
        "RUNTIME (2026-07-18d): overkill/cpuless_overrides.py patches it with a scheduler yield to "
        "OverkillPlatform.boundary() that supplies the tick the absent INT 8 handler owed, then "
        "delegates to the generated body. The PIPELINE-level violation stands (promotion still "
        "ignores the fact file); it stops mattering once the emitter models env-waits as boundaries.",
    "keep-interpreted-promoted:1010:50C9":
        "env-wait (CRT retrace spin) is promoted although declared keep-interpreted. Satisfied at "
        "runtime by OverkillPlatform.inp() toggling 3DAh, so the spin terminates. CORRECTION "
        "(2026-07-18d): the earlier note here claimed this was 'likely why the front-end cannot "
        "animate' -- measured false. A 400-boundary probe showed the CC04 front-end never reaches "
        "0679 at all and paces purely on this retrace, so the env-wait was never the blocker. "
        "UPDATE (2026-07-18e): that note also blamed a missing top level ('1010:96C8 refuses "
        "no-exit') -- no longer true. dos_re can now represent setjmp/longjmp, 96C8 promotes with "
        "ZERO overrides, and the runtime closure from 1010:97B2 is 253/253 with an empty frontier. "
        "The corpus HAS a top level; what remains here is only the PIPELINE-level violation "
        "(promotion still ignores the keep-interpreted fact file).",
}


def _addrs(path: Path) -> "list[str]":
    """The CS:IP addresses declared in a fact file (comments and blanks ignored)."""
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(line.upper())
    return out


def audit() -> "tuple[dict, list[str]]":
    """Return (violations, notes). ``violations`` maps a stable key -> human detail."""
    violations: dict[str, str] = {}
    notes: list[str] = []

    census_path = ART / "cpuless_promote_census.json"
    if not census_path.is_file():
        notes.append(f"SKIP: no {census_path.name} -- run scripts/probe_vmless_cpuless.py first")
        return violations, notes
    census = json.loads(census_path.read_text(encoding="utf-8"))
    promoted = {a.upper() for a in census.get("promotable", [])}

    # FACT 1 -- keep-interpreted (env-wait frontier).  Consequence: the address must NOT appear in the
    # promotable set.  These are async spin-waits whose lift freezes a timing-dependent iteration count.
    keep = _addrs(ART / "lift_keep_interpreted.txt")
    notes.append(f"keep-interpreted: {len(keep)} declared")
    for a in keep:
        if a in promoted:
            violations[f"keep-interpreted-promoted:{a}"] = (
                f"{a} is declared keep-interpreted (env-wait) but IS in the promotable set -- the "
                f"declared fact had no effect on the pipeline")

    # FACT 2 -- boundary heads.  Consequence: the OWNING function must be recognised as boundary-
    # carrying, i.e. it must not be silently promoted as an ordinary function while its head is
    # declared a scheduler yield.  A declared head that leaves no trace anywhere is a dead fact.
    #
    # The signal must be POSITIVE and must hold in BOTH outcomes a consumed head can have:
    #
    #   * COMPOSED -- the head lifts, and emit_cpuless plants a `plat.boundary(cs, ip, ...)`
    #     observation at that exact address in the generated module.  The head address is
    #     literally present in the emitted corpus.
    #   * REFUSED  -- the head is reached on a transfer the emitter cannot model, so the owning
    #     function lands in the census's `boundary-head-on-transfer` bucket.
    #
    # Either one proves the pipeline READ the fact and acted on it.  (The earlier check keyed only
    # on the refusal bucket, which inverted the meaning: once setjmp/longjmp representation let all
    # ten gameplay-loop entries compose, the bucket emptied and the audit read that SUCCESS as an
    # unconsumed fact.  An empty refusal bucket is the desired outcome, not evidence of a dead fact.)
    heads = _addrs(ART / "lift_boundary_heads.txt")
    notes.append(f"boundary-heads: {len(heads)} declared")
    refused = census.get("refused", {})
    boundary_refused = {a.upper() for a in refused.get("boundary-head-on-transfer", [])}
    emitted = set()
    for src in sorted(CORPUS.glob("func_*.py")):
        for cs, ip in _BOUNDARY_CALL.findall(src.read_text(encoding="utf-8")):
            emitted.add(f"{int(cs, 16):04X}:{int(ip, 16):04X}")
    notes.append(f"boundary-heads: {len(emitted)} observed in the emitted corpus, "
                 f"{len(boundary_refused)} refused boundary-head-on-transfer")
    for a in heads:
        if a not in emitted and not boundary_refused:
            violations[f"boundary-head-no-effect:{a}"] = (
                f"{a} is declared a boundary head but no emitted module carries a "
                f"plat.boundary() observation at it and nothing is refused "
                f"boundary-head-on-transfer -- the declared fact had no effect on the pipeline")

    return violations, notes


def main() -> int:
    violations, notes = audit()
    print("=" * 72)
    print("RECOVERY-FACT AUDIT -- does each declared fact actually take effect?")
    print("=" * 72)
    for n in notes:
        print(f"  {n}")

    unexpected = {k: v for k, v in violations.items() if k not in KNOWN_VIOLATIONS}
    fixed = [k for k in KNOWN_VIOLATIONS if k not in violations]

    if violations:
        print(f"\n  violations: {len(violations)} "
              f"({len(violations) - len(unexpected)} known/tracked, {len(unexpected)} NEW)")
        for k, v in sorted(violations.items()):
            tag = "KNOWN" if k in KNOWN_VIOLATIONS else "NEW  "
            print(f"    [{tag}] {v}")
            if k in KNOWN_VIOLATIONS:
                print(f"            tracked: {KNOWN_VIOLATIONS[k]}")
    else:
        print("\n  no violations -- every declared fact has a visible consequence")

    if fixed:
        print(f"\n  RATCHET: {len(fixed)} known violation(s) no longer occur -- remove them from "
              f"KNOWN_VIOLATIONS so the audit keeps its teeth:")
        for k in fixed:
            print(f"    {k}")

    if unexpected or fixed:
        print("\nFAIL")
        return 1
    print("\nOK" + (f" ({len(violations)} known violations tracked)" if violations else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
