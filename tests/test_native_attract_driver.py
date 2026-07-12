"""The NativeAttract driver + scene-0 setup -- the D007 loop composition (front-end slice C)."""
from __future__ import annotations

from overkill.native_attract import SETUP_SCENE, FIRST_CELL_SCENE, NativeAttract


def _run(driver, frames, *, fire_at=None, setup_after=0):
    """Step the driver `frames` times; report scene-0 setup done after `setup_after` setup frames;
    fire on frame `fire_at`.  Returns the action-kind sequence."""
    kinds = []
    setup_seen = 0
    for f in range(frames):
        done = False
        if kinds and kinds[-1] == "scene0_setup":
            setup_seen += 1
            done = setup_seen >= setup_after
        driver, action = driver.step(fire_pressed=(f == fire_at), any_key=False, setup_done=done)
        kinds.append(action.kind)
        if action.kind == "exit":
            break
    return kinds, driver


def test_starts_at_scene_0_setup():
    d = NativeAttract.start()
    assert d.state.scene == SETUP_SCENE
    _, action = d.step(fire_pressed=False, any_key=False, setup_done=False)
    assert action.kind == "scene0_setup"


def test_setup_done_advances_to_first_cell_scene():
    d = NativeAttract.start()
    d, action = d.step(fire_pressed=False, any_key=False, setup_done=True)
    assert action.kind == "draw_cell" and action.scene == FIRST_CELL_SCENE


def test_full_flow_setup_cells_gameplay():
    d = NativeAttract.start()
    kinds, _ = _run(d, 1000, setup_after=1)
    assert kinds[0] == "scene0_setup"
    assert "draw_cell" in kinds and "gameplay" in kinds     # setup -> cells -> auto-fire gameplay


def test_scene_3_and_5_countdown_override():
    """The D0DB per-scene tail (D183) reloads [BE08]=0x32 for scenes 3 and 5 -- half the default 0x64 --
    so they display for half as long; the native attract must apply it to match the cold-start demo."""
    from overkill.recovered.domain.attract import AttractSceneState
    # scene 2 with countdown 1: the next step advances to scene 3, which OVERRIDES the countdown to 0x32
    d = NativeAttract(AttractSceneState(scene=2, countdown=1, autofire_tick=0))
    d2, _ = d.step(fire_pressed=False, any_key=False)
    assert d2.state.scene == 3 and d2.state.countdown == 0x32
    # scene 4 -> 5 also overrides
    d = NativeAttract(AttractSceneState(scene=4, countdown=1, autofire_tick=0))
    d2, _ = d.step(fire_pressed=False, any_key=False)
    assert d2.state.scene == 5 and d2.state.countdown == 0x32
    # a non-overriding scene (1 -> 2) keeps the default 0x64 reload
    d = NativeAttract(AttractSceneState(scene=1, countdown=1, autofire_tick=0))
    d2, _ = d.step(fire_pressed=False, any_key=False)
    assert d2.state.scene == 2 and d2.state.countdown == 0x64


def test_fire_exits_the_attract():
    d = NativeAttract.start()
    kinds, _ = _run(d, 10, fire_at=2, setup_after=1)
    assert kinds[-1] == "exit"


def test_scene0_setup_scrolls_the_anchor_and_terminates():
    import pathlib
    bundle = pathlib.Path(__file__).resolve().parent.parent / "artifacts" / "static_runtime_bundle" / "memory_1mb.bin"
    if not bundle.is_file():
        return
    from overkill.native_frame import ATTRACT_ANCHOR_TARGET, ATTRACT_VIEW_ANCHOR, attract_scene0_setup_d160, DS
    from overkill.recovered.adapters.flat_memory import MutFlatMemory
    mem = MutFlatMemory(bundle.read_bytes())
    mem.ww(DS, ATTRACT_VIEW_ANCHOR, ATTRACT_ANCHOR_TARGET + 5)     # 5 above target
    dones = [attract_scene0_setup_d160(mem) for _ in range(5)]
    assert dones == [False, False, False, False, True]            # decremented to target, then done
    assert mem.rw(DS, ATTRACT_VIEW_ANCHOR) == ATTRACT_ANCHOR_TARGET
    assert mem.rw(DS, 0xBE08) == 0x0032                            # countdown reloaded at the end
