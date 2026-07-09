#!/bin/bash
# watch_lane.sh SESSION [SENTINEL_REGEX] [DEADLINE_S] [WAITBUSY]
# Lane watcher, file-first: exits on a signal file in /tmp/rbss_lane_signals/
# (SESSION.<TAG>.done / .blocked — the machine channel, immune to scrolled
# viewports and echo false-fires), else falls back to pane sentinel regex and
# change-gated idle detection. Read-only: never sends keys.
# ponytail: polling loop; launchd/fswatch if this ever needs to be evented.
SIG_DIR=/tmp/rbss_lane_signals
SESSION=$1; SENTINEL=${2:-}; DEADLINE=${3:-540}; WAITBUSY=${4:-0}; INTERVAL=15
mkdir -p "$SIG_DIR"
start=$(date +%s)
init=$(tmux capture-pane -p -t "$SESSION" -S -40 2>/dev/null)
prev=""
while :; do
  # file channel first — authoritative
  for f in "$SIG_DIR/$SESSION".*.done "$SIG_DIR/$SESSION".*.blocked; do
    if [[ -e "$f" ]]; then
      echo "SIGNAL-FILE $f"
      cat "$f" 2>/dev/null
      exit 0
    fi
  done
  now=$(date +%s)
  if (( now - start > DEADLINE )); then
    echo "WATCH-TIMEOUT $SESSION (still busy after ${DEADLINE}s)"
    tmux capture-pane -p -t "$SESSION" -S -12 2>/dev/null
    exit 0
  fi
  sleep "$INTERVAL"
  cur=$(tmux capture-pane -p -t "$SESSION" -S -40 2>/dev/null)
  # pane sentinel is a FALLBACK: skip while the dispatch echo is on screen
  # ("print exactly" / "COMPLETION SIGNAL"), which false-fires it (2026-07-09).
  if [[ -n "$SENTINEL" ]] && ! grep -qE 'print exactly|COMPLETION SIGNAL' <<<"$cur" \
     && grep -qE "$SENTINEL" <<<"$cur"; then
    echo "SENTINEL-HIT $SESSION"
    tail -30 <<<"$cur"
    exit 0
  fi
  if [[ "$WAITBUSY" == 1 ]]; then
    [[ "$cur" != "$init" ]] && WAITBUSY=0
    continue
  fi
  # idle = 3+ consecutive identical captures (2 catches long thinking stretches)
  if [[ -n "$prev" && "$cur" == "$prev" ]]; then
    idle_count=$((${idle_count:-0} + 1))
    if (( idle_count >= 2 )); then
      echo "IDLE $SESSION"
      tail -25 <<<"$cur"
      exit 0
    fi
  else
    idle_count=0
  fi
  prev="$cur"
done
