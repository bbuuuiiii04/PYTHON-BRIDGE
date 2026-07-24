#!/bin/bash
# dispatch_lane.sh SESSION MODEL EFFORT MSGFILE TAG [AGENT]
# The standard lane-dispatch ritual, automated end to end (2026-07-09 overnight
# lessons): hands-off typed-text check, create/boot if missing, pin BOTH model
# and effort explicitly (they save as global defaults — never rely on
# inheritance), verify the model pin on-screen BEFORE task text, paste the
# message with the mandatory sentinel-FILE instruction appended, clear the
# unsubmitted-paste trap, and verify submission.
# AGENT = claude (default) | codex. Codex lanes pin model+effort as LAUNCH FLAGS
# (codex -m MODEL -c model_reasoning_effort=EFFORT — verified codex-cli 0.142.5)
# because flags-at-boot are deterministic where in-session commands are not; the
# on-screen pin verification is Claude-only (Codex TUI has no "set model to"
# acknowledgment line — dispatch prints VERIFY-MODEL-MANUALLY instead).
# The signal-file completion contract is identical for both agents.
# ponytail: fixed sleeps; tune per machine if flaky.
set -u
SESSION=$1; MODEL=$2; EFFORT=$3; MSGFILE=$4; TAG=$5; AGENT=${6:-claude}
REPO=/Users/bbui/rb_ss_bridge_v2
SIG=/tmp/rbss_lane_signals; mkdir -p "$SIG"
rm -f "$SIG/$SESSION.$TAG.done" "$SIG/$SESSION.$TAG.blocked"

# "=" = exact match. Bare -t prefix-matches (-t r4b hits a live r4bimpl seat),
# which would /clear and hijack someone else's lane. Quoted, so zsh's own "="
# word expansion never sees it.
if tmux has-session -t "=$SESSION" 2>/dev/null; then
  # hands-off: abort if a human sits mid-thought at the prompt. Only the LAST
  # prompt line counts (older ❯ lines are transcript echoes), and a bare
  # slash-command echo like "/clear" is not typed text (2026-07-09 field bug).
  # prompt char: ❯ = claude, › = codex TUI
  LASTPROMPT=$(tmux capture-pane -p -t "$SESSION" -S -5 | grep -E '^[❯›]' | tail -1)
  if [[ -n "$LASTPROMPT" ]] && echo "$LASTPROMPT" | grep -qE '^[❯›] +[^ ]' \
     && ! echo "$LASTPROMPT" | grep -qE '^[❯›] +/[a-z-]+ *$'; then
    echo "ABORT: typed text at $SESSION prompt — hands off"; exit 1
  fi
  # Reused session: stale context bleeds into the new task (2026-07-09 field
  # lesson: /clear per task). Claude gets /clear here; Codex has no verified
  # in-session equivalent — warn so the dispatcher decides.
  if [[ "$AGENT" == "codex" ]]; then
    echo "REUSED-SESSION-NO-CLEAR $SESSION (codex: no verified in-session clear — kill+respawn the session if the previous task's context must not bleed)"
  else
    tmux send-keys -t "$SESSION" '/clear' Enter; sleep 3
  fi
else
  tmux new-session -d -s "$SESSION" -c "$REPO"
  sleep 1
  if [[ "$AGENT" == "codex" ]]; then
    tmux send-keys -t "$SESSION" "command codex -m $MODEL -c model_reasoning_effort=\"$EFFORT\"" Enter
  else
    tmux send-keys -t "$SESSION" 'claude' Enter
  fi
  sleep 10
fi

if [[ "$AGENT" == "codex" ]]; then
  # Pins were launch flags; no in-session pin commands, no ack line to grep.
  echo "VERIFY-MODEL-MANUALLY $SESSION (codex lane: pins are launch flags -m $MODEL / effort $EFFORT)"
else
  tmux send-keys -t "$SESSION" "/model $MODEL" Enter; sleep 4
  # Claude acks with the model's DISPLAY name, not the id we passed
  # (claude-opus-5 -> "Set model to Opus 5", claude-opus-4-8 -> "Opus 4.8",
  # fable -> "Fable 5", claude-haiku-4-5-20251001 -> "Haiku 4.5" — captured
  # live 2026-07-24, Claude Code v2.1.219). The old literal "$MODEL" grep
  # false-negatived on every dated/versioned id. Compare alphanumerics only,
  # and accept when either side is a prefix of the other: aliases are shorter
  # than the display name (fable -> fable5), dated ids are longer
  # (haiku4520251001 vs haiku45). A wrong family or version still aborts.
  ACK=$(tmux capture-pane -p -t "$SESSION" -S -12 | grep -i 'set model to' | tail -1)
  ACKKEY=$(printf '%s' "$ACK" | sed -E 's/.*[Ss]et model to //; s/ and saved.*//' | tr -cd '[:alnum:]' | tr '[:upper:]' '[:lower:]')
  WANTKEY=$(printf '%s' "$MODEL" | sed -E 's/^claude-//' | tr -cd '[:alnum:]' | tr '[:upper:]' '[:lower:]')
  if [[ -z "$ACKKEY" || -z "$WANTKEY" ]] \
     || { [[ "$ACKKEY" != "$WANTKEY"* ]] && [[ "$WANTKEY" != "$ACKKEY"* ]]; }; then
    echo "MODEL-PIN-FAILED $SESSION -> $MODEL (pane ack: ${ACK:-<none>}; verify manually; task NOT sent)"; exit 1
  fi
  tmux send-keys -t "$SESSION" "/effort $EFFORT" Enter
  # /effort renders a picker that EATS a paste landing while it is open
  # (field bug 2026-07-09: task text vanished, lane sat idle). Wait for the
  # ack line before pasting; proceed after 12s either way — the paste-retry
  # loop below is the backstop.
  for i in 1 2 3 4; do
    sleep 3
    tmux capture-pane -p -t "$SESSION" -S -12 | grep -qi 'set effort level' && break
  done
fi

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
sleep 2
if ! tmux capture-pane -p -t "$SESSION" -S -40 | grep -q 'COMPLETION SIGNAL'; then
  # One re-paste: a transient UI element (picker, dialog) can eat the first
  # paste entirely — observed live 2026-07-09.
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
  sleep 2
fi
rm -f "$TMP"
if tmux capture-pane -p -t "$SESSION" -S -40 | grep -q 'COMPLETION SIGNAL'; then
  echo "DISPATCHED $SESSION ($MODEL/$EFFORT, tag=$TAG, signal=$SIG/$SESSION.$TAG.*)"
else
  echo "VERIFY-MANUALLY $SESSION (submission not confirmed in pane)"
fi
