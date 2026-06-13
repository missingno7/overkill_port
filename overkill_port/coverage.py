from __future__ import annotations

import json
import re
import threading
import time
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

Addr = tuple[int, int]

COVERAGE_STATES = (
    "HOOKED_VERIFIED",
    "HOOKED_UNVERIFIED",
    "BOUNDED_ORIGINAL",
    "INTERPRETED_ASM",
    "UNKNOWN",
)

ISLANDS = (
    "asset_codecs",
    "overlay",
    "file_io",
    "bootstrap",
    "startup_graphics",
    "coordinates",
    "layer_sprites",
    "tandy_renderer",
    "cga_renderer",
    "ega_renderer",
    "game_state",
    "gameplay_objects",
    "movement",
    "collision",
    "input_menu",
    "sound",
    "unknown",
)


def fmt_addr(addr: Addr) -> str:
    return f"{addr[0]:04X}:{addr[1]:04X}"


def parse_addr(text: str) -> Addr:
    cs, ip = text.split(":", 1)
    return int(cs, 16) & 0xFFFF, int(ip, 16) & 0xFFFF


@dataclass
class HookCoverageStats:
    addr: Addr
    name: str
    island: str
    calls: int = 0
    verified_calls: int = 0
    unverified_calls: int = 0
    skipped_calls: int = 0
    asm_equiv_instructions: int = 0
    estimated_asm_equiv_instructions: int = 0
    unmeasured_calls: int = 0
    last_asm_equiv: int = 0

    @property
    def total_equiv(self) -> int:
        return self.asm_equiv_instructions + self.estimated_asm_equiv_instructions


@dataclass
class IslandCoverageStats:
    interpreted_asm: int = 0
    bounded_original: int = 0
    hooked_verified_equiv: int = 0
    hooked_estimated_equiv: int = 0
    hooked_unverified_calls: int = 0
    unmeasured_hook_calls: int = 0
    hook_calls: int = 0
    verified_hook_calls: int = 0
    skipped_hook_calls: int = 0


