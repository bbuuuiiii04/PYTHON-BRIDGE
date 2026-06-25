"""SoundSwitch MIDI input adapter — learned DDJ controller routing.

Owns a worker thread that reads physical MIDI input, normalizes note-on
velocity 0 → note-off, and maintains a bounded state snapshot the 200 Hz
hot path polls via snapshot().  No MIDI API call enters _push_tick.

Classification (F-3) applied here:
  static_override  — DDJ note-on selects slot; matching note-off releases
                     only if still current; repeated note-on is idempotent.
  blackout_mask    — note-on holds blackout; note-off releases it.
  Others (pack_selection, bridge_owned_safety, no_project_target,
          inactive_report_only) — inventoried but never mutate player state.

On any of: device disconnect, worker failure, stale held input, shutdown,
pack reload, or panic → held state is cleared and output resolves zero
before normal base output may resume.
"""
from __future__ import annotations

import collections
import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Iterator, Mapping, Sequence

from .soundswitch_pack_loader import PackMidiBinding

log = logging.getLogger("soundswitch_midi_input")

# Maximum MIDI messages buffered between worker wake-ups before drops are
# counted.  Bounded to prevent unbounded memory growth on runaway input.
_MAILBOX_MAXLEN = 256


@dataclass(frozen=True, slots=True)
class MidiInputSnapshot:
    """Pure non-blocking snapshot of current MIDI input state.

    Safe to call from the 200 Hz push loop.  All fields are immutable once
    constructed.
    """
    held_static_slot: int | None
    blackout_held: bool
    worker_alive: bool
    error: str | None
    mail_drop_count: int


def _key(binding: PackMidiBinding) -> tuple:
    return (binding.device_name, binding.message_type,
            binding.channel_zero_based, binding.data_byte)


