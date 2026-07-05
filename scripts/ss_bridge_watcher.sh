#!/bin/bash
# ss_bridge_watcher.sh
# Launcher for rb_ss_bridge_v2. Auto mode (default) watches for Rekordbox and
# SoundSwitch and starts or adopts one bridge process; manual mode
# (RBSS_BRIDGE_MANUAL=1) starts the bridge directly with the same env as auto.
# Both modes open exactly one Terminal monitor window running bridge_view.py
# (AWR-125), the read-only JSONL log viewer. Closing the viewer window never
# stops the bridge -- only the menubar (auto mode) or the bridge process itself
# exiting (manual mode) does that; the watcher just reopens a missing viewer.
# Bridge uses direct Rekordbox memory paths (B1-B6) as primary signals, with
# MTC available as the timecode fallback.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
# The package imports from the repo parent; `python3 -m rb_ss_bridge_v2`
# fails when launched from inside the repo directory.
BRIDGE_DIR="$(dirname "${REPO_ROOT}")"
LOG_FILE="${LOG_FILE:-/tmp/bridge.log}"
PYTHON="${PYTHON:-/opt/homebrew/bin/python3}"
MONITOR_MARKER="RBSS_BRIDGE_MONITOR"
MANUAL_MODE="${RBSS_BRIDGE_MANUAL:-0}"
# Art-Net truth-check (U1 shadow capture) is a validation-only mode kept for
# future truth exams. Default OFF for normal shows; opt in per-launch with
# RBSS_BRIDGE_TRUTH=1 (universe defaults to 1, override via RBSS_ARTNET_UNIVERSE).
TRUTH_ENV=""
if [ "${RBSS_BRIDGE_TRUTH:-0}" = "1" ]; then
    TRUTH_ENV="RBSS_ARTNET_TRUTH_CHECK=1 RBSS_ARTNET_UNIVERSE=${RBSS_ARTNET_UNIVERSE:-1}"
fi
LASER_CONFIG_PATH="${REPO_ROOT}/config/laser_director.json"
LASER_CONFIG_EXAMPLE="${REPO_ROOT}/config/laser_director.example.json"
BRIDGE_PID=""
BRIDGE_MANAGED=0
BACKOFF_INDEX=0
BACKOFF_VALUES=(3 10 30 60)
STARTED_AT=0
WARNED_MULTIPLE=0
MONITOR_OPENED=0
GOVEE_ENV_FILE="$HOME/Library/Application Support/RBSS Bridge/govee.env"
STREAMDECK_SCRIPT="${REPO_ROOT}/streamdeck/streamdeck_midi.py"
STREAMDECK_LOG="${STREAMDECK_LOG:-/tmp/streamdeck.log}"
STREAMDECK_PAT="[p]ython3?.*streamdeck_midi\.py"

ss_running() {
    pgrep -x "SoundSwitch" > /dev/null 2>&1
}

rb_running() {
    pgrep -x "rekordbox" > /dev/null 2>&1
}

bridge_alive() {
    [ -n "$BRIDGE_PID" ] && kill -0 "$BRIDGE_PID" 2>/dev/null
}

log_watcher() {
    printf '[watcher] %s\n' "$*" >> "$LOG_FILE"
}

streamdeck_running() {
    pgrep -f "$STREAMDECK_PAT" > /dev/null 2>&1
}

start_streamdeck() {
    streamdeck_running && return 0
    "$PYTHON" "$STREAMDECK_SCRIPT" >> "$STREAMDECK_LOG" 2>&1 &
    log_watcher "started streamdeck pid=$!"
}

stop_streamdeck() {
    streamdeck_running || return 0
    printf '%s [watcher] stopping streamdeck reason=%s\n' \
        "$(date +%Y-%m-%dT%H:%M:%S)" "${1:-unspecified}" >> "$STREAMDECK_LOG"
    pkill -f "$STREAMDECK_PAT" 2>/dev/null
    log_watcher "stopped streamdeck reason=${1:-unspecified}"
}

# ponytail: the child may sit briefly until bash reaps it; add wait only if zombies accumulate.

ensure_laser_config() {
    if [ ! -f "$LASER_CONFIG_PATH" ]; then
        if [ -f "$LASER_CONFIG_EXAMPLE" ]; then
            cp "$LASER_CONFIG_EXAMPLE" "$LASER_CONFIG_PATH"
            log_watcher "created laser config from example path=$LASER_CONFIG_PATH"
        else
            log_watcher "WARNING missing laser config example path=$LASER_CONFIG_EXAMPLE"
            return 0
        fi
    fi

    "$PYTHON" - "$LASER_CONFIG_PATH" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
data["enabled"] = True
data["dry_run"] = False
path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
PY
}

