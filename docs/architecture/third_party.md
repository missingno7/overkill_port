# Vendored Third-Party Components

Third-party code lives outside both first-party role packages:

- `dos_re/` remains the reusable DOS reverse-engineering framework.
- `overkill/` remains the OVERKILL-specific reverse-engineered game layer.
- `nuked_opl3/` is vendored optional third-party audio synthesis support.

## `nuked_opl3`

`nuked_opl3` is a vendored CFFI binding around the Nuked-OPL3 Yamaha OPL2/OPL3
emulator.  It is used only by the SDL viewer to turn the YM3812 register stream
emitted by OVERKILL's original AdLib driver into audible PCM.

The VM and the game logic do not depend on the compiled extension.  Without it,
`--sound adlib` still runs the original driver, models AdLib detection, records
and forwards register writes, and remains deterministic; only audible FM output
is unavailable.

Build the extension in place when audio synthesis is desired:

```bash
python -m pip install -e .[adlib]
python -m nuked_opl3._ffi_build
```

The generated extension artifact is local build output and must not be checked
in:

```text
nuked_opl3/_opl3_cffi*.pyd
nuked_opl3/_opl3_cffi*.so
nuked_opl3/_opl3_cffi*.dylib
```

## Ownership rule

`nuked_opl3` must not import `dos_re` or `overkill`.  It should remain reusable as
a plain OPL emulator binding.  OVERKILL-specific concerns such as the original
AdLib driver segment, port-capture timing, SDL chunk buffering, underrun status,
and game audio policy belong in `overkill/` or `scripts/sdl_view.py`, not in the
vendored package.

## Licensing

The vendored Nuked-OPL3 core is LGPL-2.1-or-later.  Keep `nuked_opl3/LICENSE`
with the package and do not remove the upstream notices in `vendor/opl3.c` or
`vendor/opl3.h`.
