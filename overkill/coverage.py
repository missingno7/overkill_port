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
    _sound_re = re.compile(r"(sound|speaker|pc_speaker|timer_isr|irq0|pit|audio|adlib|ym3812|opl)", re.IGNORECASE)
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
        # Additional temporary nested LZEXE/self-relocation segments observed
        # during pure-original cold starts.  These are bootstrap artefacts, not
        # stable inner-game modules.
        0x1B65, 0x1C43, 0x23AD,
    }
    COORDINATE_ADDRS: set[Addr] = {
        (0x1010, 0x5A00), (0x1010, 0x5A24), (0x1010, 0x5A36),
    }
    LAYER_SPRITE_ADDRS: set[Addr] = {
        (0x1010, 0x75A6), (0x1010, 0x768E), (0x1010, 0x7746),
        (0x1010, 0x77C5), (0x1010, 0x77CA), (0x1010, 0x77CC), (0x1010, 0x77CD),
        (0x1010, 0x77DF), (0x1010, 0x77E0), (0x1010, 0x77F6), (0x1010, 0x780E), (0x1010, 0x789A), (0x1010, 0x78A6),
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
        (0x1010, 0xA891), (0x1010, 0xA894), (0x1010, 0xA8BE), (0x1010, 0xA8C1), (0x1010, 0xA8C4),
        (0x1010, 0xA8C7), (0x1010, 0xA8F1), (0x1010, 0xA8F4), (0x1010, 0xA8F5),
        (0x1010, 0xA8F7), (0x1010, 0xA8FC), (0x1010, 0xA8FE),
        (0x1010, 0xA90C),
        (0x1010, 0xA90F), (0x1010, 0xA91E), (0x1010, 0xA921), (0x1010, 0xA922),
        (0x1010, 0xA924), (0x1010, 0xA927), (0x1010, 0xA936), (0x1010, 0xA939),
        (0x1010, 0xA93A), (0x1010, 0xA93C), (0x1010, 0xA93F),
    }
    TANDY_RENDER_ADDRS: set[Addr] = {
        (0x1010, 0x2E6E), (0x1010, 0x2ECB), (0x1010, 0x2F40),
        (0x1010, 0x2F81), (0x1010, 0x2FB6), (0x1010, 0x306F),
        (0x1010, 0x30B0), (0x1010, 0x30BA), (0x1010, 0x3389),
        (0x1010, 0x3153), (0x1010, 0x518C), (0x1010, 0x519A), (0x1010, 0x5EDB), (0x1010, 0x5EF9), (0x1010, 0x5F06),
        (0x1010, 0x3354), (0x1010, 0x34AD), (0x1010, 0x5C74),
        (0x1010, 0x34C5), (0x1010, 0x34D8), (0x1010, 0x3542),
        (0x1010, 0x356C), (0x1010, 0x36A2), (0x1010, 0x3657),
        (0x1010, 0x35AA), (0x1010, 0x35CC), (0x1010, 0x375B),
        (0x1010, 0x4E0D), (0x1010, 0x4E26), (0x1010, 0x4E0E), (0x1010, 0x4E0F),
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
        (0x1010, 0x412B), (0x1010, 0x5160),
    }
    GAME_STATE_ADDRS: set[Addr] = {
        (0x1F8F, 0x081D), (0x1F8F, 0x0922), (0x1F8F, 0x0960), (0x1F8F, 0x0927), (0x1F8F, 0x0929), (0x1F8F, 0x092D),
        (0x1F8F, 0x0932), (0x1F8F, 0x0934), (0x1F8F, 0x0937), (0x1F8F, 0x093A),
        (0x1F8F, 0x093D), (0x1F8F, 0x0941), (0x1F8F, 0x0946), (0x1F8F, 0x0948),
        (0x1F8F, 0x094B), (0x1F8F, 0x094E), (0x1F8F, 0x0952), (0x1F8F, 0x0957),
        (0x1F8F, 0x0959), (0x1F8F, 0x095C), (0x1F8F, 0x095F),
        (0x1010, 0x61C7), (0x1010, 0x61CA), (0x1010, 0x61CD), (0x1010, 0x61DC), (0x1010, 0x61F7), (0x1010, 0x61FA),
        (0x1010, 0x613E), (0x1010, 0x6143), (0x1010, 0x6145), (0x1010, 0x6150), (0x1010, 0x6154), (0x1010, 0x6156),
        (0x1010, 0x6120), (0x1010, 0x6122), (0x1010, 0x6125), (0x1010, 0x612A), (0x1010, 0x612D), (0x1010, 0x6130), (0x1010, 0x6133), (0x1010, 0x6136), (0x1010, 0x6138), (0x1010, 0x613D),
        (0x1010, 0x615A), (0x1010, 0x615F), (0x1010, 0x6161), (0x1010, 0x616C), (0x1010, 0x6170), (0x1010, 0x6172),
        (0x1010, 0x859E), (0x1010, 0x859F), (0x1010, 0x85A2), (0x1010, 0x85A8), (0x1010, 0x85AA), (0x1010, 0x85AD), (0x1010, 0x85B0), (0x1010, 0x85B3), (0x1010, 0x85B4), (0x1010, 0x85B5), (0x1010, 0x85B8), (0x1010, 0x85BA), (0x1010, 0x85BD), (0x1010, 0x85C0), (0x1010, 0x85C3), (0x1010, 0x85C6), (0x1010, 0x85C9), (0x1010, 0x85CC), (0x1010, 0x85CF), (0x1010, 0x85D2),
        (0x1010, 0xC51D), (0x1010, 0xC523), (0x1010, 0xC529), (0x1010, 0xC52F), (0x1010, 0xC535), (0x1010, 0xC53B), (0x1010, 0xC541), (0x1010, 0xC547), (0x1010, 0xC54D), (0x1010, 0xC553), (0x1010, 0xC559), (0x1010, 0xC55F), (0x1010, 0xC562),
        (0x1010, 0x8517), (0x1010, 0x851D), (0x1010, 0x8520), (0x1010, 0x8522),
        (0x1010, 0x8525), (0x1010, 0x8528), (0x1010, 0x852B), (0x1010, 0x852D),
        (0x1010, 0x852E), (0x1010, 0x8531), (0x1010, 0x8536), (0x1010, 0x8539),
        (0x1010, 0x853E), (0x1010, 0x8541), (0x1010, 0x8542), (0x1010, 0x8545),
        (0x1010, 0x85D5), (0x1010, 0x85EF), (0x1010, 0x861B), (0x1010, 0x8625), (0x1010, 0x8629),
        (0x1010, 0x863A), (0x1010, 0x863E), (0x1010, 0x864B), (0x1010, 0x864E),
        (0x1010, 0x99CD), (0x1010, 0x99D0), (0x1010, 0x99D3), (0x1010, 0x99D4), (0x1010, 0x99D7), (0x1010, 0x99DA), (0x1010, 0x99DB),
        (0x1010, 0x9B2E), (0x1010, 0x9BFB), (0x1010, 0x9BFE), (0x1010, 0x9C01),
        (0x1010, 0x9CD9), (0x1010, 0x9CF1),
        (0x1010, 0xA031),
        (0x1010, 0xD318), (0x1010, 0xD31B), (0x1010, 0xD31E), (0x1010, 0xD321),
        (0x1010, 0xD327), (0x1010, 0xD329), (0x1010, 0xD32C), (0x1010, 0xD32F),
        (0x1010, 0xD332), (0x1010, 0xD337), (0x1010, 0xD33A), (0x1010, 0xD33D),
        (0x1010, 0xD340), (0x1010, 0xD343), (0x1010, 0xD346), (0x1010, 0xD34A),
        (0x1010, 0xD350), (0x1010, 0xD352), (0x1010, 0xD355), (0x1010, 0xD35A),
        (0x1010, 0xD35C), (0x1010, 0xD35F), (0x1010, 0xD364), (0x1010, 0xD366),
        (0x1010, 0xD367), (0x1010, 0xD369), (0x1010, 0xD36B), (0x1010, 0xD36E),
        (0x1010, 0xD370), (0x1010, 0xD375), (0x1010, 0xD378), (0x1010, 0xD37D),
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
        (0x1010, 0xAA07), (0x1010, 0xAA0D), (0x1010, 0xAA25), (0x1010, 0xAA2A),
        (0x1010, 0x5BDC), (0x1010, 0x5BE1), (0x1010, 0x5BE3),
        (0x1010, 0x5F61), (0x1010, 0x60A2), (0x1010, 0x60A5), (0x1010, 0x60A8), (0x1010, 0x60AB),
        (0x1010, 0x606B), (0x1010, 0x606F),
        (0x1010, 0x97B2), (0x1010, 0x97B5), (0x1010, 0x97B8), (0x1010, 0x97BB),
        (0x1010, 0xA212), (0x1010, 0xA21A), (0x1010, 0xA258),
        (0x1010, 0x073C), (0x1010, 0x0741), (0x1010, 0x0743),
        (0x1010, 0x6296),
        (0x1010, 0xD007), (0x1010, 0xD00A), (0x1010, 0xD00D), (0x1010, 0xD010),
        (0x1010, 0xD013), (0x1010, 0xD016), (0x1010, 0xD019), (0x1010, 0xD01C),
        (0x1010, 0xD01F), (0x1010, 0xD022), (0x1010, 0xD025), (0x1010, 0xD028),
        (0x1010, 0xD02D), (0x1010, 0xD02F), (0x1010, 0xD032), (0x1010, 0xD037),
        (0x1010, 0xD039), (0x1010, 0xD03E), (0x1010, 0xD040), (0x1010, 0xD046),
        (0x1010, 0xD049), (0x1010, 0xD04C), (0x1010, 0xD04D), (0x1010, 0xD053),
        (0x1010, 0xD055), (0x1010, 0xD057), (0x1010, 0xD05A), (0x1010, 0xD05E),
        (0x1010, 0xD060), (0x1010, 0xD062), (0x1010, 0xD064), (0x1010, 0xD066),
        (0x1010, 0xD06A), (0x1010, 0xD06C), (0x1010, 0xD06E), (0x1010, 0xD072),
    }
    GAMEPLAY_OBJECT_ADDRS: set[Addr] = {
        (0x1010, 0xB73E), (0x1010, 0xB86D), (0x1010, 0xB872), (0x1010, 0xB877),
        (0x1010, 0x7524), (0x1010, 0x7547), (0x1010, 0x7573),
        (0x1010, 0xA4D7), (0x1010, 0xA4EA), (0x1010, 0xA571),
        (0x1010, 0xA5D1), (0x1010, 0xA5D8), (0x1010, 0xA5DB), (0x1010, 0xA5E2),
        (0x1010, 0xA5EA), (0x1010, 0xA5ED), (0x1010, 0xA5F5),
        (0x1010, 0xA5F9), (0x1010, 0xA5FC), (0x1010, 0xA603),
        (0x1010, 0xA607), (0x1010, 0xA60A), (0x1010, 0xA612),
        (0x1010, 0xA616), (0x1010, 0xA61F), (0x1010, 0xA622), (0x1010, 0xA629),
        (0x1010, 0xA63C), (0x1010, 0xA643), (0x1010, 0xA648), (0x1010, 0xA64E),
        (0x1010, 0xA65D), (0x1010, 0xA662), (0x1010, 0xA66A),
        (0x1010, 0xC3BF), (0x1010, 0xC3C0), (0x1010, 0xC3C2), (0x1010, 0xC3C4), (0x1010, 0xC3C8),
        (0x1010, 0xC3CD), (0x1010, 0xC3D2), (0x1010, 0xC3D7), (0x1010, 0xC3DB), (0x1010, 0xC3DE),
        (0x1010, 0xC3E4), (0x1010, 0xC3E5),
        (0x1010, 0xC3F1), (0x1010, 0xC3F2), (0x1010, 0xC3F4), (0x1010, 0xC3F6), (0x1010, 0xC3FA),
        (0x1010, 0xC3FF), (0x1010, 0xC403), (0x1010, 0xC405), (0x1010, 0xC40A), (0x1010, 0xC40F),
        (0x1010, 0xC414), (0x1010, 0xC419), (0x1010, 0xC41E), (0x1010, 0xC422), (0x1010, 0xC425),
        (0x1010, 0xC42C), (0x1010, 0xC42D),
        (0x1010, 0xC4E5), (0x1010, 0xC4E6), (0x1010, 0xC4E8), (0x1010, 0xC4EA), (0x1010, 0xC4EE),
        (0x1010, 0xC4F3), (0x1010, 0xC4F8), (0x1010, 0xC4FD), (0x1010, 0xC502), (0x1010, 0xC507),
        (0x1010, 0xC50C), (0x1010, 0xC510), (0x1010, 0xC513), (0x1010, 0xC51A), (0x1010, 0xC51B),
        (0x1010, 0xB87C), (0x1010, 0xB87E), (0x1010, 0xB883), (0x1010, 0xB885),
        (0x1010, 0xB88B), (0x1010, 0xB890), (0x1010, 0xB894), (0x1010, 0xB898),
        (0x1010, 0xB89C), (0x1010, 0xB8A0), (0x1010, 0xB8A3), (0x1010, 0xB8A5),
        (0x1010, 0xB8A8), (0x1010, 0xB8AD), (0x1010, 0xB8B0), (0x1010, 0xB8B6),
        (0x1010, 0xB8BB), (0x1010, 0xB8C1), (0x1010, 0xB8C6), (0x1010, 0xB8CB),
        (0x1010, 0xB8D0), (0x1010, 0xB8D3), (0x1010, 0xB8D5), (0x1010, 0xB8D8),
        (0x1010, 0xB24D), (0x1010, 0xB250), (0x1010, 0xB2A3), (0x1010, 0xADC9),
        (0x1010, 0xB8DB), (0x1010, 0xB8E0), (0x1010, 0xB8E2), (0x1010, 0xB8E5),
        (0x1010, 0xB8E8), (0x1010, 0xB8ED), (0x1010, 0xB8EF), (0x1010, 0xB8F3),
        (0x1010, 0xB909), (0x1010, 0xB90F), (0x1010, 0xB912), (0x1010, 0xB914),
        (0x1010, 0xB9F0),
        (0x1010, 0xAA01), (0x1010, 0xAA04), (0x1010, 0xAA05),
        (0x1010, 0xAA10), (0x1010, 0xAA1F), (0x1010, 0xAA22), (0x1010, 0xAA23),
        (0x1010, 0x9FAF), (0x1010, 0x9FB4), (0x1010, 0x9FB9), (0x1010, 0x9FBF),
        (0x1010, 0x9FC6), (0x1010, 0x9FC9), (0x1010, 0x9FD0), (0x1010, 0x9FD3),
        (0x1010, 0x9FD9), (0x1010, 0x9FE0), (0x1010, 0x9FE3), (0x1010, 0x9FE6),
        (0x1010, 0x9FEA), (0x1010, 0x9FED), (0x1010, 0x9FEF),
        (0x1010, 0xAA2B), (0x1010, 0xAB10), (0x1010, 0xABA3), (0x1010, 0xAB59), (0x1010, 0xAB61), (0x1010, 0xAB69), (0x1010, 0xAB71), (0x1010, 0xAB77), (0x1010, 0xABCA), (0x1010, 0xAB34), (0x1010, 0xAB4F),
        (0x1010, 0xAD04), (0x1010, 0xAD5A), (0x1010, 0xAD5D), (0x1010, 0xAD60), (0x1010, 0xAD64), (0x1010, 0xAD69), (0x1010, 0xAD6E),
        (0x1010, 0xAD73), (0x1010, 0xAD78), (0x1010, 0xAD7D), (0x1010, 0xAD81), (0x1010, 0xADC8),
        (0x1010, 0xADC9), (0x1010, 0xADCE), (0x1010, 0xADD0), (0x1010, 0xADD3),
        (0x1010, 0xADD6), (0x1010, 0xADD9), (0x1010, 0xADDD), (0x1010, 0xADDF),
        (0x1010, 0xADE2), (0x1010, 0xADE5), (0x1010, 0xADE8), (0x1010, 0xADEC),
        (0x1010, 0xADEF), (0x1010, 0xADF2), (0x1010, 0xADF5), (0x1010, 0xADF7),
        (0x1010, 0xADFA), (0x1010, 0xADFD), (0x1010, 0xAE00), (0x1010, 0xAE02),
        (0x1010, 0xAE05), (0x1010, 0xAE06),
        (0x1010, 0xD281), (0x1010, 0xD284), (0x1010, 0xD287), (0x1010, 0xD28A), (0x1010, 0xD28D),
        (0x1010, 0xD293), (0x1010, 0xD296), (0x1010, 0xD29C), (0x1010, 0xD2A1), (0x1010, 0xD2A3),
        (0x1010, 0xAE09), (0x1010, 0xAE2C), (0x1010, 0xAE31), (0x1010, 0xAE33), (0x1010, 0xAE37),
        (0x1010, 0xAE3C), (0x1010, 0xAE5E), (0x1010, 0xAE63), (0x1010, 0xAE67), (0x1010, 0xAE6A),
        (0x1010, 0xAE6C), (0x1010, 0xAE6E), (0x1010, 0xAE71), (0x1010, 0xAE74), (0x1010, 0xAE77), (0x1010, 0xAE7A),
        (0x1010, 0xAE7D), (0x1010, 0xAE81), (0x1010, 0xAE86), (0x1010, 0xAE8A), (0x1010, 0xAE8F),
        (0x1010, 0xAEAA), (0x1010, 0xAEAF), (0x1010, 0xAEB3), (0x1010, 0xAEB6), (0x1010, 0xAEB9), (0x1010, 0xAEBC),
        (0x1010, 0xAED8), (0x1010, 0xEFAE),
    }
    MOVEMENT_ADDRS: set[Addr] = {
        (0x1010, 0x5827), (0x1010, 0x5DB2), (0x1010, 0x5E42),
        (0x1010, 0xAEE4), (0x1010, 0xAF22), (0x1010, 0xAF60), (0x1010, 0xAF63), (0x1010, 0xB729),
    }
    COLLISION_ADDRS: set[Addr] = {
        (0x1010, 0x4FF9), (0x1010, 0x4FFC), (0x1010, 0x4FFF),
        (0x1010, 0x5001), (0x1010, 0x5003), (0x1010, 0x5005),
        (0x1010, 0x5009), (0x1010, 0x500C), (0x1010, 0x500F),
        (0x1010, 0x5010), (0x1010, 0x5013), (0x1010, 0x5014),
        (0x1010, 0x5017), (0x1010, 0x501A), (0x1010, 0x501D),
        (0x1010, 0x5020), (0x1010, 0x5023), (0x1010, 0x5026),
        (0x1010, 0x5029), (0x1010, 0x502B), (0x1010, 0x502E),
        (0x1010, 0x502F), (0x1010, 0x5030), (0x1010, 0x5033),
        (0x1010, 0x5035), (0x1010, 0x503A), (0x1010, 0x503C),
        (0x1010, 0x503D), (0x1010, 0x5040), (0x1010, 0x5042),
        (0x1010, 0x5043), (0x1010, 0x5046), (0x1010, 0x5047),
        (0x1010, 0x5049), (0x1010, 0x504C), (0x1010, 0x504F),
        (0x1010, 0x5050), (0x1010, 0x5051), (0x1010, 0x5052),
        (0x1010, 0x5053), (0x1010, 0x5056),
        (0x1010, 0x5059), (0x1010, 0x505B), (0x1010, 0x505E),
        (0x1010, 0x5063), (0x1010, 0x5066), (0x1010, 0x5068),
        (0x1010, 0x506A), (0x1010, 0x506C), (0x1010, 0x506E),
        (0x1010, 0x506F), (0x1010, 0x5073),
        (0x1010, 0x8331), (0x1010, 0x835B),
        (0x1010, 0x9E69), (0x1010, 0xAA44), (0x1010, 0x9E98), (0x1010, 0xAC28), (0x1010, 0xAC81), (0x1010, 0xBCCB),
        (0x1010, 0xB00D), (0x1010, 0xB032), (0x1010, 0xB039), (0x1010, 0xB03C),
        (0x1010, 0xB07A), (0x1010, 0xB07D), (0x1010, 0xB0C9), (0x1010, 0xB0CC),
        (0x1010, 0xB10C), (0x1010, 0xB10F),
        (0x1010, 0xACD2), (0x1010, 0xACD5), (0x1010, 0xACD7), (0x1010, 0xACD8),
        (0x1010, 0xACD9), (0x1010, 0xACDD), (0x1010, 0xACDF), (0x1010, 0xACE3),
        (0x1010, 0xACE5), (0x1010, 0xACE8), (0x1010, 0xACEC), (0x1010, 0xACEE),
        (0x1010, 0xACF1), (0x1010, 0xACF4), (0x1010, 0xACF6), (0x1010, 0xACF7),
        (0x1010, 0xACF8), (0x1010, 0xACF9), (0x1010, 0xACFA), (0x1010, 0xACFC),
        (0x1010, 0xACFF), (0x1010, 0xAD01), (0x1010, 0xAD02), (0x1010, 0xAD03),
        (0x1010, 0xBC45), (0x1010, 0xBC48), (0x1010, 0xBC4B), (0x1010, 0xBDE3), (0x1010, 0xBDD0),
    }
    INPUT_MENU_ADDRS: set[Addr] = {
        (0x1010, 0x0162), (0x1010, 0x017E),
        (0x1010, 0x4E9F), (0x1010, 0x4EBF), (0x1010, 0x5497),
        (0x1010, 0x50AB), (0x1010, 0x50BA),
        (0x1010, 0x53C9), (0x1010, 0x53CC), (0x1010, 0x53CF), (0x1010, 0x53D2),
        (0x1010, 0x53D5), (0x1010, 0x53D8), (0x1010, 0x53DA), (0x1010, 0x53DC),
        (0x1010, 0x53DE), (0x1010, 0x53E0), (0x1010, 0x53E6), (0x1010, 0x53E8),
        (0x1010, 0x53EA), (0x1010, 0x53EC), (0x1010, 0x53EE), (0x1010, 0x53F0),
        (0x1010, 0x53F4), (0x1010, 0x53F6), (0x1010, 0x53FA), (0x1010, 0x53FC),
        (0x1010, 0x5401), (0x1010, 0x5408), (0x1010, 0x5410), (0x1010, 0x5414),
        (0x1010, 0x5418), (0x1010, 0x541A), (0x1010, 0x541C), (0x1010, 0x541E),
        (0x1010, 0x5426), (0x1010, 0x5433), (0x1010, 0x5443), (0x1010, 0x544B),
        (0x1010, 0x544E),
        (0x1010, 0x96C5), (0x1010, 0x96C8), (0x1010, 0x96CA),
        (0x1010, 0xCE40), (0x1010, 0xCE45), (0x1010, 0xCE48), (0x1010, 0xCE49),
        (0x1010, 0xCE4C), (0x1010, 0xCE4D), (0x1010, 0xCE52), (0x1010, 0xCE59),
        (0x1010, 0xCE5C),
        (0x1010, 0x9810), (0x1010, 0x986E), (0x1010, 0x9873),
        (0x1010, 0x989E), (0x1010, 0x98A3), (0x1010, 0x98A8),
        (0x1010, 0x98AA), (0x1010, 0x98AF), (0x1010, 0x98B4),
        (0x1010, 0x98D8), (0x1010, 0x98DD), (0x1010, 0xD439),
    }
    SOUND_ADDRS: set[Addr] = {
        (0x1010, 0x0672), (0x1010, 0x0679), (0x1010, 0x9921),
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

    # Ranges are used only after the exact-address sets above.  They classify
    # already-triaged bounded-original frontiers and routine interiors so the
    # coverage dashboard does not collapse known work into the undifferentiated
    # ``unknown`` bucket.  They are not hook permissions and must not be used as
    # proof that a range is fully lifted.
    ISLAND_RANGES: tuple[tuple[int, int, int, str, str], ...] = (
        # Interior/child addresses around the now-lifted 9B2E parent.  9B2E
        # and 9CB6 are exact game_state hooks; this range keeps any remaining
        # nearby interpreted tails attributed to the same frame-controller family.
        (0x1010, 0x9B2E, 0x9CBB, "game_state", "9B2E frame-controller interior/contact probe family"),
        # A067 is reached from both 9B2E and D04D as a low-level frame UI/input
        # object helper.  Keep it in game_state until it is lifted separately.
        (0x1010, 0xA060, 0xA211, "game_state", "A067 frame UI/object helper frontier"),
        # Observed BE3C/BEC5 collision-handler tail variants reached from the
        # BC4B postmove chain.
        (0x1010, 0xBE3C, 0xBEB6, "collision", "observed BEC5/BE3C collision tail"),
        # Overlay-resident object-spawn script reached through 1F8F:0922.  It
        # allocates/spawns runtime object slots, so it belongs with object logic
        # rather than overlay file/decode helpers.
        (0x1F8F, 0x027A, 0x0451, "gameplay_objects", "overlay object-spawn script"),
        # Observed object logic waypoint/patrol helper and its far-call entry
        # veneer.
        (0x1010, 0x8D4F, 0x8D8D, "gameplay_objects", "object waypoint/patrol helper"),
        # B729 is now a hook; this range keeps historical/interior traces named
        # as the target-copy + 5DB2 movement wrapper rather than unknown glue.
        (0x1010, 0xB72A, 0xB73D, "movement", "B729 object target-copy movement wrapper interior"),
        (0x1010, 0xB00E, 0xB159, "collision", "B00D directional tile-sweep dispatcher interior"),
        # Interior writes observed by world-write tracing while the 35CC hook
        # composes Tandy object draw blocks.  These touch object-record draw
        # scratch fields, not gameplay materialisation.
        (0x1010, 0x356C, 0x35A9, "tandy_renderer", "356C Tandy split-object draw interior"),
        (0x1010, 0x35CC, 0x361D, "tandy_renderer", "35CC Tandy object draw block interior"),
        # Observed object deactivation / out-of-bounds helper used by collision
        # and postmove tails.
        (0x1010, 0xBD17, 0xBD65, "gameplay_objects", "object deactivation tail"),
        # Tile/contact probe continuation after the tiny AA44 CLC/RET leaf.
        (0x1010, 0xAA44, 0xAA70, "collision", "tile/contact probe tail"),
        # One-instruction 97B2 tail after the timer wait, visible when resuming
        # snapshots at the last jump of the frame loop.
        (0x1010, 0x981D, 0x981D, "game_state", "97B2 frame-loop jump tail"),
        # Object deactivation logic selector used by BD17/BFC7.  This is a
        # bounded-original selector family, not a renderer/status loop.
        (0x1010, 0xC054, 0xC15B, "gameplay_objects", "object deactivate logic selector"),
        # 61DC is now lifted as a parent hook; keep the rest of its interior
        # classified for historical bounded traces and snapshots that stop
        # inside the parent.  The exact hook address above wins for 61DC itself.
        (0x1010, 0x61DD, 0x6295, "game_state", "61DC status display parent interior"),
        # Packed decimal score helper.  Some object death/contact branches still
        # run the original helper directly before returning into lifted tails.
        (0x1010, 0x5F0D, 0x5F42, "game_state", "packed decimal score/status add helper"),
        # Contact side-effect tail after the AA46 probe; may jump into BD17 or
        # the BC45 postmove epilogue depending on the live object state.
        (0x1010, 0xAAC2, 0xAAFB, "collision", "post-contact side-effect tail"),
        # Rectangle/contact test helper already documented in symbols.json.
        (0x1010, 0x8331, 0x835A, "collision", "view/contact rectangle test helper"),
        # 9D67/9EC2 are status/effect redraw tails: they update A95A/A95C and
        # call the 61DC status-display parent before returning to the object tail.
        (0x1010, 0x9D67, 0x9EF2, "game_state", "status/effect redraw tail"),
        # Rare bounded effect renderer reached by 9EE4 and 606F.  Exact helper
        # entries still win above; the range keeps the wrapper bytes named.
        (0x1010, 0x77DF, 0x77F5, "layer_sprites", "77DF frame-effect wrapper"),
        # Tail-jump from the post-contact jump table back into BD17.  The bytes
        # before AB0C are data, so keep this deliberately tiny.
        (0x1010, 0xAB0C, 0xAB0D, "gameplay_objects", "post-contact jump-table tail"),
    )

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
        if addr in self.SOUND_ADDRS or addr[0] == 0x2032:
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

        cs, ip = addr
        for range_cs, start, end, island, _label in self.ISLAND_RANGES:
            if cs == range_cs and start <= ip <= end:
                return island

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


    def _top_regions_from(self, hits_by_addr: Counter[Addr], *, top_n: int, gap: int = 16) -> list[dict[str, Any]]:
        """Aggregate nearby CS:IP hits into routine-like regions.

        Per-IP counters answer "which exact instruction is hottest?".  That is
        faithful, but it can hide the next absorbable boundary when a routine has
        many moderately-hot instructions.  Region grouping is intentionally only
        diagnostic; it never changes execution or hook eligibility.
        """
        if not hits_by_addr:
            return []

        groups: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        for (cs, ip), hits in sorted(hits_by_addr.items(), key=lambda item: (item[0][0], item[0][1])):
            if current is None or cs != current["cs"] or ip > int(current["last_ip"]) + gap:
                current = {
                    "cs": cs,
                    "start": ip,
                    "end": ip,
                    "last_ip": ip,
                    "hits": int(hits),
                    "addresses": 1,
                    "max_addr": (cs, ip),
                    "max_hits": int(hits),
                    "island_hits": Counter({self.classifier.classify((cs, ip)): int(hits)}),
                    "symbols": [],
                }
                symbol = self.classifier.symbol_text.get((cs, ip), "")
                if symbol:
                    current["symbols"].append(symbol)
                groups.append(current)
                continue

            current["end"] = ip
            current["last_ip"] = ip
            current["hits"] += int(hits)
            current["addresses"] += 1
            current["island_hits"].update({self.classifier.classify((cs, ip)): int(hits)})
            if hits > current["max_hits"]:
                current["max_addr"] = (cs, ip)
                current["max_hits"] = int(hits)
            symbol = self.classifier.symbol_text.get((cs, ip), "")
            if symbol and symbol not in current["symbols"]:
                current["symbols"].append(symbol)

        result: list[dict[str, Any]] = []
        for group in groups:
            island_hits: Counter[str] = group["island_hits"]
            island = island_hits.most_common(1)[0][0] if island_hits else "unknown"
            result.append({
                "start": (group["cs"], group["start"]),
                "end": (group["cs"], group["end"]),
                "hits": group["hits"],
                "addresses": group["addresses"],
                "max_addr": group["max_addr"],
                "max_hits": group["max_hits"],
                "island": island,
                "symbol": "; ".join(group["symbols"][:2]),
            })
        result.sort(key=lambda item: (item["hits"], item["max_hits"]), reverse=True)
        return result[:top_n]

    def _top_interpreted_regions(self, *, top_n: int, gap: int = 16) -> list[dict[str, Any]]:
        """Aggregate interpreted instruction hits into nearby-address regions."""
        return self._top_regions_from(self.interpreted_hits, top_n=top_n, gap=gap)

    def _top_bounded_regions(self, *, top_n: int, gap: int = 16) -> list[dict[str, Any]]:
        """Aggregate bounded-original instruction hits into nearby regions."""
        return self._top_regions_from(self.bounded_hits, top_n=top_n, gap=gap)

    def snapshot(self, *, top_n: int = 12) -> dict[str, Any]:
        with self._lock:
            hook_equiv = sum(h.total_equiv for h in self.hooks.values())
            measured_total = self.total_interpreted_instructions + self.total_bounded_original_instructions + hook_equiv
            activity_total = measured_total + self.total_unmeasured_hook_calls
            elapsed = max(0.001, time.perf_counter() - self.start_time)
            hooks = sorted(self.hooks.values(), key=lambda h: (h.total_equiv, h.calls), reverse=True)[:top_n]
            interpreted = self.interpreted_hits.most_common(top_n)
            interpreted_regions = self._top_interpreted_regions(top_n=top_n)
            bounded = self.bounded_hits.most_common(top_n)
            bounded_regions = self._top_bounded_regions(top_n=top_n)
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
                "top_interpreted_regions": interpreted_regions,
                "top_bounded": [
                    {"addr": addr, "hits": hits, "island": self.classifier.classify(addr), "symbol": self.classifier.symbol_text.get(addr, "")}
                    for addr, hits in bounded
                ],
                "top_bounded_regions": bounded_regions,
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
        lines += ["", "Top remaining interpreted ASM hotspots (per instruction):", "  address       hits  island            symbol/category"]
        for item in snap["top_interpreted"][:top_n]:
            symbol = item["symbol"]
            if len(symbol) > 70:
                symbol = symbol[:67] + "..."
            lines.append(f"  {fmt_addr(item['addr'])} {item['hits']:10,d}  {item['island']:<16} {symbol}")
        lines += ["", "Top remaining interpreted ASM regions (nearby IPs grouped):", "  range             hits  addrs  hottest       island            symbol/category"]
        for item in snap.get("top_interpreted_regions", [])[:top_n]:
            symbol = item["symbol"]
            if len(symbol) > 58:
                symbol = symbol[:55] + "..."
            start = fmt_addr(item["start"])
            end = f"{item['end'][1]:04X}"
            lines.append(
                f"  {start}-{end} {item['hits']:10,d} {item['addresses']:6,d}  "
                f"{fmt_addr(item['max_addr'])} {item['island']:<16} {symbol}"
            )
        lines += ["", "Top bounded-original ASM hotspots (per instruction):", "  address       hits  island            symbol/category"]
        for item in snap["top_bounded"][:top_n]:
            symbol = item["symbol"]
            if len(symbol) > 70:
                symbol = symbol[:67] + "..."
            lines.append(f"  {fmt_addr(item['addr'])} {item['hits']:10,d}  {item['island']:<16} {symbol}")
        lines += ["", "Top bounded-original ASM regions (nearby IPs grouped):", "  range             hits  addrs  hottest       island            symbol/category"]
        for item in snap.get("top_bounded_regions", [])[:top_n]:
            symbol = item["symbol"]
            if len(symbol) > 58:
                symbol = symbol[:55] + "..."
            start = fmt_addr(item["start"])
            end = f"{item['end'][1]:04X}"
            lines.append(
                f"  {start}-{end} {item['hits']:10,d} {item['addresses']:6,d}  "
                f"{fmt_addr(item['max_addr'])} {item['island']:<16} {symbol}"
            )
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
