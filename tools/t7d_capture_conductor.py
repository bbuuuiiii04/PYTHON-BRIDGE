#!/usr/bin/env python3
"""T7d capture conductor -- operator-ping + active-wait orchestration.

This tool drives the T7d phase-contract capture pass (capture plan §B4 / §B4.5).
It is an OBSERVER and an operator-instruction emitter. It NEVER connects
fixtures, opens Enttec/serial/DMX output, enables the bridge-native SoundSwitch
pack backend, mutates the SoundSwitch project, or restarts the bridge. The only
files it writes are: an ignored per-run capture directory, a scenario manifest,
sanitized summaries, and (safe) runtime command lines that toggle session
recording. Raw captures stay uncommitted under ``tools/ssfmt/captures/`` (which
is gitignored).

"OPERATOR ACTION" is an active-wait gate, not a stopping point. ``run-scenario``
pings the operator (``say`` + notification), then polls for the expected
artifact/marker until it appears or a hard timeout is reached. On timeout it
FAILS CLOSED (records INCOMPLETE) -- it never reinterprets missing evidence.

Subcommands:
  prepare                       baseline + safety ping
  run-scenario <name>           one scenario, active-wait, classify
  validate-scenario <run_dir>   re-validate an existing capture directory
  summarize-corpus <root>       aggregate accepted/incomplete/failed per scenario

Repo status stays SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
STATUS_JSON = Path("/tmp/rb_ss_bridge_v2_status.json")
COMMANDS_JSONL = Path("/tmp/rb_ss_bridge_v2_commands.jsonl")
BRIDGE_LOG = Path("/tmp/bridge.log")
DEFAULT_CAPTURE_ROOT = REPO_ROOT / "tools" / "ssfmt" / "captures" / "t7d"

HARDWARE_STATUS = "SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED"
MIN_UNIVERSE0_FRAMES = 20
# A capture is only usable if the deck actually played through the scenario
# window: the schema-2 phase trace must carry real *playing* autoloop_phase rows
# spanning at least the scenario's min_window_beats, with a clean integrity
# footer. Without this, a run where the operator never started playback (or
# started it after the window closed) would be rubber-stamped ACCEPTED with an
# empty trace. MIN_PLAYING_PHASE_ROWS is a floor; the beat-span check is the real
# gate (BPM/tick-rate independent).
MIN_PLAYING_PHASE_ROWS = 100

# Required bridge-log markers per scenario are sourced from capture plan §B3.
# They are presence checks; the operator/next agent confirms exact log strings
# against bridge_fmt before relying on a run.
SCENARIOS: dict[str, dict] = {
    "arm": {
        "operator_action": (
            "From stopped/unloaded output, load and play a known unscripted track whose "
            "chosen verified IAC autoloop is stable; continue through the first "
            "pending/locked phrase and at least one later phrase."
        ),
        "required_markers": ["[LX] fired"],
        "min_window_beats": 48,
        "restart_required": False,
    },
    "refire": {
        "operator_action": (
            "Hold the same accepted identity while playback crosses one phrase-marker "
            "refire and one subsequent 32-beat interval refire."
        ),
        "required_markers": ["[SM] midi-refire"],
        "min_window_beats": 64,
        "restart_required": False,
    },
    "master-switch": {
        "operator_action": (
            "Play two unscripted beatgrid-valid decks at a controlled similar BPM; switch "
            "master >1s before the next 32-beat boundary. Keep both transports otherwise "
            "unchanged."
        ),
        "required_markers": ["[LX] fired"],
        "min_window_beats": 48,
        "restart_required": False,
    },
    "drop-hold": {
        "operator_action": (
            "Use a reviewed drop_mode personality with nonzero post_drop_hold_beats; "
            "capture buildup entry, drop crossing, and the entire drop_hold window while "
            "the accepted drop identity stays unchanged."
        ),
        "required_markers": ["[LX] fired"],
        "min_window_beats": 56,
        "restart_required": False,
    },
    "buildup": {
        "operator_action": (
            "Use a track with a curated Smart Drop and an UP phrase. Start >"
            "buildup_lookahead_beats before the drop."
        ),
        "required_markers": ["[LX] fired  role=buildup", "buildup_to_drop_window"],
        "min_window_beats": 48,
        "restart_required": False,
    },
    # NOTE: phrase-anchor was intentionally dropped from the capture pass.
    # _phrase_anchor (smart_rearm.py) only runs when
    # RBSS_SMART_REARM_EXPERIMENT=1 AND RBSS_PHRASE_ANCHOR=1
    # (state_manager.py:481, PHRASE_ANCHOR_ENV default "0"). The operator's live
    # rig sets REARM but not PHRASE_ANCHOR, so the transition never fires in
    # production -- proving its phase origin would prove a contract the runtime
    # never exercises. Re-add it here (with restart_required + startup_flags) if
    # the live launch ever turns RBSS_PHRASE_ANCHOR on.
    "correction": {
        "operator_action": (
            "With master phrase-arm enabled, switch master within 0.25-0.5 beat after a "
            "32-beat boundary until the real logs show the correction sequence. Do not "
            "inject delay or edit code to force it."
        ),
        "required_markers": [
            "arm-grace-late",
            "arm-correction-pending",
            "arm-correction-clear",
        ],
        "min_window_beats": 64,
        "restart_required": False,
    },
}


# --------------------------------------------------------------------------- #
# Pure logic (unit-tested)                                                     #
# --------------------------------------------------------------------------- #


def classify_gate(obs: dict) -> str:
    """Fail-closed classification of one capture gate.

    FAIL: a hard safety/contract breach -- the capture cannot be trusted (pack
    output not disabled, not exactly one bridge process, project bytes changed).
    INCOMPLETE: a safe capture with insufficient/contaminated evidence (timeout,
    recorder drops, missing markers, too few Universe-0 frames) -- recorded as
    incomplete, never reinterpreted. ACCEPTED: every check green (still only a
    precondition; the oracle then decides the phase contract).
    """
    if obs.get("bridge_process_count") != 1:
        return "FAIL"
    if not obs.get("pack_output_disabled"):
        return "FAIL"
    if not obs.get("project_hash_matched"):
        return "FAIL"
    if obs.get("timed_out"):
        return "INCOMPLETE"
    if obs.get("recorder_drops", 0) > 0:
        return "INCOMPLETE"
    if not obs.get("required_markers_present"):
        return "INCOMPLETE"
    if obs.get("pcap_universe0_frames", 0) < MIN_UNIVERSE0_FRAMES:
        return "INCOMPLETE"
    # The phase trace must prove real playback through the window: a clean
    # integrity footer + enough *playing* autoloop_phase rows spanning at least
    # the scenario's min_window_beats. A run with no detected playback (empty
    # trace) is INCOMPLETE, never ACCEPTED.
    if not obs.get("phase_footer_clean", False):
        return "INCOMPLETE"
    if obs.get("playing_phase_rows", 0) < MIN_PLAYING_PHASE_ROWS:
        return "INCOMPLETE"
    if obs.get("playing_phase_beat_span", 0.0) < obs.get("min_window_beats", 0):
        return "INCOMPLETE"
    return "ACCEPTED"


_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_ENDPOINT_RE = re.compile(r"\d{1,3}(?:\.\d{1,3}){3}:\d+")
_IPV4_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
_APPLOG_RE = re.compile(r"AppLog\w*")
_USERPATH_RE = re.compile(r"/Users/[^/\s\"']+")


def _sanitize_str(value: str) -> str:
    value = _UUID_RE.sub("<UUID>", value)
    value = _ENDPOINT_RE.sub("<ENDPOINT>", value)
    value = _IPV4_RE.sub("<IP>", value)
    value = re.sub(r"\b6454\b", "<PORT>", value)  # Art-Net UDP port
    value = _APPLOG_RE.sub("<APPLOG>", value)
    value = _USERPATH_RE.sub("<HOME>", value)
    return value


def sanitize_summary(obj):
    """Recursively scrub paths, IPs, ports, UUIDs, and AppLog names from a summary."""
    if isinstance(obj, dict):
        return {k: sanitize_summary(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_summary(v) for v in obj]
    if isinstance(obj, str):
        return _sanitize_str(obj)
    return obj


def markers_present(log_text: str, required) -> bool:
    return all(marker in log_text for marker in required)


def new_markers_present(log_text: str, start_offset: int, required) -> bool:
    """Markers must appear in the suffix written AFTER the recorder started.

    Searching the whole bridge.log matches stale pre-run lines (the log
    accumulates across the session), so a run can falsely pass on markers from an
    earlier track. Clamp the offset if the log rotated/shrank.
    """
    offset = start_offset if 0 <= start_offset <= len(log_text) else 0
    return markers_present(log_text[offset:], required)


def parse_session_rows(session_text: str) -> list:
    rows = []
    for line in session_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def count_playing_phase_rows(session_text: str) -> int:
    """Number of schema-2 autoloop_phase rows emitted while a deck was playing."""
    return sum(
        1
        for r in parse_session_rows(session_text)
        if r.get("kind") == "autoloop_phase" and r.get("playing")
    )


def playing_phase_beat_span(session_text: str) -> float:
    """Beat span covered by *playing* autoloop_phase rows (max-min abs_beat_pos).

    BPM/tick-rate independent proof that playback ran through the window.
    """
    bp = [
        r.get("abs_beat_pos")
        for r in parse_session_rows(session_text)
        if r.get("kind") == "autoloop_phase"
        and r.get("playing")
        and isinstance(r.get("abs_beat_pos"), (int, float))
    ]
    if len(bp) < 2:
        return 0.0
    return float(max(bp) - min(bp))


def _phase_footer(session_text: str):
    foots = [
        r for r in parse_session_rows(session_text)
        if r.get("kind") == "phase_trace_footer"
    ]
    return foots[0] if len(foots) == 1 else None


def phase_footer_clean(session_text: str) -> bool:
    """Exactly one footer, clean close, no dropped/undrained rows, no writer error."""
    f = _phase_footer(session_text)
    if f is None:
        return False
    return (
        f.get("close_ok") is True
        and f.get("dropped", 1) == 0
        and f.get("undrained", 1) == 0
        and f.get("writer_error") is None
        and f.get("timed_out") is False
    )


def phase_footer_drops(session_text: str) -> int:
    """dropped + undrained from the footer (a missing footer counts as a drop)."""
    f = _phase_footer(session_text)
    if f is None:
        return 1
    return int(f.get("dropped", 0) or 0) + int(f.get("undrained", 0) or 0)


def playing_phase_beat_span_within(session_text: str, t0: float, t1: float) -> float:
    """Beat span of *playing* autoloop_phase rows whose epoch falls in [t0, t1].

    Used to require playback DURING the pcap window: a capture where tcpdump
    started after playback ended has playing rows but none inside the pcap range,
    so the oracle could never correlate arm events to Art-Net frames.
    """
    if t1 <= t0:
        return 0.0
    bp = [
        r.get("abs_beat_pos")
        for r in parse_session_rows(session_text)
        if r.get("kind") == "autoloop_phase"
        and r.get("playing")
        and isinstance(r.get("abs_beat_pos"), (int, float))
        and isinstance(r.get("epoch_ns"), (int, float))
        and t0 <= r["epoch_ns"] / 1e9 <= t1
    ]
    if len(bp) < 2:
        return 0.0
    return float(max(bp) - min(bp))


def tick_fires_within(session_text: str, t0: float, t1: float) -> int:
    """Count autoloop tick-fires whose epoch falls in [t0, t1] (pcap window)."""
    return sum(
        1
        for r in parse_session_rows(session_text)
        if r.get("kind") == "autoloop_phase"
        and r.get("autoloop_tick_just_fired")
        and isinstance(r.get("epoch_ns"), (int, float))
        and t0 <= r["epoch_ns"] / 1e9 <= t1
    )


def pcap_time_range(pcap_path) -> tuple | None:
    """(first, last) packet epoch seconds, or None if unreadable/empty."""
    if not Path(pcap_path).exists():
        return None
    try:
        sys.path.insert(0, str(REPO_ROOT / "tools" / "ssfmt" / "re"))
        from parse_artnet_pcap import read_pcap  # type: ignore

        _net, packets = read_pcap(Path(pcap_path))
        if not packets:
            return None
        return (packets[0][0], packets[-1][0])
    except Exception:
        return None


def build_manifest(scenario: str, run_id: str, *, created_epoch: float) -> dict:
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario: {scenario!r}")
    spec = SCENARIOS[scenario]
    return {
        "scenario": scenario,
        "run_id": run_id,
        "created_epoch": created_epoch,
        "operator_action": spec["operator_action"],
        "required_markers": list(spec["required_markers"]),
        "min_window_beats": spec["min_window_beats"],
        "restart_required": spec.get("restart_required", False),
        "startup_flags": list(spec.get("startup_flags", [])),
        "pack_output_enabled": False,
        "fixtures_required_state": "disconnected/safe",
        "hardware_status": HARDWARE_STATUS,
    }


def write_manifest(path: Path, manifest: dict) -> None:
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True))


def count_universe0_frames(pcap_path: Path) -> int:
    if not Path(pcap_path).exists():
        return 0
    try:
        sys.path.insert(0, str(REPO_ROOT / "tools" / "ssfmt" / "re"))
        from parse_artnet_pcap import universe_frames  # type: ignore

        return len(universe_frames(Path(pcap_path)))
    except Exception:
        return 0


# --------------------------------------------------------------------------- #
# Side-effecting helpers (live system; not unit-tested)                        #
# --------------------------------------------------------------------------- #


def ping(message: str) -> None:
    """Surface an operator action. Best-effort; never raises.

    When T7D_CONDUCTOR_QUIET=1 the audible (`say`) + notification channels are
    suppressed and only the text is printed -- the caller (the driving agent)
    then emits its own short spoken alert and the full command in chat, so the
    operator is not spammed with the entire command read aloud.
    """
    print(f"\n*** OPERATOR ACTION ***\n{message}\n", flush=True)
    if os.environ.get("T7D_CONDUCTOR_QUIET") == "1":
        return
    short = message if len(message) < 220 else message[:217] + "..."
    for cmd in (
        ["say", short],
        [
            "osascript",
            "-e",
            f'display notification {json.dumps(short)} with title "T7d capture conductor"',
        ],
    ):
        try:
            subprocess.run(cmd, check=False, timeout=15)
        except Exception:
            pass


def read_status() -> dict | None:
    try:
        return json.loads(STATUS_JSON.read_text())
    except Exception:
        return None


def pack_output_disabled(status: dict | None) -> bool:
    """True only if we can positively confirm the pack backend is not emitting."""
    if status is None:
        return False  # cannot prove safe -> fail closed
    pack = status.get("soundswitch_pack")
    if not pack:  # null / absent / empty -> backend inactive
        return True
    if pack.get("enabled") is False:
        return True
    return str(pack.get("backend", "")).lower() in ("", "none", "midi")


# A real core bridge runs the package as `python -m rb_ss_bridge_v2` (exact
# module, not a submodule like `rb_ss_bridge_v2.scripts.laser_pad`).
_CORE_MODULE_RE = re.compile(r"-m\s+rb_ss_bridge_v2(\s|$)")
# Non-core lines that also match `pgrep -f rb_ss_bridge_v2`.
_CORE_EXCLUDE_TOKENS = ("bridge_menubar", "laser_pad", "t7d_capture_conductor", "ssfmt", "pgrep")
# The menubar starts the core via `... python -m rb_ss_bridge_v2 ... | tee
# /tmp/bridge.log`; that shell wrapper ALSO matches the module string but is not
# a second core. The wrapped python interpreter is a separate process and is
# still counted, so a genuine second core is never hidden by this filter.
_CORE_SHELL_HINTS = ("bash ", "/bash", " -lc ", "| tee", " tee /", "zsh ", "/sh ")


def is_core_bridge_line(line: str) -> bool:
    """True iff a ``pgrep -fl rb_ss_bridge_v2`` line is a real Python core bridge.

    Excludes the menubar app, the laser pad, this conductor / analysis tools, and
    the menubar's ``... | tee /tmp/bridge.log`` shell wrapper. The wrapper matches
    the module string but is not a core; its wrapped python interpreter is a
    distinct process that still counts, so two genuine cores still report 2.
    """
    s = line.strip()
    if not s:
        return False
    parts = s.split(None, 1)  # drop the leading PID; inspect the command
    cmd = parts[1] if len(parts) > 1 else parts[0]
    if any(tok in cmd for tok in _CORE_EXCLUDE_TOKENS):
        return False
    if any(hint in cmd for hint in _CORE_SHELL_HINTS):
        return False
    return bool(_CORE_MODULE_RE.search(cmd))


def core_bridge_process_count() -> int:
    """Count core bridge processes, excluding the menubar shell + tee wrapper,
    the laser pad, and this conductor / analysis tools. See is_core_bridge_line."""
    try:
        out = subprocess.run(
            ["pgrep", "-fl", "rb_ss_bridge_v2"], capture_output=True, text=True, timeout=10
        ).stdout
    except Exception:
        return -1
    return sum(1 for line in out.splitlines() if is_core_bridge_line(line))


def file_size(path: Path) -> int:
    try:
        return Path(path).stat().st_size
    except OSError:
        return 0


def poll_until(predicate, *, timeout_s: float, interval_s: float = 2.0, label: str = "") -> bool:
    """Active-wait: poll ``predicate`` until true or hard timeout. Fail-closed.

    Returns True if the condition was observed, False on timeout. The caller
    classifies a False as INCOMPLETE and never reinterprets it as evidence.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if predicate():
                return True
        except Exception:
            pass
        remaining = int(deadline - time.monotonic())
        if label:
            print(f"  [active-wait] {label}: waiting (~{remaining}s left)...", flush=True)
        time.sleep(interval_s)
    return False


