"""Bridge: collect this frame's positioned, identified sprite textures.

Turns the verified sprite-texture decoder into the `RenderSnapshot`'s sprite
list. Grounded by `witness_draw_structure`: each on-screen object is drawn by one
layer-draw routine (1010:75A6 / 768E / 7746) with the object record at ``SS:BP``
(stable identity; sprite id ``+08``, screen destination ``+0C``/``+10``), and the
masked compositor block(s) that follow it (``DS:SI`` source, ``ES:DI`` dest) are
its pixels at ``DI == screen_di``.

The collector wraps those routines (to capture the object context) and the masked
compositors (to decode each block via the verified
:func:`sprite_textures.decode_masked_sprite`) and attaches each block to the
current object. ``take_frame`` returns the frame's :class:`CapturedSprite` list.
Identity is the object-record address ``SS:BP`` (the table slot is fixed across
frames), so the renderer can interpolate a sprite's position between source ticks.

This is the VM-bound extractor; the decode it relies on is pure. Non-masked
compositor leaves (the OR-inverted 2F40/2ECB, the strided object copies) are NOT
silently skipped - they are counted as ``unmodeled_blocks`` so missing coverage
is explicit (recovery-first).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from overkill.recovered.systems.sprite_textures import (
    MASKED_COMPOSITORS,
    SpriteTexture,
    decode_masked_sprite,
)

CS = 0x1010
OBJ_SPRITE_INDEX = 0x08
OBJ_ANIMATION_PHASE = 0x12
OFFSCREEN_DESTINATION = 0xFFFF

# Masked-sprite draw routines whose SS:BP is the object record at entry
# (witnessed), with the anchor destination slot offset(s) each reports. 75A6 is a
# double-slot sprite (can draw slot +10 even when +0C is culled). 3657 is a tiny
# tiled object: one object emits many compositor blocks at computed destinations
# (not the anchor slot), so its blocks are attributed temporally, not by slot.
LAYER_DRAW_ROUTINES: dict[int, tuple[int, ...]] = {
    0x75A6: (0x0C, 0x10),
    0x768E: (0x0C,),
    0x7746: (0x0C,),
    0x3657: (0x0C,),
}


@dataclass
class SpriteBlock:
    """One decoded compositor block placed in the page."""

    di: int                 # ES:DI destination (== an object screen_di slot)
    compositor_ip: int      # which masked compositor produced it
    texture: SpriteTexture  # the decoded, background-independent pixels


@dataclass
class CapturedSprite:
    """One on-screen object's draw: identity + position + decoded texture blocks."""

    identity: int           # SS:BP object-record address (stable table slot)
    sprite_id: int
    anim_phase: int
    screen_di: int          # the topmost on-screen destination slot
    slots: tuple[int, ...]  # all on-screen destination slots this draw targets
    source_ip: int          # the layer-draw routine (75A6/768E/7746)
    blocks: list[SpriteBlock] = field(default_factory=list)


@dataclass
class _Stats:
    high_calls: int = 0
    masked_blocks: int = 0
    unmodeled_blocks: int = 0
    orphan_blocks: int = 0
    orphan_dis: list[int] = field(default_factory=list)


class SpriteDrawCollector:
    """Installs draw-routine + compositor wrappers and accumulates frame sprites."""

    def __init__(self, registry) -> None:
        self._registry = registry
        self._wrapped: list[tuple[object, object]] = []
        self._current: CapturedSprite | None = None
        self._sprites: list[CapturedSprite] = []
        self.stats = _Stats()

    # -- lifecycle ---------------------------------------------------------
    def install(self) -> None:
        for ip, slot_offsets in LAYER_DRAW_ROUTINES.items():
            self._wrap(ip, self._make_high_hook(ip, slot_offsets))
        for ip in MASKED_COMPOSITORS:
            self._wrap(ip, self._make_comp_hook(ip))

    def uninstall(self) -> None:
        for rep, orig in self._wrapped:
            object.__setattr__(rep, "handler", orig)
        self._wrapped.clear()

    def take_frame(self) -> list[CapturedSprite]:
        """Return the sprites drawn since the last call and reset for the next frame.

        ``_current`` is intentionally NOT cleared: a draw routine always sets it
        before its compositor blocks fire, so it is never stale when a block
        arrives; clearing it at this (publish-time) boundary would strand a block
        whose draw pass straddles the present point under the double buffer."""
        out = [s for s in self._sprites if s.blocks]
        for spr in out:
            if spr.screen_di == OFFSCREEN_DESTINATION:
                # anchor +0C is off the top (e.g. a tiled object): use the topmost block
                spr.screen_di = min(b.di for b in spr.blocks)
        self._sprites = []
        return out

    # -- internals ---------------------------------------------------------
    def _wrap(self, ip: int, hook) -> None:
        try:
            rep = self._registry.replacements[(CS, ip)]
        except KeyError:
            return
        orig = rep.handler

        def wrapper(cpu, _orig=orig, _hook=hook):
            _hook(cpu, _orig)

        object.__setattr__(rep, "handler", wrapper)
        self._wrapped.append((rep, orig))

    def _make_high_hook(self, ip: int, slot_offsets: tuple[int, ...]):
        def hook(cpu, orig):
            ss, bp = cpu.s.ss & 0xFFFF, cpu.s.bp & 0xFFFF
            slots = tuple(
                di for off in slot_offsets
                if (di := cpu.mem.rw(ss, (bp + off) & 0xFFFF)) != OFFSCREEN_DESTINATION
            )
            self.stats.high_calls += 1
            # Always set the object context: a single-slot routine with a culled
            # anchor draws nothing (its sprite stays empty -> dropped), but a tiled
            # routine (3657) can still emit blocks with the anchor +0C == FFFF, and
            # those blocks must attribute to this object, not orphan.
            spr = CapturedSprite(
                identity=bp,
                sprite_id=cpu.mem.rw(ss, (bp + OBJ_SPRITE_INDEX) & 0xFFFF),
                anim_phase=cpu.mem.rw(ss, (bp + OBJ_ANIMATION_PHASE) & 0xFFFF),
                screen_di=slots[0] if slots else OFFSCREEN_DESTINATION,
                slots=slots,
                source_ip=ip,
            )
            self._current = spr
            self._sprites.append(spr)
            orig(cpu)
        return hook

    def _make_comp_hook(self, ip: int):
        from dos_re.cpu import DF
        wpr, _row_add, fixed_rows = MASKED_COMPOSITORS[ip]

        def hook(cpu, orig):
            s = cpu.s
            rows = fixed_rows if fixed_rows is not None else (s.cx & 0xFFFF) or 0x10000
            forward = not (s.flags & DF)
            ds, si, di = s.ds & 0xFFFF, s.si & 0xFFFF, s.di & 0xFFFF
            captured = None
            if forward and self._current is not None:
                base = (ds << 4) & 0xFFFFF
                src = bytes(cpu.mem.data[base + si: base + si + wpr * rows * 4])
                captured = SpriteBlock(di=di, compositor_ip=ip,
                                       texture=decode_masked_sprite(src, wpr, rows))
            orig(cpu)
            if captured is not None:
                self._current.blocks.append(captured)
                self.stats.masked_blocks += 1
            elif self._current is None:
                self.stats.orphan_blocks += 1
                if len(self.stats.orphan_dis) < 32:
                    self.stats.orphan_dis.append(di)
        return hook
