"""SDL/pygame display backend for the interactive OVERKILL viewer (``play.py``).

OVERKILL used to render through Tk; profiling showed two stacked costs per
displayed frame that motivated moving to SDL:

  * ``render_*_ppm`` builds a *scaled* RGB byte string in a pure-Python pixel
    loop (~3.1 ms at scale 2), then it is written to a temp ``.ppm`` file and a
    brand-new ``tk.PhotoImage(file=...)`` is parsed back from disk every frame
    (~2.1 ms);  and
  * Tk's ``root.after(1, ...)`` repaint scheduling is ~15 ms-granular on Windows,
    so the emulator stalls in ``FrameSync.publish_and_wait`` waiting for the UI.

This backend instead:

  * decodes the video memory with vectorised NumPy at *native* 320x200 (so the
    Python pixel work is ~0.8 ms and independent of ``--scale``);
  * uploads it straight to an SDL surface (no temp file, no per-frame PhotoImage)
    and lets SDL scale it to the window; and
  * polls ``FrameSync`` directly from the pygame loop, so the present round-trip
    is ~1-2 ms instead of ~15 ms.

The decoders are pixel-identical to the reference ``render_*_ppm`` functions in
``render_cga.py`` (asserted by ``tests/test_render_rgb.py``); those PPM renderers
remain as the headless PNG-dump tool and as the decode oracle, while this module
is what the live viewer uses.

``play.py`` imports this module only when it actually launches the viewer, so the
core runtime, the PNG tool and the tests do not require ``pygame``.
"""
from __future__ import annotations

from typing import Callable

import numpy as np

from render_cga import (
    CGA_PALETTES,
    EGA_BYTES_PER_ROW,
    EGA_LEGACY_PLANE_STRIDE,
    EGA_PALETTE,
    EGA_SHADOW_BASE,
    EGA_PLANE_STRIDE,
    TANDY_BANK_STRIDE,
    TANDY_BYTES_PER_ROW,
)

WIDTH, HEIGHT = 320, 200

_EGA_PAL = np.array(EGA_PALETTE, dtype=np.uint8)  # (16, 3)


def render_ega_rgb(mem: bytes, start_offset: int = 0, seg: int = 0xA000) -> np.ndarray:
    """Decode the EGA shadow planes to a native (200, 320, 3) RGB array.

    Mirrors ``render_cga.render_ega_ppm`` exactly, including its three accepted
    buffer layouts (distinguished by length): a tight view of just the four shadow
    planes (planes at offset 0, the layout the live viewer publishes), full runtime
    memory (planes at ``EGA_SHADOW_BASE``), or the legacy in-aperture layout for old
    byte snapshots.  Each byte is eight horizontal pixels (MSB first) and the colour
    index is one bit from each plane.  ``start_offset`` is the CRTC display-start
    byte offset (the original wraps it at 16 bits per row).
    """
    arr = np.frombuffer(mem, dtype=np.uint8)
    if arr.size == EGA_PLANE_STRIDE * 4:
        base, stride = 0, EGA_PLANE_STRIDE
    elif arr.size >= EGA_SHADOW_BASE + EGA_PLANE_STRIDE * 4:
        base, stride = EGA_SHADOW_BASE, EGA_PLANE_STRIDE
    else:
        base, stride = (seg & 0xFFFF) * 16, EGA_LEGACY_PLANE_STRIDE
    start = start_offset & 0xFFFF
    rowbase = (start + np.arange(HEIGHT) * EGA_BYTES_PER_ROW) & 0xFFFF
    off = (rowbase[:, None] + np.arange(EGA_BYTES_PER_ROW)[None, :]) & 0xFFFF  # (200,40)
    color = np.zeros((HEIGHT, EGA_BYTES_PER_ROW, 8), dtype=np.uint8)
    for plane in range(4):
        plane_bytes = arr[base + plane * stride + off]              # (200,40)
        bits = np.unpackbits(plane_bytes[..., None], axis=2)        # (200,40,8) MSB-first
        color |= bits << plane
    return _EGA_PAL[color.reshape(HEIGHT, WIDTH)]


