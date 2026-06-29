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