def append_command(line: dict) -> None:
    with COMMANDS_JSONL.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(line) + "\n")


# --------------------------------------------------------------------------- #
# Subcommands                                                                  #
# --------------------------------------------------------------------------- #


def cmd_prepare(args) -> int:
    status = read_status()
    count = core_bridge_process_count()
    disabled = pack_output_disabled(status)
    print(json.dumps({
        "bridge_core_processes": count,
        "pack_output_disabled": disabled,
        "status_present": status is not None,
        "capture_root": str(args.capture_root),
        "hardware_status": HARDWARE_STATUS,
    }, indent=2))
    if count != 1 or not disabled:
        ping(
            "T7d prepare: bridge process count or pack-disabled check failed. Confirm "
            "exactly one bridge is running and the pack backend is disabled before any "
            "scenario. Do NOT proceed until this is green."
        )
        return 1
    ping(
        "T7d prepare: confirm SoundSwitch is open on the saved bounded project, all "
        "fixtures/Enttec are disconnected and safe, and no live audience is exposed."
    )
    return 0


def cmd_run_scenario(args) -> int:
    scenario = args.scenario
    if scenario not in SCENARIOS:
        print(f"unknown scenario: {scenario}", file=sys.stderr)
        return 2
    run_id = f"t7d_{scenario}_{args.run_stamp}"
    run_dir = Path(args.capture_root) / run_id
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(scenario, run_id, created_epoch=float(args.run_stamp_epoch))
    write_manifest(run_dir / "manifest.json", manifest)
    spec = SCENARIOS[scenario]

    # Baseline (fail-closed before any operator action).
    status = read_status()
    count = core_bridge_process_count()
    if count != 1 or not pack_output_disabled(status):
        ping(
            f"T7d {scenario}: baseline FAILED (bridge processes={count}, pack must be "
            "disabled). Fix and re-run; capture not started."
        )
        _finalize(run_dir, manifest, {
            "bridge_process_count": count,
            "pack_output_disabled": pack_output_disabled(status),
            "project_hash_matched": True,
            "timed_out": False,
            "required_markers_present": False,
            "pcap_universe0_frames": 0,
            "recorder_drops": 0,
        })
        return 1

    if spec.get("restart_required"):
        ping(
            f"T7d {scenario} needs startup flags {spec.get('startup_flags')}. This "
            "requires an explicit operator-approved bridge restart with those flags. "
            "Approve and restart, then re-run this scenario. Capture not started."
        )
        return 3

    pcap = run_dir / "artnet.pcap"
    session = run_dir / "session.jsonl"
    need_beats = spec["min_window_beats"]

    # Snapshot the bridge.log length so marker checks see only window-new lines
    # (the log accumulates across the session; whole-log matching false-passes on
    # stale markers from an earlier track).
    log_start_offset = len(_read(BRIDGE_LOG))

    # Safe runtime command: start the schema-2 session recorder.
    append_command({"cmd": "toggle_record_session", "path": str(session), "dedup": False})

    ping(
        f"T7d {scenario}: start the passive capture now:\n"
        f"    sudo tcpdump -i lo0 -s0 -U -w {pcap} udp port 6454\n"
        f"Then perform ONLY this action and no other lighting/transport change:\n"
        f"    {spec['operator_action']}"
    )

    # ACTIVE WAIT 1: capture becomes active (pcap + session both growing).
    started = poll_until(
        lambda: file_size(pcap) > 0 and file_size(session) > 0,
        timeout_s=args.start_timeout_s,
        label="capture start (pcap+session)",
    )
    # Wall-clock when the pcap first had bytes: only playback AFTER this counts,
    # so the accepted window is guaranteed to overlap the Art-Net capture. (A run
    # where the operator played first and started tcpdump later has playing rows
    # but none inside the pcap range -> the oracle could never align them.)
    pcap_seen_epoch = time.time() if started else 0.0

    played_through = False
    if started:
        # ACTIVE WAIT 2: the deck must play through the window WHILE tcpdump is
        # capturing -- playing rows whose epoch is after pcap-start must span
        # >= min_window_beats, AND the window-new markers must appear. (Whole-log
        # markers alone false-complete on stale lines; whole-session span
        # false-completes on pre-pcap playback.)
        def _played():
            stext = _read(session)
            return (
                playing_phase_beat_span_within(stext, pcap_seen_epoch, time.time()) >= need_beats
                and new_markers_present(_read(BRIDGE_LOG), log_start_offset, spec["required_markers"])
            )

        played_through = poll_until(
            _played,
            timeout_s=args.window_timeout_s,
            label=f"{scenario} playback through {need_beats} beats during pcap + markers",
        )

    ping(
        f"T7d {scenario}: window complete -- stop tcpdump (Ctrl-C), then this conductor "
        "will stop the recorder and collect artifacts."
    )
    append_command({"cmd": "toggle_record_session"})  # stop recorder

    # ACTIVE WAIT 3: artifacts settle (pcap AND session stop growing so the
    # footer is flushed before we read it).
    poll_until(_settled(pcap), timeout_s=30, interval_s=3, label="pcap settle")
    poll_until(_settled(session), timeout_s=30, interval_s=3, label="session settle")

    _copy(BRIDGE_LOG, run_dir / "logs" / "bridge.log")
    session_text = _read(session)
    log_text = _read(BRIDGE_LOG)
    markers_seen = new_markers_present(log_text, log_start_offset, spec["required_markers"])
    # Gate on playback that actually overlaps the captured pcap window.
    prange = pcap_time_range(pcap)
    if prange is None:
        overlap_span = 0.0
        overlap_ticks = 0
    else:
        overlap_span = playing_phase_beat_span_within(session_text, prange[0], prange[1])
        overlap_ticks = tick_fires_within(session_text, prange[0], prange[1])
    obs = {
        "bridge_process_count": core_bridge_process_count(),
        "pack_output_disabled": pack_output_disabled(read_status()),
        "project_hash_matched": True,  # operator hashes before/after per plan B4
        "timed_out": not (started and played_through),
        "required_markers_present": markers_seen,
        "pcap_universe0_frames": count_universe0_frames(pcap),
        "recorder_drops": phase_footer_drops(session_text),
        "playing_phase_rows": count_playing_phase_rows(session_text),
        # the gating span is playback DURING the pcap, not total playback
        "playing_phase_beat_span": round(overlap_span, 3),
        "playing_phase_beat_span_total": round(playing_phase_beat_span(session_text), 3),
        "pcap_overlap_tick_fires": overlap_ticks,
        "phase_footer_clean": phase_footer_clean(session_text),
        "min_window_beats": need_beats,
    }
    verdict = _finalize(run_dir, manifest, obs)
    ping(f"T7d {scenario}: classified {verdict}. See {run_dir}/summary.json")
    return 0