bridge_pids() {
    pgrep -f "^[^[:space:]]*(python3|Python)[^[:space:]]*([[:space:]]+-u)?[[:space:]]+-m[[:space:]]+rb_ss_bridge_v2$" 2>/dev/null
}

kill_bridge_processes() {
    pkill -f "^[^[:space:]]*(python3|Python)[^[:space:]]*([[:space:]]+-u)?[[:space:]]+-m[[:space:]]+rb_ss_bridge_v2$" 2>/dev/null
}

monitor_open() {
    # Count only viewer processes that still own a terminal. A bare pgrep -f
    # kept matching a headless orphan bridge_view.py (ppid 1, tty "??") left
    # behind when a marker-only pkill killed the wrapper bash but not its
    # python child -- which suppressed open_monitor forever (the 2026-07-05
    # "menubar start but no viewer window" regression). Full path so an
    # unrelated process merely mentioning bridge_view.py doesn't count.
    local pid tty
    for pid in $(pgrep -f "$MONITOR_MARKER" 2>/dev/null; \
                 pgrep -f "${REPO_ROOT}/bridge_view\.py" 2>/dev/null); do
        tty=$(ps -o tty= -p "$pid" 2>/dev/null | tr -d ' ')
        case "$tty" in
            ""|"??"|"?"|"-") ;;  # headless or already gone: not a window
            *) return 0 ;;
        esac
    done
    return 1
}

start_bridge() {
    (
        cd "$BRIDGE_DIR" || exit 1
        ensure_laser_config
        if [ -f "$GOVEE_ENV_FILE" ]; then
            set -a
            # shellcheck disable=SC1090
            . "$GOVEE_ENV_FILE"
            set +a
        fi
        echo "Laser Director config: $LASER_CONFIG_PATH"
        echo "Laser Director mode: enabled=true dry_run=false"
        exec env \
            RBSS_GOVEE_REALTIME=1 \
            RBSS_LIVE_BPM_FOLLOW=1 \
            RBSS_ANLZ_DIRECT=1 \
            RBSS_POS_CHAIN_DIRECT=1 \
            RBSS_POS_CHAIN_SKIP_OBJC=1 \
            RBSS_MASTER_SEED_DIRECT=1 \
            RBSS_MASTER_DIRECT=1 \
            RBSS_PLAY_DIRECT=1 \
            RBSS_TRACK_LOAD_DIRECT=1 \
            RBSS_SCRIPTED_DIRECT=1 \
            RBSS_SCRIPTED_SHOWFILE_DIRECT=1 \
            RBSS_SMART_REARM_EXPERIMENT=1 \
            RBSS_SMART_DROP=1 \
            RBSS_SMART_BREAKDOWN=1 \
            RBSS_LED_PHRASE_MONOTONIC=1 \
            RBSS_LED_MIN_DWELL=1 \
            RBSS_LED_CANCEL_PENDING=1 \
            RBSS_LED_RT_RECONCILE=1 \
            RBSS_LED_TRANSPORT_STICKY=1 \
            RBSS_LED_TRANSPORT_COOLDOWN=0 \
            RBSS_LASER_CONFIG="$LASER_CONFIG_PATH" \
            $TRUTH_ENV \
            "$PYTHON" -m rb_ss_bridge_v2
    ) > "$LOG_FILE" 2>&1 &
    BRIDGE_PID=$!
    BRIDGE_MANAGED=1
    STARTED_AT=$(date +%s)
    WARNED_MULTIPLE=0
    log_watcher "started bridge pid=$BRIDGE_PID follow=on anlz_direct=on pos_chain_direct=on master_seed_direct=on master_direct=on play_direct=on track_load_direct=on scripted_direct=on smart_drop=on smart_breakdown=on laser_config=${LASER_CONFIG_PATH} manual=${MANUAL_MODE}"
}

adopt_existing_bridge() {
    local pids
    local count

    pids=$(bridge_pids)
    count=$(printf '%s\n' "$pids" | sed '/^$/d' | wc -l | tr -d ' ')

    if [ "$count" -eq 1 ]; then
        BRIDGE_PID="$pids"
        BRIDGE_MANAGED=0
        STARTED_AT=$(date +%s)
        WARNED_MULTIPLE=0
        log_watcher "adopted existing bridge pid=$BRIDGE_PID"
        return 0
    fi

    if [ "$count" -gt 1 ]; then
        if [ "$WARNED_MULTIPLE" -eq 0 ]; then
            log_watcher "WARNING multiple bridge processes found; not starting another bridge: $(printf '%s' "$pids" | tr '\n' ' ')"
            WARNED_MULTIPLE=1
        fi
        BRIDGE_PID=""
        BRIDGE_MANAGED=0
        return 0
    fi

    return 1
}

