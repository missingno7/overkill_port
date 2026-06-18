"""DOS-memory views for the recovered source layer (the translation layer).

Each module here is a *live* typed lens over the original OVERKILL memory image:
field reads/writes go straight to ``seg:base+offset`` in the VM, so the source-
like code mutates the real game state with no parallel/owned copy.  Views may
know original segment:offset layout, but must stay thin overlays -- no high-level
gameplay decisions live here (those belong in ``recovered/systems``).

Members (each introduced by a real live consumer, see ARCHITECTURE.md):

* :mod:`object_slots` -- ``ObjectSlotView`` (one 0x38-byte object/effect slot)
  and ``ObjectTableView`` (a whole effect/gameplay table of slot views).
* :mod:`frame_timers` -- ``FrameTimersView`` (the six ``DS:2368`` per-frame
  countdown counters scanned by 1010:61C7).
"""
