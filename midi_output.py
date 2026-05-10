"""MIDI transport for Laser Director.

Design constraints:
- All MIDI I/O is performed on a dedicated sender thread.
- trigger() is non-blocking and uses a bounded queue.
- Dry-run mode is dependency-free and does not import mido.
- Live mode imports mido lazily and degrades safely on failures.
"""
from __future__ import annotations

import importlib
import heapq
import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

from .laser_models import LaserMidiMessage

log = logging.getLogger("midi_output")

_DURATION_MIN_MS = 10
_DURATION_MAX_MS = 250
_HOLD_MIN_MS = 10
_HOLD_MAX_MS = 30000

_PRIORITY_MAP = {
    "high": 0,
    "normal": 1,
    "low": 2,
}

_CMD_TRIGGER = "trigger"
_CMD_PANIC = "panic"
_CMD_STOP = "stop"


@dataclass(frozen=True)
class _QueuedCommand:
    kind: str
    message: Optional[LaserMidiMessage] = None


class MidiOutput:
    """Bounded, non-blocking MIDI output transport."""

    def __init__(
        self,
        *,
        port_name: str,
        dry_run: bool = True,
        queue_maxsize: int = 64,
    ) -> None:
        self._port_name = str(port_name)
        self._dry_run = bool(dry_run)
        self._queue: queue.PriorityQueue[tuple[int, int, _QueuedCommand]] = queue.PriorityQueue(
            maxsize=max(1, int(queue_maxsize))
        )
        self._seq = 0
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._panic_event = threading.Event()
        self._sender_thread: Optional[threading.Thread] = None

        self._mido: Any = None
        self._outport: Any = None
        self._running = False
        self._degraded = False
        self._degraded_reason = ""
        self._last_error = ""

        self._trigger_count = 0
        self._drop_count = 0
        self._rejected_count = 0
        self._send_error_count = 0
        self._sent_count = 0
        self._panic_count = 0
        self._scheduled_offs: list[tuple[float, int, int, int]] = []
        self._active_held_notes: dict[tuple[int, int], float] = {}

    def start(self) -> None:
        """Start sender loop. Idempotent."""
        with self._lock:
            if self._running:
                return
            self._stop_event.clear()
            self._panic_event.clear()
            self._running = True

        # Dry-run must remain dependency-free: no import or port open.
        if not self._dry_run:
            self._prepare_live_output()

        thread = threading.Thread(target=self._sender_loop, name="laser-midi-sender", daemon=True)
        self._sender_thread = thread
        thread.start()

    def stop(self) -> None:
        """Bounded, idempotent shutdown that never hangs indefinitely."""
        with self._lock:
            thread = self._sender_thread
            self._running = False
        self._stop_event.set()
        self._panic_event.set()
        self._enqueue_control(_CMD_STOP)
        if thread is not None and thread.is_alive():
            thread.join(timeout=0.5)
        with self._lock:
            self._sender_thread = None
        self._clear_held_notes(send_note_off=not self._dry_run)
        self._close_port()

    def trigger(self, msg: LaserMidiMessage, priority: str = "normal") -> bool:
        """Queue one MIDI message without blocking.

        Returns:
            True when queued, False when rejected (degraded/unavailable) or dropped
            due to queue-full.
        """
        if not self._dry_run:
            with self._lock:
                degraded = self._degraded
                running = self._running
            if degraded or not running:
                self._record_rejection()
                return False

        cmd = _QueuedCommand(kind=_CMD_TRIGGER, message=msg)
        level = _PRIORITY_MAP.get(str(priority).lower(), _PRIORITY_MAP["normal"])
        if not self._enqueue(level, cmd):
            with self._lock:
                self._drop_count += 1
                self._rejected_count += 1
            return False

        with self._lock:
            self._trigger_count += 1
        return True

    def panic(self) -> None:
        """Interrupt active pulses and force all-notes-off in live mode."""
        with self._lock:
            self._panic_count += 1
        self._panic_event.set()
        self._drain_queue()
        if self._dry_run:
            return
        self._enqueue_control(_CMD_PANIC)

    def status(self) -> dict:
        with self._lock:
            return {
                "available": True,
                "running": self._running,
                "dry_run": self._dry_run,
                "degraded": self._degraded,
                "degraded_reason": self._degraded_reason,
                "port_name": self._port_name,
                "queue_size": self._queue.qsize(),
                "queue_max": self._queue.maxsize,
                "trigger_count": self._trigger_count,
                "drop_count": self._drop_count,
                "rejected_count": self._rejected_count,
                "send_error_count": self._send_error_count,
                "sent_count": self._sent_count,
                "panic_count": self._panic_count,
                "last_error": self._last_error,
                "active_held_notes": [
                    {
                        "channel": channel,
                        "note": note,
                        "off_at": off_at,
                    }
                    for (channel, note), off_at in sorted(self._active_held_notes.items())
                ],
            }

    def _prepare_live_output(self) -> None:
        try:
            self._mido = importlib.import_module("mido")
        except Exception as exc:
            self._set_degraded("dependency_missing", exc)
            return

        try:
            self._outport = self._mido.open_output(self._port_name)
        except Exception as exc:
            self._set_degraded("port_unavailable", exc)

    def _enqueue(self, level: int, cmd: _QueuedCommand) -> bool:
        with self._lock:
            seq = self._seq
            self._seq += 1
        try:
            self._queue.put_nowait((level, seq, cmd))
            return True
        except queue.Full:
            return False

    def _enqueue_control(self, kind: str) -> None:
        cmd = _QueuedCommand(kind=kind)
        if self._enqueue(-1, cmd):
            return
        self._drain_queue(max_items=1)
        self._enqueue(-1, cmd)

    def _drain_queue(self, max_items: Optional[int] = None) -> None:
        drained = 0
        while max_items is None or drained < max_items:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
            drained += 1

    def _sender_loop(self) -> None:
        while not self._stop_event.is_set():
            self._process_due_note_offs()
            timeout = self._next_wait_timeout()
            try:
                _, _, cmd = self._queue.get(timeout=timeout)
            except queue.Empty:
                continue

            if cmd.kind == _CMD_STOP:
                break
            if cmd.kind == _CMD_PANIC:
                self._clear_held_notes(send_note_off=True)
                self._send_panic_all_notes_off()
                continue
            if cmd.kind == _CMD_TRIGGER and cmd.message is not None:
                self._send_trigger(cmd.message)
        self._clear_held_notes(send_note_off=not self._dry_run)

    def _send_trigger(self, msg: LaserMidiMessage) -> None:
        if self._dry_run:
            with self._lock:
                self._sent_count += 1
            return

        with self._lock:
            degraded = self._degraded
            outport = self._outport
            mido = self._mido
        if degraded or outport is None or mido is None:
            self._record_rejection()
            return

        channel = max(0, min(15, int(msg.channel) - 1))
        note = int(msg.note)
        try:
            if msg.kind == "cc":
                outport.send(
                    mido.Message(
                        "control_change",
                        channel=channel,
                        control=int(msg.cc),
                        value=int(msg.value),
                    )
                )
                with self._lock:
                    self._sent_count += 1
                return
            behavior = (msg.behavior or "").strip().lower()
            if not behavior:
                if msg.kind == "note_pulse":
                    behavior = "pulse"
                elif msg.kind == "note_on":
                    behavior = "note_on"
                elif msg.kind == "note_off":
                    behavior = "note_off"

            if behavior == "pulse" or msg.kind == "note_pulse":
                duration_ms = max(_DURATION_MIN_MS, min(_DURATION_MAX_MS, int(msg.duration_ms)))
                self._send_note_on(channel=channel, note=note, velocity=int(msg.velocity))
                self._schedule_note_off(channel=channel, note=note, hold_ms=duration_ms)
            elif behavior == "hold_ms":
                hold_ms = max(_HOLD_MIN_MS, min(_HOLD_MAX_MS, int(msg.hold_ms)))
                self._send_note_on(channel=channel, note=note, velocity=int(msg.velocity))
                self._schedule_note_off(channel=channel, note=note, hold_ms=hold_ms)
            elif behavior == "note_on" or msg.kind == "note_on":
                self._send_note_on(channel=channel, note=note, velocity=int(msg.velocity))
            elif behavior == "note_off" or msg.kind == "note_off":
                self._send_note_off(channel=channel, note=note)
            else:
                # Unknown message kinds are treated as send errors.
                raise ValueError(f"unsupported midi behavior={behavior!r} kind={msg.kind!r}")
            with self._lock:
                self._sent_count += 1
        except Exception as exc:
            self._record_send_error(exc)

    def _send_panic_all_notes_off(self) -> None:
        if self._dry_run:
            return
        with self._lock:
            degraded = self._degraded
            outport = self._outport
            mido = self._mido
        if degraded or outport is None or mido is None:
            self._record_rejection()
            return
        try:
            for ch in range(16):
                outport.send(mido.Message("control_change", channel=ch, control=123, value=0))
            with self._lock:
                self._sent_count += 16
        except Exception as exc:
            self._record_send_error(exc)
        finally:
            self._panic_event.clear()
            self._clear_scheduled_note_offs()

    def _send_note_on(self, *, channel: int, note: int, velocity: int) -> None:
        with self._lock:
            outport = self._outport
            mido = self._mido
        if outport is None or mido is None:
            return
        key = (channel, note)
        if self._is_note_held(key):
            self._send_note_off(channel=channel, note=note)
        outport.send(mido.Message("note_on", channel=channel, note=note, velocity=velocity))

    def _send_note_off(self, *, channel: int, note: int) -> None:
        with self._lock:
            outport = self._outport
            mido = self._mido
        if outport is None or mido is None:
            return
        outport.send(mido.Message("note_off", channel=channel, note=note, velocity=0))
        with self._lock:
            self._active_held_notes.pop((channel, note), None)

    def _schedule_note_off(self, *, channel: int, note: int, hold_ms: int) -> None:
        off_at = time.monotonic() + max(0.0, hold_ms / 1000.0)
        key = (channel, note)
        with self._lock:
            self._active_held_notes[key] = off_at
            heapq.heappush(
                self._scheduled_offs,
                (off_at, channel, note, int(off_at * 1000)),
            )

    def _process_due_note_offs(self) -> None:
        while True:
            with self._lock:
                if not self._scheduled_offs:
                    return
                off_at, channel, note, _ = self._scheduled_offs[0]
                if off_at > time.monotonic():
                    return
                heapq.heappop(self._scheduled_offs)

            key = (channel, note)
            with self._lock:
                active_off_at = self._active_held_notes.get(key)
            if active_off_at is None or abs(active_off_at - off_at) > 1e-6:
                continue
            try:
                self._send_note_off(channel=channel, note=note)
            except Exception as exc:
                self._record_send_error(exc)
                continue

    def _next_wait_timeout(self) -> float:
        with self._lock:
            if not self._scheduled_offs:
                return 0.05
            next_off = self._scheduled_offs[0][0]
        return max(0.0, min(0.05, next_off - time.monotonic()))

    def _is_note_held(self, key: tuple[int, int]) -> bool:
        with self._lock:
            return key in self._active_held_notes

    def _clear_scheduled_note_offs(self) -> None:
        with self._lock:
            self._scheduled_offs.clear()

    def _clear_held_notes(self, *, send_note_off: bool) -> None:
        with self._lock:
            held = list(self._active_held_notes.keys())
            if not send_note_off:
                self._active_held_notes.clear()
        self._clear_scheduled_note_offs()
        if not send_note_off:
            return
        for channel, note in held:
            try:
                self._send_note_off(channel=channel, note=note)
            except Exception as exc:
                self._record_send_error(exc)
        # Defensive final cleanup: _send_note_off normally removes these keys,
        # but stop/panic paths must clear local tracking even if a note-off send fails.
        with self._lock:
            for key in held:
                self._active_held_notes.pop(key, None)

    def _record_rejection(self) -> None:
        with self._lock:
            self._drop_count += 1
            self._rejected_count += 1

    def _record_send_error(self, exc: Exception) -> None:
        with self._lock:
            self._send_error_count += 1
            self._last_error = f"{type(exc).__name__}: {exc}"
            self._degraded = True
            if not self._degraded_reason:
                self._degraded_reason = "send_error"
        log.warning("[MIDI] send-error err=%s", exc)
        self._close_port()

    def _set_degraded(self, reason: str, exc: Optional[Exception] = None) -> None:
        with self._lock:
            self._degraded = True
            self._degraded_reason = reason
            self._last_error = "" if exc is None else f"{type(exc).__name__}: {exc}"
        if exc is not None:
            log.warning("[MIDI] degraded reason=%s err=%s", reason, exc)
        else:
            log.warning("[MIDI] degraded reason=%s", reason)

    def _close_port(self) -> None:
        with self._lock:
            outport = self._outport
            self._outport = None
        if outport is not None:
            try:
                outport.close()
            except Exception:
                pass
