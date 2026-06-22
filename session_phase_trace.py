"""B1 evidence-only autoloop phase trace (schema-2 session rows).

This is preparatory capture tooling for the T7d phase-contract evidence pass --
NOT a T7d runtime feature and NOT an output path. It exists so the capture pass
can prove same-tick reset/continue/snap behavior, which a 2 Hz status scrape
cannot.

Hot-path contract (the part that, once reviewed, runs inside the 200 Hz
``StateManager._push_tick``): the tick side calls :meth:`AutoloopPhaseTracer.emit`
which performs ONLY a bounded ``put_nowait``. No file, socket, MIDI, serial,
subprocess, sleep, or contended lock touches the tick path. A dedicated writer
thread performs all file I/O. When the bounded mailbox is full, samples are
dropped and counted; a dropped sample invalidates any segment spanning the gap
(enforced by the offline oracle, not here).

:func:`build_autoloop_phase_row` is a pure function (primitive reads only) so the
exact set of captured fields is unit-testable without a running bridge.
"""
from __future__ import annotations

import queue
import threading
from typing import Callable

# Primitive fields captured in the StateManager tick that owns a transition.
# All are plain scalars/strings already owned by StateManager; mapping scene ->
# pack identity happens offline (never swap the reference MIDI backend here).
PHASE_FIELDS = (
    "epoch_ns",
    "mono_ns",
    "active_deck",
    "load_gen",
    "playing",
    "position_stale",
    "elapsed_ms",
    "bpm",
    "abs_beat_pos",
    "beatgrid_source",
    "lighting_mode",
    "autoloop_arm_pending",
    "autoloop_arm_sync_beat",
    "autoloop_arm_target_elapsed_ms",
    "pending_autoloop_arm_reason",
    "midi_refire_origin_beat",
    "last_autoloop_status_phrase_beat",
    "phrase_anchor_last_beat",
    "drop_cut_armed",
    "role",
    "reason",
    "autoloop_tick_just_fired",
    "accepted_scene",
    "accepted_note",
    "accepted_trigger_gen",
)


def build_autoloop_phase_row(*, mono_ns: int, epoch_ns: int, **fields) -> dict:
    """Build a schema-2 ``autoloop_phase`` row from primitive scalar inputs.

    Pure: no I/O, no clock reads, no locks. ``t`` is the monotonic replay key
    (seconds) derived from ``mono_ns`` so phase rows sort alongside event /
    position / live_bpm rows during replay.
    """
    row = {"kind": "autoloop_phase", "t": mono_ns / 1e9, "mono_ns": mono_ns, "epoch_ns": epoch_ns}
    for name, value in fields.items():
        row[name] = value
    return row


class AutoloopPhaseTracer:
    """Bounded nonblocking mailbox + writer thread for phase rows.

    ``writer`` is a callable taking one row dict and persisting it (e.g. the
    recorder's lock-guarded ``write_phase_row``). The writer runs only on the
    dedicated thread, never on the caller of :meth:`emit`.
    """

    _SENTINEL = object()

    def __init__(
        self,
        writer: Callable[[dict], None],
        *,
        maxsize: int = 4096,
        autostart: bool = True,
    ) -> None:
        self._writer = writer
        self._queue: "queue.Queue" = queue.Queue(maxsize=maxsize)
        self.dropped = 0
        self._closed = False
        self._thread = threading.Thread(
            target=self._run, name="autoloop-phase-writer", daemon=True
        )
        self._started = False
        if autostart:
            self.start()

    def start(self) -> None:
        if not self._started:
            self._started = True
            self._thread.start()

    def emit(self, row: dict) -> None:
        """Hot-path entry: bounded ``put_nowait`` only. Never blocks or raises."""
        try:
            self._queue.put_nowait(row)
        except queue.Full:
            self.dropped += 1

    @property
    def queued(self) -> int:
        return self._queue.qsize()

    def _run(self) -> None:
        while True:
            row = self._queue.get()
            if row is self._SENTINEL:
                self._queue.task_done()
                return
            try:
                self._writer(row)
            finally:
                self._queue.task_done()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._started:
            self._queue.put(self._SENTINEL)
            self._thread.join(timeout=5.0)