class OverkillCoverageClassifier:
    """OVERKILL-specific island classifier kept outside the generic CPU.

    It intentionally uses hook names, symbol labels and coarse address ranges;
    it does not affect emulation logic.  Unknown addresses remain explicit so the
    dashboard can point at the next island to close.
    """

    _asset_re = re.compile(
        r"(asset|codec|packed|lz|rle|decoder|encode|decode|expand|startup|loading|checksum|input_byte|output_byte)",
        re.IGNORECASE,
    )
    _overlay_re = re.compile(r"(\boverlay\b|overlay_directory|overlay_signature|entry_name|path_normalizer|xor_decode)", re.IGNORECASE)
    _file_io_re = re.compile(r"(file_io|file[-_ ]?i/o|overlay_container_open|container_open|open_entry|lseek|seek)", re.IGNORECASE)
    _coord_re = re.compile(r"(coord|coordinate|row_addr|column|address)", re.IGNORECASE)
    _layer_re = re.compile(r"(layer|sprite_dispatch|scan_draw|scan_present|scan_layer)", re.IGNORECASE)
    _tandy_re = re.compile(r"(tandy|pcjr)", re.IGNORECASE)
    _cga_re = re.compile(r"\bcga\b", re.IGNORECASE)
    _ega_re = re.compile(r"\bega\b|4plane|plane", re.IGNORECASE)
    _game_state_re = re.compile(r"(game_state|gameplay_counter|frame[-_ ]?state|per[-_ ]?frame)", re.IGNORECASE)
    _obj_re = re.compile(r"(object|enemy|boss|projectile|formation|reward|pickup|behavior|behaviour)", re.IGNORECASE)
    _move_re = re.compile(r"(move|movement|velocity|direction|scroll|camera)", re.IGNORECASE)
    _collision_re = re.compile(r"(collision|collide|contact|hitbox|masked|mask)", re.IGNORECASE)
    _sound_re = re.compile(r"(sound|speaker|pc_speaker|timer_isr|irq0|pit|audio)", re.IGNORECASE)
    _input_re = re.compile(r"(input|keyboard|key|menu|prompt|confirm|\besc\b|sure)", re.IGNORECASE)
    _bootstrap_re = re.compile(r"(bootstrap|unpack|relocation|self[-_ ]?relocat|loader stub)", re.IGNORECASE)

    OVERLAY_ADDRS: set[Addr] = {
        (0x254A, 0x0582), (0x254A, 0x05A1), (0x254A, 0x05BF),
        (0x254A, 0x05D9), (0x254A, 0x0701),
    }
    FILE_IO_ADDRS: set[Addr] = {
        (0x254A, 0x04D7),
    }
    STARTUP_GRAPHICS_ADDRS: set[Addr] = {
        (0x1010, 0x0F0B), (0x1010, 0x0FA3), (0x1010, 0x0FE4),
        (0x1010, 0x33AF), (0x1010, 0x33B2), (0x1010, 0x33DD),
        (0x1010, 0x450C), (0x1010, 0x4511), (0x1010, 0x4537),
        (0x1010, 0x45CB), (0x1010, 0x45F6),
    }
    BOOTSTRAP_SEGMENTS: set[int] = {
        # Runtime-allocated inner unpack/self-relocation bootstrap segment seen
        # during cold start.  It is useful to classify it away from `unknown`,
        # but it is not a durable game-module island and should not be hooked
        # just to reduce interpreted-instruction counts.
        0x32FF,
    }
    COORDINATE_ADDRS: set[Addr] = {
        (0x1010, 0x5A00), (0x1010, 0x5A24), (0x1010, 0x5A36),
    }
    LAYER_SPRITE_ADDRS: set[Addr] = {
        (0x1010, 0x75A6), (0x1010, 0x768E), (0x1010, 0x7746),
        (0x1010, 0x7596),
        # Presence/occupancy-list helpers are shared by CGA, EGA, and Tandy
        # layer/object rendering.  They used to be labelled as CGA because the
        # first investigated caller was mode 0, but mode 2 gameplay calls them
        # too.
        (0x1010, 0x4CED), (0x1010, 0x4CF2), (0x1010, 0x4CF5), (0x1010, 0x4CF8),
        (0x1010, 0x4CFB), (0x1010, 0x4CFE), (0x1010, 0x4D01), (0x1010, 0x4D04),
        (0x1010, 0x4D07), (0x1010, 0x4D0A), (0x1010, 0x4D0D), (0x1010, 0x4D10),
        (0x1010, 0x4D14), (0x1010, 0x4D15),
        (0x1010, 0x4D64), (0x1010, 0x4D69), (0x1010, 0x4D6C), (0x1010, 0x4D6F),
        (0x1010, 0x511F),
        (0x1010, 0x5A6C),
        (0x1010, 0xA846),
        (0x1010, 0xA849), (0x1010, 0xA858), (0x1010, 0xA85B), (0x1010, 0xA85C),
        (0x1010, 0xA85E),
        (0x1010, 0xA861), (0x1010, 0xA870), (0x1010, 0xA873), (0x1010, 0xA874),
        (0x1010, 0xA876),
        (0x1010, 0xA87C), (0x1010, 0xA88B), (0x1010, 0xA88E), (0x1010, 0xA88F),
        (0x1010, 0xA894), (0x1010, 0xA8BE), (0x1010, 0xA8C1), (0x1010, 0xA8C4),
        (0x1010, 0xA8C7), (0x1010, 0xA8F1), (0x1010, 0xA8F4), (0x1010, 0xA8F5),
        (0x1010, 0xA90C),
        (0x1010, 0xA90F), (0x1010, 0xA91E), (0x1010, 0xA921), (0x1010, 0xA922),
        (0x1010, 0xA924), (0x1010, 0xA927), (0x1010, 0xA936), (0x1010, 0xA939),
        (0x1010, 0xA93A), (0x1010, 0xA93C), (0x1010, 0xA93F),
    }
    TANDY_RENDER_ADDRS: set[Addr] = {
        (0x1010, 0x2E6E), (0x1010, 0x2ECB), (0x1010, 0x2F40),
        (0x1010, 0x2F81), (0x1010, 0x2FB6), (0x1010, 0x306F),
        (0x1010, 0x30B0), (0x1010, 0x30BA),
        (0x1010, 0x3153), (0x1010, 0x519A), (0x1010, 0x5F06),
        (0x1010, 0x3354), (0x1010, 0x34AD),
        (0x1010, 0x34C5), (0x1010, 0x34D8), (0x1010, 0x3542),
        (0x1010, 0x356C), (0x1010, 0x36A2), (0x1010, 0x3657),
        (0x1010, 0x35AA), (0x1010, 0x35CC), (0x1010, 0x375B),
        (0x1010, 0x4E0D), (0x1010, 0x4E0E), (0x1010, 0x4E0F),
        (0x1010, 0xA781), (0x1010, 0xA782), (0x1010, 0xA788), (0x1010, 0xA78D),
        (0x1010, 0xA78F), (0x1010, 0xA794), (0x1010, 0xA799), (0x1010, 0xA79E),
        (0x1010, 0xA7A2), (0x1010, 0xA7A8), (0x1010, 0xA7AD), (0x1010, 0xA7B2),
        (0x1010, 0xCC7F), (0x1010, 0xCCAA), (0x1010, 0xCCC4), (0x1010, 0xCCF0),
        (0x1010, 0xCD68), (0x1010, 0xCD69), (0x1010, 0xCD6D), (0x1010, 0xCD72),
        (0x1010, 0xCD77), (0x1010, 0xCD7C), (0x1010, 0xCD7E), (0x1010, 0xCDA7),
        (0x1010, 0xCE02), (0x1010, 0xCE07), (0x1010, 0xCE0B), (0x1010, 0xCE0C),
        (0x1010, 0xCE10), (0x1010, 0xCE13),
    }
    CGA_RENDER_ADDRS: set[Addr] = {
        (0x1010, 0x3849), (0x1010, 0x387C), (0x1010, 0x38B7),
        (0x1010, 0x38D6), (0x1010, 0x38F9), (0x1010, 0x390E),
        (0x1010, 0x3E12), (0x1010, 0x3EE1), (0x1010, 0x3EFB),
        (0x1010, 0x3EFC), (0x1010, 0x41A6), (0x1010, 0x41DA),
        (0x1010, 0x447B), (0x1010, 0x469F), (0x1010, 0x477E),
        (0x1010, 0x497A), (0x1010, 0x58DF), (0x1010, 0xCD8D),
    }
    EGA_RENDER_ADDRS: set[Addr] = {
        (0x1010, 0x103C), (0x1010, 0x10B7),
        (0x1010, 0x13E7), (0x1010, 0x1AEB), (0x1010, 0x1D1B),
        (0x1010, 0x2193), (0x1010, 0x21D6), (0x1010, 0x2223),
        (0x1010, 0x2285), (0x1010, 0x22FC), (0x1010, 0x238D),
        (0x1010, 0x2410), (0x1010, 0x247E), (0x1010, 0x2750),
        (0x1010, 0x27EB), (0x1010, 0x280D), (0x1010, 0x2824),
        (0x1010, 0x291C), (0x1010, 0x2932), (0x1010, 0x29C6),
        (0x1010, 0x2AB9), (0x1010, 0x409D), (0x1010, 0x40D7),
        (0x1010, 0x412B),
    }
    GAME_STATE_ADDRS: set[Addr] = {
        (0x1F8F, 0x0922), (0x1F8F, 0x0960), (0x1F8F, 0x0927), (0x1F8F, 0x0929), (0x1F8F, 0x092D),
        (0x1F8F, 0x0932), (0x1F8F, 0x0934), (0x1F8F, 0x0937), (0x1F8F, 0x093A),
        (0x1F8F, 0x093D), (0x1F8F, 0x0941), (0x1F8F, 0x0946), (0x1F8F, 0x0948),
        (0x1F8F, 0x094B), (0x1F8F, 0x094E), (0x1F8F, 0x0952), (0x1F8F, 0x0957),
        (0x1F8F, 0x0959), (0x1F8F, 0x095C), (0x1F8F, 0x095F),
        (0x1010, 0x61C5), (0x1010, 0x61C8), (0x1010, 0x61CA), (0x1010, 0x61CD),
        (0x1010, 0x61D0), (0x1010, 0x61D2), (0x1010, 0x61D5), (0x1010, 0x61D9),
        (0x1010, 0xA940), (0x1010, 0xA945), (0x1010, 0xA947), (0x1010, 0xA94B),
        (0x1010, 0xA94E), (0x1010, 0xA951), (0x1010, 0xA954), (0x1010, 0xA957),
        (0x1010, 0xA95D), (0x1010, 0xA962), (0x1010, 0xA964), (0x1010, 0xA969),
        (0x1010, 0xA96B), (0x1010, 0xA96F), (0x1010, 0xA974), (0x1010, 0xA979),
        (0x1010, 0xA97B), (0x1010, 0xA980), (0x1010, 0xA982), (0x1010, 0xA987),
        (0x1010, 0xA989), (0x1010, 0xA98D), (0x1010, 0xA98F), (0x1010, 0xA992),
        (0x1010, 0xA994), (0x1010, 0xA997), (0x1010, 0xA999), (0x1010, 0xA99B),
        (0x1010, 0xA99E), (0x1010, 0xA9A0), (0x1010, 0xA9A2), (0x1010, 0xA9A5),
        (0x1010, 0xA9A7), (0x1010, 0xA9A9), (0x1010, 0xA9AD), (0x1010, 0xA9B1),
        (0x1010, 0xA9B3), (0x1010, 0xA9B8), (0x1010, 0xA9BD), (0x1010, 0xA9C2),
        (0x1010, 0xA9C7), (0x1010, 0xA9C9), (0x1010, 0xA9CE), (0x1010, 0xA9D3),
        (0x1010, 0xA9D8), (0x1010, 0xA9DA), (0x1010, 0xA9DD),
        (0x1010, 0xAA07), (0x1010, 0xAA0D), (0x1010, 0xAA2A),
        (0x1010, 0xD007), (0x1010, 0xD00A), (0x1010, 0xD00D), (0x1010, 0xD010),
        (0x1010, 0xD013), (0x1010, 0xD016), (0x1010, 0xD019), (0x1010, 0xD01C),
        (0x1010, 0xD01F), (0x1010, 0xD022), (0x1010, 0xD025), (0x1010, 0xD028),
        (0x1010, 0xD02D), (0x1010, 0xD02F), (0x1010, 0xD032), (0x1010, 0xD037),
        (0x1010, 0xD039), (0x1010, 0xD03E), (0x1010, 0xD040), (0x1010, 0xD046),
        (0x1010, 0xD049), (0x1010, 0xD04C), (0x1010, 0xD04D), (0x1010, 0xD053),
        (0x1010, 0xD055), (0x1010, 0xD057), (0x1010, 0xD05A), (0x1010, 0xD05E),
        (0x1010, 0xD060), (0x1010, 0xD062), (0x1010, 0xD064), (0x1010, 0xD066),
        (0x1010, 0xD06A), (0x1010, 0xD06E), (0x1010, 0xD072),
    }
    GAMEPLAY_OBJECT_ADDRS: set[Addr] = {
        (0x1010, 0xB73E),
        (0x1010, 0xAA01), (0x1010, 0xAA04), (0x1010, 0xAA05),
        (0x1010, 0xAA10), (0x1010, 0xAA1F), (0x1010, 0xAA22), (0x1010, 0xAA23),
        (0x1010, 0xAA2B), (0x1010, 0xAB10), (0x1010, 0xABA3), (0x1010, 0xAB77), (0x1010, 0xAB34), (0x1010, 0xAB4F), (0x1010, 0xAD04), (0x1010, 0xAE09), (0x1010, 0xAED8), (0x1010, 0xEFAE),
    }
    MOVEMENT_ADDRS: set[Addr] = {
        (0x1010, 0x5827), (0x1010, 0x5DB2), (0x1010, 0xB729),
    }
    COLLISION_ADDRS: set[Addr] = {
        (0x1010, 0x5059), (0x1010, 0x505B), (0x1010, 0x505E),
        (0x1010, 0x5063), (0x1010, 0x5066), (0x1010, 0x5068),
        (0x1010, 0x506A), (0x1010, 0x506C), (0x1010, 0x506E),
        (0x1010, 0x506F), (0x1010, 0x5073),
        (0x1010, 0x9E69), (0x1010, 0xAA44), (0x1010, 0x9E98), (0x1010, 0xAC28), (0x1010, 0xAC81), (0x1010, 0xBCCB),
        (0x1010, 0xBC45), (0x1010, 0xBC48), (0x1010, 0xBC4B), (0x1010, 0xBDE3), (0x1010, 0xBDD0),
    }
    INPUT_MENU_ADDRS: set[Addr] = {
        (0x1010, 0x0162), (0x1010, 0x017E),
        (0x1010, 0x96C5), (0x1010, 0x96C8), (0x1010, 0x96CA),
        (0x1010, 0xCE40), (0x1010, 0xCE45), (0x1010, 0xCE48), (0x1010, 0xCE49),
        (0x1010, 0xCE4C), (0x1010, 0xCE4D), (0x1010, 0xCE52), (0x1010, 0xCE59),
        (0x1010, 0xCE5C),
        (0x1010, 0x9810), (0x1010, 0x986E), (0x1010, 0x9873),
        (0x1010, 0x989E), (0x1010, 0x98B4), (0x1010, 0xD439),
    }
    SOUND_ADDRS: set[Addr] = {
        (0x1010, 0x0672), (0x1010, 0x0679),
        (0x1010, 0x06E5), (0x1010, 0xD50E), (0x1010, 0xD566),
        (0x1010, 0xD5AC), (0x1010, 0xD5BB), (0x1010, 0xD602),
        (0x1010, 0xD612), (0x1010, 0xD61F), (0x1010, 0xD62F),
    }
    ASSET_CODEC_ADDRS: set[Addr] = {
        (0x1010, 0x0324), (0x1010, 0x0367), (0x1010, 0x03A8),
        (0x1010, 0x0615), (0x1010, 0x0624),
        (0x1010, 0xC713), (0x1010, 0xC916),
        (0x1010, 0xECF2), (0x1010, 0xED7A), (0x1010, 0xED97),
        (0x1010, 0xEDE9),
    }

    def __init__(self, symbols_path: Path | None = None) -> None:
        self.symbol_text: dict[Addr, str] = {}
        if symbols_path is not None and symbols_path.exists():
            try:
                raw = json.loads(symbols_path.read_text(encoding="utf-8"))
                for key, value in raw.items():
                    try:
                        addr = parse_addr(key)
                    except Exception:
                        continue
                    if isinstance(value, dict):
                        text = " ".join(str(value.get(k, "")) for k in ("name", "status", "notes"))
                    else:
                        text = str(value)
                    self.symbol_text[addr] = text
            except Exception:
                self.symbol_text = {}

    def classify(self, addr: Addr, name: str = "") -> str:
        # Exact OVERKILL address islands are more reliable than loose symbol-text
        # regexes.  For example, notes containing "Descending" used to match the
        # old "esc" input regex, and text saying "loads" could make a layer
        # dispatcher look like an asset loader.
        if addr in self.INPUT_MENU_ADDRS:
            return "input_menu"
        if addr in self.SOUND_ADDRS:
            return "sound"
        if addr in self.OVERLAY_ADDRS:
            return "overlay"
        if addr in self.FILE_IO_ADDRS:
            return "file_io"
        if addr[0] in self.BOOTSTRAP_SEGMENTS:
            return "bootstrap"
        if addr in self.STARTUP_GRAPHICS_ADDRS:
            return "startup_graphics"
        if addr in self.COORDINATE_ADDRS:
            return "coordinates"
        if addr in self.LAYER_SPRITE_ADDRS:
            return "layer_sprites"
        if addr in self.TANDY_RENDER_ADDRS:
            return "tandy_renderer"
        if addr in self.CGA_RENDER_ADDRS:
            return "cga_renderer"
        if addr in self.EGA_RENDER_ADDRS:
            return "ega_renderer"
        if addr in self.COLLISION_ADDRS:
            return "collision"
        if addr in self.MOVEMENT_ADDRS:
            return "movement"
        if addr in self.GAME_STATE_ADDRS:
            return "game_state"
        if addr in self.GAMEPLAY_OBJECT_ADDRS:
            return "gameplay_objects"
        if addr in self.ASSET_CODEC_ADDRS:
            return "asset_codecs"

        text = f"{name} {self.symbol_text.get(addr, '')}"
        if self._overlay_re.search(text):
            return "overlay"
        if self._file_io_re.search(text):
            return "file_io"
        if self._bootstrap_re.search(text):
            return "bootstrap"
        if self._input_re.search(text):
            return "input_menu"
        if self._sound_re.search(text):
            return "sound"
        if self._coord_re.search(text):
            return "coordinates"
        if self._layer_re.search(text):
            return "layer_sprites"
        if self._tandy_re.search(text):
            return "tandy_renderer"
        if self._cga_re.search(text):
            return "cga_renderer"
        if self._ega_re.search(text):
            return "ega_renderer"
        if self._collision_re.search(text):
            return "collision"
        if self._move_re.search(text):
            return "movement"
        if self._game_state_re.search(text):
            return "game_state"
        if self._obj_re.search(text):
            return "gameplay_objects"
        if self._asset_re.search(text):
            return "asset_codecs"
        return "unknown"


