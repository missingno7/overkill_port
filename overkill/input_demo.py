"""Compatibility shim for the reusable DOS input-demo implementation.

The deterministic demo recorder/replayer is VM infrastructure, not an
OVERKILL-specific subsystem.  New code should import from ``dos_re.input_demo``.
This module remains only so older scripts/tests or archived experiments keep
working while the project transitions.
"""
from __future__ import annotations

from dos_re.input_demo import (  # noqa: F401
    DEMO_VERSION,
    InputDemoEvent,
    InputDemoPlayback,
    InputDemoRecorder,
    bios_key_value_from_scancode,
    dos_key_value,
)
