"""SoundSwitch MIDI input adapter — learned DDJ controller routing.

Owns a worker thread that reads physical MIDI input, normalizes note-on
velocity 0 → note-off, and maintains a bounded state snapshot the 200 Hz
hot path polls via snapshot().  No MIDI API call enters _push_tick.

Classification (F-3) applied here:
  static_override  — note-on adds a recency-ordered layer; note-off removes a
                     matching press layer; toggles remove/re-add on note-on.
  blackout_mask    — note-on holds blackout; note-off releases it.
  Others (pack_selection, bridge_owned_safety, no_project_target,
          inactive_report_only) — inventoried but never mutate player state.

On any of: input port disappearance, worker failure, shutdown, pack reload, or
panic → held layers are cleared before normal base output may resume.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Iterator, Literal, Mapping, Sequence

from .soundswitch_pack_loader import PackMidiBinding

log = logging.getLogger("soundswitch_midi_input")

# python-rtmidi's get_message() is non-blocking; sleep this long between empty
# polls so the worker is responsive to stop without busy-spinning a core.
_INPUT_POLL_INTERVAL_S = 0.003
_PORT_RETRY_INTERVAL_S = 0.25
_PORT_CHECK_INTERVAL_S = 0.25

_LAYER_SEQ_LOCK = threading.Lock()
_LAYER_SEQ = 0


def _next_layer_seq() -> int:
    global _LAYER_SEQ
    with _LAYER_SEQ_LOCK:
        _LAYER_SEQ += 1
        return _LAYER_SEQ


@dataclass(frozen=True, slots=True)
class LayerEntry:
    slot: int
    kind: Literal["toggle", "press"]
    seq: int


@dataclass(frozen=True, slots=True)
class MidiInputSnapshot:
    """Pure non-blocking snapshot of current MIDI input state.

    Safe to call from the 200 Hz push loop.  All fields are immutable once
    constructed.
    """
    held_layers: tuple[LayerEntry, ...]
    blackout_held: bool
    worker_alive: bool
    error: str | None
    mail_drop_count: int
    blackout_bindings: tuple[str, ...] = ()


def _key(binding: PackMidiBinding) -> tuple:
    return (binding.device_name, binding.message_type,
            binding.channel_zero_based, binding.data_byte)


def _binding_key(binding: PackMidiBinding) -> str:
    return f"{binding.channel_zero_based}:{binding.data_byte}"


class _InputPortGone(Exception):
    pass


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
        self._lock = threading.Lock()
        self._layers: list[LayerEntry] = []
        self._blackout_held: bool = False
        self._blackout_bindings: set[str] = set()
        self._worker_alive: bool = False
        self._error: str | None = None
        self._mail_drop_count: int = 0
        self._stop_event = threading.Event()
        self._ready_event = threading.Event()
        self._startup_error: str | None = None
        self._thread: threading.Thread | None = None
        # Pack device identity this port corresponds to; set by start().
        # Only messages whose binding.device_name matches are dispatched.
        # None means "accept from any device" (used in tests without a port).
        self._connected_device: str | None = None
        self._snapshot = self._build_snapshot_locked()

    # ------------------------------------------------------------------
    # Hot-path API (no MIDI API calls, no locks held for duration)
    # ------------------------------------------------------------------

    def snapshot(self) -> MidiInputSnapshot:
        """Return current state; safe for the 200 Hz push loop."""
        return self._snapshot

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(
        self,
        port_name: str,
        *,
        device_name: str | None = None,
        _message_source: Callable[[], Iterator[tuple[int, int, int] | None]] | None = None,
        _port_checker: Callable[[], Sequence[object]] | None = None,
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
            self._refresh_snapshot_locked()

        source = _message_source or self._make_real_source(port_name)
        t = threading.Thread(
            target=self._worker,
            args=(source, port_name, _port_checker),
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

    def mark_unavailable(self) -> None:
        """Mark this input unavailable without raising into pack output startup."""
        self._clear_held("input_unavailable", error_msg="input_unavailable")

    def panic(self) -> None:
        """Immediately clear all held state (e.g. on bridge emergency)."""
        self._clear_held("panic")

    def on_pack_reload(self) -> None:
        """Clear held state on pack reload before fresh authoritative state arrives."""
        with self._lock:
            changed = bool(self._layers) or self._blackout_held
            self._layers.clear()
            self._blackout_held = False
            self._blackout_bindings.clear()
            self._error = None
            self._refresh_snapshot_locked()
        if changed:
            log.info("[SS-MIDI] held state cleared: reason=pack_reload")

    # ------------------------------------------------------------------
    # Internal state mutation (always called under _lock or via _clear_held)
    # ------------------------------------------------------------------

    def _build_snapshot_locked(self) -> MidiInputSnapshot:
        return MidiInputSnapshot(
            held_layers=tuple(self._layers),
            blackout_held=self._blackout_held,
            worker_alive=self._worker_alive,
            error=self._error,
            mail_drop_count=self._mail_drop_count,
            blackout_bindings=tuple(sorted(self._blackout_bindings)),
        )

    def _refresh_snapshot_locked(self) -> None:
        self._snapshot = self._build_snapshot_locked()

    def _clear_held(
        self,
        reason: str,
        *,
        error_msg: str | None = None,
        worker_alive: bool = False,
    ) -> None:
        """Clear held state; error is set to error_msg if given, else reason."""
        with self._lock:
            changed = bool(self._layers) or self._blackout_held
            self._layers.clear()
            self._blackout_held = False
            self._blackout_bindings.clear()
            self._worker_alive = worker_alive
            self._error = error_msg if error_msg is not None else reason
            self._refresh_snapshot_locked()
        if changed:
            log.info("[SS-MIDI] held state cleared: reason=%s", reason)

    def _mark_port_gone(self) -> None:
        self._clear_held("input_port_gone", error_msg="input_port_gone")

    def _process_note_on(self, binding: PackMidiBinding, velocity: int) -> None:
        """Handle a normalised note-on (velocity already != 0 here)."""
        kind = binding.target_kind
        with self._lock:
            if kind == "static_look":
                slot = binding.target_slot
                if slot is None:
                    self._refresh_snapshot_locked()
                    return
                if binding.interaction == "toggle":
                    prior_len = len(self._layers)
                    self._layers = [
                        layer for layer in self._layers
                        if not (layer.slot == slot and layer.kind == "toggle")
                    ]
                    if len(self._layers) != prior_len:
                        log.debug("[SS-MIDI] static slot toggled off: slot=%s", slot)
                    else:
                        self._layers.append(LayerEntry(slot, "toggle", _next_layer_seq()))
                        log.debug("[SS-MIDI] static slot toggled on: slot=%s", slot)
                    self._refresh_snapshot_locked()
                    return
                self._layers.append(LayerEntry(slot, "press", _next_layer_seq()))
                self._refresh_snapshot_locked()
                log.debug("[SS-MIDI] static slot selected: slot=%s", slot)
            elif kind == "blackout_mask":
                self._blackout_held = True
                self._blackout_bindings.add(_binding_key(binding))
                self._refresh_snapshot_locked()
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
                for index in range(len(self._layers) - 1, -1, -1):
                    layer = self._layers[index]
                    if layer.slot == slot and layer.kind == "press":
                        del self._layers[index]
                        self._refresh_snapshot_locked()
                        log.debug("[SS-MIDI] static slot released: slot=%s", slot)
                        break
                else:
                    log.debug("[SS-MIDI] note-off for non-current slot=%s; ignored", slot)
            elif kind == "blackout_mask":
                self._blackout_bindings.discard(_binding_key(binding))
                self._blackout_held = False
                if self._blackout_bindings:
                    self._blackout_held = True
                self._refresh_snapshot_locked()
                log.debug("[SS-MIDI] blackout released")
            else:
                log.debug("[SS-MIDI] note-off for non-render kind=%s (no-op)", kind)

    @staticmethod
    def _exact_port_index(ports: Sequence[object], port_name: str) -> int | None:
        matches = [i for i, name in enumerate(ports)
                   if isinstance(name, str) and name == port_name]
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def _port_present(ports: Sequence[object], port_name: str) -> bool:
        return SoundSwitchMidiInputAdapter._exact_port_index(ports, port_name) is not None

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
                    if self._worker_alive and self._error == "input_port_gone":
                        self._error = None
                        self._refresh_snapshot_locked()
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
        """Return a factory that opens a real python-rtmidi input port.

        Uses python-rtmidi's ``MidiIn`` API (the MIDI package the rest of the
        bridge ships).  ``get_message()`` is non-blocking and returns
        ``(message_bytes, delta)`` or ``None``; empty polls sleep briefly and
        yield ``None`` so the worker can observe stop between messages.
        """
        def factory() -> Iterator[tuple[int, int, int] | None]:
            import rtmidi  # type: ignore[import-untyped]
            midi_in = rtmidi.MidiIn()
            try:
                ignore_types = getattr(midi_in, "ignore_types", None)
                if callable(ignore_types):
                    ignore_types(sysex=True, timing=True, active_sense=True)
                ports = midi_in.get_ports()
                match = SoundSwitchMidiInputAdapter._exact_port_index(ports, port_name)
                if match is None:
                    raise _InputPortGone(port_name)
                midi_in.open_port(match)
                next_check = 0.0
                while True:
                    now = time.monotonic()
                    if now >= next_check:
                        next_check = now + _PORT_CHECK_INTERVAL_S
                        if not SoundSwitchMidiInputAdapter._port_present(
                            midi_in.get_ports(), port_name,
                        ):
                            raise _InputPortGone(port_name)
                    msg = midi_in.get_message()
                    if msg is not None:
                        data, _delta = msg
                        if len(data) >= 3:
                            yield (data[0], data[1], data[2])
                        else:
                            time.sleep(_INPUT_POLL_INTERVAL_S)
                            yield None
                        continue  # drain queued messages before sleeping
                    time.sleep(_INPUT_POLL_INTERVAL_S)
                    yield None
            finally:
                try:
                    midi_in.close_port()
                except Exception:
                    pass
        return factory

    def _worker(
        self,
        source_factory: Callable[[], Iterator[tuple[int, int, int] | None]],
        port_name: str,
        port_checker: Callable[[], Sequence[object]] | None,
    ) -> None:
        ever_ready = False
        ready = False
        source: Iterator[tuple[int, int, int] | None] | None = None
        try:
            while not self._stop_event.is_set():
                try:
                    source = source_factory()
                    for msg in source:
                        if not ready:
                            with self._lock:
                                self._worker_alive = True
                                self._error = None
                                self._refresh_snapshot_locked()
                            ready = True
                            ever_ready = True
                            self._ready_event.set()
                            log.info("[SS-MIDI] worker started")
                        if self._stop_event.is_set():
                            break
                        if msg is None:
                            if port_checker is not None and not self._port_present(
                                port_checker(), port_name,
                            ):
                                raise _InputPortGone(port_name)
                            continue
                        status, data1, data2 = msg
                        self._feed_raw_message(status, data1, data2)
                    if not self._stop_event.is_set():
                        raise _InputPortGone(port_name)
                except _InputPortGone:
                    try:
                        close = getattr(source, "close", None)
                        if callable(close):
                            close()
                    finally:
                        source = None
                    if ready or not ever_ready:
                        self._mark_port_gone()
                        self._ready_event.set()
                        log.warning("[SS-MIDI] input port gone; retrying exact port")
                    ready = False
                    # ponytail: clear on first absence; add debounce only if live flaps prove noisy.
                    self._stop_event.wait(_PORT_RETRY_INTERVAL_S)
                    continue
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
            try:
                close = getattr(source, "close", None)
                if callable(close):
                    close()
            finally:
                if not ever_ready and self._startup_error is None:
                    self._ready_event.set()
                with self._lock:
                    self._worker_alive = False
                    self._refresh_snapshot_locked()
                log.info("[SS-MIDI] worker stopped")


class SoundSwitchMidiInputGroup:
    """Own one input adapter per render-affecting controller as one lifecycle.

    Construction validates aliases before any worker starts.  Static-look
    devices are auto-bound by pack device name when no explicit alias exists;
    blackout-only devices are not opened as inputs.  Port aliases and device
    names are intentionally absent from ``status()``.
    """

    def __init__(
        self,
        bindings: Sequence[PackMidiBinding],
        aliases: Mapping[str, str],
        *,
        stale_timeout_ms: int = 2000,
        adapter_factory=SoundSwitchMidiInputAdapter,
    ) -> None:
        input_devices = {
            binding.device_name
            for binding in bindings
            if binding.target_kind == "static_look"
        }
        if len(set(aliases.values())) != len(aliases):
            raise ValueError("controller input aliases must own distinct ports")
        unknown = sorted(set(aliases) - input_devices)
        if unknown:
            raise ValueError("controller input alias has no verified static-look binding")
        self._entries: tuple[tuple[str, str, str, SoundSwitchMidiInputAdapter], ...] = tuple(
            (
                device_name,
                aliases.get(device_name, device_name),
                "override" if device_name in aliases else "auto",
                adapter_factory(
                    [binding for binding in bindings if binding.device_name == device_name],
                    stale_timeout_ms=stale_timeout_ms,
                ),
            )
            for device_name in sorted(input_devices)
        )
        self._started = False

    @property
    def worker_count(self) -> int:
        return len(self._entries)

    def start(self) -> None:
        if self._started:
            raise RuntimeError("SoundSwitchMidiInputGroup already started")
        available = 0
        for device_name, port_alias, mode, adapter in self._entries:
            try:
                adapter.start(port_alias, device_name=device_name)
            except Exception as exc:
                try:
                    adapter.stop()
                except Exception:
                    pass
                mark_unavailable = getattr(adapter, "mark_unavailable", None)
                if callable(mark_unavailable):
                    mark_unavailable()
                log.warning(
                    "[SS-MIDI] controller input unavailable  mode=%s  error=%s",
                    mode,
                    type(exc).__name__,
                )
                continue
            available += 1
            log.info("[SS-MIDI] controller input bound  mode=%s", mode)
        if self._entries and available == 0:
            log.warning(
                "[SS-MIDI] no controller inputs available; pack DMX continues without manual static looks"
            )
        self._started = True

    def stop(self) -> None:
        for _device_name, _port_alias, _mode, adapter in reversed(self._entries):
            try:
                adapter.stop()
            except Exception:
                pass
        self._started = False

    def panic(self) -> None:
        for _device_name, _port_alias, _mode, adapter in self._entries:
            adapter.panic()

    def on_pack_reload(self) -> None:
        for _device_name, _port_alias, _mode, adapter in self._entries:
            adapter.on_pack_reload()

    def snapshot(self) -> MidiInputSnapshot:
        snapshots = [adapter.snapshot() for _device, _port, _mode, adapter in self._entries]
        has_error = any(snapshot.error for snapshot in snapshots)
        layers = tuple(sorted(
            (layer for snapshot in snapshots for layer in snapshot.held_layers),
            key=lambda layer: layer.seq,
        ))
        return MidiInputSnapshot(
            held_layers=layers,
            blackout_held=any(snapshot.blackout_held for snapshot in snapshots),
            worker_alive=(all(snapshot.worker_alive for snapshot in snapshots)
                          if snapshots else True),
            error=("input_error" if has_error else None),
            mail_drop_count=sum(snapshot.mail_drop_count for snapshot in snapshots),
            blackout_bindings=tuple(sorted({
                key
                for snapshot in snapshots
                for key in getattr(snapshot, "blackout_bindings", ())
            })),
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
    "LayerEntry",
    "MidiInputSnapshot",
    "PackMidiBinding",
    "SoundSwitchMidiInputAdapter",
    "SoundSwitchMidiInputGroup",
]
