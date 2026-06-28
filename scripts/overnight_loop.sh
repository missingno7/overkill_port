#!/usr/bin/env bash
# Overnight endgame recovery loop launcher.
#
# Runs the DEMAND-DRIVEN recovery loop in docs/overkill/overnight_endgame_execution.md
# unattended, CONTINUOUSLY, until the full game is recovered (the §1 done-condition).
# The agent keeps recovering slices one after the next -- flowing into the next step and
# the next -- committing each verified slice as it goes. This bash loop is just a
# restart-on-exit safety net: if the agent ever stops (context got heavy, a crash, a
# limit), it relaunches a fresh agent that picks up exactly where the last one left off,
# because all progress lives in git + loop_blockers.md. Killing it never loses work.
#
#   Usage:  bash scripts/overnight_loop.sh [max_restarts]
#           CLAUDE_MODEL=opus bash scripts/overnight_loop.sh
#   Stop:   Ctrl-C, or it stops itself when the agent prints "ENDGAME REACHED".
#
# WARNING: this uses `claude --dangerously-skip-permissions` so the agent can edit, run,
# and commit without prompts. The safety is the doc's invariants (never commit red, never
# weaken an oracle, revert + document any failed attempt). Run it on a branch you are happy
# to let it push to, and review the commit log in the morning.
set -u
cd "$(cd "$(dirname "$0")/.." && pwd)"

MAX="${1:-1000}"                            # max RESTARTS (each runs continuously, many slices)
MODEL="${CLAUDE_MODEL:-}"
ITER_TIMEOUT="${ITER_TIMEOUT:-0}"           # per-run wall-clock cap (s); 0 = no cap (default).
                                            # committed slices are always safe, so a cap only
                                            # ever loses the one in-progress slice.
TIMEOUT_BIN="$(command -v timeout || true)"
LOG="artifacts/overnight_loop.log"
mkdir -p artifacts

GOAL="$(cat <<'PROMPT'
Run the unattended recovery loop in docs/overkill/overnight_endgame_execution.md. Read that
doc first -- it is the binding brief -- and follow it exactly.

CONTINUE recovering slices one after the next -- flow into the next step and the next,
committing each verified slice -- and do NOT stop after a single slice. Keep going,
autonomously, until the §1 done-condition is reached (the full game recovered). The only
reason to exit early is that your context has grown heavy after a good batch of slices: in
that case commit cleanly and stop, and a fresh run will pick up exactly where you left off
from git.

Demand-driven, never top-down: for each step, choose the next native feature to attempt
(the doc's §6 work queue; skip anything in docs/overkill/loop_blockers.md and anything
`git log` shows is already done). Try it on --backend native. Where it needs state /
behavior / timing / render-data that is missing, GO DOWN to the ASM boundary, recover that
leaf (shadow -> verified hook -> source-level system), VERIFY it against the demos /
snapshots / per-routine ASM / full demo-replay (the §5 gates), then LIFT it upward into
native source state, and close the island. NEVER fake a missing gap in the renderer or
runtime -- recover it at the hybrid/source layer first.

Unattended safety (§3), non-negotiable: never commit red; never weaken an oracle or test to
pass; on ANY failure REVERT that attempt completely (leave the tree exactly as before),
append a short entry to docs/overkill/loop_blockers.md, and MOVE ON to the next attempt -- a
single failed slice never stops the run. On each success, make ONE focused commit + push of
the verified slice and update metrics / run_status.md.

If the §1 done-condition already holds (standalone --backend native runs every demo with no
VM and verify-mode shows zero divergence from the oracle), do nothing and print exactly:
ENDGAME REACHED
PROMPT
)"

run_agent() {
  local cmd=(claude -p "$GOAL" --dangerously-skip-permissions)
  [ -n "$MODEL" ] && cmd+=(--model "$MODEL")
  if [ -n "$TIMEOUT_BIN" ] && [ "$ITER_TIMEOUT" != "0" ]; then
    "$TIMEOUT_BIN" "$ITER_TIMEOUT" "${cmd[@]}"
  else
    "${cmd[@]}"
  fi
}

echo "overnight loop starting $(date -Is); max_restarts=$MAX; model=${MODEL:-default}; per_run_cap=${ITER_TIMEOUT}s" | tee -a "$LOG"
i=0
while [ "$i" -lt "$MAX" ]; do
  i=$((i + 1))
  echo "=== run $i (fresh agent, runs continuously) $(date -Is) ===" | tee -a "$LOG"
  run_agent 2>&1 | tee -a "$LOG"
  if tail -n 80 "$LOG" | grep -q "ENDGAME REACHED"; then
    echo "ENDGAME REACHED on run $i; stopping." | tee -a "$LOG"
    break
  fi
  echo "agent exited (context refresh / restart); relaunching..." | tee -a "$LOG"
  sleep 10
done
echo "overnight loop ended $(date -Is) after $i run(s)" | tee -a "$LOG"
