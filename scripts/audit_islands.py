from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from overkill_port.hook_verify import DEFAULT_STOPS  # noqa: E402
from overkill_port.hooks import registry  # noqa: E402
import overkill_port.replacements  # noqa: F401,E402  # registers hooks


Addr = tuple[int, int]


@dataclass(frozen=True)
class Island:
    key: str
    title: str
    module_paths: tuple[Path, ...]


ISLANDS: tuple[Island, ...] = (
    Island(
        "asset_codecs",
        "asset loading / asset codecs / startup materialization",
        (
            ROOT / "overkill_port/games/overkill/asset_codecs/checksum.py",
            ROOT / "overkill_port/games/overkill/asset_codecs/lz.py",
            ROOT / "overkill_port/games/overkill/asset_codecs/packed_stream.py",
            ROOT / "overkill_port/games/overkill/asset_codecs/rle.py",
        ),
    ),
    Island(
        "overlay",
        "overlay loading / overlay decode / overlay directory scan",
        (ROOT / "overkill_port/games/overkill/asset_codecs/overlay.py",),
    ),
    Island(
        "startup_graphics",
        "startup graphics expansion",
        (
            ROOT / "overkill_port/games/overkill/asset_codecs/startup_graphics.py",
            ROOT / "overkill_port/games/overkill/rendering/tandy.py",
        ),
    ),
    Island(
        "coordinates",
        "coordinate/address helpers",
        (ROOT / "overkill_port/games/overkill/rendering/coordinates.py",),
    ),
    Island(
        "layer_sprites",
        "shared layer sprite dispatch",
        (ROOT / "overkill_port/games/overkill/rendering/layer_sprites.py",),
    ),
    Island(
        "tandy_rendering",
        "Tandy-specific rendering primitives",
        (ROOT / "overkill_port/games/overkill/rendering/tandy.py",),
    ),
)


STARTUP_GRAPHICS_ADDRS: set[Addr] = {
    (0x1010, 0x33B2),
    (0x1010, 0x33DD),
    (0x1010, 0x450C),
    (0x1010, 0x4511),
    (0x1010, 0x4537),
    (0x1010, 0x45CB),
    (0x1010, 0x45F6),
}

COORDINATE_ADDRS: set[Addr] = {
    (0x1010, 0x5A00),
    (0x1010, 0x5A24),
    (0x1010, 0x5A36),
}

LAYER_SPRITE_ADDRS: set[Addr] = {
    (0x1010, 0x75A6),
    (0x1010, 0x768E),
    (0x1010, 0x7746),
    (0x1010, 0xA87C),
    (0x1010, 0xA894),
    (0x1010, 0xA8C7),
}

TANDY_RENDER_ADDRS: set[Addr] = {
    (0x1010, 0x2E6E),
    (0x1010, 0x2ECB),
    (0x1010, 0x2F40),
    (0x1010, 0x2F81),
    (0x1010, 0x2FB6),
    (0x1010, 0x3354),
    (0x1010, 0x34AD),
    (0x1010, 0x34C5),
    (0x1010, 0x34D8),
    (0x1010, 0x3542),
    (0x1010, 0x356C),
    (0x1010, 0x3657),
    (0x1010, 0x35AA),
    (0x1010, 0x35CC),
    (0x1010, 0x375B),
}

ASSET_CODEC_NAME_RE = re.compile(
    r"(checksum|packed|lz_|lz_decoder|rle|vertical_rle|linear_byte_rle|output_byte|input_byte|backref)",
    re.IGNORECASE,
)


def fmt_addr(addr: Addr) -> str:
    return f"{addr[0]:04X}:{addr[1]:04X}"


def classify_hook(addr: Addr, name: str) -> str | None:
    lname = name.lower()
    if addr[0] == 0x254A or "overlay" in lname:
        return "overlay"
    if addr in STARTUP_GRAPHICS_ADDRS:
        return "startup_graphics"
    if addr in COORDINATE_ADDRS:
        return "coordinates"
    if addr in LAYER_SPRITE_ADDRS:
        return "layer_sprites"
    if addr in TANDY_RENDER_ADDRS:
        return "tandy_rendering"
    if ASSET_CODEC_NAME_RE.search(name):
        return "asset_codecs"
    return None


def classify_symbol(addr_text: str, value: Any) -> str | None:
    try:
        cs_s, ip_s = addr_text.split(":")
        addr = (int(cs_s, 16), int(ip_s, 16))
    except ValueError:
        return None
    text = json.dumps(value, sort_keys=True) if not isinstance(value, str) else value
    return classify_hook(addr, text)


def load_text(paths: list[Path]) -> str:
    chunks: list[str] = []
    for path in paths:
        if path.exists():
            chunks.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(chunks)


def test_mentions_for(addr: Addr, names: tuple[str, ...], tests_text: str) -> list[str]:
    needles = {fmt_addr(addr), f"0x{addr[1]:04X}", f"0x{addr[1]:04x}", f"{addr[0]:04X}, 0x{addr[1]:04X}"}
    needles.update(n for n in names if n)
    found = sorted(n for n in needles if n and n in tests_text)
    return found


def parse_trace(path: Path | None) -> set[Addr]:
    if path is None:
        return set()
    text = path.read_text(encoding="utf-8", errors="replace")
    out: set[Addr] = set()
    for match in re.finditer(r"\b([0-9A-Fa-f]{4}):([0-9A-Fa-f]{4})\b", text):
        out.add((int(match.group(1), 16), int(match.group(2), 16)))
    return out


