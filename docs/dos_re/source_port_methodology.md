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
