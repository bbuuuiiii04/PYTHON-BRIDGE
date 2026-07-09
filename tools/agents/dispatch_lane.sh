#!/bin/bash
# dispatch_lane.sh SESSION MODEL EFFORT MSGFILE TAG
# The standard lane-dispatch ritual, automated end to end (2026-07-09 overnight
# lessons): hands-off typed-text check, create/boot if missing, pin BOTH model
# and effort explicitly (they save as global defaults — never rely on
# inheritance), verify the model pin on-screen BEFORE task text, paste the
# message with the mandatory sentinel-FILE instruction appended, clear the
# unsubmitted-paste trap, and verify submission.
# ponytail: fixed sleeps; tune per machine if flaky.
set -u
SESSION=$1; MODEL=$2; EFFORT=$3; MSGFILE=$4; TAG=$5
REPO=/Users/bbui/rb_ss_bridge_v2
SIG=/tmp/rbss_lane_signals; mkdir -p "$SIG"
rm -f "$SIG/$SESSION.$TAG.done" "$SIG/$SESSION.$TAG.blocked"

if tmux has-session -t "$SESSION" 2>/dev/null; then
  # hands-off: abort if a human sits mid-thought at the prompt. Only the LAST
  # prompt line counts (older ❯ lines are transcript echoes), and a bare
  # slash-command echo like "/clear" is not typed text (2026-07-09 field bug).
  LASTPROMPT=$(tmux capture-pane -p -t "$SESSION" -S -5 | grep '^❯' | tail -1)
  if [[ -n "$LASTPROMPT" ]] && echo "$LASTPROMPT" | grep -qE '^❯ +[^ ]' \
     && ! echo "$LASTPROMPT" | grep -qE '^❯ +/[a-z-]+ *$'; then
    echo "ABORT: typed text at $SESSION prompt — hands off"; exit 1
  fi
else
  tmux new-session -d -s "$SESSION" -c "$REPO"
  sleep 1
  tmux send-keys -t "$SESSION" 'claude' Enter
  sleep 10
fi

tmux send-keys -t "$SESSION" "/model $MODEL" Enter; sleep 4
if ! tmux capture-pane -p -t "$SESSION" -S -12 | grep -qi "set model to.*$MODEL"; then
  echo "MODEL-PIN-FAILED $SESSION -> $MODEL (verify manually; task NOT sent)"; exit 1
fi
tmux send-keys -t "$SESSION" "/effort $EFFORT" Enter; sleep 3

TMP=$(mktemp)
cat "$MSGFILE" > "$TMP"
printf '\nCOMPLETION SIGNAL (mandatory, machine channel): when fully done run exactly: touch %s/%s.%s.done — if blocked instead run: echo "<one-line reason>" > %s/%s.%s.blocked. ALSO print your sentinel on its own line as usual. Do not pause at checkpoints for acknowledgment; run straight through unless genuinely blocked.\n' \
  "$SIG" "$SESSION" "$TAG" "$SIG" "$SESSION" "$TAG" >> "$TMP"
tmux load-buffer "$TMP"
tmux paste-buffer -t "$SESSION"
sleep 1
tmux send-keys -t "$SESSION" Enter
for i in 1 2 3 4 5; do
  sleep 3
  if tmux capture-pane -p -t "$SESSION" -S -6 | grep -q '\[Pasted text'; then
    tmux send-keys -t "$SESSION" Enter
  else
    break
  fi
done
rm -f "$TMP"
sleep 2
if tmux capture-pane -p -t "$SESSION" -S -40 | grep -q 'COMPLETION SIGNAL'; then
  echo "DISPATCHED $SESSION ($MODEL/$EFFORT, tag=$TAG, signal=$SIG/$SESSION.$TAG.*)"
else
  echo "VERIFY-MANUALLY $SESSION (submission not confirmed in pane)"
fi
