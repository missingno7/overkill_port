"""Pure collision-domain records for recovered OVERKILL systems."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ViewContactCenter:
    """Prepared center words used by the 1010:8331 contact-window test."""

    x_word: int
    y_word: int


@dataclass(frozen=True, slots=True)
class RectContactResult:
    """Pure result of an object-vs-view rectangle/contact test."""

    hit: bool


@dataclass(frozen=True, slots=True)
class ProbePoint:
    """Pure point/probe words used by object-centered collision scans."""

    x_word: int
    y_word: int