def module_seams(island: Island) -> list[str]:
    patterns = (
        "KNOWN_ORIGINAL",
        "fail_unverified",
        "unverified",
        "candidate",
        "frontier",
        "bounded original",
        "_run_original",
    )
    seams: list[str] = []
    for path in island.module_paths:
        if not path.exists():
            continue
        rel = path.relative_to(ROOT)
        for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            lowered = line.lower()
            if any(p.lower() in lowered for p in patterns):
                seams.append(f"{rel}:{lineno}: {line.strip()}")
    return seams


def build_report(trace_path: Path | None = None) -> dict[str, Any]:
    tests_text = load_text(list((ROOT / "tests").glob("test_*.py")))
    symbols = json.loads((ROOT / "symbols.json").read_text(encoding="utf-8"))
    trace_seen = parse_trace(trace_path)

    by_island: dict[str, dict[str, Any]] = {
        island.key: {
            "title": island.title,
            "hooks": [],
            "missing_verifier_metadata": [],
            "missing_test_mentions": [],
            "symbols_to_review": [],
            "module_seams": module_seams(island),
            "trace_hits": [],
        }
        for island in ISLANDS
    }

    for addr, repl in sorted(registry.replacements.items()):
        island_key = classify_hook(addr, repl.name)
        if island_key is None:
            continue
        handler_name = getattr(repl.handler, "__name__", "")
        mentions = test_mentions_for(addr, (repl.name, handler_name), tests_text)
        item = {
            "addr": fmt_addr(addr),
            "name": repl.name,
            "handler": handler_name,
            "has_verifier_metadata": addr in DEFAULT_STOPS,
            "test_mentions": mentions,
            "trace_hit": addr in trace_seen if trace_path else None,
        }
        by_island[island_key]["hooks"].append(item)
        if addr not in DEFAULT_STOPS:
            by_island[island_key]["missing_verifier_metadata"].append(item["addr"])
        if not mentions:
            by_island[island_key]["missing_test_mentions"].append(item["addr"])
        if trace_path and addr in trace_seen:
            by_island[island_key]["trace_hits"].append(item["addr"])

    review_words = ("candidate", "frontier", "unverified", "fallback", "next target", "active investigation")
    for addr_text, value in symbols.items():
        island_key = classify_symbol(addr_text, value)
        if island_key is None:
            continue
        text = json.dumps(value, sort_keys=True).lower() if not isinstance(value, str) else value.lower()
        if any(word in text for word in review_words):
            by_island[island_key]["symbols_to_review"].append({addr_text: value})

    for island_key, info in by_island.items():
        blockers = []
        if info["missing_verifier_metadata"]:
            blockers.append("missing verifier metadata")
        if info["missing_test_mentions"]:
            blockers.append("missing obvious oracle/regression test mention")
        if info["symbols_to_review"]:
            blockers.append("symbols still marked candidate/frontier/unverified/fallback")
        if info["module_seams"]:
            blockers.append("module contains explicit seam markers")
        info["hook_count"] = len(info["hooks"])
        info["exhaustion_status"] = "closed-candidate" if not blockers else "open"
        info["blockers"] = blockers
    return by_island


def print_report(report: dict[str, Any], *, show_all_hooks: bool) -> None:
    for island_key, info in report.items():
        print(f"\n== {info['title']} ({island_key}) ==")
        print(f"status: {info['exhaustion_status']}  hooks: {info['hook_count']}")
        if info["blockers"]:
            print("blockers:")
            for blocker in info["blockers"]:
                print(f"  - {blocker}")
        if info["missing_verifier_metadata"]:
            print("missing verifier metadata:", ", ".join(info["missing_verifier_metadata"]))
        if info["missing_test_mentions"]:
            print("missing test mentions:", ", ".join(info["missing_test_mentions"]))
        if info["symbols_to_review"]:
            print("symbols to review:")
            for item in info["symbols_to_review"]:
                addr, value = next(iter(item.items()))
                if isinstance(value, dict):
                    label = value.get("name") or value.get("status") or ""
                    status = value.get("status", "")
                    print(f"  - {addr} {label} {status}".rstrip())
                else:
                    print(f"  - {addr} {value}")
        if info["module_seams"]:
            print("module seams:")
            for seam in info["module_seams"][:12]:
                print(f"  - {seam}")
            if len(info["module_seams"]) > 12:
                print(f"  - ... {len(info['module_seams']) - 12} more")
        if info["trace_hits"]:
            print("trace hits:", ", ".join(info["trace_hits"]))
        if show_all_hooks:
            print("hooks:")
            for hook in info["hooks"]:
                meta = "meta" if hook["has_verifier_metadata"] else "no-meta"
                tests = "tests" if hook["test_mentions"] else "no-tests"
                print(f"  - {hook['addr']} {hook['name']} [{meta}, {tests}]")


def main() -> int:
    parser = argparse.ArgumentParser(description="Report closure signals for existing OVERKILL source-port islands.")
    parser.add_argument("--trace", type=Path, default=None, help="optional trace file to mark island hook addresses seen in execution")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--all-hooks", action="store_true", help="show every hook assigned to each island")
    args = parser.parse_args()

    report = build_report(args.trace)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_report(report, show_all_hooks=args.all_hooks)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
