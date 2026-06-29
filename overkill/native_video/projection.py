"""Pure recovered object screen-di projection (Tandy), from 1010:30D2.

The per-object draw routes through ``5AC8`` (draw-type dispatch) → ``5A36``
(video-mode dispatch) → ``30D2`` (the Tandy projection), which computes the object's
destination offset into the composited page as::

    di = (obj_y >> 1) + column_di           where column_di = DS:99C8[obj_x]

with a cull (no draw) when ``obj_x >= 0xE0`` or the column entry is ``FFFFh``.  The
``DS:99C8`` word table is the scroll-dependent per-column base offset (the X axis is a
*table lookup*, not arithmetic — which is why a naive camera-relative derive fails).
The draw handler then adds ``DS:234C`` (the present scroll) to land the slot ``+0C``.

Pure: no ``cpu``/``mem``.  The caller supplies ``column_di`` from the live/native column
table; this owns the projection arithmetic + cull, so the native sprite layer can place
objects from ``NativeGameState`` instead of reading the VM's ``+0C``.
"""
from __future__ import annotations

PROJECTION_X_CULL = 0x00E0   # 30D5: CMP BX,00E0h / JB -> off-screen X cull
PROJECTION_CULL_ENTRY = 0xFFFF  # 30E4: CMP BX,FFFFh column-table cull sentinel


def project_object_to_di(obj_x: int, obj_y: int, column_di: int) -> int | None:
    """Project an object to its composited-page di per 1010:30D2.

    ``column_di`` is the ``DS:99C8`` entry for ``obj_x`` (the per-column base).  Returns
    the di ``(obj_y >> 1) + column_di`` (16-bit), or ``None`` when culled (``obj_x`` past
    the right edge, or the column entry is the ``FFFFh`` off-screen sentinel).
    """
    if (obj_x & 0xFFFF) >= PROJECTION_X_CULL or (column_di & 0xFFFF) == PROJECTION_CULL_ENTRY:
        return None
    return (((obj_y & 0xFFFF) >> 1) + (column_di & 0xFFFF)) & 0xFFFF


def project_object_screen_di(obj_x: int, obj_y: int, column_di: int, scroll: int) -> int | None:
    """Project an object to its final slot ``+0C`` screen-di per the 1010:35CC draw handler.

    35CC writes ``+0C`` from the 30D2 core projection, then -- when not culled -- adds the
    present scroll cursor ``DS:234C`` and rewrites ``+0C`` (the ASM is ``35CF mov [bp+0C],ax``
    / ``35D8 add ax,ds:[234C]`` / ``35DC mov [bp+0C],ax``)::

        +0C = (project_object_to_di(obj_x, obj_y, column_di) + DS:234C) & 0xFFFF

    Returns that final di, or ``None`` when the object culls (30D2 jumps to 25B2 and ``+0C``
    is left as the ``FFFFh`` off-screen sentinel).  ``scroll`` is the live ``DS:234C`` cursor.
    This is exactly the value ``frame_snapshot_adapter`` reads from the slot ``+0C`` as
    ``screen_di``; computing it here lets the native sprite layer place objects from
    ``NativeGameState`` without reading the VM's ``+0C``.
    """
    core = project_object_to_di(obj_x, obj_y, column_di)
    if core is None:
        return None
    return (core + (scroll & 0xFFFF)) & 0xFFFF


def build_native_sprite_layer(objects, column_table, scroll) -> tuple:
    """Compose the native sprite draw list from recovered state (Bucket C).

    Projects each active object through the recovered draw projection
    (:func:`project_object_screen_di`) using ``column_table`` (the DS:99C8 per-column base,
    indexed by object X; the static 0F0B-built table) and ``scroll`` (the present cursor
    ``DS:234C``), dropping culled (off-screen) objects.  ``objects`` is an iterable of
    ``(sprite, x, y)`` from ``NativeGameState``'s pool; returns ``((sprite, di), ...)``
    where ``di`` is the slot ``+0C`` the backend blits via ``composite_sprites`` --
    *computed* from recovered state rather than read from the VM's ``+0C``.
    """
    out = []
    n = len(column_table)
    for sprite, x, y in objects:
        col = column_table[x] if 0 <= x < n else PROJECTION_CULL_ENTRY
        di = project_object_screen_di(x, y, col, scroll)
        if di is not None:
            out.append((sprite, di))
    return tuple(out)