def render_cga_rgb(mem: bytes, palette: str = "1h") -> np.ndarray:
    """Decode CGA B800h 320x200x4 to a native (200, 320, 3) RGB array.

    Mirrors ``render_cga.render_ppm``: interlaced layout
    ``offset = (y & 1)*0x2000 + (y >> 1)*80``; each byte is four pixels, two bits
    each, most-significant pixel first.
    """
    arr = np.frombuffer(mem, dtype=np.uint8)
    pal = np.array(CGA_PALETTES[palette], dtype=np.uint8)           # (4,3)
    base = 0xB8000
    y = np.arange(HEIGHT)
    rowbase = base + (y & 1) * 0x2000 + (y >> 1) * 80               # (200,)
    cols = arr[(rowbase[:, None] + np.arange(80)[None, :])]         # (200,80)
    idx = np.stack([(cols >> s) & 3 for s in (6, 4, 2, 0)], axis=2)  # (200,80,4)
    return pal[idx.reshape(HEIGHT, WIDTH)]


def render_tandy_rgb(mem: bytes) -> np.ndarray:
    """Decode Tandy/PCjr B800h 320x200x16 packed graphics to (200, 320, 3) RGB.

    Mirrors ``render_cga.render_tandy_ppm``: four 8 KiB banks,
    ``offset = (y & 3)*0x2000 + (y >> 2)*160 + x_byte``; each byte is two pixels,
    high nibble first.
    """
    arr = np.frombuffer(mem, dtype=np.uint8)
    base = 0xB8000
    y = np.arange(HEIGHT)
    rowbase = base + (y & 3) * TANDY_BANK_STRIDE + (y >> 2) * TANDY_BYTES_PER_ROW
    cols = arr[(rowbase[:, None] + np.arange(TANDY_BYTES_PER_ROW)[None, :])]  # (200,160)
    idx = np.stack([(cols >> 4) & 0x0F, cols & 0x0F], axis=2)                  # (200,160,2)
    return _EGA_PAL[idx.reshape(HEIGHT, WIDTH)]


# pygame key -> XT make scan code.  Letters/digits use pygame's lowercase names;
# the named keys cover the OVERKILL controls (Q/A/O/P move, Z/Space fire) plus the
# usual editing/arrow keys, matching the Tk KEYSYM_SCAN table in play.py.
def _build_pygame_scan() -> dict[int, int]:
    import pygame

    name_scan: dict[str, int] = {
        "escape": 0x01, "-": 0x0C, "=": 0x0D, "backspace": 0x0E, "tab": 0x0F,
        "[": 0x1A, "]": 0x1B, "return": 0x1C, "enter": 0x1C,
        "left ctrl": 0x1D, "right ctrl": 0x1D, ";": 0x27, "'": 0x28,
        "`": 0x29, "left shift": 0x2A, "\\": 0x2B, ",": 0x33, ".": 0x34,
        "/": 0x35, "right shift": 0x36, "left alt": 0x38, "right alt": 0x38,
        "space": 0x39, "caps lock": 0x3A,
        "f1": 0x3B, "f2": 0x3C, "f3": 0x3D, "f4": 0x3E, "f5": 0x3F, "f6": 0x40,
        "f7": 0x41, "f8": 0x42, "f9": 0x43, "f10": 0x44, "f11": 0x57, "f12": 0x58,
        "up": 0x48, "down": 0x50, "left": 0x4B, "right": 0x4D,
    }
    for i, ch in enumerate("1234567890"):
        name_scan[ch] = 0x02 + i
    for i, ch in enumerate("qwertyuiop"):
        name_scan[ch] = 0x10 + i
    for i, ch in enumerate("asdfghjkl"):
        name_scan[ch] = 0x1E + i
    for i, ch in enumerate("zxcvbnm"):
        name_scan[ch] = 0x2C + i

    scan: dict[int, int] = {}
    for name, code in name_scan.items():
        try:
            key = pygame.key.key_code(name)
        except (ValueError, AttributeError):
            continue  # name not known to this SDL build; skip it
        scan[key] = code
    return scan


