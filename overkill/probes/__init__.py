"""Temporary observation / diagnostic tools.

Probes observe the original VM/recovered state for discovery. They are NOT part
of the recovered runtime and carry no game logic — evidence-gathering only, to be
deleted or promoted to a regression test once the finding is recovered. See
`docs/overkill/rescue_refactor.md`.
"""
