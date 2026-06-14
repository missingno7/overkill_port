# Package Boundary

The repository has two first-party packages with intentionally different roles.

## `dos_re`

`dos_re` is the reusable reverse-engineering environment.  It contains only
machinery that can plausibly be reused by another DOS RE project:

- 8086 CPU state and interpreter,
- 20-bit memory and MZ loading,
- narrow DOS/BIOS/port services,
- interrupt and keyboard plumbing,
- generic hook registry,
- generic runtime and snapshot helpers,
- reusable differential frame-verification engine and artifact writer.

`dos_re` must not import `overkill` or know OVERKILL addresses, islands,
filenames, command-tail bytes, frame hooks, sound-driver locations, or gameplay
concepts.

## `overkill`

`overkill` is the reverse-engineered game result.  It contains all knowledge that
only makes sense for OVERKILL:

- canonical command-tail construction,
- bootstrap/static-runtime boundary and bundle materialization,
- exact `CS:IP` hooks,
- hook-verifier metadata and frame-verifier adapters that know OVERKILL waits, frame boundaries, video memory layouts, and renderers,
- coverage islands and symbol classification,
- asset codecs, overlay loading, renderer helpers, sound-driver behavior,
- gameplay/object/collision/game-state lifted logic.

New lifted code should move into coherent modules under `overkill/`; the
address-facing hook registration surface is `overkill/hooks.py`.

## `nuked_opl3`

`nuked_opl3` is vendored third-party code plus a small Python CFFI wrapper. It
may be imported by the SDL viewer as an optional PCM backend for AdLib/YM3812
register writes, but it must stay independent of both `dos_re` and `overkill`.

Do not put game logic, VM hooks, timing policy, or OVERKILL-specific register
trace handling inside this package. The package should remain reusable as a
plain OPL2/OPL3 emulator binding.

## Boundary rule

If a module needs a literal address such as `1010:D007`, a symbol/island name, an
OVERKILL asset path, or a field in the game's data segment, it belongs in
`overkill`, not `dos_re`.

If a module can operate on an arbitrary DOS MZ program with no OVERKILL-specific
knowledge, it belongs in `dos_re`.

## Documentation boundary

Documentation follows the same rule as code:

- reusable methodology and generic verification/runtime notes belong in
  `docs/dos_re/`;
- OVERKILL addresses, islands, assets, current status, runtime findings, and
  source-port design notes belong in `docs/overkill/`;
- cross-package dependency-direction rules belong in `docs/architecture/`.

Do not create new durable documents directly under `docs/` except for the
`docs/README.md` map.
