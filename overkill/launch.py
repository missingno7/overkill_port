"""OVERKILL original-container launch selector helpers."""

from __future__ import annotations

_VIDEO_SELECTOR = {"cga": 0x00, "ega": 0x01, "tandy": 0x02}
_SOUND_SELECTOR = {"pc": None, "adlib": ord("A"), "roland": ord("R")}


def build_command_tail(video: str, sound: str = "pc") -> bytes:
    """Return the PSP command tail expected by the extensionless OVERKILL MZ.

    The large original ``OVERKILL`` executable is a packed/container program, but
    after unpack it starts the inner game by reading three raw bytes from the PSP:

    * ``PSP:81``: legacy option byte, not an ASCII switch introducer here;
    * ``PSP:82``: video mode selector (0=CGA, 1=EGA, 2=Tandy/PCjr);
    * ``PSP:83``: optional sound driver selector (``A``=AdLib, ``R``=Roland).

    Plain ASCII tails such as ``" /A /T"`` trigger the sound parser but put ``/``
    in ``PSP:82``, which the inner startup clamps to EGA.  This compact tail keeps
    video and sound selection independent.
    """
    try:
        video_byte = _VIDEO_SELECTOR[video]
    except KeyError as exc:  # pragma: no cover - argparse normally enforces this
        raise ValueError(f"unknown OVERKILL video mode {video!r}") from exc
    try:
        sound_byte = _SOUND_SELECTOR[sound]
    except KeyError as exc:  # pragma: no cover - argparse normally enforces this
        raise ValueError(f"unknown OVERKILL sound mode {sound!r}") from exc

    if sound_byte is None:
        if video == "cga":
            # Preserve the original compact no-argument CGA startup path.
            return b""
        return bytes((0x0D, video_byte))
    return bytes((0x0D, video_byte, sound_byte))
