"""Frame-accurate translation of physical key events into scan-code delivery.

OVERKILL polls its key-state table once per rendered frame (see the poller at
1010:017E).  A key therefore has to be *held down for at least one full frame* to
be observed.  A quick tap can deliver its press and release between two frames; if
both are applied before the frame runs, the key is set and cleared before the
game ever polls it and the press is silently lost -- which is why a single tap on
the menu's FIRE key did nothing.

``KeyDispatcher`` sits between the UI (which posts raw key up/down events from any
thread) and the interpreter (which calls :meth:`pump` once per frame).  It
delivers a make code as soon as a key goes down and defers the matching break
until the key has been held for at least one frame, so every tap is seen.
"""
from __future__ import annotations

import collections
from typing import Callable


class KeyDispatcher:
    def __init__(self, deliver: Callable[[int], None]) -> None:
        # ``deliver`` is called with an XT scan code (make, or make|0x80 for break).
        self._deliver = deliver
        self._events: "collections.deque[tuple[str, int]]" = collections.deque()
        self._down: dict[int, int] = {}   # scancode -> frames held so far
        self._release: set[int] = set()   # scancodes with a release pending

    # Posted from the UI thread; deque ops are atomic under the GIL.
    def post_down(self, scancode: int) -> None:
        self._events.append(("down", scancode & 0xFF))

    def post_up(self, scancode: int) -> None:
        self._events.append(("up", scancode & 0xFF))

    def pump(self) -> None:
        """Apply queued events for one frame.  Call before running the frame."""
        while self._events:
            kind, sc = self._events.popleft()
            if kind == "down":
                self._release.discard(sc)      # a re-press cancels a pending release
                if sc not in self._down:
                    self._deliver(sc)          # make code
                    self._down[sc] = 0
            else:
                self._release.add(sc)
        # Only release keys that have already been held for a full frame.
        for sc in list(self._release):
            if self._down.get(sc, -1) >= 1:
                self._deliver(sc | 0x80)       # break code
                self._down.pop(sc, None)
                self._release.discard(sc)
        for sc in self._down:
            self._down[sc] += 1
