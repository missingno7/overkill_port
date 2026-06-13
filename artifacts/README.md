# Artifacts retention policy

This directory is intentionally small. Keep only durable oracle/evidence data here.

## Kept

- `test_oracles/`: snapshots loaded directly by regression tests, including promoted former `snapshot_play_*`, `play_*`, and `tmp_*` fixtures.
- `evidence/`: minimal snapshots still referenced by tests or current hook-verifier work.
- `hook_coverage_cache.json`: compact hook coverage/cost cache.

## Generated locally; do not keep by default

- `snapshot_play_*` live snapshots.
- `play_*` gameplay captures.
- `tmp_*` stop/verify snapshots.
- `frame_verify/` PNG/VRAM diff dumps.
- one-off probe captures after their findings are documented.

Promote a generated snapshot into `test_oracles/` or `evidence/` only when a
test, documented finding, or active verifier command depends on it.
