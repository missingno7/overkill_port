"""Canonical catalog of OVERKILL's cross-subsystem DS-segment global cells.

A handful of 16-bit data-segment locations are touched by more than one
subsystem (collision, movement, object behaviour, rendering).  Each subsystem's
adapter historically named the cell from its own point of view, so the same
physical address picked up two or three different names.  This module is the
single source of truth for those shared cells: one canonical name per address,
with the subsystem-specific interpretations recorded alongside.

The subsystem modules keep their local names as thin aliases
(``LOCAL = CANONICAL``) so existing call sites stay readable while the address
is defined exactly once here.  Because the alias equals the canonical value, the
per-hook oracle and demo-replay gates prove the consolidation changed nothing.

Single-subsystem DS globals are intentionally left local to their module: only
cells genuinely shared across subsystems belong in this catalog.
"""
from __future__ import annotations

# --- View / camera scroll target, reused as the contact reference box --------
# The camera scroll target (X, Y).  Collision's overlap test reads it as the
# reference-box origin (OVERLAP_REF_BOX_*); the post-move contact path reads it
# as the current view position (POSTMOVE_CONTACT_VIEW_X / _Y_GUARD).
VIEW_TARGET_X = 0x237E
VIEW_TARGET_Y = 0x2380

# --- Renderer / tile pipeline video-mode selector ----------------------------
# Mode byte consulted by both the coordinate transform and the layer-sprite path.
VIDEO_MODE_SELECTOR_OFF = 0x95BC

# --- Shared collision / boss-group debug gate --------------------------------
# Debug flag gating the same diagnostic path from the tile-collision and the
# boss-group sides (TILE_COLLISION_DEBUG_FLAG / BOSS_GROUP_DEBUG_FLAG), plus the
# companion code-address constant it compares against.
COLLISION_DEBUG_FLAG = 0x98C0
COLLISION_DEBUG_CODE = 0xBEFF

# --- Boss-group / final-boss contact-mode latch ------------------------------
# State latch read by the final-boss contact path (FINAL_BOSS_CONTACT_MODE) and
# written/read by the boss-group state machine (BOSS_GROUP_LATCH_GLOBAL).
BOSS_GROUP_LATCH = 0xA8C2

# --- Contact fan-out / tile-collision dispatch selector (the BEDC gate) -------
# Selector steering the contact dispatch (CONTACT_FANOUT_SELECTOR) and gating the
# tile-collision branch (TILE_COLLISION_BEDC_GATE).
CONTACT_DISPATCH_GATE = 0xBEDC
