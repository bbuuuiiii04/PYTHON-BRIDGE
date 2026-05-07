#!/bin/bash
# ss_bridge_watcher.sh
# Manual launcher for rb_ss_bridge_v2.
# Watches for Rekordbox, SoundSwitch, and TimecodeLink. When they are present,
# starts or adopts one bridge process and opens one dedicated Terminal monitor.

BRIDGE_DIR="/Users/bbui"
LOG_FILE="/tmp/bridge.log"
PYTHON="/opt/homebrew/bin/python3"
MONITOR_MARKER="RBSS_BRIDGE_MONITOR"
MANUAL_MODE="${RBSS_BRIDGE_MANUAL:-0}"
BRIDGE_PID=""
BRIDGE_MANAGED=0
BACKOFF_INDEX=0
BACKOFF_VALUES=(3 10 30 60)
STARTED_AT=0
WARNED_MULTIPLE=0
MONITOR_OPENED=0

ss_running() {
    pgrep -x "SoundSwitch" > /dev/null 2>&1 && pgrep -x "TimecodeLink" > /dev/null 2>&1
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
        exec env \
            RBSS_LIVE_BPM_FOLLOW=1 \
            RBSS_ANLZ_DIRECT=1 \
            RBSS_POS_CHAIN_DIRECT=1 \
            RBSS_MASTER_SEED_DIRECT=1 \
            RBSS_MASTER_DIRECT=1 \
            RBSS_PLAY_DIRECT=1 \
            RBSS_TRACK_LOAD_DIRECT=1 \
            RBSS_SCRIPTED_DIRECT=1 \
            "$PYTHON" -m rb_ss_bridge_v2
    ) > "$LOG_FILE" 2>&1 &
    BRIDGE_PID=$!
    BRIDGE_MANAGED=1
    STARTED_AT=$(date +%s)
    WARNED_MULTIPLE=0
    log_watcher "started bridge pid=$BRIDGE_PID follow=on anlz_direct=on pos_chain_direct=on master_seed_direct=on master_direct=on play_direct=on track_load_direct=on scripted_direct=on master_phrase_arm=default manual=${MANUAL_MODE}"
}

start_manual_terminal_bridge() {
    MONITOR_OPENED=1
    log_watcher "opening manual bridge terminal"
    osascript <<'EOF'
tell application "Terminal"
    activate
    do script "bash -lc 'printf \"\\033]0;RBSS_BRIDGE_MONITOR\\007\"; echo \"━━━ Bridge Manual Session ━━━\"; cd /Users/bbui || exit 1; env RBSS_LIVE_BPM_FOLLOW=1 RBSS_ANLZ_DIRECT=1 RBSS_POS_CHAIN_DIRECT=1 RBSS_MASTER_SEED_DIRECT=1 RBSS_MASTER_DIRECT=1 RBSS_PLAY_DIRECT=1 RBSS_TRACK_LOAD_DIRECT=1 RBSS_SCRIPTED_DIRECT=1 /opt/homebrew/bin/python3 -u -m rb_ss_bridge_v2 2>&1 | tee /tmp/bridge.log' RBSS_BRIDGE_MONITOR"
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
    do script "bash -c 'printf \"\\033]0;RBSS_BRIDGE_MONITOR\\007\"; echo \"━━━ Bridge Monitor ━━━\"; tail -n 100 -F /tmp/bridge.log & wait $!' RBSS_BRIDGE_MONITOR"
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
    if [ "$MONITOR_OPENED" -eq 1 ] || monitor_open; then
        close_monitor
        MONITOR_OPENED=0
    fi
}

cleanup() {
    stop_bridge
}

trap cleanup EXIT
trap 'cleanup; exit 0' INT TERM

while true; do
    if [ "$MANUAL_MODE" = "1" ]; then
        if [ "$MONITOR_OPENED" -eq 1 ] && ! monitor_open; then
            log_watcher "manual terminal closed; stopping bridge"
            kill_bridge_processes
            exit 0
        fi
        if ! bridge_pids > /dev/null; then
            if [ "$MONITOR_OPENED" -eq 1 ]; then
                log_watcher "manual terminal bridge exited"
                exit 0
            fi
            start_manual_terminal_bridge
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
        if [ "$MONITOR_OPENED" -eq 0 ] && ! monitor_open; then
            open_monitor
        fi
    else
        stop_bridge
    fi
    sleep 3
done
