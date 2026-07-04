"""The flat DOS-image memory shape the recovered adapters read (and seed) -- plain bytes, no VM.

The recovered projections (``read_native_game_state``, the starfield reader, ...) take a ``mem``
object with the ``rb``/``rw`` read shape of ``dos_re.memory.Memory`` (byte/word reads at ``seg:off``).
When the source is a STATIC FILE -- the cold runtime bundle or a captured snapshot dump -- these
classes provide that shape over plain bytes: not an emulator, just ``seg*16 + off`` arithmetic over a
1 MiB image, so the recovered layer stays VM-free (no ``dos_re`` import anywhere near them).

* :class:`FlatMemory` -- read-only; for projecting state out of an image.
* :class:`MutFlatMemory` -- adds ``ww`` over a private ``bytearray`` copy; for applying recovered
  seed/write maps to an image and reading the result back through the same verified projections.

Consolidates the previously duplicated ``scripts/play_native._FlatMemory`` and
``adapters/cold_level_start._MutMem``.
"""
from __future__ import annotations


class FlatMemory:
    """A read-only flat 1 MiB image with the ``rb``/``rw`` reader shape (plain bytes, no VM)."""

    def __init__(self, data: bytes) -> None:
        self.data = data

    def _phys(self, seg: int, off: int) -> int:
        return ((seg & 0xFFFF) * 16 + (off & 0xFFFF)) & 0xFFFFF

    def rb(self, seg: int, off: int) -> int:
        return self.data[self._phys(seg, off)]

    def rw(self, seg: int, off: int) -> int:
        p = self._phys(seg, off)
        return self.data[p] | (self.data[(p + 1) & 0xFFFFF] << 8)


class MutFlatMemory(FlatMemory):
    """A mutable flat image (private ``bytearray`` copy) adding word writes (``ww``).

    Lets recovered seed maps be applied to a cold image and the result read back through the
    VM-verified projections exactly as if they had run on the real data segment.
    """

    def __init__(self, data: bytes) -> None:
        super().__init__(bytearray(data))

    def ww(self, seg: int, off: int, val: int) -> None:
        p = self._phys(seg, off)
        self.data[p] = val & 0xFF
        self.data[(p + 1) & 0xFFFFF] = (val >> 8) & 0xFF