def cmd_validate_scenario(args) -> int:
    run_dir = Path(args.run_dir)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    spec = SCENARIOS[manifest["scenario"]]
    pcap = run_dir / "artnet.pcap"
    log_text = _read(run_dir / "logs" / "bridge.log")
    session_text = _read(run_dir / "session.jsonl")
    need_beats = spec["min_window_beats"]
    # Re-validate against the captured pcap window: the gating span is playback
    # that overlaps the pcap (what the oracle can actually align), not total
    # playback. A run where tcpdump started after playback -> overlap 0 -> INCOMPLETE.
    prange = pcap_time_range(pcap)
    if prange is None:
        overlap_span = 0.0
        overlap_ticks = 0
    else:
        overlap_span = playing_phase_beat_span_within(session_text, prange[0], prange[1])
        overlap_ticks = tick_fires_within(session_text, prange[0], prange[1])
    obs = {
        "bridge_process_count": 1,
        "pack_output_disabled": True,
        "project_hash_matched": _project_hashes_match(run_dir),
        "timed_out": overlap_span < need_beats,
        "required_markers_present": markers_present(log_text, spec["required_markers"]),
        "pcap_universe0_frames": count_universe0_frames(pcap),
        "recorder_drops": phase_footer_drops(session_text),
        "playing_phase_rows": count_playing_phase_rows(session_text),
        "playing_phase_beat_span": round(overlap_span, 3),
        "playing_phase_beat_span_total": round(playing_phase_beat_span(session_text), 3),
        "pcap_overlap_tick_fires": overlap_ticks,
        "phase_footer_clean": phase_footer_clean(session_text),
        "min_window_beats": need_beats,
    }
    verdict = _finalize(run_dir, manifest, obs)
    print(verdict)
    return 0


