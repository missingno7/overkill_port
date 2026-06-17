"""OVERKILL gameplay-logic islands lifted out of the hook registry module.

Architecture layer: **lifted** (see ``ARCHITECTURE.md``).  VM-aware Python that
reproduces original behaviour on the original memory layout.  May depend on the
``recovered`` domain/bridge and backend *constants*; backend code must not
depend on this package, and the pure ``recovered.domain``/``game_core`` layers
must never be pulled back into the VM through here.
"""