def run_sdl_ui(
    *,
    args,
    frame_sync,
    keyboard,
    stop,
    status: dict,
    counters: dict,
    queue_snapshot_save: Callable[[], None],
    queue_dos_key: Callable[[int, str], None],
    ega_render_start: Callable[[int], int],
    live_memory: Callable[[], bytes],
    live_display_start: Callable[[], int],
) -> None:
    """Run the pygame display loop until the window closes or ``stop`` is set.

    The emulator thread is already running and publishing one frame at a time
    through ``frame_sync``; this loop consumes those frames, decodes them with
    NumPy, scales them with SDL, and feeds keyboard input back to ``keyboard``.
    """
    import pygame

    video = args.video
    palette = args.palette
    scale = max(1, int(args.scale))

    if video == "ega":
        decode = lambda snap, ds: render_ega_rgb(snap, ds)
    elif video == "tandy":
        decode = lambda snap, ds: render_tandy_rgb(snap)
    else:
        decode = lambda snap, ds: render_cga_rgb(snap, palette)

    pygame.init()
    pygame.display.set_caption(f"OVERKILL (emulated {video.upper()})  -  Q/A/O/P move, Z/Space fire")
    screen = pygame.display.set_mode((WIDTH * scale, HEIGHT * scale), pygame.RESIZABLE)
    scan = _build_pygame_scan()

    def present(snapshot: bytes, display_start: int) -> None:
        rgb = decode(snapshot, display_start)                        # (200,320,3)
        surf = pygame.image.frombuffer(rgb.tobytes(), (WIDTH, HEIGHT), "RGB")
        win_w, win_h = screen.get_size()
        fit = max(1, min(win_w // WIDTH, win_h // HEIGHT))
        target = (WIDTH * fit, HEIGHT * fit)
        if fit != 1:
            surf = pygame.transform.scale(surf, target)
        x = (win_w - target[0]) // 2
        y = (win_h - target[1]) // 2
        screen.fill((0, 0, 0))
        screen.blit(surf, (x, y))
        pygame.display.flip()

    def caption() -> None:
        base = f"OVERKILL (emulated {video.upper()})  -  Q/A/O/P move, Z/Space fire"
        c = counters
        tail = (f"visible={c['visible']['n']} boundaries={c['boundary']['n']} "
                f"blits={c['blits']['n']} timers={c['timers']['n']} retraces={c['retraces']['n']}")
        if "direct_video" in c:
            tail += f" direct={c['direct_video']['n']}"
        if c["boundary"]["n"] == 0 and not status["text"]:
            pygame.display.set_caption("OVERKILL - decoding startup assets, please wait (~10-15s)...")
        elif status["text"]:
            pygame.display.set_caption(f"{base}  |  {status['text']}  |  {tail}")
        else:
            pygame.display.set_caption(f"{base}  |  {tail}")

    last_caption = 0.0
    try:
        running = True
        while running and not stop.is_set():
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    running = False
                elif ev.type == pygame.VIDEORESIZE:
                    screen = pygame.display.set_mode((max(WIDTH, ev.w), max(HEIGHT, ev.h)), pygame.RESIZABLE)
                elif ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_F12:
                        queue_snapshot_save()
                    else:
                        sc = scan.get(ev.key)
                        if sc is not None:
                            keyboard.post_down(sc)
                            if queue_dos_key is not None:
                                queue_dos_key(sc, getattr(ev, "unicode", ""))
                elif ev.type == pygame.KEYUP:
                    sc = scan.get(ev.key)
                    if sc is not None:
                        keyboard.post_up(sc)

            pending = frame_sync.take_pending()
            if pending is not None:
                frame_id, snapshot, display_start = pending
                present(snapshot, display_start)
                frame_sync.mark_displayed(frame_id)
            elif getattr(args, "no_present_sync", False):
                ds = ega_render_start(live_display_start()) if video == "ega" else 0
                present(live_memory(), ds)
            else:
                # No frame ready: yield the GIL so the emulator thread runs.
                pygame.time.wait(1)

            now = pygame.time.get_ticks() / 1000.0
            if now - last_caption > 0.25:
                caption()
                last_caption = now
    finally:
        stop.set()
        frame_sync.close()
        pygame.quit()
