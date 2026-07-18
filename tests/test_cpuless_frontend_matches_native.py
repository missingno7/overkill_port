"""CROSS-VALIDATION: the CPUless front-end's frame == the hand-verified native composer's frame.

Two INDEPENDENT recoveries of the same screen must agree:

* the GENERATED corpus -- `1010:CC04` run under the CPUless wall, drawing into the image's B800 exactly
  as the original does;
* the hand-recovered composer -- `native_video.blueprint.compose_blueprint`, which reads the game's own
  `DS:BD54` recipe table and was separately verified against the VM ("grid + all 15 recipe cells ==
  the VM's blueprint with ZERO under-draw", run_status 2026-07-13).

They share no code, so byte-equality is real evidence for BOTH: it says the lifted front-end reproduces
the blueprint the VM draws, and that the manual composer models the same machine behaviour. This is the
cross-check that corrected an earlier misreading -- the `ax=0` frame was assumed to be a menu SELECTION
until this comparison identified it as the blueprint intro at +5 cells revealed.

Artifact-gated on the data-only boot image (original-game bytes, never committed).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dos_re"))

BOOT_IMAGE = ROOT / "artifacts" / "frontend_intro_snapshot" / "memory_1mb.bin"
_DS = 0x25CC
_KEY_TABLE = 0x98C4
_FIRE = 0x39            # the scancode the front-end loop breaks out on


@pytest.mark.skipif(not BOOT_IMAGE.is_file(),
                    reason="no front-end boot image -- this cross-validation is artifact-gated")
def test_cpuless_frontend_frame_matches_hand_recovered_blueprint():
    from overkill.cpuless_host import install_import_guard, run_deep, run_recovered
    from overkill.cpuless_runtime import OverkillPlatform
    from overkill.native_video.blueprint import compose_blueprint
    from overkill.native_video.page_raster import decode_tandy_b800_indices
    from overkill.recovered.adapters.flat_memory import MutFlatMemory

    install_import_guard()
    img = MutFlatMemory(BOOT_IMAGE.read_bytes())
    img.wb(_DS, (_KEY_TABLE + _FIRE) & 0xFFFF, 1)          # hold fire: the loop runs the reveal + exits
    run_deep(run_recovered, "1010:CC04", img, OverkillPlatform(),
             ds=_DS, es=_DS, ss=0x2000, sp=0x1000)

    generated = decode_tandy_b800_indices(np.frombuffer(bytes(img.data), dtype=np.uint8), 0xB8000)
    manual = compose_blueprint(img, 5)                     # the +5-cells reveal beat

    assert generated.shape == manual.shape == (200, 320)
    assert np.array_equal(generated, manual), (
        "the CPUless front-end and the hand-recovered composer disagree: "
        f"generated lit={int((generated != 0).sum())} manual lit={int((manual != 0).sum())} "
        f"differing pixels={int((generated != manual).sum())}")
