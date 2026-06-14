# Bootstrap/static-runtime boundary

OVERKILL should be treated as two related but different systems:

```text
original files / outer shell / unpacker / startup materialization
        ↓
canonical initialized inner-game image + deterministic derived assets
        ↓
clean source-port runtime
```

The first system is archaeology and extraction.  The second system is the actual
source-port target.

## Source-of-truth assets

The only canonical inputs are the original game files:

```text
assets/OVERKILL
assets/OVERKILL.EXE
```

Generated convenience files must not come back as source inputs:

```text
assets/OVERKILL.UNLZEXE.EXE
assets/OVERKILL.OVERLAY.BIN
```

If an unpacked image, overlay blob, screen dump, driver body, or asset table is
needed, it must be produced deterministically by a tool from the original files
and treated as a build/evidence artifact.

## What belongs to bootstrap

Bootstrap includes code and behavior that prepares the inner game but is not a
stable gameplay island:

- the text-mode launcher and adapter selector in `assets/OVERKILL.EXE`;
- the original extensionless `OVERKILL` MZ/container startup path;
- `32FF:*` inner unpack/self-relocation code;
- optional AdLib/Roland driver loading into `2032:*`;
- startup screen, menu, font, sprite, and table materialization.

This code may be emulated, traced, snapshotted, and used to build artifacts.  It
should not be lifted as final gameplay/source-port architecture unless a small
piece is still needed as a deterministic codec or file-format rule.

## What belongs to the target runtime

The target runtime should start from a canonical initialized inner-game state and
extracted assets.  In other words, the clean source port should eventually do
this:

```text
load static bundle → initialize high-level runtime state → run menu/gameplay
```

not this:

```text
DOS MZ load → outer launcher → unpacker → relocation bootstrap → inner game
```

The VM still follows the full original path while hooks are being verified,
because the original binary remains the oracle.  The final port should replace
that path with explicit static data and source code.

## Current known boundary facts

The importable manifest lives in:

```text
overkill/bootstrap_boundary.py
```

Write it with:

```bash
python -m overkill.cli bootstrap-boundary --video tandy --sound adlib --out artifacts/static_runtime_boundary.json
```

The current manifest records:

- first confirmed transfer into relocated inner runtime code: `1010:95C9`;
- current high-level game/frame orchestration frontier: `1010:D007`;
- level-select input selector frontier: `1010:D445`;
- compact inner PSP selector tails, for example Tandy + AdLib is `0D 02 41`;
- important initial-state cells such as `CS:95BC`, `DS:0055`, and optional driver
  code at `2032:0000`.

These are evidence frontiers, not a promise that every downstream system is
semantically clean yet.

## Runtime self-modifying code policy

Runtime-installed code bodies are not preserved as Python-level self-modifying
code.  The required transformation is:

```text
observed live bytes → named variant → byte guard → explicit static Python logic
```

For example, `1010:5E42` is now classified as bootstrap materialization: the
transient `32FF:*` code installs a gameplay body over unrelated cold bytes.  The
accepted body is guarded by signature and implemented as normal Python in the
movement island.  Unknown live bytes fail loudly.

## Derived assets policy

Screens and data produced by bootstrap are assets, not runtime architecture.
Examples:

- splash and adapter-selector text pages;
- intro/menu/level-select graphics;
- fonts, tiles, sprites, planar buffers;
- planet/level metadata and object tables;
- optional sound-driver blobs and captured OPL register streams.

The desired long-term shape is a deterministic extractor that creates a static
bundle from the original files.  The source-port runtime consumes that bundle;
it does not run the historical loader on every normal launch.

## Engineering rule

When a bug appears after switching from generated unpacked files to original
assets, first ask which side of the boundary it belongs to:

```text
bootstrap/extraction bug?
  missing PSP tail, driver load, mode set, memory materialization, asset decode

runtime/source-port bug?
  bad hook assumption, wrong object/selector semantics, renderer state, input loop
```

Fix the VM faithfully at the lowest layer, then record the fact in the boundary
manifest or the relevant island document.  Do not patch around the symptom by
reintroducing noncanonical generated assets.

## Static runtime bundle materializer

The boundary is now executable, not only prose.  Use this command to run the
original packed/container startup with a compact selector tail, stop at an
inner-runtime frontier, and write a canonical initialized image:

```bash
python -m overkill.cli static-runtime-bundle assets/OVERKILL \
  --game-root assets \
  --video tandy \
  --sound adlib \
  --stop-at 1010:D007 \
  --out-dir artifacts/static_runtime_bundle
```

The output directory is a normal snapshot plus `static_runtime_bundle.json`:

```text
artifacts/static_runtime_bundle/
  memory_1mb.bin
  state.json
  trace_tail.txt
  static_runtime_bundle.json
```

The bundle manifest currently records:

- the compact PSP tail, such as `0D 02 41` for Tandy + AdLib;
- whether the requested frontier was reached;
- the full 1 MiB memory hash;
- named hashes for the PSP, relocated `1010:*` inner runtime, and optional
  `2032:*` sound-driver area when present;
- small bootstrap-produced globals such as `CS:95BC`, `DS:0055`, and
  `DS:95DA`;
- the prose boundary manifest that explains which parts are extraction-only.

This is intentionally still a low-level initialized image.  Future extractor
passes should promote screens, fonts, tables, sprites, level metadata, and sound
driver blobs into separate deterministic artifacts, but they should be derived
from this original-file bootstrap path rather than checked in as hand-made
source inputs.

### CLI launch-tail guardrail

Cold-start `trace` and `snapshot` now accept the same canonical launch selectors:

```bash
python -m overkill.cli snapshot assets/OVERKILL \
  --game-root assets \
  --video tandy \
  --sound adlib \
  --stop-at 1010:D007 \
  --out-dir artifacts/evidence/snapshot_tandy_adlib_d007
```

Use `--dos-args` only for deliberate experiments with raw PSP command tails.
Normal OVERKILL runs should prefer `--video`/`--sound` so we do not accidentally
recreate the invalid ASCII-tail or empty-tail startup bugs.
