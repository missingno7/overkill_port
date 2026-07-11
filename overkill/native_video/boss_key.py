"""The F9 BOSS KEY fake screen (``1010:075F``).

The original's boss key switches to text mode 3 and paints a fake "SNAFU V4.2" file-manager screen at
B800 -- a convincing decoy to hide the game from a passing boss; any key restores play.  The 80x25
char/attribute screen is baked into the loaded image at segment ``0x25CC`` offset ``0x0056`` (the
``CS:[9596]`` text segment 075F copies from), so the VM-less port reads it straight from the runtime
image and renders it with the CGA text palette.
"""
from __future__ import annotations

BOSS_SCREEN_SEG = 0x25CC     # CS:[9596] -- the text-image segment 075F sets DS to
BOSS_SCREEN_OFF = 0x0056     # 075F: mov si, 0056h -- the first cell copied to B800
COLS, ROWS = 80, 25

#: the 16-colour CGA/EGA text palette (RGB): low nibble = foreground, bits 4-6 = background.
CGA_PALETTE = (
    (0x00, 0x00, 0x00), (0x00, 0x00, 0xAA), (0x00, 0xAA, 0x00), (0x00, 0xAA, 0xAA),
    (0xAA, 0x00, 0x00), (0xAA, 0x00, 0xAA), (0xAA, 0x55, 0x00), (0xAA, 0xAA, 0xAA),
    (0x55, 0x55, 0x55), (0x55, 0x55, 0xFF), (0x55, 0xFF, 0x55), (0x55, 0xFF, 0xFF),
    (0xFF, 0x55, 0x55), (0xFF, 0x55, 0xFF), (0xFF, 0xFF, 0x55), (0xFF, 0xFF, 0xFF),
)


def read_boss_screen(image_bytes: "bytes | bytearray") -> "list[tuple[int, int]]":
    """Return the boss key's 80x25 ``(char, attr)`` cells, in row-major order, from the runtime image
    (segment ``0x25CC`` offset ``0x0056`` -- the char/attribute pairs 075F blits to B800)."""
    base = BOSS_SCREEN_SEG * 16 + BOSS_SCREEN_OFF
    return [(image_bytes[base + i * 2], image_bytes[base + i * 2 + 1]) for i in range(COLS * ROWS)]


def boss_screen_text(image_bytes: "bytes | bytearray") -> "list[str]":
    """The boss screen as 25 decoded (cp437) text rows -- handy for tests / a text fallback."""
    cells = read_boss_screen(image_bytes)
    rows = []
    for r in range(ROWS):
        row = bytes(cells[r * COLS + c][0] for c in range(COLS))
        rows.append(row.decode("cp437", errors="replace"))
    return rows


def cell_colors(attr: int) -> "tuple[tuple[int,int,int], tuple[int,int,int]]":
    """(foreground, background) RGB for a text attribute byte (blink bit ignored)."""
    return CGA_PALETTE[attr & 0x0F], CGA_PALETTE[(attr >> 4) & 0x07]