class SoundSwitchMidiInputAdapter:
    """Bounded non-blocking MIDI input adapter for SoundSwitch learned controls.

    Usage:
        adapter = SoundSwitchMidiInputAdapter(bindings)
        adapter.start("IAC Driver Bus 1")    # starts worker thread
        # ... 200 Hz hot path calls adapter.snapshot() ...
        adapter.stop()                        # clears state + stops thread

    For tests inject events via _feed_raw_message() without starting the
    worker thread.
    """

    def __init__(
        self,
        bindings: Sequence[PackMidiBinding],
        *,
        stale_timeout_ms: int = 2000,
    ) -> None:
        self._bindings: dict[tuple, PackMidiBinding] = {
            _key(b): b for b in bindings
        }
        self._stale_timeout_ms = int(stale_timeout_ms)
        self._lock = threading.Lock()
        self._held_static_slot: int | None = None
        self._static_held_at: float | None = None
        self._blackout_held: bool = False
        self._blackout_held_at: float | None = None
        self._worker_alive: bool = False
        self._error: str | None = None
        self._mail_drop_count: int = 0
        self._mailbox: collections.deque = collections.deque(maxlen=_MAILBOX_MAXLEN)
        self._stop_event = threading.Event()
        self._ready_event = threading.Event()
        self._startup_error: str | None = None
        self._thread: threading.Thread | None = None
        # Pack device identity this port corresponds to; set by start().
        # Only messages whose binding.device_name matches are dispatched.
        # None means "accept from any device" (used in tests without a port).
        self._connected_device: str | None = None

    # ------------------------------------------------------------------
    # Hot-path API (no MIDI API calls, no locks held for duration)
    # ------------------------------------------------------------------

    def snapshot(self) -> MidiInputSnapshot:
        """Return current state; safe for the 200 Hz push loop."""
        with self._lock:
            now = time.monotonic()
            timeout_s = self._stale_timeout_ms / 1000.0
            stale = False
            if self._static_held_at is not None and now - self._static_held_at >= timeout_s:
                self._held_static_slot = None
                self._static_held_at = None
                stale = True
            if self._blackout_held_at is not None and now - self._blackout_held_at >= timeout_s:
                self._blackout_held = False
                self._blackout_held_at = None
                stale = True
            if stale:
                self._error = "stale_hold"
            return MidiInputSnapshot(
                held_static_slot=self._held_static_slot,
                blackout_held=self._blackout_held,
                worker_alive=self._worker_alive,
                error=self._error,
                mail_drop_count=self._mail_drop_count,
            )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(
        self,
        port_name: str,
        *,
        device_name: str | None = None,
        _message_source: Callable[[], Iterator[tuple[int, int, int] | None]] | None = None,
        readiness_timeout_s: float = 2.0,
    ) -> None:
        """Start the MIDI worker thread.

        device_name: the pack device identity this port corresponds to
            (e.g. "DDJ-800").  When provided, only MIDI messages whose
            binding's device_name matches are dispatched; messages from any
            other device on the same port are silently ignored.  Omit in
            tests that inject events without a real port.

        _message_source: injectable factory for tests (returns an iterator
            of (status_byte, data1, data2) tuples or None on timeout).
            In production a real MIDI port is opened.
        """
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeError("SoundSwitchMidiInputAdapter already started")
            self._stop_event.clear()
            self._ready_event.clear()
            self._startup_error = None
            self._worker_alive = False
            self._error = None
            self._connected_device = device_name

        source = _message_source or self._make_real_source(port_name)
        t = threading.Thread(
            target=self._worker,
            args=(source,),
            name="ss-midi-input",
            daemon=True,
        )
        self._thread = t
        t.start()
        if not self._ready_event.wait(timeout=max(0.01, readiness_timeout_s)):
            self.stop()
            raise RuntimeError("controller input startup readiness timed out")
        if self._startup_error is not None:
            self.stop()
            raise RuntimeError("controller input port failed to open")

    def stop(self) -> None:
        """Stop worker, clear held state. Safe to call multiple times."""
        self._stop_event.set()
        t = self._thread
        if t is not None:
            t.join(timeout=2.0)
            if t.is_alive():
                # Worker did not exit within the timeout.  The stop_event is
                # set so it will exit on the next poll interval (~250 ms), but
                # we cannot guarantee it has stopped now.  State is cleared
                # below; the zombie thread can still race, but snapshot() will
                # reflect worker_alive=False for the hot path to gate on.
                log.warning("[SS-MIDI] worker did not exit within stop timeout; state cleared")
        self._clear_held("stop")

    def panic(self) -> None:
        """Immediately clear all held state (e.g. on bridge emergency)."""
        self._clear_held("panic")

    def on_pack_reload(self) -> None:
        """Clear held state on pack reload before fresh authoritative state arrives."""
        self._clear_held("pack_reload")

    # ------------------------------------------------------------------
    # Internal state mutation (always called under _lock or via _clear_held)
    # ------------------------------------------------------------------

    def _clear_held(self, reason: str, *, error_msg: str | None = None) -> None:
        """Clear held state; error is set to error_msg if given, else reason."""
        with self._lock:
            changed = self._held_static_slot is not None or self._blackout_held
            self._held_static_slot = None
            self._static_held_at = None
            self._blackout_held = False
            self._blackout_held_at = None
            self._worker_alive = False
            self._error = error_msg if error_msg is not None else reason
        if changed:
            log.info("[SS-MIDI] held state cleared: reason=%s", reason)

    def _process_note_on(self, binding: PackMidiBinding, velocity: int) -> None:
        """Handle a normalised note-on (velocity already != 0 here)."""
        kind = binding.target_kind
        with self._lock:
            if kind == "static_look":
                slot = binding.target_slot
                if binding.interaction == "toggle":
                    if self._held_static_slot == slot:
                        self._held_static_slot = None
                        self._static_held_at = None
                        log.debug("[SS-MIDI] static slot toggled off: slot=%s", slot)
                    else:
                        self._held_static_slot = slot
                        self._static_held_at = None
                        log.debug("[SS-MIDI] static slot toggled on: slot=%s", slot)
                    return
                self._static_held_at = time.monotonic()
                if self._held_static_slot == slot:
                    log.debug("[SS-MIDI] note-on idempotent: slot=%s", slot)
                    return
                self._held_static_slot = slot
                log.debug("[SS-MIDI] static slot selected: slot=%s", slot)
            elif kind == "blackout_mask":
                self._blackout_held = True
                self._blackout_held_at = time.monotonic()
                log.debug("[SS-MIDI] blackout held")
            # pack_selection / bridge_owned_safety / no_project_target /
            # inactive_report_only — inventoried but do not mutate player state.
            else:
                log.debug("[SS-MIDI] note-on for non-render kind=%s (no-op)", kind)

    def _process_note_off(self, binding: PackMidiBinding) -> None:
        """Handle a normalised note-off."""
        kind = binding.target_kind
        with self._lock:
            if kind == "static_look":
                slot = binding.target_slot
                if binding.interaction == "toggle":
                    log.debug("[SS-MIDI] note-off ignored for toggle slot=%s", slot)
                    return
                # Releasing an old, non-current note must not clear its replacement.
                if self._held_static_slot == slot:
                    self._held_static_slot = None
                    self._static_held_at = None
                    log.debug("[SS-MIDI] static slot released: slot=%s", slot)
                else:
                    log.debug(
                        "[SS-MIDI] note-off for non-current slot=%s (held=%s); ignored",
                        slot, self._held_static_slot,
                    )
            elif kind == "blackout_mask":
                self._blackout_held = False
                self._blackout_held_at = None
                log.debug("[SS-MIDI] blackout released")
            else:
                log.debug("[SS-MIDI] note-off for non-render kind=%s (no-op)", kind)

    # ------------------------------------------------------------------
    # Raw message ingestion (used by worker + test injection)
    # ------------------------------------------------------------------

    def _feed_raw_message(self, status: int, data1: int, data2: int) -> None:
        """Process a single raw MIDI message.  Thread-safe; called by worker."""
        msg_type_nib = (status >> 4) & 0xF
        channel = status & 0xF  # zero-based

        # Normalize note-on velocity 0 → note-off.
        is_note_on = msg_type_nib == 0x9 and data2 != 0
        is_note_off = msg_type_nib == 0x8 or (msg_type_nib == 0x9 and data2 == 0)
        is_cc = msg_type_nib == 0xB
        is_pitch = msg_type_nib == 0xE

        if is_note_on or is_note_off:
            msg_type_str = "note"
            data_byte = data1
        elif is_cc:
            msg_type_str = "control_change"
            data_byte = data1
        elif is_pitch:
            msg_type_str = "pitch_bend"
            data_byte = data1
        else:
            return

        # Dispatch only to bindings whose device_name matches the connected
        # device (spec: "exact device identity, message type, zero-based
        # channel, and data byte").  When _connected_device is None (test
        # injection without a real port) all device names are accepted.
        connected = self._connected_device
        for key, binding in self._bindings.items():
            if connected is not None and key[0] != connected:
                continue
            if key[1] == msg_type_str and key[2] == channel and key[3] == data_byte:
                with self._lock:
                    if self._worker_alive and self._error == "stale_hold":
                        self._error = None
                if is_note_on:
                    self._process_note_on(binding, data2)
                elif is_note_off:
                    self._process_note_off(binding)
                # CC/pitch arrive here only for non-render targets; logged above.

    # ------------------------------------------------------------------
    # Worker thread
    # ------------------------------------------------------------------

    @staticmethod
    def _make_real_source(
        port_name: str,
    ) -> Callable[[], Iterator[tuple[int, int, int] | None]]:
        """Return a factory that opens a real rtmidi port and iterates messages."""
        def factory() -> Iterator[tuple[int, int, int] | None]:
            import rtmidi  # type: ignore[import-untyped]
            midi_in = rtmidi.RtMidiIn()
            try:
                ports = [midi_in.getPortName(i) for i in range(midi_in.getPortCount())]
                matches = [i for i, name in enumerate(ports) if port_name in name]
                if not matches:
                    raise OSError(f"MIDI port not found: {port_name!r}; available={ports!r}")
                midi_in.openPort(matches[0])
                while True:
                    msg = midi_in.getMessage(250)  # 250 ms poll
                    if msg:
                        yield (msg.getRawByte(0), msg.getRawByte(1), msg.getRawByte(2))
                    else:
                        yield None
            finally:
                try:
                    midi_in.closePort()
                except Exception:
                    pass
        return factory

    def _worker(
        self,
        source_factory: Callable[[], Iterator[tuple[int, int, int] | None]],
    ) -> None:
        ready = False
        try:
            for msg in source_factory():
                if not ready:
                    with self._lock:
                        self._worker_alive = True
                        self._error = None
                    ready = True
                    self._ready_event.set()
                    log.info("[SS-MIDI] worker started")
                if self._stop_event.is_set():
                    break
                if msg is None:
                    continue
                status, data1, data2 = msg
                self._feed_raw_message(status, data1, data2)
        except Exception as exc:
            self._startup_error = type(exc).__name__
            self._ready_event.set()
            log.warning("[SS-MIDI] worker died: error=%s", type(exc).__name__)
            # Preserve the specific exception in error_msg; _clear_held sets
            # it rather than the generic "worker_death" reason string.
            self._clear_held(
                "worker_death", error_msg=f"worker_error:{type(exc).__name__}",
            )
        finally:
            if not ready and self._startup_error is None:
                self._startup_error = "source_closed"
                self._ready_event.set()
            with self._lock:
                self._worker_alive = False
            log.info("[SS-MIDI] worker stopped")


