"""The cold-start differential's own INVARIANTS, pinned so they cannot quietly erode.

`scripts/verify_cpuless_coldstart.py` takes ~15 minutes for a full run, so it is not a suite test.
What IS cheap, and what actually decides whether its green means anything, is the set of properties
that make it evidence rather than ceremony.  Each of these has a recorded failure behind it:

* an ORACLE that is not the original program reports a wrong frontier and looks authoritative
  (skyroads ran 29 replacements on a "pure-ASM" reference, including a behaviour-changing loop-skip,
  and blamed an entire claimed frontier on its candidate);
* a step budget that returns QUIETLY leaves the oracle parked mid-frame, so every later frame blames
  the candidate for the oracle's truncation;
* a differential that drives its OWN frame model proves nothing about the shipped runner;
* re-seeding the candidate from the oracle each frame structurally hides cross-frame drift, which is
  exactly the hole this harness exists to close in the port's existing gates.

These read the source rather than run it, deliberately: they are asserting that the harness has not
been rewritten into a weaker one.
"""
from __future__ import annotations

from pathlib import Path

import pytest

SRC = (Path(__file__).resolve().parents[1] / "scripts" / "verify_cpuless_coldstart.py")


@pytest.fixture(scope="module")
def src() -> str:
    return SRC.read_text(encoding="utf-8")


def test_the_oracle_purity_is_asserted_with_nothing_allowed(src):
    """`allow=frozenset()` is the strong form.  The port's other harnesses keep three env-wait hooks
    live on their reference side; this one delivers real INT 08h interrupts instead, so the game's own
    wait loops terminate on the game's own code and nothing needs allowing.  Any address added to
    `allow` is a place the reference stops being the original program and must be argued for."""
    assert "assert_pure_oracle(rt.cpu, allow=frozenset())" in src


def test_the_registry_is_stripped_after_boot_not_guarded_at_import(src):
    """Guarding the hooks IMPORT does not work -- the registry is populated at decoration time and
    install() wires it onto the "pure" CPU regardless.  Loading an OVERKILL snapshot was measured to
    leave 337 replacements live."""
    assert "hook_registry.uninstall(rt.cpu)" in src
    assert "import overkill.hooks" not in src, "must not try to gate the import instead"


def test_step_budget_exhaustion_raises_and_never_returns_silently(src):
    """A silent truncation is worse than a crash: the oracle stays parked mid-frame and still looks
    authoritative, so the comparison blames the candidate for the reference's own shortfall."""
    body = src[src.index("def run_to_cut"):src.index("for frame in range(frames)")]
    assert "raise RuntimeError(" in body
    assert "budget exhausted" in body
    # the loop must have no quiet exit: every path out is either the cut or the raise
    assert "return\n" in body or "            return" in body
    assert "break" not in body, "a break would leave the oracle parked and the run continuing"


def test_the_candidate_uses_the_shipped_frame_driver(src):
    """Not a verification-only lookalike: the same `CPUlessFrameDriver` the runner and
    `coldboot_frontier.py` use, and the game's own recovered IRQ0 ISR."""
    assert "from overkill.cpuless_driver import CPUlessFrameDriver" in src
    assert "func_1010_06e5" in src, "the game's own IRQ0 ISR, not a synthetic tick"
    assert "CPUlessFrameDriver(" in src and ".install(plat)" in src


def test_the_candidate_is_entered_once_and_never_reseeded(src):
    """The whole point.  The port's existing gates re-seed the candidate from the oracle at every
    frame boundary, which cannot see an error that only compounds across frames."""
    cand = src[src.index("def _capture_candidate"):src.index("def _report")]
    assert cand.count("run_deep(run_recovered") == 1, "the root is entered exactly once"
    assert "load_overkill_snapshot" not in cand, "the candidate must never read the oracle's runtime"
    assert "rt.cpu" not in cand and "cpu.s" not in cand, "the candidate side touches no CPU"


def test_both_sides_start_from_the_same_recorded_state(src):
    """A differential between two different start states is not a differential."""
    assert src.count("COLD_SNAPSHOT") >= 4
    assert 'ROOT_KEY = "1010:96C8"' in src


def test_the_observable_covers_the_page_selection_not_just_the_pixels(src):
    """OVERKILL on Tandy page-flips via the CRTC start address, so identical pixel bytes with a
    different displayed page is a real divergence a plain frame-buffer compare cannot see."""
    assert "_crtc(dos)" in src and "_PortTap" in src
    assert "B800_TANDY_LEN = 0x8000" in src


def test_the_frame_cut_is_the_declared_boundary_head(src):
    """Both sides must cut at the same place, and that place must be the head the corpus actually
    calls `plat.boundary` at -- not a separately chosen address."""
    assert "HEAD = (0x1010, 0x0679)" in src
    heads = (SRC.parent.parent / "artifacts" / "lift_boundary_heads.txt").read_text(encoding="utf-8")
    declared = {ln.strip().upper() for ln in heads.splitlines()
                if ln.strip() and not ln.lstrip().startswith("#")}
    assert "1010:0679" in declared
