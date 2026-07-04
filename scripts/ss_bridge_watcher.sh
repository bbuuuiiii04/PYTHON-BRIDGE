#!/bin/bash
# ss_bridge_watcher.sh
# Manual launcher for rb_ss_bridge_v2.
# Watches for Rekordbox and SoundSwitch. When they are present, starts or adopts
# one bridge process and opens one dedicated Terminal monitor.
# Bridge uses direct Rekordbox memory paths (B1-B6) as primary signals, with
# MTC available as the timecode fallback.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
# The package imports from the repo parent; `python3 -m rb_ss_bridge_v2`
# fails when launched from inside the repo directory.
BRIDGE_DIR="$(dirname "${REPO_ROOT}")"
LOG_FILE="/tmp/bridge.log"
PYTHON="/opt/homebrew/bin/python3"
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
STREAMDECK_LOG="/tmp/streamdeck.log"
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
    pkill -f "$STREAMDECK_PAT" 2>/dev/null
    log_watcher "stopped streamdeck"
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
    pgrep -f "$MONITOR_MARKER" > /dev/null 2>&1 || \
        pgrep -f "^tail -n 100 -F ${LOG_FILE}$" > /dev/null 2>&1
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
    log_watcher "started bridge pid=$BRIDGE_PID follow=on anlz_direct=on pos_chain_direct=on master_seed_direct=on master_direct=on play_direct=on track_load_direct=on scripted_direct=on phrase_anchor=on smart_drop=on smart_breakdown=on laser_config=${LASER_CONFIG_PATH} manual=${MANUAL_MODE}"
}

start_manual_terminal_bridge() {
    ensure_laser_config
    MONITOR_OPENED=1
    log_watcher "opening manual bridge terminal"
    osascript <<EOF
tell application "Terminal"
    activate
    do script "bash -lc 'printf \"\\\\033]0;RBSS_BRIDGE_MONITOR\\\\007\"; echo \"━━━ Bridge Manual Session ━━━\"; cd ${BRIDGE_DIR} || exit 1; echo \"Laser Director config: ${LASER_CONFIG_PATH}\"; echo \"Laser Director mode: enabled=true dry_run=false\"; GOVEE_ENV_FILE=\"${GOVEE_ENV_FILE}\"; if [ -f \"\$GOVEE_ENV_FILE\" ]; then set -a; . \"\$GOVEE_ENV_FILE\"; set +a; fi; env RBSS_GOVEE_REALTIME=1 RBSS_LIVE_BPM_FOLLOW=1 RBSS_ANLZ_DIRECT=1 RBSS_POS_CHAIN_DIRECT=1 RBSS_MASTER_SEED_DIRECT=1 RBSS_MASTER_DIRECT=1 RBSS_PLAY_DIRECT=1 RBSS_TRACK_LOAD_DIRECT=1 RBSS_SCRIPTED_DIRECT=1 RBSS_SCRIPTED_SHOWFILE_DIRECT=1 RBSS_SMART_REARM_EXPERIMENT=1 RBSS_SMART_DROP=1 RBSS_SMART_BREAKDOWN=1 RBSS_LASER_CONFIG=\"${LASER_CONFIG_PATH}\" ${TRUTH_ENV} ${PYTHON} -u -m rb_ss_bridge_v2 2>&1 | tee ${LOG_FILE}' RBSS_BRIDGE_MONITOR"
    set custom title of selected tab of front window to "RBSS_BRIDGE_MONITOR"
end tell
EOF
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
    osascript <<'EOF'
tell application "Terminal"
    activate
    do script "bash -c 'printf \"\\\\033]0;RBSS_BRIDGE_MONITOR\\\\007\"; echo \"━━━ Bridge Monitor ━━━\"; tail -n 100 -F /tmp/bridge.log & wait $!' RBSS_BRIDGE_MONITOR"
    set custom title of selected tab of front window to "RBSS_BRIDGE_MONITOR"
end tell
EOF
}

close_monitor() {
    pkill -f "$MONITOR_MARKER" 2>/dev/null
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
    stop_streamdeck
    if [ "$MONITOR_OPENED" -eq 1 ] || monitor_open; then
        close_monitor
        MONITOR_OPENED=0
    fi
}

cleanup() {
    stop_streamdeck
    stop_bridge
}

trap cleanup EXIT
trap 'cleanup; exit 0' INT TERM

while true; do
    if [ "$MANUAL_MODE" = "1" ]; then
        if [ "$MONITOR_OPENED" -eq 1 ] && ! monitor_open; then
            log_watcher "manual terminal closed; stopping bridge"
            stop_streamdeck
            kill_bridge_processes
            exit 0
        fi
        if ! bridge_pids > /dev/null; then
            if [ "$MONITOR_OPENED" -eq 1 ]; then
                log_watcher "manual terminal bridge exited"
                exit 0
            fi
            start_manual_terminal_bridge
        else
            start_streamdeck
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
        if [ "$MONITOR_OPENED" -eq 0 ] && ! monitor_open; then
            open_monitor
        fi
    else
        stop_bridge
    fi
    sleep 3
done
