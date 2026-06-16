# Documentation Map

Documentation follows the same ownership boundary as the code. Put a document in
the folder that owns the knowledge it contains; do not leave durable notes loose
in `docs/`.

## Reusable DOS RE framework

- `dos_re/source_port_methodology.md` — reusable DOS RE workflow for
  trace/snapshot/oracle/hook/source-port projects.

These documents should make sense for another DOS reverse-engineering target.
They must not depend on OVERKILL addresses, islands, assets, command-tail bytes,
or gameplay semantics.

## Cross-package architecture

- `architecture/package_boundary.md` — dependency direction between `dos_re` and
  `overkill`, including the rule that `dos_re` must not import or know the game.

- `architecture/third_party.md` — vendored third-party components, currently
  the optional Nuked-OPL3 CFFI binding used by the SDL AdLib audio backend.

Use this folder for repo-level boundary documents that describe more than one
package.

## OVERKILL-specific source-port work

- `overkill/source_port_methodology.md` — OVERKILL-specific evidence ladder,
  island workflow, and source-port playbook.
- `overkill/semantic_crystallization_plan.md` — durable plan for promoting
  verified hooks upward into recovered source-port layers without duplicating
  gameplay logic.
- `overkill/recovered_source_layer.md` — current recovered views/adapters/domain/systems
  split and the already promoted source-like collision/object-slot seed.
- `overkill/bootstrap_static_boundary.md` — original bootstrap vs canonical
  initialized runtime bundle.
- `overkill/design.md` — OVERKILL runtime/source-port architecture.
- `overkill/runtime_findings.md` — durable address-level reverse-engineering
  findings.
- `overkill/island_truth_tables.md` — per-island confidence and frontier index.
- `overkill/run_status.md` — current checkpoint, commands run, and near-term
  status.
- `overkill/next_steps.md` — current tactical investigation plan.
- `overkill/hook_naming_audit.md` — naming and wrapper placement audit.
- `overkill/runtime_code_staticization.md` — policy for converting runtime
  patched code into static Python/source-port data.
- `overkill/performance_investigation.md` — historical performance and hook
  boundary investigation notes.

Anything with literal OVERKILL addresses, assets, screenshots, islands, game
state offsets, or gameplay hypotheses belongs here.

## Maintenance helpers

- `scripts/clean.py` removes local Python caches, package build outputs, and optional unpromoted generated artifact families.
- `scripts/render_frame.py` is the dependency-free headless PNG/frame dump tool for CGA, EGA, and Tandy snapshots.
