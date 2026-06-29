"""The native frame controller -- the VM-free per-frame sequence (pillar 3 skeleton).

``1010:9B2E`` is the game-state controller: each frame it polls input, updates the player
view-anchor from that input, runs the object-update pass, fans out actions, resolves
contacts, and maintains the coordinate rings -- all over VM memory.  This module is the
VM-free counterpart: it sequences the *recovered systems* over a :class:`NativeGameState`,
the same order, with no VM.

It grows one stage at a time as each 9B2E stage becomes a pure system.  Today it covers the
two stages that are native and share a data flow -- the input decode and the movement bits --
composed end-to-end (raw key state -> decoded button byte -> view-anchor step), proven equal
to the VM by ``overkill.probes.verify_native_frame_loop``.  Stages still owned by the VM
(the A212 anchor pre-update, the 8546 secondary fire, the A067 action fan-out, the 9CB6
contact probe, the coordinate rings) are noted at their call sites and join as they land.

The input stage here models the *keyboard* path.  When the scripted-input mode is active
(DS:A47C != 0, boss/cutscene auto-movement) 9B2E first runs 1010:99F6, which overwrites the
button byte with a scripted value instead of decoding the keyboard; that scripted-input stage
is not native yet, so ``native_player_frame_step`` applies to the normal-gameplay frames
(no_clamp == False).  The no-clamp movement path itself is still exercised by the standalone
movement-bits verify, which reads the VM's actual button byte.
"""
from __future__ import annotations

from overkill.recovered.domain.frame_loop import FrameInput, PlayerFrameStep
from overkill.recovered.domain.object_slots import ObjectPool
from overkill.recovered.systems.input import decode_keyboard_input_flags
from overkill.recovered.systems.movement import step_view_anchor_by_input

# View-anchor record field offsets the controller writes (cf. recovered.views.object_slots);
# the pure systems layer names the small set it touches rather than importing the bridge views.
_OFF_X = 0x02
_OFF_Y = 0x04
_VIEW_ANCHOR_SLOT = 0  # special_pool holds the single DS:237C view-anchor slot


def decode_frame_input(frame_input: FrameInput) -> int:
    """Frame stage 1 (9B2E:9B3A): decode the per-frame input source to the button byte.

    The native controller decodes from the raw key state itself, so the rest of the frame
    consumes the same DS:98BE the VM would -- without the VM's INT 9 path.
    """
    return decode_keyboard_input_flags(frame_input.control_map, frame_input.key_state)


def native_player_frame_step(
    special_pool: ObjectPool, frame_input: FrameInput, *, no_clamp: bool
) -> PlayerFrameStep:
    """Frame stages 1->2 composed: decode input, then apply the movement bits to the anchor.

    Mirrors 9B2E from the input poll through the four direction bits (9B6F..9B94): decode the
    button byte, then step the view-anchor slot (DS:237C, ``special_pool`` slot 0) via the
    recovered :func:`step_view_anchor_by_input`.  ``no_clamp`` is the DS:A47C movement-mode
    gate the up-step consults.  Returns the updated pool plus the decoded flags the later
    action/fire stages will consume.
    """
    input_flags = decode_frame_input(frame_input)
    move = step_view_anchor_by_input(
        special_pool.x_word(_VIEW_ANCHOR_SLOT),
        special_pool.y_word(_VIEW_ANCHOR_SLOT),
        input_flags,
        no_clamp=no_clamp,
    )
    new_pool = special_pool
    if move.stepped:
        new_pool = (new_pool
                    .with_word(_VIEW_ANCHOR_SLOT, _OFF_X, move.x_word)
                    .with_word(_VIEW_ANCHOR_SLOT, _OFF_Y, move.y_word))
    return PlayerFrameStep(special_pool=new_pool, input_flags=input_flags, moved=move.stepped)
