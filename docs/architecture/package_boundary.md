# Package Boundary

The repository has two first-party packages with intentionally different roles.

## `dos_re`

`dos_re` is a git submodule (https://github.com/missingno7/dos_re), not
vendored code here -- clone with `--recurse-submodules`, or
`git submodule update --init --recursive`. It contains only machinery that can
plausibly be reused by another DOS RE project (and, in fact, now is: `pre2_port`
consumes the same submodule):

- 8086 CPU state and interpreter,
- 20-bit memory and MZ loading,
- narrow DOS/BIOS/port services,
- interrupt and keyboard plumbing,
- generic hook registry,
- generic runtime and snapshot helpers,
- reusable differential frame-verification engine and artifact writer,
- target-neutral deterministic input-demo recording/replay (`dos_re.input_demo`).

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

## `pynuked_opl3`

`pynuked_opl3` is third-party code plus a small Python CFFI wrapper -- `dos_re`'s
own submodule (`dos_re/pynuked_opl3/`), not vendored in this repo at all. It may
be imported by the SDL viewer as an optional PCM backend for AdLib/YM3812
register writes, but it must stay independent of both `dos_re` and `overkill`
(enforced in its own repo).

Do not put game logic, VM hooks, timing policy, or OVERKILL-specific register
trace handling inside this package. The package should remain reusable as a
plain OPL2/OPL3 emulator binding.

## Boundary rule

If a module needs a literal address such as `1010:D007`, a symbol/island name, an
OVERKILL asset path, or a field in the game's data segment, it belongs in
`overkill`, not `dos_re`.

If a module can operate on an arbitrary DOS MZ program with no OVERKILL-specific
knowledge, it belongs in `dos_re`.  For example, input-demo storage/replay belongs
in `dos_re`; the OVERKILL viewer only supplies keybindings, boundary policy, and
metadata such as video/sound mode.

## Documentation boundary

Documentation follows the same rule as code:

- reusable methodology and generic verification/runtime notes belong in
  `docs/dos_re/`;
- OVERKILL addresses, islands, assets, current status, runtime findings, and
  source-port design notes belong in `docs/overkill/`;
- cross-package dependency-direction rules belong in `docs/architecture/`.

Do not create new durable documents directly under `docs/` except for the
`docs/README.md` map.
