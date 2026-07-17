# `overkill/cpuless_recovered/` — the generated CPUless corpus (COMMITTED runtime source)

These `func_<cs>_<ip>.py` modules are the **CPUless-lifted implementations** of the OVERKILL binary's
functions (DOS_RE 2.0 stage 3): pure `func(mem, plat, *, <regs>)` over a flat memory image + a platform
device object, touching **no CPU carrier** (no `cpu.s`/flags/machine stack — enforced by the CPUless
recovered-purity wall). Each returns a dict of live register outputs.

**This directory is committed source, not a disposable artifact.** It is what `scripts/play_cpuless.py`
imports as the game's DEFAULT implementations; a hand-written `overkill/native/overrides/func_<cs>_<ip>.py`
may drop in at the SAME identity via `sys.modules` aliasing (see the campaign doc), with the generated
version kept for differential comparison. This mirrors `lemmings_port`'s `lemmings/recovered/`.

- **Regenerate:** `python scripts/probe_vmless_cpuless.py` (emits here + scores the walls). Do not
  hand-edit a `func_*.py` (each says so) — write a native override instead.
- **The CPU-ABI adapters** (`overkill/cpuless_adapters/`) are the verification shims that occupy the
  lifted slot; they stay gitignored and must NEVER be imported at runtime (the import wall forbids it).
- **Coverage** (2026-07-18): 561/626 discovered functions promoted; the remainder are the fail-loud
  frontier (tail-dispatch, boundary-head, sp-as-data, ir-not-liftable) — see the campaign doc.