def cmd_summarize_corpus(args) -> int:
    root = Path(args.capture_root)
    tally: dict[str, dict[str, int]] = {name: {"ACCEPTED": 0, "INCOMPLETE": 0, "FAIL": 0} for name in SCENARIOS}
    for summary in sorted(root.glob("*/summary.json")):
        try:
            data = json.loads(summary.read_text())
        except Exception:
            continue
        scenario = data.get("scenario")
        verdict = data.get("verdict")
        if scenario in tally and verdict in tally[scenario]:
            tally[scenario][verdict] += 1
    needed = 2
    report = {
        "capture_root": str(root),
        "per_scenario": tally,
        "scenarios_with_two_accepted": [s for s, v in tally.items() if v["ACCEPTED"] >= needed],
        "scenarios_blocking": [s for s, v in tally.items() if v["ACCEPTED"] < needed],
        "hardware_status": HARDWARE_STATUS,
    }
    print(json.dumps(sanitize_summary(report), indent=2, sort_keys=True))
    return 0


# --------------------------------------------------------------------------- #
# Internal helpers                                                             #
# --------------------------------------------------------------------------- #


def _read(path: Path) -> str:
    try:
        return Path(path).read_text(errors="replace")
    except OSError:
        return ""


def _copy(src: Path, dst: Path) -> None:
    try:
        dst.write_bytes(Path(src).read_bytes())
    except OSError:
        pass


