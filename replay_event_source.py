"""Test-the-Lights replay source.

Drives the LIVE bridge's StateManager from a recorded session
(``session_recorder.py`` output) instead of the Rekordbox readers, so the
operator can watch the whole rig respond to a real set with Rekordbox closed.
Enabled per run by ``RBSS_REPLAY_SESSION=<path>``; the launcher and the menubar
set it only after the live-safety guards pass.

Design notes:
- Purely ADDITIVE to the running bridge. The readers stay up but are inert
  (no Rekordbox process to attach to), so this never gates or replaces the live
  path -- it just pumps recorded rows onto the SAME ``event_queue`` /
  ``PositionCache`` / ``LiveBPMService`` the readers would feed.
- RE-STAMP to the live clock. The offline ``ReplayHarness`` patches
  ``time.monotonic`` so recorded positions aren't treated as stale; a real-time
  replay can't patch the clock (the realtime frame engine needs real time), so
  it re-stamps each row's timestamp to "now" as it injects, preserving the
  recorded *spacing* via real-time pacing.

End-to-end behavior (lights actually respond) is verified by the operator's
Task-7 parity run, not by software tests -- the tests here cover the pure
timeline/re-stamp/pacing and preflight logic only.
"""
from __future__ import annotations

import dataclasses
import logging
import os
import threading
import time
from typing import Callable, Optional

from .session_replayer import CapturedSession

log = logging.getLogger(__name__)

REPLAY_SESSION_ENV = "RBSS_REPLAY_SESSION"

_UNSET = object()


def _timeline(session: CapturedSession) -> list[tuple[float, str, object]]:
    """Merge events / positions / live_bpm into one time-ordered row list."""
    rows: list[tuple[float, str, object]] = []
    rows.extend((ev.mono, "event", ev) for ev in session.events)
    for snaps in session.positions.values():
        rows.extend((snap.updated_at, "position", snap) for snap in snaps)
    for deck, samples in session.live_bpm.items():
        rows.extend((t, "live_bpm", (deck, bpm)) for t, bpm in samples)
    rows.sort(key=lambda row: row[0])
    return rows


def run_replay(
    session: CapturedSession,
    event_queue,
    pos_cache,
    live_bpm,
    *,
    stop: Optional[threading.Event] = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Replay a session's rows at recorded pacing, re-stamped to the live clock.

    ``clock``/``sleep`` are injectable so pacing is unit-testable without real
    wall-clock waits. Returns the number of rows injected.
    """
    rows = _timeline(session)
    if not rows:
        return 0

    origin = rows[0][0]
    start = clock()
    injected = 0
    for row_mono, kind, value in rows:
        if stop is not None and stop.is_set():
            break
        target = start + (row_mono - origin)
        now = clock()
        if target > now:
            sleep(target - now)
            now = target

        if kind == "event":
            event_queue.put_nowait(dataclasses.replace(value, mono=now))
        elif kind == "position":
            pos_cache.update(dataclasses.replace(value, updated_at=now))
        elif kind == "live_bpm":
            deck, bpm = value
            if bpm is not None:
                live_bpm.update_hint(deck, float(bpm))
        injected += 1
    return injected


def maybe_start_from_env(event_queue, pos_cache, live_bpm) -> Optional[threading.Thread]:
    """Start a daemon replay pump iff ``RBSS_REPLAY_SESSION`` is set.

    Fails CLOSED and loud on a bad/missing session file (``from_jsonl`` raises)
    -- a Test-the-Lights run that can't load its session must NOT silently fall
    through to a live-reader bridge.
    """
    path = os.environ.get(REPLAY_SESSION_ENV)
    if not path:
        return None
    # Bridge-side live-safety gate. The launcher preflights too, but a STRAY
    # RBSS_REPLAY_SESSION on a watcher/menubar-launched bridge (Rekordbox open,
    # real readers live) would otherwise pump recorded events into a LIVE bridge
    # -- two drivers racing, the exact forbidden case. Refuse here too: fail
    # closed, log loudly, start no pump, never crash the bridge.
    problem = replay_preflight(path)
    if problem is not None:
        log.error("[REPLAY] refusing %s=%s: %s", REPLAY_SESSION_ENV, path, problem)
        return None
    try:
        session = CapturedSession.from_jsonl(path)
    except Exception as exc:
        log.error("[REPLAY] could not load session %s: %r -- not starting replay", path, exc)
        return None
    thread = threading.Thread(
        target=run_replay,
        args=(session, event_queue, pos_cache, live_bpm),
        name="test-lights-replay",
        daemon=True,
    )
    thread.start()
    return thread


def _rekordbox_pid() -> Optional[int]:
    """Rekordbox pid via the canonical reader helper, pgrep fallback."""
    try:
        from .rb_memory import get_rb_pid

        return get_rb_pid()
    except Exception:
        import subprocess

        result = subprocess.run(
            ["pgrep", "-x", "rekordbox"], capture_output=True, text=True
        )
        pids = [p for p in result.stdout.split() if p]
        return int(pids[0]) if pids else None


def replay_preflight(path: Optional[str], *, rekordbox_pid=_UNSET) -> Optional[str]:
    """Return a plain-language refusal message, or None if replay may start.

    Fails closed: Rekordbox running (live-safety) OR a missing session file both
    block; if Rekordbox state can't even be checked, refuse (fail-safe).
    ``rekordbox_pid`` is injectable for tests.
    """
    if rekordbox_pid is _UNSET:
        try:
            rekordbox_pid = _rekordbox_pid()
        except Exception:
            return "Couldn't check whether Rekordbox is running — refusing to start Test the Lights (fail-safe)."
    if rekordbox_pid:
        return (
            "Rekordbox is running — quit Rekordbox before Test the Lights. "
            "It replays a recorded set and must not run against live decks."
        )
    if not path or not os.path.isfile(path):
        return (
            "No test session recorded yet — record one first "
            "(menubar → Record Session during a real set), then Test the Lights."
        )
    return None
