# OVERKILL interpreter/source-port design

This is intentionally not a general DOSBox replacement. It is a migration scaffold for one game:

1. load the original DOS MZ executable exactly enough to reach real game code,
2. execute original 8086 instructions and produce deterministic traces,
3. identify routines by `CS:IP`,
4. replace those routines one by one with Python code,
5. later move stable Python replacements into a cleaner engine/source port.

## Runtime pieces

- `mz.py` parses DOS MZ headers, load modules, relocation tables and overlay/trailing data.
- `memory.py` provides a 20-bit real-mode memory model and a minimal PSP.
- `cpu.py` contains a dependency-free 8086 interpreter core with a practical subset of instructions already used by OVERKILL startup.
- `dos.py` provides narrow DOS/BIOS/port hooks: text output, file open/read/seek/close, memory APIs, video mode calls, timer, keyboard placeholders and VGA status-port behavior.
- `hooks.py` contains the replacement mechanism used for gradual source-porting.
- `replacements.py` contains verified built-in game-specific replacements.
- `snapshot.py` writes full memory/state snapshots for reverse-engineering checkpoints.
- `runtime.py` wires all components together for the unpacked OVERKILL binary.

## Address model

The DOS loader puts the PSP at `1000h` and the EXE load module at `1010h` by default. Therefore MZ `CS:IP 1366:0010` starts executing at real-mode address:

```text
load segment = 1010h
runtime CS   = 1010h + 1366h = 2376h
runtime IP   = 0010h
physical     = 2376h * 16 + 0010h = 23770h
```

The original static disassembly in the RE pack uses load-module offsets. The helper rule is:

```text
runtime segment = load_segment + mz_relative_segment
load_module_offset = mz_relative_segment * 16 + offset
```

Be careful: OVERKILL modifies/unpacks code into memory. For many addresses after `1010:95C9`, the runtime memory snapshot is more authoritative than the original file load module.

## Replacement hooks

A replacement is registered against the runtime `CS:IP` where the original routine starts:

```python
from overkill_port.hooks import registry, return_near

@registry.replace(0x1234, 0x5678, "decoded_original_routine")
def decoded_original_routine(cpu):
    # emulate routine side effects here
    cpu.s.ax = 0
    return_near(cpu)
```

This lets the rest of the binary continue running normally while one known routine is implemented as readable source.

The first real replacement is `overkill_file_checksum_loop` at `1010:C916`. It replaces:

```asm
mov dl, [si]
add ax, dx
add ah, al
inc si
loop C916
```

The replacement is covered by a regression test that compares AX/DX/CX/SI/FLAGS against the original instruction sequence.

## Snapshot workflow

Generate a post-bootstrap snapshot with:

```bash
python scripts/make_runtime_snapshot.py
```

or directly:

```bash
python -m overkill_port.cli snapshot assets/OVERKILL.UNLZEXE.EXE \
  --game-root assets \
  --steps 100000 \
  --trace-tail 128 \
  --out-dir artifacts/snapshot_after_bootstrap_100k
```

This writes:

```text
memory_1mb.bin   complete real-mode memory image
state.json       CPU, loader, DOS, hook and port metadata
trace_tail.txt   capped execution trace tail
```

## Current bootstrap progress

The initial LZEXE layers are already unpacked in `assets/OVERKILL.UNLZEXE.EXE`, but the binary still contains an internal bootstrap/self-relocation stage. The interpreter now gets through that stage far enough to reach relocated game code at `1010:95C9`, set interrupt vectors, resize the DOS memory block, open/read/seek/close the original `OVERKILL` data file, and run beyond the original checksum loop and VGA retrace wait.

The current 100k-step snapshot stops in a hot path around `1010:45CB`. This appears to be self-modified graphics/bit expansion code. The true menu/game main loop is still unknown.

## Fidelity notes

The interpreter is currently permissive for hardware ports and some DOS memory APIs. It returns simple placeholder values rather than trying to fully emulate DOS/VGA/OPL yet. That is intentional for bootstrap progress, but once the game loop is reached these areas should become explicit subsystems:

- VGA memory and port model,
- keyboard/input queue,
- timer tick source,
- PC speaker / OPL hooks,
- file/resource loader with named source-level wrappers.