class CoverageTelemetry:
    """Thread-safe live ASM/hook coverage collector.

    The CPU only emits generic events (interpreted instruction, hook call).  This
    object owns all OVERKILL-specific classification and cached hook-cost logic.
    """

    def __init__(
        self,
        *,
        classifier: OverkillCoverageClassifier | None = None,
        cache_path: Path | None = None,
        enabled: bool = True,
    ) -> None:
        self.enabled = enabled
        self.classifier = classifier or OverkillCoverageClassifier()
        self.cache_path = cache_path
        self._lock = threading.RLock()
        self.start_time = time.perf_counter()
        self.interpreted_hits: Counter[Addr] = Counter()
        self.bounded_hits: Counter[Addr] = Counter()
        self.hooks: dict[Addr, HookCoverageStats] = {}
        self.islands: dict[str, IslandCoverageStats] = {key: IslandCoverageStats() for key in ISLANDS}
        self.total_interpreted_instructions = 0
        self.total_bounded_original_instructions = 0
        self.total_hook_calls = 0
        self.total_verified_hook_calls = 0
        self.total_skipped_hooks = 0
        self.total_unverified_hook_calls = 0
        self.total_unmeasured_hook_calls = 0
        self._bounded_depth = 0
        self._cache: dict[str, dict[str, float]] = {}
        self._load_cache()

    def _load_cache(self) -> None:
        if self.cache_path is None or not self.cache_path.exists():
            return
        try:
            raw = json.loads(self.cache_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self._cache = raw.get("hooks", {}) if isinstance(raw.get("hooks"), dict) else {}
        except Exception:
            self._cache = {}

    def save_cache(self) -> None:
        if self.cache_path is None:
            return
        with self._lock:
            hooks: dict[str, dict[str, float]] = dict(self._cache)
            for addr, stat in self.hooks.items():
                if stat.verified_calls <= 0:
                    continue
                hooks[fmt_addr(addr)] = {
                    "avg_asm_equiv": float(stat.asm_equiv_instructions) / float(stat.verified_calls),
                    "samples": float(stat.verified_calls),
                    "last_asm_equiv": float(stat.last_asm_equiv),
                    "name": stat.name,
                    "island": stat.island,
                }
            payload = {"version": 1, "updated": time.time(), "hooks": hooks}
            try:
                self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                self.cache_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
            except Exception:
                pass

    def _hook_stat(self, addr: Addr, name: str) -> HookCoverageStats:
        stat = self.hooks.get(addr)
        if stat is None:
            island = self.classifier.classify(addr, name)
            stat = HookCoverageStats(addr=addr, name=name, island=island)
            self.hooks[addr] = stat
        elif name and stat.name != name:
            stat.name = name
        return stat

    def _island(self, island: str) -> IslandCoverageStats:
        if island not in self.islands:
            island = "unknown"
        return self.islands[island]

    @contextmanager
    def bounded_original(self, addr: Addr | None = None, name: str = ""):
        with self._lock:
            self._bounded_depth += 1
        try:
            yield
        finally:
            with self._lock:
                self._bounded_depth = max(0, self._bounded_depth - 1)

    def record_interpreted_instruction(self, addr: Addr) -> None:
        if not self.enabled:
            return
        with self._lock:
            if self._bounded_depth:
                self.bounded_hits[addr] += 1
                self.total_bounded_original_instructions += 1
                island = self.classifier.classify(addr)
                self._island(island).bounded_original += 1
                return
            self.interpreted_hits[addr] += 1
            self.total_interpreted_instructions += 1
            island = self.classifier.classify(addr)
            self._island(island).interpreted_asm += 1

    def record_hook_verified(self, addr: Addr, name: str, asm_equiv_instructions: int) -> None:
        if not self.enabled:
            return
        asm_equiv_instructions = max(0, int(asm_equiv_instructions))
        with self._lock:
            stat = self._hook_stat(addr, name)
            stat.calls += 1
            stat.verified_calls += 1
            stat.asm_equiv_instructions += asm_equiv_instructions
            stat.last_asm_equiv = asm_equiv_instructions
            self.total_hook_calls += 1
            self.total_verified_hook_calls += 1
            island = self._island(stat.island)
            island.hook_calls += 1
            island.verified_hook_calls += 1
            island.hooked_verified_equiv += asm_equiv_instructions

    def record_hook_unverified(self, addr: Addr, name: str) -> None:
        if not self.enabled:
            return
        with self._lock:
            stat = self._hook_stat(addr, name)
            stat.calls += 1
            stat.unverified_calls += 1
            self.total_hook_calls += 1
            self.total_unverified_hook_calls += 1
            island = self._island(stat.island)
            island.hook_calls += 1
            island.hooked_unverified_calls += 1
            cached = self._cache.get(fmt_addr(addr), {})
            avg = cached.get("avg_asm_equiv") if isinstance(cached, dict) else None
            if isinstance(avg, (int, float)) and avg > 0:
                estimated = int(round(avg))
                stat.estimated_asm_equiv_instructions += estimated
                island.hooked_estimated_equiv += estimated
            else:
                stat.unmeasured_calls += 1
                self.total_unmeasured_hook_calls += 1
                island.unmeasured_hook_calls += 1

    def record_hook_skipped(self, addr: Addr, name: str) -> None:
        if not self.enabled:
            return
        with self._lock:
            stat = self._hook_stat(addr, name)
            stat.calls += 1
            stat.skipped_calls += 1
            stat.unmeasured_calls += 1
            self.total_hook_calls += 1
            self.total_skipped_hooks += 1
            self.total_unmeasured_hook_calls += 1
            island = self._island(stat.island)
            island.hook_calls += 1
            island.skipped_hook_calls += 1
            island.unmeasured_hook_calls += 1

    def snapshot(self, *, top_n: int = 12) -> dict[str, Any]:
        with self._lock:
            hook_equiv = sum(h.total_equiv for h in self.hooks.values())
            measured_total = self.total_interpreted_instructions + self.total_bounded_original_instructions + hook_equiv
            activity_total = measured_total + self.total_unmeasured_hook_calls
            elapsed = max(0.001, time.perf_counter() - self.start_time)
            hooks = sorted(self.hooks.values(), key=lambda h: (h.total_equiv, h.calls), reverse=True)[:top_n]
            interpreted = self.interpreted_hits.most_common(top_n)
            bounded = self.bounded_hits.most_common(top_n)
            islands = {key: IslandCoverageStats(**vars(value)) for key, value in self.islands.items()}
            return {
                "elapsed": elapsed,
                "states": COVERAGE_STATES,
                "total_interpreted_instructions": self.total_interpreted_instructions,
                "total_bounded_original_instructions": self.total_bounded_original_instructions,
                "hook_equiv_instructions": hook_equiv,
                "hook_verified_equiv_instructions": sum(h.asm_equiv_instructions for h in self.hooks.values()),
                "hook_estimated_equiv_instructions": sum(h.estimated_asm_equiv_instructions for h in self.hooks.values()),
                "unknown_unmeasured_hook_calls": self.total_unmeasured_hook_calls,
                "total_hook_calls": self.total_hook_calls,
                "verified_hook_calls": self.total_verified_hook_calls,
                "skipped_hooks": self.total_skipped_hooks,
                "unverified_hook_calls": self.total_unverified_hook_calls,
                "measured_total": measured_total,
                "activity_total": activity_total,
                "instr_per_second": (self.total_interpreted_instructions + hook_equiv) / elapsed,
                "top_hooks": [
                    {**vars(h), "total_equiv": h.total_equiv}
                    for h in hooks
                ],
                "top_interpreted": [
                    {"addr": addr, "hits": hits, "island": self.classifier.classify(addr), "symbol": self.classifier.symbol_text.get(addr, "")}
                    for addr, hits in interpreted
                ],
                "top_bounded": [
                    {"addr": addr, "hits": hits, "island": self.classifier.classify(addr), "symbol": self.classifier.symbol_text.get(addr, "")}
                    for addr, hits in bounded
                ],
                "islands": islands,
            }

    def format_summary(self, *, top_n: int = 12) -> str:
        snap = self.snapshot(top_n=top_n)
        total = max(1, int(snap["activity_total"]))

        def pct(value: int | float) -> float:
            return 100.0 * float(value) / float(total)

        lines = [
            "",
            "ASM / Hook Coverage Summary",
            "===========================",
            "States: HOOKED_VERIFIED, HOOKED_UNVERIFIED, BOUNDED_ORIGINAL, INTERPRETED_ASM, UNKNOWN",
            f"ASM interpreted instructions: {snap['total_interpreted_instructions']:,} ({pct(snap['total_interpreted_instructions']):5.1f}%)",
            f"Bounded original ASM instructions: {snap['total_bounded_original_instructions']:,} ({pct(snap['total_bounded_original_instructions']):5.1f}%)",
            f"Hook-covered ASM-equivalent instructions: {snap['hook_equiv_instructions']:,} ({pct(snap['hook_equiv_instructions']):5.1f}%)",
            f"  verified: {snap['hook_verified_equiv_instructions']:,}",
            f"  estimated from cache: {snap['hook_estimated_equiv_instructions']:,}",
            f"Unknown / unmeasured hook calls: {snap['unknown_unmeasured_hook_calls']:,} ({pct(snap['unknown_unmeasured_hook_calls']):5.1f}%)",
            f"Total hook calls: {snap['total_hook_calls']:,}",
            f"Verified hook calls: {snap['verified_hook_calls']:,}",
            f"Skipped hooks / missing boundary metadata: {snap['skipped_hooks']:,}",
            "",
            "Top hook-covered routines:",
            "  address     calls    asm-equiv  island            name",
        ]
        for h in snap["top_hooks"][:top_n]:
            lines.append(
                f"  {fmt_addr(h['addr'])} {h['calls']:8,d} {h['total_equiv']:11,d}  {h['island']:<16} {h['name']}"
            )
        lines += ["", "Top remaining interpreted ASM hotspots:", "  address       hits  island            symbol/category"]
        for item in snap["top_interpreted"][:top_n]:
            symbol = item["symbol"]
            if len(symbol) > 70:
                symbol = symbol[:67] + "..."
            lines.append(f"  {fmt_addr(item['addr'])} {item['hits']:10,d}  {item['island']:<16} {symbol}")
        lines += ["", "Coverage by island:", "  island             interpreted  bounded-original  hook-equiv  hook-calls  unmeasured"]
        for key in ISLANDS:
            island = snap["islands"].get(key, IslandCoverageStats())
            hook_equiv = island.hooked_verified_equiv + island.hooked_estimated_equiv
            lines.append(
                f"  {key:<17} {island.interpreted_asm:11,d} {island.bounded_original:17,d} "
                f"{hook_equiv:11,d} {island.hook_calls:11,d} {island.unmeasured_hook_calls:10,d}"
            )
        return "\n".join(lines)

    def format_dashboard(self, *, top_n: int = 10) -> str:
        return self.format_summary(top_n=top_n).lstrip("\n")


class CoverageDashboardTk:
    """Optional Tk dashboard, isolated from gameplay and updated at low rate."""

    def __init__(self, telemetry: CoverageTelemetry, *, refresh_hz: float = 4.0, geometry: str = "+760+40") -> None:
        self.telemetry = telemetry
        self.refresh_ms = max(200, int(1000.0 / max(0.1, refresh_hz)))
        self.geometry = geometry
        self._closed = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="overkill-coverage-dashboard", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._closed.set()

    def _run(self) -> None:
        try:
            import tkinter as tk
        except Exception as exc:
            print(f"coverage dashboard disabled: Tkinter unavailable: {exc}")
            return
        try:
            root = tk.Tk()
            root.title("OVERKILL ASM / Hook Coverage")
            try:
                root.geometry(f"760x820{self.geometry}")
            except Exception:
                root.geometry("760x820")
            text = tk.Text(root, wrap="none", font=("Consolas", 9))
            ybar = tk.Scrollbar(root, orient="vertical", command=text.yview)
            xbar = tk.Scrollbar(root, orient="horizontal", command=text.xview)
            text.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
            text.grid(row=0, column=0, sticky="nsew")
            ybar.grid(row=0, column=1, sticky="ns")
            xbar.grid(row=1, column=0, sticky="ew")
            root.grid_rowconfigure(0, weight=1)
            root.grid_columnconfigure(0, weight=1)

            def refresh() -> None:
                if self._closed.is_set():
                    try:
                        root.destroy()
                    except Exception:
                        pass
                    return
                body = self.telemetry.format_dashboard(top_n=10)
                text.configure(state="normal")
                text.delete("1.0", "end")
                text.insert("1.0", body)
                text.configure(state="disabled")
                root.after(self.refresh_ms, refresh)

            root.protocol("WM_DELETE_WINDOW", self.close)
            refresh()
            root.mainloop()
        except Exception as exc:
            print(f"coverage dashboard stopped: {exc}")
