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
dropped and counted; because there are no timestamped drop ranges, ANY nonzero
dropped/undrained count invalidates the ENTIRE capture run (fail-closed,
enforced by the offline oracle via the recorder's integrity footer, not here).
:meth:`AutoloopPhaseTracer.close` returns a :class:`PhaseTracerCloseResult` so a
non-clean shutdown (writer error / undrained rows / join timeout) likewise
invalidates the capture.

:func:`build_autoloop_phase_row` is a pure function (primitive reads only) so the
exact set of captured fields is unit-testable without a running bridge.
"""
from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from typing import Callable, Optional

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


@dataclass(frozen=True)
class PhaseTracerCloseResult:
    """Outcome of :meth:`AutoloopPhaseTracer.close`.

    ``ok`` is True only for a fully clean shutdown: the writer thread drained
    every queued row before the sentinel, no row was dropped on the hot path
    (queue overflow), no writer exception occurred, and the join did not time
    out. A non-clean close MUST invalidate the whole capture run (there are no
    timestamped drop ranges, so per-segment salvage is not possible).
    """

    ok: bool
    timed_out: bool
    undrained: int
    dropped: int
    writer_error: Optional[str]


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
        self.dropped = 0          # hot-path overflow (emit could not enqueue)
        self._undrained = 0       # rows discarded after a writer failure
        self._writer_error: Optional[str] = None
        self._closed = False
        self._close_result: Optional[PhaseTracerCloseResult] = None
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
            # A writer exception must not kill the thread (that would hang close()
            # and silently lose the sentinel). Capture the first error, then keep
            # draining to the sentinel, counting the remainder as undrained.
            if self._writer_error is None:
                try:
                    self._writer(row)
                except BaseException as exc:  # noqa: BLE001 - record, keep draining
                    self._writer_error = repr(exc)
                    self._undrained += 1
            else:
                self._undrained += 1
            self._queue.task_done()

    def close(self, *, timeout: float = 10.0) -> PhaseTracerCloseResult:
        """Deterministically drain and stop the writer thread, then report.

        Enqueues a sentinel; because the queue is FIFO, the writer processes every
        previously-queued row before the sentinel, so a clean join is a guaranteed
        drain. A writer exception is captured (see :meth:`_run`) so this never
        hangs. The returned :class:`PhaseTracerCloseResult` says whether the close
        was clean; a non-clean result must invalidate the capture. Idempotent.
        """
        if self._closed:
            return self._close_result  # type: ignore[return-value]
        self._closed = True
        timed_out = False
        if self._started:
            self._queue.put(self._SENTINEL)
            self._thread.join(timeout=timeout)
            timed_out = self._thread.is_alive()
        self._close_result = PhaseTracerCloseResult(
            ok=(
                not timed_out
                and self._writer_error is None
                and self._undrained == 0
                and self.dropped == 0
            ),
            timed_out=timed_out,
            undrained=self._undrained,
            dropped=self.dropped,
            writer_error=self._writer_error,
        )
        return self._close_result
