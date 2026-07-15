# Vendored Third-Party Components

Third-party code lives outside both first-party role packages:

- `dos_re/` remains the reusable DOS reverse-engineering framework (a git
  submodule, not vendored code).
- `overkill/` remains the OVERKILL-specific reverse-engineered game layer.
- `pynuked_opl3` is optional third-party audio synthesis support -- `dos_re`'s
  own submodule (`dos_re/pynuked_opl3/`), not vendored here at all.

## OPL3 synthesis: `dos_re.audio_sink.load_opl3()`

Every audio-producing call site (the SDL viewer, `play_native`'s native music sink,
`scripts/render_demo_music.py`) gets its OPL3 backend through this ONE function --
never import `pynuked_opl3` or `dos_re.opl3_fast` directly. It picks between two backends,
same choice on every interpreter:

- **`opl3-fast`** (`dos_re.opl3_fast`) -- a numpy approximate synth, ~50x real-time on
  CPython. **No build step; this is the everyday default.** Perceptually indistinguishable
  from the exact chip on real game music in blind A/B (calibration + evidence in its module
  docstring/tests).
- **`nuked-opl3-c`** (`pynuked_opl3`) -- a CFFI binding around the Nuked-OPL3 Yamaha
  OPL2/OPL3 emulator, bit-exact, native speed. Only used when its extension happens to be
  compiled; this is what shipped releases bundle.

The VM and the game logic do not depend on either backend being built: `--sound adlib`
always runs the original driver, models AdLib detection, records and forwards register
writes, and remains deterministic -- audible FM output works out of the box via opl3-fast.

Build the `pynuked_opl3` extension only if you specifically want bit-exact synthesis:

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
