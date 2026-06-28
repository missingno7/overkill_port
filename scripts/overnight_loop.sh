#!/usr/bin/env bash
# Overnight endgame recovery loop launcher.
#
# Runs the DEMAND-DRIVEN recovery loop in docs/overkill/overnight_endgame_execution.md
# unattended. Each iteration is a fresh, doc-grounded agent that: attempts one feature on
# --backend native, recovers + verifies + lifts the gap that attempt exposes, and commits
# ONE verified slice. Progress is durable in git + loop_blockers.md, so the loop is
# crash-safe and the morning report is just the commit log.
#
#   Usage:  bash scripts/overnight_loop.sh [max_iterations]
#           CLAUDE_MODEL=opus ITER_TIMEOUT=5400 bash scripts/overnight_loop.sh 200
#   Stop:   Ctrl-C, or it stops itself when the §1 done-condition is reached
#           (the agent prints "ENDGAME REACHED").
#
# WARNING: this uses `claude --dangerously-skip-permissions` so the agent can edit, run,
# and commit without prompts. The safety is the doc's invariants (never commit red, never
# weaken an oracle, revert + document any failed attempt). Run it on a branch you are happy
# to let it push to, and review the commit log in the morning.
set -u
cd "$(cd "$(dirname "$0")/.." && pwd)"

MAX="${1:-500}"
MODEL="${CLAUDE_MODEL:-}"
ITER_TIMEOUT="${ITER_TIMEOUT:-5400}"        # per-iteration wall-clock cap (s); 0 disables
TIMEOUT_BIN="$(command -v timeout || true)"
LOG="artifacts/overnight_loop.log"
mkdir -p artifacts

GOAL="$(cat <<'PROMPT'
Run ONE iteration of the unattended recovery loop in
docs/overkill/overnight_endgame_execution.md. Read that doc first -- it is the binding
brief -- and follow it exactly.

Demand-driven, never top-down: choose the next native feature to attempt (the doc's §6
work queue; skip anything in docs/overkill/loop_blockers.md and anything `git log` shows is
already done). Try it on --backend native. Where it needs state / behavior / timing /
render-data that is missing, GO DOWN to the ASM boundary, recover that leaf (shadow ->
verified hook -> source-level system), VERIFY it against the demos / snapshots /
per-routine ASM / full demo-replay (the §5 gates), then LIFT it upward into native source
state, and close the island. NEVER fake a missing gap in the renderer or runtime -- recover
it at the hybrid/source layer first.

Unattended safety (§3), non-negotiable: never commit red; never weaken an oracle or test to
pass; on ANY failure REVERT the attempt completely (leave the tree exactly as before) and
append a short entry to docs/overkill/loop_blockers.md, then stop this iteration. On
success, make ONE focused commit + push of the verified slice and update metrics /
run_status.md. Do exactly ONE verified slice this iteration, then STOP.

If the §1 done-condition already holds (standalone --backend native runs every demo with no
VM and verify-mode shows zero divergence from the oracle), do nothing and print exactly:
ENDGAME REACHED
PROMPT
)"

run_iter() {
  local cmd=(claude -p "$GOAL" --dangerously-skip-permissions)
  [ -n "$MODEL" ] && cmd+=(--model "$MODEL")
  if [ -n "$TIMEOUT_BIN" ] && [ "$ITER_TIMEOUT" != "0" ]; then
    "$TIMEOUT_BIN" "$ITER_TIMEOUT" "${cmd[@]}"
  else
    "${cmd[@]}"
  fi
}

echo "overnight loop starting $(date -Is); max=$MAX; model=${MODEL:-default}; timeout=${ITER_TIMEOUT}s" | tee -a "$LOG"
i=0
while [ "$i" -lt "$MAX" ]; do
  i=$((i + 1))
  echo "=== iteration $i  $(date -Is) ===" | tee -a "$LOG"
  run_iter 2>&1 | tee -a "$LOG"
  if tail -n 60 "$LOG" | grep -q "ENDGAME REACHED"; then
    echo "ENDGAME REACHED at iteration $i; stopping." | tee -a "$LOG"
    break
  fi
  sleep 10
done
echo "overnight loop ended $(date -Is) after $i iterations" | tee -a "$LOG"
