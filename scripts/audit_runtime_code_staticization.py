#!/usr/bin/env python
"""Audit OVERKILL runtime-code slots and their static source-port owners.

Runtime self-modifying code must not survive as runtime self-modifying Python.
Each accepted runtime-installed byte body should be named as a variant and mapped
onto a flat, verified Python implementation.  This script is the lightweight gate
for that policy.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from overkill.runtime_code import (  # noqa: E402
    RuntimeCodeStaticizationError,
    assert_runtime_code_staticization_ready,
    runtime_code_staticization_report,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--strict-installers",
        action="store_true",
        help="Also require installer/writer provenance before declaring a slot complete.",
    )
    p.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero when the selected completeness gate fails.",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    rows = runtime_code_staticization_report(strict_installers=args.strict_installers)
    print("Runtime-code staticization audit")
    print("================================")
    print(
        f"{'addr':>9}  {'island':<14} {'static':<6} {'installer':<22} "
        f"{'slot':<36} target"
    )
    for row in rows:
        static = "yes" if row["staticized"] and not row["missing"] else "no"
        target = row["static_target"] or "-"
        if row["missing"]:
            target += "  MISSING: " + ", ".join(row["missing"])
        print(
            f"{row['addr']:>9}  {row['island']:<14} {static:<6} "
            f"{row['installer_status']:<22} {row['slot']:<36} {target}"
        )
        print(f"           variants: {', '.join(row['all_variants'])}")
        if row["accepted_variants"]:
            print(f"           accepted: {', '.join(row['accepted_variants'])}")
    if args.check:
        try:
            assert_runtime_code_staticization_ready(strict_installers=args.strict_installers)
        except RuntimeCodeStaticizationError as exc:
            print()
            print(exc)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
