#!/bin/zsh
# Dispatch one implementation task to a CLI coding agent.
#
#   tools/network/delegate.sh <agent> <task-id> <prompt-file> [log-dir]
#
# agent: agy | cursor | codex
#
# Each agent runs in the repository with write access, because these tasks produce code. The blast
# radius is controlled by the prompt (explicit file ownership) and by review before commit: nothing
# an agent writes is committed until the coordinator has read the diff and run the suite.
#
# Exit status is the agent's own. Output goes to <log-dir>/<task-id>.<agent>.log.
set -u
AGENT="$1"; TASK="$2"; PROMPT_FILE="$3"; LOGDIR="${4:-/tmp/network-delegation}"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/$TASK.$AGENT.log"
PROMPT="$(cat "$PROMPT_FILE")"
cd /Users/venus/Desktop/rarepipe || exit 2

print -r -- "[$(date -u +%FT%TZ)] $TASK -> $AGENT" >> "$LOG"
case "$AGENT" in
  agy)
    agy -p "$PROMPT" --effort high --dangerously-skip-permissions >> "$LOG" 2>&1
    ;;
  cursor)
    cursor-agent -p "$PROMPT" --output-format text --force >> "$LOG" 2>&1
    ;;
  codex)
    # stdin must be closed or codex waits for more input and is eventually killed.
    codex exec --dangerously-bypass-approvals-and-sandbox "$PROMPT" < /dev/null >> "$LOG" 2>&1
    ;;
  *)
    print -r -- "unknown agent: $AGENT" >&2; exit 2
    ;;
esac
STATUS=$?
print -r -- "[$(date -u +%FT%TZ)] $TASK $AGENT exit=$STATUS" >> "$LOG"
exit $STATUS
