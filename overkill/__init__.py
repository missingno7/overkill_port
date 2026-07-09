"""OVERKILL native source port.

PyPy-proof ``dos_re`` resolution (see ``dos_re/docs/performance.md`` §1): CPython finds the
framework through its pip *editable* install, but any interpreter without that install -- PyPy,
which is the fast path for long headless oracle runs (13-17x interpretation) -- must resolve
``dos_re`` through the submodule's own repo root.  Every entry point that imports ``overkill``
(probes, scripts, tests) therefore gets it here, once, instead of each file repeating the header.

The insert is idempotent and only prepends a path that actually exists, so a checkout without the
submodule (or an environment that already resolves ``dos_re``) is unaffected.
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parents[1]
for _p in (_ROOT, _ROOT / "dos_re"):
    _s = str(_p)
    if _p.is_dir() and _s not in _sys.path:
        _sys.path.insert(0, _s)
