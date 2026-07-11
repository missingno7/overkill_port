"""The NativeAttract driver -- the D007 loop composition (front-end slice C)."""
from __future__ import annotations

from overkill.native_attract import FIRST_CELL_SCENE, NativeAttract


def _run(driver, frames, *, fire_at=None):
    """Step the driver `frames` times (fire on frame `fire_at`); return the action-kind sequence."""
    kinds = []
    for f in range(frames):
        driver, action = driver.step(fire_pressed=(f == fire_at), any_key=False)
        kinds.append(action.kind)
        if action.kind == "exit":
            break
    return kinds, driver


def test_starts_at_first_cell_scene():
    d = NativeAttract.start()
    assert d.state.scene == FIRST_CELL_SCENE      # scene 0 (D160) is a gap, so we begin at scene 1


def test_cell_scenes_draw_then_advance_to_gameplay():
    d = NativeAttract.start()
    # scenes 1..7 draw cells (100 frames each); by ~7*100 frames the scene id reaches 8 -> gameplay
    kinds, _ = _run(d, 800)
    assert kinds[0] == "draw_cell"
    assert "gameplay" in kinds                    # crossed into the auto-fire gameplay scenes


def test_fire_exits_the_attract():
    d = NativeAttract.start()
    kinds, _ = _run(d, 10, fire_at=3)
    assert kinds[-1] == "exit" and len(kinds) == 4    # exits the frame fire is pressed


def test_gameplay_scenes_carry_the_autofire_beat():
    # drive to a gameplay scene and confirm the auto-fire beat is exposed on the right ticks
    d = NativeAttract.start()
    saw_injected = False
    for f in range(1500):
        d, action = d.step(fire_pressed=False, any_key=False)
        if action.kind == "gameplay" and action.injected_fire is not None:
            saw_injected = True
            break
        if action.kind == "exit":
            break
    assert saw_injected                            # the attract injects scripted fire during gameplay
