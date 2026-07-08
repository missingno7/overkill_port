# Vendored Third-Party Components

Third-party code lives outside both first-party role packages:

- `dos_re/` remains the reusable DOS reverse-engineering framework (a git
  submodule, not vendored code).
- `overkill/` remains the OVERKILL-specific reverse-engineered game layer.
- `pynuked_opl3` is optional third-party audio synthesis support -- `dos_re`'s
  own submodule (`dos_re/pynuked_opl3/`), not vendored here at all.

## `pynuked_opl3`

`pynuked_opl3` is a CFFI binding around the Nuked-OPL3 Yamaha OPL2/OPL3
emulator.  It is used only by the SDL viewer to turn the YM3812 register stream
emitted by OVERKILL's original AdLib driver into audible PCM.

The VM and the game logic do not depend on the compiled extension.  Without it,
`--sound adlib` still runs the original driver, models AdLib detection, records
and forwards register writes, and remains deterministic; only audible FM output
is unavailable.

Build the extension in place when audio synthesis is desired:

```bash
python -m pip install -e dos_re/  # makes both dos_re and pynuked_opl3 importable
python -m pynuked_opl3._ffi_build
```

The generated extension artifact is local build output and must not be checked
in -- this lives in `dos_re/pynuked_opl3/.gitignore`, not this repo's, since the
package is no longer vendored here.

## Ownership rule

`pynuked_opl3` must not import `dos_re` or `overkill` (enforced in its own repo).
It remains a plain OPL emulator binding. OVERKILL-specific concerns such as the
original AdLib driver segment, port-capture timing, SDL chunk buffering,
underrun status, and game audio policy belong in `overkill/` or
`scripts/sdl_view.py`, not in the vendored package.

## Licensing

The Nuked-OPL3 core is LGPL-2.1-or-later -- see `dos_re/pynuked_opl3/LICENSE`.
