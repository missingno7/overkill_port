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

from overkill.coverage import ISLANDS as COVERAGE_ISLANDS, OverkillCoverageClassifier  # noqa: E402
from overkill.verification import DEFAULT_STOPS  # noqa: E402
from dos_re.hooks import registry  # noqa: E402
from overkill.frontier_manifest import FRONTIER_BY_ADDR, frontier_summary_lines  # noqa: E402
import overkill.hooks  # noqa: F401,E402  # registers hooks

Addr = tuple[int, int]

@dataclass(frozen=True)
class Island:
    key: str
    title: str
    module_paths: tuple[Path, ...]

ISLANDS: tuple[Island, ...] = (
    Island("asset_codecs", "asset loading / non-overlay codecs", (
        ROOT / "overkill/asset_codecs/asset_table.py",
        ROOT / "overkill/asset_codecs/checksum.py",
        ROOT / "overkill/asset_codecs/lz.py",
        ROOT / "overkill/asset_codecs/packed_stream.py",
        ROOT / "overkill/asset_codecs/rle.py",
    )),
    Island("overlay", "overlay directory / overlay decode helpers", (
        ROOT / "overkill/asset_codecs/overlay.py",
    )),
    Island("file_io", "file I/O and overlay/container parent loaders", (
        ROOT / "overkill/file_io/overlay_loader.py",
    )),
    Island("bootstrap", "transient unpack/self-relocation bootstrap", ()),
    Island("startup_graphics", "startup graphics / renderer table materialization", (
        ROOT / "overkill/rendering/startup_graphics.py",
        ROOT / "overkill/rendering/tandy.py",
    )),
    Island("coordinates", "coordinate/address helpers", (
        ROOT / "overkill/rendering/coordinates.py",
    )),
    Island("layer_sprites", "shared layer sprite dispatch / presence lists", (
        ROOT / "overkill/rendering/layer_sprites.py",
    )),
    Island("tandy_renderer", "Tandy-specific rendering primitives", (
        ROOT / "overkill/rendering/tandy.py",
    )),
    Island("cga_renderer", "CGA / packed-row rendering primitives", (
        ROOT / "overkill/hooks.py",
    )),
    Island("ega_renderer", "EGA planar rendering primitives", (
        ROOT / "overkill/rendering/ega.py",
        ROOT / "overkill/hooks.py",
    )),
    Island("game_state", "per-frame game-state counters and orchestration", (
        ROOT / "overkill/gameplay/game_state.py",
        ROOT / "overkill/gameplay/frame_orchestration.py",
    )),
    Island("gameplay_objects", "runtime object slot behavior and dispatch", (
        ROOT / "overkill/gameplay/object_runtime.py",
        ROOT / "overkill/gameplay/objects.py",
    )),
    Island("movement", "movement helpers", (
        ROOT / "overkill/hooks.py",
    )),
    Island("collision", "tile/object collision and contact helpers", (
        ROOT / "overkill/gameplay/collision.py",
    )),
    Island("input_menu", "input/menu/prompt/pacing helpers", (
        ROOT / "overkill/input_menu.py",
    )),
    Island("sound", "timer IRQ / PC speaker sound effects", (
        ROOT / "overkill/sounds/pc_speaker.py",
        ROOT / "overkill/sounds/timing.py",
        ROOT / "overkill/sounds/_asm.py",
    )),
    Island("sound_driver_blob", "loaded optional AdLib/Roland driver blob (non-gameplay)", (
        ROOT / "overkill/sounds/loaded_driver.py",
        ROOT / "overkill/sounds/adlib_driver.py",
    )),
    Island("unknown", "unclassified", ()),
)

ISLAND_MAP = {island.key: island for island in ISLANDS}

# Keep the tool honest if coverage.py gains/removes a dashboard island.
missing_in_audit = set(COVERAGE_ISLANDS) - set(ISLAND_MAP)
if missing_in_audit:
    raise RuntimeError(f"audit_islands.py missing coverage islands: {sorted(missing_in_audit)}")


def fmt_addr(addr: Addr) -> str:
    return f"{addr[0]:04X}:{addr[1]:04X}"


def parse_addr(text: str) -> Addr:
    cs, ip = text.split(":")
    return int(cs, 16), int(ip, 16)


def load_text(paths: list[Path]) -> str:
    chunks: list[str] = []
    for path in paths:
        if path.exists():
            chunks.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(chunks)


def test_mentions_for(addr: Addr, names: tuple[str, ...], tests_text: str) -> list[str]:
    needles = {fmt_addr(addr), f"0x{addr[1]:04X}", f"0x{addr[1]:04x}", f"{addr[0]:04X}, 0x{addr[1]:04X}"}
    needles.update(n for n in names if n)
    return sorted(n for n in needles if n and n in tests_text)


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
        if not path.exists() or path.name == "hooks.py":
            continue
        rel = path.relative_to(ROOT)
        for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            lowered = line.lower()
            if any(p.lower() in lowered for p in patterns):
                seams.append(f"{rel}:{lineno}: {line.strip()}")
    return seams


