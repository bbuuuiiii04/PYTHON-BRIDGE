"""Validate-first runtime controller for the SoundSwitch pack (T7e).

Runs on the command thread (never the 200 Hz push loop). Performs all blocking work
(load_pack/verify via the injected ``prepare``; serial open via sender ``start``;
serial close via ``zero_and_stop``) and publishes exactly one immutable
``PackRuntime`` to StateManager via a single atomic assignment.

Invariants (T7e §C):
- validate-FIRST: build + verify the new runtime BEFORE touching the live one;
- no partial swap: on any failure keep the old verified runtime, or force safe
  no-output (disabled) — never a half-swapped state;
- stop-before-start on the shared Enttec serial port: publish a disabled bundle
  (driver stops submitting), ``zero_and_stop`` the OLD sender, THEN start the new;
- physical zero: NoneBackend.submit_frame is a no-op, so disabling/swapping
  explicitly ``zero_and_stop``s the OLD sender — the bundle swap alone is not enough;
- no implicit hot-enable: ``reload``/``backend`` never enable a disabled pack;
- pack failure never falls back to MIDI (safe fallback is disabled/none);
- runtime ``backend=midi`` is deferred -> sanitized ``unsupported_action``;
- all error details are sanitized class/category strings (no paths/ports/messages).
"""
from __future__ import annotations

import threading
from typing import Any, Callable

from .soundswitch_pack_runtime import PackRuntime


def _sanitize_error(exc: BaseException) -> str:
    """Class name only — never the message (may carry paths/ports/aliases)."""
    return type(exc).__name__


def _safe_zero_and_stop(rt: PackRuntime) -> None:
    """Physically zero + stop the runtime's frame sender, then stop its input."""
    sender = getattr(rt, "frame_sender", None)
    if sender is not None:
        try:
            sender.zero_and_stop()
        except Exception:
            try:
                sender.stop()
            except Exception:
                pass
    inp = getattr(rt, "midi_input", None)
    if inp is not None:
        try:
            inp.stop()
        except Exception:
            pass


class SoundSwitchPackController:
    def __init__(
        self,
        *,
        publish: Callable[[PackRuntime], None],
        snapshot: Callable[[], PackRuntime],
        prepare: Callable[[], PackRuntime],
    ) -> None:
        # publish(rt): StateManager.set_pack_runtime (atomic single assignment)
        # snapshot(): current PackRuntime
        # prepare(): build a NEW *unstarted*, verified PackRuntime; raises on failure
        self._publish = publish
        self._snapshot = snapshot
        self._prepare = prepare
        self._lock = threading.Lock()

    # -- public dispatch (called from CommandReader's pack callback) -----------
    def handle(self, action: str, *, backend: Any = None, enabled: Any = None) -> tuple[bool, str]:
        with self._lock:
            if action == "enable":
                return self._enable(bool(enabled))
            if action == "backend":
                return self._set_backend(str(backend))
            if action == "reload":
                return self._reload()
            return False, "unsupported_action"

    # -- helpers --------------------------------------------------------------
    def _go_disabled(self, reason: str) -> None:
        """Publish a disabled (no-output) bundle, then physically zero/stop old."""
        cur = self._snapshot()
        self._publish(PackRuntime(
            enabled=False, reason=reason, pack_sha12=cur.pack_sha12,
            phase_offset_beats=cur.phase_offset_beats,
        ))
        _safe_zero_and_stop(cur)

    def _swap_to_started(self) -> tuple[bool, str]:
        """Validate-first, stop-before-start swap to a freshly started runtime."""
        old = self._snapshot()
        try:
            new_unstarted = self._prepare()  # build+verify BEFORE touching the live one
        except Exception as exc:
            return False, _sanitize_error(exc)  # old retained; no teardown
        # Publish disabled so the driver stops submitting, then free the shared port.
        self._publish(PackRuntime(
            enabled=False, reason="swapping", pack_sha12=old.pack_sha12,
            phase_offset_beats=old.phase_offset_beats,
        ))
        _safe_zero_and_stop(old)
        try:
            if new_unstarted.midi_input is not None:
                new_unstarted.midi_input.start()
            if new_unstarted.frame_sender is not None:
                new_unstarted.frame_sender.start()
        except Exception as exc:
            _safe_zero_and_stop(new_unstarted)
            self._publish(PackRuntime(
                enabled=False, reason="pack_start_failed", pack_sha12=old.pack_sha12,
                phase_offset_beats=old.phase_offset_beats,
            ))
            return False, _sanitize_error(exc)
        self._publish(PackRuntime(
            enabled=True, reason="pack", player=new_unstarted.player,
            midi_input=new_unstarted.midi_input, backend=new_unstarted.backend,
            frame_sender=new_unstarted.frame_sender, pack_sha12=new_unstarted.pack_sha12,
            phase_offset_beats=new_unstarted.phase_offset_beats,
        ))
        return True, "pack"

    # -- actions --------------------------------------------------------------
    def _enable(self, on: bool) -> tuple[bool, str]:
        if not on:
            self._go_disabled("disabled")
            return True, "disabled"
        return self._swap_to_started()  # explicit enable builds+starts (validate-first)

    def _set_backend(self, name: str) -> tuple[bool, str]:
        if name == "none":
            self._go_disabled("none")
            return True, "none"
        if name == "pack":
            return self._swap_to_started()
        # "midi" (and anything else) is deferred at runtime — never opens IAC/MidiOutput.
        return False, "unsupported_action"

    def _reload(self) -> tuple[bool, str]:
        # No implicit hot-enable: reload only swaps when already enabled.
        if not self._snapshot().enabled:
            try:
                self._prepare()  # validate the new pack is loadable, but stay OFF
            except Exception as exc:
                return False, _sanitize_error(exc)
            return True, "reloaded_disabled"
        return self._swap_to_started()