class SoundSwitchMidiInputGroup:
    """Own one input adapter per configured device alias as one lifecycle.

    Construction validates the full device/alias set before any worker starts.
    ``start()`` is rollback-safe: if any adapter start raises, every adapter is
    stopped and the group remains unavailable.  Port aliases and device names
    are intentionally absent from ``status()``.
    """

    def __init__(
        self,
        bindings: Sequence[PackMidiBinding],
        aliases: Mapping[str, str],
        *,
        stale_timeout_ms: int = 2000,
        adapter_factory=SoundSwitchMidiInputAdapter,
    ) -> None:
        binding_devices = {binding.device_name for binding in bindings}
        if len(set(aliases.values())) != len(aliases):
            raise ValueError("controller input aliases must own distinct ports")
        unknown = sorted(set(aliases) - binding_devices)
        if unknown:
            raise ValueError("controller input alias has no verified binding")
        self._entries: tuple[tuple[str, str, SoundSwitchMidiInputAdapter], ...] = tuple(
            (
                device_name,
                aliases[device_name],
                adapter_factory(
                    [binding for binding in bindings if binding.device_name == device_name],
                    stale_timeout_ms=stale_timeout_ms,
                ),
            )
            for device_name in sorted(aliases)
        )
        self._started = False

    @property
    def worker_count(self) -> int:
        return len(self._entries)

    def start(self) -> None:
        if self._started:
            raise RuntimeError("SoundSwitchMidiInputGroup already started")
        try:
            for device_name, port_alias, adapter in self._entries:
                adapter.start(port_alias, device_name=device_name)
        except Exception as exc:
            for _device_name, _port_alias, adapter in reversed(self._entries):
                try:
                    adapter.stop()
                except Exception:
                    pass
            raise RuntimeError("controller input startup failed") from exc
        self._started = True

    def stop(self) -> None:
        for _device_name, _port_alias, adapter in reversed(self._entries):
            try:
                adapter.stop()
            except Exception:
                pass
        self._started = False

    def panic(self) -> None:
        for _device_name, _port_alias, adapter in self._entries:
            adapter.panic()

    def on_pack_reload(self) -> None:
        for _device_name, _port_alias, adapter in self._entries:
            adapter.on_pack_reload()

    def snapshot(self) -> MidiInputSnapshot:
        snapshots = [adapter.snapshot() for _device, _port, adapter in self._entries]
        held_slots = {
            snapshot.held_static_slot
            for snapshot in snapshots
            if snapshot.held_static_slot is not None
        }
        conflict = len(held_slots) > 1
        has_error = any(snapshot.error for snapshot in snapshots)
        return MidiInputSnapshot(
            held_static_slot=(None if conflict or not held_slots else next(iter(held_slots))),
            blackout_held=any(snapshot.blackout_held for snapshot in snapshots),
            worker_alive=(all(snapshot.worker_alive for snapshot in snapshots)
                          if snapshots else True),
            error=("conflicting_static_holds" if conflict else
                   "input_error" if has_error else None),
            mail_drop_count=sum(snapshot.mail_drop_count for snapshot in snapshots),
        )

    def status(self) -> dict:
        snapshot = self.snapshot()
        return {
            "configured_inputs": len(self._entries),
            "worker_alive": snapshot.worker_alive,
            "has_error": snapshot.error is not None,
            "mail_drop_count": snapshot.mail_drop_count,
        }


__all__ = [
    "MidiInputSnapshot",
    "PackMidiBinding",
    "SoundSwitchMidiInputAdapter",
    "SoundSwitchMidiInputGroup",
]
