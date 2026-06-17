"""Contract + purity tests for the backend-agnostic game-core seam.

The whole value of overkill/game_core is that it does NOT depend on the
emulation/platform stack.  These tests fail loudly if that boundary is breached
or if the reference adapters drift from the protocols.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

GAME_CORE_DIR = pathlib.Path(__file__).resolve().parents[1] / "overkill" / "game_core"

# Import roots the seam may never reach: the VM, DOS, GUI toolkits, and any
# other overkill subpackage (which would drag the emulator back in).
FORBIDDEN_ROOTS = {"dos_re", "pygame", "sdl2", "tkinter", "numpy"}


def _imported_roots(path: pathlib.Path) -> set[str]:
    """Absolute top-level module names imported by ``path`` (relative imports excluded)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue  # relative import within game_core: allowed
            if node.module:
                roots.add(node.module.split(".")[0])
    return roots


def _game_core_modules() -> list[pathlib.Path]:
    return sorted(GAME_CORE_DIR.glob("*.py"))


def test_game_core_has_no_platform_or_vm_dependencies():
    offenders: dict[str, set[str]] = {}
    for module in _game_core_modules():
        roots = _imported_roots(module)
        bad = {r for r in roots if r in FORBIDDEN_ROOTS}
        # Any absolute overkill.* import other than game_core itself is also a
        # boundary breach (it would pull emulator code into the neutral core).
        for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and not (node.level and node.level > 0):
                mod = node.module or ""
                if mod.split(".")[0] == "overkill" and not mod.startswith("overkill.game_core"):
                    bad.add(mod)
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] == "overkill" and not alias.name.startswith("overkill.game_core"):
                        bad.add(alias.name)
        if bad:
            offenders[module.name] = bad
    assert not offenders, f"game_core breached its platform-neutral boundary: {offenders}"


def _code_only_text(path: pathlib.Path) -> str:
    """Source with string literals and comments stripped (docstrings may freely
    discuss forbidden concepts; executable code may not touch them)."""
    import io
    import tokenize

    pieces: list[str] = []
    with path.open("rb") as fh:
        for tok in tokenize.tokenize(fh.readline):
            if tok.type in (tokenize.STRING, tokenize.COMMENT, tokenize.ENCODING):
                continue
            pieces.append(tok.string)
    return " ".join(pieces)


def test_game_core_code_never_touches_forbidden_concepts():
    # Guard against re-introducing VM/layout coupling in executable code.
    forbidden_substrings = (
        "replacement_hooks",
        "ega_planar",
        "deliver_scancode",
        "port_writer",
        "port_reader",
    )
    for module in _game_core_modules():
        code = _code_only_text(module)
        for needle in forbidden_substrings:
            assert needle not in code, f"{module.name} code touches forbidden concept {needle!r}"


def test_null_adapters_satisfy_protocols_structurally():
    from overkill.game_core.backends import (
        AssetProvider,
        AudioBackend,
        InputBackend,
        TimingBackend,
        VideoBackend,
    )
    from overkill.game_core.null_backends import (
        InMemoryAssetProvider,
        ManualTimingBackend,
        NullAudioBackend,
        NullVideoBackend,
        ScriptedInputBackend,
    )

    assert isinstance(NullVideoBackend(), VideoBackend)
    assert isinstance(ScriptedInputBackend(), InputBackend)
    assert isinstance(NullAudioBackend(), AudioBackend)
    assert isinstance(ManualTimingBackend(), TimingBackend)
    assert isinstance(InMemoryAssetProvider(), AssetProvider)


def test_framebuffer_is_indexed_and_validated():
    from overkill.game_core.types import Framebuffer

    palette = tuple((i * 16, 0, 0) for i in range(16))
    fb = Framebuffer(width=2, height=2, pixels=bytes([0, 1, 2, 15]), palette=palette)
    assert fb.index_at(1, 0) == 1
    assert fb.rgb_at(1, 1) == (15 * 16, 0, 0)
    with pytest.raises(ValueError):
        Framebuffer(width=2, height=2, pixels=bytes([0, 1, 2]), palette=palette)


def test_reference_backends_compose_into_a_headless_frame_loop():
    """A minimal core-style loop drives all five backends with no VM in sight."""
    from overkill.game_core.null_backends import (
        InMemoryAssetProvider,
        ManualTimingBackend,
        NullAudioBackend,
        NullVideoBackend,
        ScriptedInputBackend,
    )
    from overkill.game_core.types import (
        Asset,
        Framebuffer,
        GameButton,
        InputEvent,
    )

    video = NullVideoBackend()
    audio = NullAudioBackend()
    timing = ManualTimingBackend(frame_hz=72.0)
    inputs = ScriptedInputBackend([InputEvent(GameButton.BUTTON_PRIMARY, True)])
    assets = InMemoryAssetProvider({7: Asset(asset_id=7, data=b"sprite")})

    palette = tuple((0, 0, 0) for _ in range(16))
    fired = False
    for _ in range(3):
        for event in inputs.poll():
            if event.button is GameButton.BUTTON_PRIMARY and event.pressed:
                fired = True
                audio.set_tone(880.0)
        video.present(Framebuffer(4, 4, bytes(16), palette))
        timing.wait_next_frame()

    assert fired is True
    assert audio.tone_hz == 880.0
    assert video.frames_presented == 3
    assert timing.frames_waited == 3
    assert inputs.is_pressed(GameButton.BUTTON_PRIMARY)
    assert assets.has(7) and assets.load(7).data == b"sprite"