ensure_bridge() {
    if bridge_alive; then
        local now
        now=$(date +%s)
        if [ "$STARTED_AT" -gt 0 ] && [ $((now - STARTED_AT)) -ge 60 ]; then
            BACKOFF_INDEX=0
        fi
        return
    fi

    if [ -n "$BRIDGE_PID" ]; then
        log_watcher "bridge pid=$BRIDGE_PID exited"
        BRIDGE_PID=""
        BRIDGE_MANAGED=0

        local delay
        delay=${BACKOFF_VALUES[$BACKOFF_INDEX]}
        log_watcher "restart backoff ${delay}s"
        sleep "$delay"
        if [ "$BACKOFF_INDEX" -lt 3 ]; then
            BACKOFF_INDEX=$((BACKOFF_INDEX + 1))
        fi
    fi

    adopt_existing_bridge || start_bridge
}

open_monitor() {
    MONITOR_OPENED=1
    # Unquoted heredoc (deliberate): $PYTHON/$REPO_ROOT are static, operator-controlled
    # paths that must expand here so bridge_view.py resolves without relying on the
    # spawned Terminal shell's environment. Nothing else in this heredoc uses "$" --
    # the quadruple backslash before 033/007 is not a typo: bash's own heredoc
    # backslash-collapsing (unquoted here-docs only special-case \\, \$, \`) halves it
    # once to \\033, then AppleScript's string-literal escaping halves it again to the
    # single \033 printf needs for the terminal-title escape sequence.
    osascript <<EOF
tell application "Terminal"
    activate
    do script "bash -c 'printf \"\\\\033]0;RBSS_BRIDGE_MONITOR\\\\007\"; echo \"━━━ Bridge Monitor ━━━\"; \"$PYTHON\" \"$REPO_ROOT/bridge_view.py\"' RBSS_BRIDGE_MONITOR"
    set custom title of selected tab of front window to "RBSS_BRIDGE_MONITOR"
    try
        set number of rows of front window to 40
        set number of columns of front window to 140
    end try
end tell
EOF
}

close_monitor() {
    pkill -f "$MONITOR_MARKER" 2>/dev/null
    # The marker lives on the wrapper bash's argv, not the python viewer's:
    # kill the viewer by full path too, or it survives the marker pkill
    # orphaned (its own tty-hangup exit is the backstop, this is the clean path).
    pkill -f "${REPO_ROOT}/bridge_view\.py" 2>/dev/null
    pkill -f "^tail -n 100 -F ${LOG_FILE}$" 2>/dev/null

    osascript <<'EOF' >/dev/null 2>&1
tell application "Terminal"
    repeat
        set closedTab to false
        repeat with w in windows
            repeat with t in tabs of w
                if custom title of t is "RBSS_BRIDGE_MONITOR" then
                    close t
                    set closedTab to true
                    exit repeat
                end if
            end repeat
            if closedTab then exit repeat
        end repeat
        if not closedTab then exit repeat
    end repeat
end tell
EOF
}

stop_bridge() {
    if bridge_alive && [ "$BRIDGE_MANAGED" -eq 1 ]; then
        log_watcher "stopping managed bridge pid=$BRIDGE_PID"
        kill "$BRIDGE_PID" 2>/dev/null
        wait "$BRIDGE_PID" 2>/dev/null
    elif bridge_alive; then
        log_watcher "leaving adopted bridge pid=$BRIDGE_PID running"
    fi

    BRIDGE_PID=""
    BRIDGE_MANAGED=0
    STARTED_AT=0
    stop_streamdeck bridge_stop
    if [ "$MONITOR_OPENED" -eq 1 ] || monitor_open; then
        close_monitor
        MONITOR_OPENED=0
    fi
}

cleanup() {
    stop_streamdeck watcher_exit
    stop_bridge
}

trap cleanup EXIT
trap 'cleanup; exit 0' INT TERM

if [ -z "${WATCHER_NO_LOOP:-}" ]; then
while true; do
    if [ "$MANUAL_MODE" = "1" ]; then
        # Manual semantics: no crash-restart backoff (ensure_bridge is never
        # called here) -- a bridge exit ends the watcher, same as today.
        # Closing the viewer window must NOT stop the bridge (menubar/manual
        # process-exit are the only things that do); no "viewer closed" check.
        if ! bridge_pids > /dev/null; then
            if [ "$MONITOR_OPENED" -eq 1 ]; then
                log_watcher "manual bridge exited"
                exit 0
            fi
            start_bridge
        fi
        if bridge_alive; then
            start_streamdeck
        fi
        if ! monitor_open; then
            open_monitor
        fi
        sleep 3
        continue
    fi

    if ! rb_running; then
        stop_bridge
        sleep 5
        continue
    fi

    if ss_running; then
        ensure_bridge
        if bridge_alive; then
            start_streamdeck
        fi
        if ! monitor_open; then
            open_monitor
        fi
    else
        stop_bridge
    fi
    sleep 3
done
fi
