"""Adapters between original DOS execution state and pure recovered code.

Adapters are the only recovered-layer modules that should translate CPU/memory
state into domain records, run pure systems, then project results back to the
ASM-compatible hook world.
"""
