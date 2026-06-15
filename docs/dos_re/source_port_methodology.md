# DOS RE Source-Port Methodology

This is the reusable part of the project method. It applies to any DOS program
that can be run inside `dos_re` and gradually replaced by verified source-level
code.

The method is:

```text
original executable -> trace/snapshot -> exact boundary -> verified hook -> domain module -> source-port code
```

## Core loop

Use the same loop for every lifted routine:

```text
observe -> classify -> choose boundary -> build oracle -> implement hook -> verify -> document -> promote
```

- **Observe** with traces, snapshots, port writes, file offsets, and frame/audio
  captures.
- **Classify** the code only as far as evidence supports.
- **Choose a boundary** that has a clear entry, exit, and observable side
  effects.
- **Build an oracle** by running the original code at that boundary.
- **Implement a hook** that preserves CPU-visible state, memory, I/O, timing
  counters, and continuation behavior.
- **Verify** by comparing reference execution against the hook or by comparing
  frame/audio/file artifacts.
- **Document** the evidence and the confidence level.
- **Promote** stable behavior out of the address-facing hook layer into a
  coherent domain module.

## Reusable rules

The original binary remains the oracle until a subsystem has enough verified
coverage to stand on its own.

Do not infer behavior from other DOS games. A reusable framework can provide CPU,
DOS, BIOS, memory, hooks, snapshots, and verification tools, but domain meaning
must come from the target program being observed.

Bootstrap, packers, overlays, and runtime-installed code should be separated from
the target source-port runtime. The bootstrap path can be executed as an oracle
or extraction layer, but the final port should prefer a deterministic static
bundle or explicit decoded assets.

## Package ownership

Reusable tooling belongs in `dos_re` when it can operate on an arbitrary DOS MZ
program without target-specific addresses, assets, islands, or semantics.

Target-specific knowledge belongs in that target's package. In this repository,
that package is `overkill`. See `docs/architecture/package_boundary.md` for the
hard dependency rules.


## Minimal agent/sandbox test loop

When working on the reusable layer, start with the target-neutral smoke scope:

```bash
python scripts/run_tests.py --scope dos-re
```

This path intentionally needs only the Python standard library.  It does not load
OVERKILL assets, open SDL/pygame, or run the long game hook suite.  Each test is
run in an isolated worker with a timeout by default, which makes it safe for
automated agents to run even while CPU or verifier bugs are being investigated.
Use explicit file/function filters for narrow OVERKILL checks when needed:

```bash
python scripts/run_tests.py tests/test_overkill_hooks.py --name 'test_object_*' --timeout 10 --fail-fast
```

Use normal `pytest` when you want the richer local developer experience and are
prepared to debug long-running integration tests.

## Reusable input demos

`dos_re.input_demo` owns deterministic input-demo recording and replay.  A demo is
not a video capture; it is a start snapshot plus VM-visible keyboard events
indexed by an emulated boundary counter.  Because the events are delivered to the
DOS runtime rather than replayed from host wall-clock timestamps, the same demo
can drive a normal run, hook verification, and frame verification.

The format is target-neutral:

- `snapshot` points at the start snapshot directory;
- `events` contains ordered `scan` and `dos_key` events;
- `metadata` is an opaque front-end dictionary for game-specific information
  such as video mode, sound mode, command tail, or executable identity.

A target package should provide only integration policy: which host key toggles
recording, which boundary counter to use, and what metadata to write.  The
recorder/replayer itself must not know target addresses, islands, renderers, or
assets.
