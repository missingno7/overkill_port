# OVERKILL source-port scaffold

This project is a working scaffold for a game-specific DOS 8086 interpreter that can execute original OVERKILL code and gradually replace known ASM routines with readable Python handlers.

It is deliberately narrow: the goal is **not** to emulate all of DOS, but to build the smallest reliable runtime that can run this one game's original binary and make reverse engineering productive.

## Included assets

- `assets/OVERKILL.UNLZEXE.EXE` — the final LZEXE-unpacked bound executable from the RE pack.
- `assets/OVERKILL.OVERLAY.BIN` — preserved large overlay/trailing data from the original no-extension `OVERKILL` file.
- `assets/OVERKILL`, `assets/OVERKILL.EXE`, `assets/OVERKILL.DOC` — original files copied in so DOS file-open calls can resolve game data.

## Quick start

```bash
python -m overkill_port.cli info assets/OVERKILL.UNLZEXE.EXE
python -m overkill_port.cli trace assets/OVERKILL.UNLZEXE.EXE --steps 5000 --out trace_start.txt
python -m overkill_port.cli snapshot assets/OVERKILL.UNLZEXE.EXE --game-root assets --steps 100000 --trace-tail 128 --out-dir artifacts/snapshot_after_bootstrap_100k
python -m pytest tests -q
```

Or use the convenience scripts:

```bash
python scripts/trace_start.py
python scripts/make_runtime_snapshot.py
python scripts/profile_hotspots.py 2000000          # hottest interpreted addresses
python scripts/render_cga.py --steps 2000000 --out frame.png   # decode B800 -> PNG
python scripts/play.py                              # interactive Tk viewer, default CGA
python scripts/play.py --video ega                  # launch/render using the original /E EGA selector
```

## What works now

- DOS MZ parser and loader.
- 20-bit real-mode memory model.
- Minimal PSP creation.
- Runtime segment setup matching a DOS EXE launch.
- Relocation support, even though this unpacked target currently has zero relocation entries.
- Initial 8086 interpreter core with the instructions needed by the first bootstrap and loader path.
- DOS/BIOS hook layer for early file/video/timer/keyboard/memory calls.
- Port IO layer with a minimal VGA `0x3DA` retrace model.
- Replacement hook registry for gradual source-porting.
- First verified replacement: `1010:C916 overkill_file_checksum_loop`.
- Trace output with call depth and clearer CALL/RET/JMP/INT annotations.
- Full memory snapshot writer: `memory_1mb.bin` + `state.json` + trace tail.

## Current RE status

The interpreter now boots OVERKILL all the way into its **main loop** and renders
real frames.  Highlights of the path: post-inner-unpacker entry at `1010:95C9`,
verified checksum/LZ/RLE/4-plane startup hooks, the DOS PSP heap fix, a verified
reprogrammed-IRQ0 timer-tick model (`1010:0679`) that unblocks the per-frame
timing wait, and the mode-0 frame-present blit (`1010:447B`) that copies the work
buffer to `B800h` video memory.

Decoding `B800h` as CGA 320x200 4-colour shows the actual OVERKILL outfitting/shop
screen (player ship, HUD, `WEAPON/MISSILES/DRONE/GADGETS/UPGRADES`).  See
`scripts/render_cga.py` (frame -> PNG) and `scripts/play.py` (interactive Tk
viewer with keyboard input).  CGA is the default stable path.  `scripts/play.py --video ega` now passes the documented `/E` PSP command tail and decodes the mode-1 `A000h` EGA shadow planes as 320x200 16-colour output.

Next targets are the remaining hot per-frame render routines (`1010:CCAA`
dirty-word copy, `1010:41A6` variable-width interlaced blit) and the first
input-dependent paths exercised by interactive play.

See:

- `RUN_STATUS.md`
- `docs/runtime_findings.md`
- `symbols.json`
- `artifacts/snapshot_after_bootstrap_100k/state.json`

## Project layout

```text
overkill_port/
  mz.py          MZ parsing
  memory.py      real-mode memory + loader
  cpu.py         dependency-free 8086 interpreter core
  dos.py         narrow DOS/BIOS/port services
  hooks.py       source-port replacement hooks
  replacements.py built-in verified OVERKILL replacements
  runtime.py     OVERKILL runtime wiring
  snapshot.py    memory/state snapshot helpers
  cli.py         info/trace/snapshot commands
assets/          unpacked target binary, original files and overlay
artifacts/       generated runtime snapshots
docs/            design notes and findings
scripts/         convenience runners
tests/           CPU and replacement regression tests
```

## Intended workflow

1. Generate an execution trace from the original code.
2. Match trace addresses against static disassembly and the runtime memory snapshot.
3. Name routines and data tables in `symbols.json`.
4. Add replacement hooks for decoded routines.
5. Verify each replacement with before/after CPU/memory snapshots or regression tests.
6. Keep running the rest of the original binary until enough of the game has been lifted into source code.
