"""The WALK-SHADOW CACHE: record a demo's per-walk-frame VM states once, replay them in seconds.

The demo walk shadow (``verify_native_walk_demo``) spends ~5 minutes emulating the VM side of a
demo -- yet that side is fully DETERMINISTIC for a given demo + game data.  This module records,
during one normal VM run, exactly what the shadow consumes per ``A9D3..AA25`` walk frame:

* the full 1MB machine state at the walk ENTRY (what the native walk runs over), and
* the DGROUP window at the walk END (what the native result is compared against), and
* the ref-side SP (the stack-window compare exclusion).

Storage is delta-encoded (the between-frame VM writes touch a few hundred DGROUP bytes; the tile
plane changes only on scroll row-pulls and is stored dedup-by-hash; everything outside DGROUP+plane
is static code/tables kept once from frame 0), so a whole 8294-frame demo caches in ~10-20MB and
replays natively in seconds -- the SAME states, the SAME comparison, no oracle weakening.  The cache
is keyed on the demo's own input file (sha1) + the recorded frame budget and refuses a mismatch.
"""
from __future__ import annotations

import hashlib
import pickle
import zlib
from pathlib import Path

CACHE_FORMAT = 3
DGROUP = 0x25CC
CS = 0x1010
PLANE_SEG_CELL = 0x9592
PLANE_SIZE = 0x4000

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "artifacts" / "shadow_cache"


def _delta(prev: bytes, cur: bytes) -> "list[tuple[int, bytes]]":
    """Sparse (offset, replacement-bytes) runs turning ``prev`` into ``cur`` (equal lengths)."""
    import numpy as np

    a = np.frombuffer(prev, dtype=np.uint8)
    b = np.frombuffer(cur, dtype=np.uint8)
    idx = np.flatnonzero(a != b)
    if idx.size == 0:
        return []
    runs: list[tuple[int, bytes]] = []
    start = prev_i = int(idx[0])
    for i in idx[1:]:
        i = int(i)
        if i != prev_i + 1:
            runs.append((start, cur[start:prev_i + 1]))
            start = i
        prev_i = i
    runs.append((start, cur[start:prev_i + 1]))
    return runs


def _apply(buf: bytearray, runs) -> None:
    for off, data in runs:
        buf[off:off + len(data)] = data


def demo_key(demo) -> str:
    """The cache-validity key: a sha1 over the demo's own input file."""
    manifest = Path(demo.demo_dir) / "input_demo.json"
    if manifest.is_file():
        return hashlib.sha1(manifest.read_bytes()).hexdigest()
    return hashlib.sha1(repr(getattr(demo, "manifest", "")).encode()).hexdigest()


def cache_path_for(demo) -> Path:
    return CACHE_DIR / (Path(demo.demo_dir).name + ".walkcache")


class WalkShadowRecorder:
    """Accumulates per-walk-frame states during a live VM run; ``save()`` writes the cache."""

    def __init__(self, key: str, max_frames) -> None:
        self.key = key
        self.max_frames = max_frames
        self.frame0_full: bytes | None = None
        self.plane_seg: int | None = None
        self.pre_deltas: list = []       # DGROUP delta vs the previous frame's POST DGROUP
        self.post_deltas: list = []      # DGROUP delta vs this frame's PRE DGROUP
        self.plane_refs: list = []       # index into self.planes
        self.sps: list = []
        self.planes: list = []           # zlib-compressed plane blobs, dedup'd
        self._plane_index: dict = {}
        self._last_post_dgroup: bytes | None = None

    def add_frame(self, pre_full: bytes, post_dgroup: bytes, sp: int) -> None:
        base = DGROUP * 16
        pre_dgroup = pre_full[base:base + 0x10000]
        if self.frame0_full is None:
            self.frame0_full = pre_full
            self.plane_seg = pre_full[CS * 16 + PLANE_SEG_CELL] | (pre_full[CS * 16 + PLANE_SEG_CELL + 1] << 8)
            self.pre_deltas.append(None)          # frame 0's pre comes from frame0_full
        else:
            self.pre_deltas.append(_delta(self._last_post_dgroup, pre_dgroup))
        plane = pre_full[self.plane_seg * 16:self.plane_seg * 16 + PLANE_SIZE]
        h = hashlib.sha1(plane).digest()
        ref = self._plane_index.get(h)
        if ref is None:
            ref = len(self.planes)
            self.planes.append(zlib.compress(plane, 6))
            self._plane_index[h] = ref
        self.plane_refs.append(ref)
        self.post_deltas.append(_delta(pre_dgroup, post_dgroup))
        self.sps.append(sp)
        self._last_post_dgroup = post_dgroup

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        blob = pickle.dumps({
            "format": CACHE_FORMAT, "key": self.key, "max_frames": self.max_frames,
            "frames": len(self.sps), "plane_seg": self.plane_seg,
            "frame0_full": zlib.compress(self.frame0_full, 6),
            "pre_deltas": self.pre_deltas, "post_deltas": self.post_deltas,
            "plane_refs": self.plane_refs, "sps": self.sps, "planes": self.planes,
        }, protocol=pickle.HIGHEST_PROTOCOL)
        path.write_bytes(zlib.compress(blob, 6))


def load_cache(path: Path, key: str, max_frames):
    """Load + validate a cache; None if missing/mismatched (caller falls back to the VM)."""
    if not path.is_file():
        return None
    try:
        d = pickle.loads(zlib.decompress(path.read_bytes()))
    except Exception:
        return None
    if d.get("format") != CACHE_FORMAT or d.get("key") != key:
        return None
    # the walk frames are keyed to BOUNDARIES only implicitly, so serve EXACT budget matches only
    # (a different budget shadows a different frame count -- fall back to the live oracle)
    if max_frames != d.get("max_frames"):
        return None
    return d


def iter_cached_frames(d):
    """Yield ``(pre_full_1mb: bytearray, post_dgroup: bytes, sp)`` per cached walk frame.

    ``pre_full_1mb`` is rebuilt as: frame-0's full machine state, with the rolling DGROUP window and
    the current tile plane overlaid -- everything else the walk reads (code, dispatch tables) is
    static.  The caller may mutate the yielded buffer (a fresh copy per frame).
    """
    base_full = bytearray(zlib.decompress(d["frame0_full"]))
    plane_seg = d["plane_seg"]
    dg_off = DGROUP * 16
    dgroup = bytearray(base_full[dg_off:dg_off + 0x10000])
    planes = d["planes"]
    plane_cache: dict = {}
    for i in range(d["frames"]):
        pre_delta = d["pre_deltas"][i]
        if pre_delta is not None:
            _apply(dgroup, pre_delta)
        ref = d["plane_refs"][i]
        plane = plane_cache.get(ref)
        if plane is None:
            plane = zlib.decompress(planes[ref])
            plane_cache = {ref: plane}      # keep only the current plane decompressed
        pre_full = bytearray(base_full)
        pre_full[dg_off:dg_off + 0x10000] = dgroup
        pre_full[plane_seg * 16:plane_seg * 16 + PLANE_SIZE] = plane
        post = bytearray(dgroup)
        _apply(post, d["post_deltas"][i])
        yield pre_full, bytes(post), d["sps"][i]
        dgroup = post
