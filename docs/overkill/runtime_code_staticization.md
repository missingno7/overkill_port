> **SUPERSEDED (2026-07-07).** This document is a historical plan/report from an earlier phase.
> It is NOT the current direction and may contradict the present state.  The live authorities:
> [`campaigns/README.md`](campaigns/README.md) (the operating model) →
> [`campaigns/demo_lockstep.md`](campaigns/demo_lockstep.md) (THE active campaign) →
> the TOP HEADER of [`run_status.md`](run_status.md) (the current frontier).

# Runtime-code staticization policy

OVERKILL can write executable bytes into addresses that are later called as code.
The source port must not preserve that as runtime self-modifying Python.  Treat
it as an old DOS specialization mechanism: the original program installs a small
body, and the port replaces each accepted installed body with explicit static
source code.

Target transformation:

```text
runtime self-modifying code
        ↓
observed runtime patch/code slots
        ↓
named byte variants
        ↓
static dispatch / parameters / runtime state
        ↓
flat verified Python source-port logic
```

This policy is one piece of the broader bootstrap/static-runtime boundary:
bootstrap may install or materialize code, but the source port records accepted
live bodies as static Python.  See `docs/overkill/bootstrap_static_boundary.md`.

## Hard rules

- A `CS:IP` address is not always a routine identity.  Runtime-patched addresses
  are **polyvariant code slots**.
- No hook may silently fall back because live bytes differ.
- Every accepted live-byte body must be named in `overkill/runtime_code.py`.
- Every accepted variant must have a static source owner: a normal Python
  function in the correct island.
- Live bytes may be used as an oracle/variant guard, but Python code must not
  reproduce the original self-modifying behavior by mutating Python functions or
  generating behavior at runtime.
- Unknown live bytes must raise `UnknownRuntimeCodeVariant` with enough bytes to
  add a new manifest entry.
- Installer/writer provenance is a separate exhaustion gate.  A slot can be safe
  to execute once its accepted variant is staticized, but it is not fully
  exhausted until the writer that installed the variant is known or deliberately
  retired.

## Current implementation shape

`overkill/runtime_code.py` owns the manifest:

```text
RuntimeCodeSlot
  stable address/role/island/owner
  accepted and rejected RuntimeCodeVariant records
  RuntimeCodeStaticization target
  installer/writer provenance status
```

The hook pattern is:

```python
require_runtime_code_variant(cpu, (0x1010, 0x5E42), "gameplay_object_steer_5e42")
run_flat_static_python_logic(cpu)
```

This means:

```text
known accepted variant -> verified static function
known wrong/cold variant -> fail loudly
unknown variant -> fail loudly
```

Not:

```text
bytes differ -> interpret original ASM
```

## Staticization workflow for a new slot

1. **Detect the slot.**
   Use grouped interpreted hotspots, verifier divergences, or a live-byte guard
   failure to identify an address whose runtime bytes differ from the cold image.

2. **Capture variants.**
   Save the cold bytes and one or more live snapshots.  The signature should cover
   the whole accepted body and any internal leaves it calls, not merely the first
   few entry instructions.

3. **Name the slot and variants.**
   Add a `RuntimeCodeSlot` and `RuntimeCodeVariant` entries.  Do not use semantic
   game names unless already proven; use technical names such as
   `runtime_patched_object_steer_5e42`.

4. **Write a flat source function.**
   Implement the accepted body as ordinary Python in its semantic island, for
   example `gameplay/object_runtime.py` or `rendering/tandy.py`.  Preserve
   CPU-visible effects exactly: flags, stack scratch, continuation IPs, segment
   registers, and memory writes.

5. **Guard the hook by variant.**
   At the hook boundary call `require_runtime_code_variant(...)`.  Do not call
   the interpreter as a fallback when the guard fails.

6. **Verify against the oracle.**
   Add a focused snapshot/oracle test and run the normal hook verifier.

7. **Trace the installer.**
   Run `scripts/trace_runtime_code_writes.py` to discover which original code
   writes the accepted body.  Update `installer_status` and `installer_evidence`.

8. **Promote when stable.**
   Once the byte variant, installer, and static source function are known, the
   slot can be treated as a closed runtime-code island and later lifted further
   into a higher-level system model.

## Audit commands

Basic source-port safety gate:

```bash
python scripts/audit_runtime_code_staticization.py --check
```

Final exhaustion gate that also requires installer provenance:

```bash
python scripts/audit_runtime_code_staticization.py --check --strict-installers
```

Trace known runtime-code frontiers:

```bash
python scripts/trace_runtime_code_writes.py --steps 500000 --dump-final-variants
```

Trace broad code-segment writes from the cold interpreter.  This is noisy because
OVERKILL keeps data in the same segment, but it is useful when searching for the
installer of a known slot:

```bash
python scripts/trace_runtime_code_writes.py --all-code --no-hooks --steps 500000 --out artifacts/runtime_code_writes.log
```

## Current slots

- `1010:5E42 runtime_patched_object_steer_5e42`
  - accepted variant: `gameplay_object_steer_5e42`
  - cold rejected variant: `cold_display_helper_5e42_prefix`
  - static target:
    `overkill.gameplay.object_runtime.run_runtime_patched_object_steer_5e42`
  - installer status: pending writer trace

## Current census result: 5E42 is bootstrap materialization, not Tandy selection

The first runtime-code slot (`1010:5E42`) looked suspicious because the cold EXE
contains a different display/text helper at the same address.  A cold-start write
trace with hooks disabled shows the installer is the already-classified
`32FF:*` inner unpack/self-relocation bootstrap:

```text
writer=32FF:009B target=1010:5E42..1010:5F1A, 211 byte writes
final variant=gameplay_object_steer_5e42
```

The same body is installed for CGA, EGA, and Tandy command tails.  Therefore this
slot is **not** a video-card, sound-card, keyboard, joystick, or Amstrad-joystick
selector.  It is a bootstrapped inner-code body that the source port has already
staticized as `run_runtime_patched_object_steer_5e42`.

The actual video choice observed in the same census is a normal data/config word
inside the code segment:

```text
CS:95BC = 0000  # CGA
CS:95BC = 0001  # EGA
CS:95BC = 0002  # Tandy/PCjr
```

That is DOS-era code/data cohabitation, not an executable-byte mutation.  A
Tandy-first source port can eventually replace this with explicit high-level
configuration, but the current binary oracle still keeps the word in place so
ASM-compatible hooks can verify shared video dispatch paths.

Use the census tool when checking whether new suspicious writes are true runtime
code or merely CS-segment data:

```bash
python scripts/audit_runtime_code_census.py --video all --steps 250000 --show-bootstrap
```

The safety invariant after the census is:

```text
known bootstrap-installed runtime body -> staticized Python + byte guard
post-bootstrap unknown write into a registered runtime-code slot -> fail loudly
post-bootstrap CS-segment data/config write -> classify as data/config, not SMC
```
