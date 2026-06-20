"""Regenerate ``docs/overkill/recovered_islands.md`` from the in-code metadata.

The manifest is *generated*, never hand-edited: the source of truth is the
``@recovered_island`` metadata on each pure recovered function.  Run this after
adding or changing an island; ``tests/test_island_registry.py`` fails if the
checked-in manifest drifts from the code.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from overkill.recovered.islands import MANIFEST_PATH, render_manifest  # noqa: E402


def main() -> int:
    MANIFEST_PATH.write_text(render_manifest(), encoding="utf-8", newline="\n")
    print(f"wrote {MANIFEST_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