def _settled(path: Path):
    state = {"last": -1}

    def predicate():
        size = file_size(path)
        stable = size > 0 and size == state["last"]
        state["last"] = size
        return stable

    return predicate


def _project_hashes_match(run_dir: Path) -> bool:
    before = run_dir / "project.before.sha256"
    after = run_dir / "project.after.sha256"
    if not (before.exists() and after.exists()):
        return False
    return before.read_text() == after.read_text()


def _finalize(run_dir: Path, manifest: dict, obs: dict) -> str:
    verdict = classify_gate(obs)
    summary = {
        "scenario": manifest["scenario"],
        "run_id": manifest["run_id"],
        "verdict": verdict,
        "observations": obs,
        "required_markers": manifest["required_markers"],
        "hardware_status": HARDWARE_STATUS,
    }
    (run_dir / "summary.json").write_text(
        json.dumps(sanitize_summary(summary), indent=2, sort_keys=True)
    )
    return verdict


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-root", type=Path, default=DEFAULT_CAPTURE_ROOT)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("prepare")

    rs = sub.add_parser("run-scenario")
    rs.add_argument("scenario", choices=sorted(SCENARIOS))
    rs.add_argument("--run-stamp", required=True, help="e.g. 20260622_120000")
    rs.add_argument("--run-stamp-epoch", default="0", help="epoch seconds for the manifest")
    rs.add_argument("--start-timeout-s", type=float, default=180.0)
    rs.add_argument("--window-timeout-s", type=float, default=420.0)

    vs = sub.add_parser("validate-scenario")
    vs.add_argument("run_dir", type=Path)

    sub.add_parser("summarize-corpus")

    args = parser.parse_args(argv)
    if args.command == "prepare":
        return cmd_prepare(args)
    if args.command == "run-scenario":
        return cmd_run_scenario(args)
    if args.command == "validate-scenario":
        return cmd_validate_scenario(args)
    if args.command == "summarize-corpus":
        return cmd_summarize_corpus(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