def import_seams() -> list[str]:
    """Report obvious lower->higher island imports inside game modules."""
    order = {
        "asm": 0,
        "asset_codecs": 1,
        "overlay": 1,
        "file_io": 2,
        "startup_graphics": 2,
        "coordinates": 2,
        "layer_sprites": 3,
        "tandy_renderer": 3,
        "cga_renderer": 3,
        "ega_renderer": 3,
        "game_state": 4,
        "movement": 4,
        "collision": 4,
        "gameplay_objects": 4,
        "input_menu": 4,
        "sound": 4,
    }
    # Currently this is intentionally conservative; it flags only game modules
    # that import from an obviously higher conceptual directory.
    seams: list[str] = []
    for path in (ROOT / "overkill").rglob("*.py"):
        rel = path.relative_to(ROOT)
        text = path.read_text(encoding="utf-8", errors="replace")
        if "overkill.gameplay" in text and "asset_codecs" in str(rel):
            seams.append(f"{rel}: asset codec imports gameplay layer")
        if "overkill.rendering" in text and "asset_codecs" in str(rel):
            seams.append(f"{rel}: asset codec imports rendering layer")
        if "overkill.gameplay" in text and "rendering" in str(rel):
            seams.append(f"{rel}: rendering imports gameplay layer")
    return seams


def build_report(trace_path: Path | None = None) -> dict[str, Any]:
    tests_text = load_text(list((ROOT / "tests").glob("test_*.py")))
    symbols_path = ROOT / "symbols.json"
    symbols = json.loads(symbols_path.read_text(encoding="utf-8")) if symbols_path.exists() else {}
    classifier = OverkillCoverageClassifier(symbols_path)
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
        island_key = classifier.classify(addr, repl.name)
        info = by_island[island_key]
        item = {"addr": fmt_addr(addr), "name": repl.name}
        item["has_verifier_metadata"] = addr in DEFAULT_STOPS
        item["test_mentions"] = test_mentions_for(addr, (repl.name, repl.handler.__name__), tests_text)
        item["seen_in_trace"] = addr in trace_seen
        info["hooks"].append(item)
        if not item["has_verifier_metadata"]:
            info["missing_verifier_metadata"].append(item["addr"])
        if not item["test_mentions"]:
            info["missing_test_mentions"].append(item["addr"])
        if item["seen_in_trace"]:
            info["trace_hits"].append(item["addr"])

    for addr_text, value in symbols.items():
        try:
            addr = parse_addr(addr_text)
        except Exception:
            continue
        island_key = classifier.classify(addr)
        if island_key == "unknown":
            continue
        text = json.dumps(value, sort_keys=True) if not isinstance(value, str) else value
        if any(word in text.lower() for word in ("candidate", "frontier", "unverified", "fallback")):
            if addr in FRONTIER_BY_ADDR:
                by_island[island_key].setdefault("manifest_reviewed_symbols", []).append(addr_text)
            else:
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
        info["blockers"] = blockers
        info["status"] = "closed-candidate" if info["hooks"] and not blockers else ("classified" if island_key == "bootstrap" else "open")
    by_island["_import_seams"] = {"items": import_seams()}
    by_island["_frontier_manifest"] = {"items": frontier_summary_lines()}
    return by_island


def print_report(report: dict[str, Any], *, all_hooks: bool = False) -> None:
    manifest_lines = report.pop("_frontier_manifest", {"items": []})["items"]
    if manifest_lines:
        print()
        for item in manifest_lines:
            print(item)

    import_seams = report.pop("_import_seams", {"items": []})["items"]
    if import_seams:
        print("\n== import seams ==")
        for item in import_seams:
            print(f"  - {item}")

    for island in ISLANDS:
        info = report[island.key]
        print(f"\n== {info['title']} ({island.key}) ==")
        print(f"status: {info['status']}  hooks: {len(info['hooks'])}")
        if info["blockers"]:
            print("blockers:")
            for blocker in info["blockers"]:
                print(f"  - {blocker}")
        if info["missing_verifier_metadata"]:
            print("missing verifier metadata:", ", ".join(info["missing_verifier_metadata"]))
        if info["missing_test_mentions"]:
            print("missing test mentions:", ", ".join(info["missing_test_mentions"][:20]))
            if len(info["missing_test_mentions"]) > 20:
                print(f"  ... +{len(info['missing_test_mentions']) - 20} more")
        if info["symbols_to_review"]:
            print("symbols to review:")
            for item in info["symbols_to_review"][:10]:
                print(f"  - {next(iter(item))} {next(iter(item.values()))}")
            if len(info["symbols_to_review"]) > 10:
                print(f"  ... +{len(info['symbols_to_review']) - 10} more")
        if info["module_seams"]:
            print("module seams:")
            for seam in info["module_seams"][:20]:
                print(f"  - {seam}")
            if len(info["module_seams"]) > 20:
                print(f"  ... +{len(info['module_seams']) - 20} more")
        if info["trace_hits"]:
            print("trace hits:", ", ".join(info["trace_hits"]))
        if all_hooks:
            print("hooks:")
            for hook in info["hooks"]:
                flags = []
                flags.append("meta" if hook["has_verifier_metadata"] else "no-meta")
                flags.append("tests" if hook["test_mentions"] else "no-tests")
                print(f"  - {hook['addr']} {hook['name']} [{', '.join(flags)}]")


def main() -> int:
    parser = argparse.ArgumentParser(description="Report closure signals for OVERKILL source-port islands.")
    parser.add_argument("--trace", type=Path, default=None, help="optional trace file to mark island hook addresses seen in execution")
    parser.add_argument("--all-hooks", action="store_true", help="show every hook assigned to each island")
    args = parser.parse_args()
    print_report(build_report(args.trace), all_hooks=args.all_hooks)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
