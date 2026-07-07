"""Isolated Govee transport adapter for LED look decisions (Phase 5)."""
from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable, Mapping

from .led_models import LEDAdapterCommand, LEDAdapterStatus, LEDConfig, LEDLookDecision
from . import bridge_fmt as bf
from . import bridge_log

log = logging.getLogger("govee_scene_adapter")

_QUEUE_MAXSIZE_HARD_CAP = 16
_DEDUPE_RECENT_WINDOW_S = 0.5
_CIRCUIT_FAILURE_THRESHOLD = 3
_CIRCUIT_OPEN_SECONDS = 5.0
_POLL_TIMEOUT_S = 0.05


@dataclass(frozen=True)
class _QueuedCommand:
    command: LEDAdapterCommand
    dedupe_key: tuple[str, str, str, str]
    enqueued_at: float


@dataclass(frozen=True)
class _SendResult:
    ok: bool
    reason: str = ""
    malformed: bool = False


def _default_send_command(_command: LEDAdapterCommand, _timeout_s: float) -> Any:
    raise RuntimeError("live_sender_not_configured")


def _default_status_provider() -> Mapping[str, Any]:
    return {}


class GoveeSceneAdapter:
    """Bounded queue adapter with non-blocking trigger semantics."""

    def __init__(
        self,
        config: LEDConfig,
        *,
        send_command: Callable[[LEDAdapterCommand, float], Any] | None = None,
        status_provider: Callable[[], Mapping[str, Any]] | None = None,
        time_fn: Callable[[], float] | None = None,
    ) -> None:
        self._config = config
        queue_max = max(
            1,
            min(int(config.rate_limits.queue_maxsize), _QUEUE_MAXSIZE_HARD_CAP),
        )
        self._queue: queue.Queue[_QueuedCommand] = queue.Queue(maxsize=queue_max)
        self._send_command = send_command or _default_send_command
        self._status_provider = status_provider or _default_status_provider
        self._time_fn = time_fn or time.monotonic

        self._worker_stop = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self._lock = threading.Lock()

        self._accepted_count = 0
        self._rejected_count = 0
        self._dropped_count = 0
        self._queue_full_count = 0
        self._deduped_count = 0
        self._rate_limited_count = 0
        self._send_count = 0
        self._send_error_count = 0
        self._malformed_response_count = 0
        self._consecutive_send_failures = 0
        self._circuit_open_until = 0.0

        self._last_error = ""
        self._degraded_reason = ""
        self._last_command_at = 0.0
        self._last_command: LEDAdapterCommand | None = None
        self._last_accepted_key: tuple[str, str, str, str] | None = None
        self._last_accepted_at = float("-inf")
        self._last_scene_at = float("-inf")
        self._last_high_impact_at = float("-inf")

        self._pending_keys: set[tuple[str, str, str, str]] = set()
        self._inflight_key: tuple[str, str, str, str] | None = None

        if self._config.enabled and not self._config.dry_run:
            self._start_worker()

    def trigger(self, decision: LEDLookDecision) -> bool:
        """Queue one command without blocking.

        Returns:
            True when accepted into the bounded queue.
            False when disabled, rate-limited, deduped, degraded, or queue full.
        """
        if not self._config.enabled:
            self._record_rejection("disabled")
            return False

        if not self._config.dry_run and self._send_command is _default_send_command:
            self._record_rejection("live_output_not_supported_in_phase3")
            return False

        now = self._time_fn()
        command = LEDAdapterCommand(
            look=decision.look,
            target=decision.target,
            action=decision.action,
            scene_ref=decision.scene_ref,
            reason=decision.reason,
            source=decision.source,
            role=decision.role,
        )
        capability_error = self._capability_error(command)
        if capability_error:
            self._record_rejection(capability_error)
            return False
        dedupe_key = self._dedupe_key(command)
        emergency = self._is_emergency_blackout(command)

        with self._lock:
            worker_running = (
                self._worker_thread is not None and self._worker_thread.is_alive()
            )
            # A blackout is the safety kill switch (honors
            # safety.emergency_blackout_always_available): it must always be
            # delivered, so it bypasses the circuit breaker, dedupe, and
            # rate-limit gates, and evicts a queued command if the queue is full.
            if not emergency:
                if self._is_circuit_open_locked(now):
                    self._record_rejection_locked("circuit_open", dropped=True, degraded=True)
                    return False

                if worker_running:
                    if dedupe_key in self._pending_keys or dedupe_key == self._inflight_key:
                        self._record_rejection_locked("dedupe_pending", deduped=True)
                        return False

                    if (
                        self._last_accepted_key == dedupe_key
                        and (now - self._last_accepted_at) < _DEDUPE_RECENT_WINDOW_S
                    ):
                        self._record_rejection_locked("dedupe_recent", deduped=True)
                        return False

                rate_reason = self._rate_limit_reason_locked(command, now)
                if rate_reason:
                    self._record_rejection_locked(rate_reason, rate_limited=True)
                    return False

            queued = _QueuedCommand(command=command, dedupe_key=dedupe_key, enqueued_at=now)
            try:
                self._queue.put_nowait(queued)
            except queue.Full:
                if not emergency:
                    self._record_rejection_locked(
                        "queue_full",
                        dropped=True,
                        queue_full=True,
                        degraded=True,
                    )
                    return False
                self._make_room_for_emergency_locked()
                try:
                    self._queue.put_nowait(queued)
                except queue.Full:
                    self._record_rejection_locked(
                        "queue_full",
                        dropped=True,
                        queue_full=True,
                        degraded=True,
                    )
                    return False

            self._accepted_count += 1
            self._last_command = command
            self._last_command_at = now
            self._last_error = ""
            if worker_running:
                self._pending_keys.add(dedupe_key)
            self._last_accepted_key = dedupe_key
            self._last_accepted_at = now
            if self._is_high_impact_command(command):
                self._last_high_impact_at = now
            elif command.action == "scene":
                self._last_scene_at = now

        return True

    def pop_next_command(self) -> LEDAdapterCommand | None:
        """Testing/debug helper: non-blocking read of queued command."""
        try:
            queued = self._queue.get_nowait()
        except queue.Empty:
            return None
        with self._lock:
            self._pending_keys.discard(queued.dedupe_key)
        self._queue.task_done()
        return queued.command

    def cancel_pending(self) -> int:
        """Drain queued-but-unsent cloud commands.

        Thread-safe: acquires _lock and uses get_nowait() so it never blocks
        while holding the lock. The in-flight HTTP request (if any) cannot be
        cancelled at this layer; WI-6 RT reconcile covers that residual race.

        Returns the number of commands drained.
        """
        drained = 0
        with self._lock:
            while True:
                try:
                    queued = self._queue.get_nowait()
                except queue.Empty:
                    break
                self._pending_keys.discard(queued.dedupe_key)
                self._queue.task_done()
                drained += 1
        if drained:
            log.info("[RGB] cancel-pending drained=%d", drained)
        return drained

    def shutdown(self) -> bool:
        """Stop worker with bounded join timeout."""
        thread = self._worker_thread
        if thread is None:
            return True
        self._worker_stop.set()
        timeout_s = max(0.001, float(self._config.rate_limits.worker_shutdown_timeout_s))
        thread.join(timeout=timeout_s)
        if thread.is_alive():
            self._set_degraded("worker_shutdown_timeout")
            return False
        with self._lock:
            self._worker_thread = None
        return True

    def close(self) -> bool:
        return self.shutdown()

    def status(self) -> dict:
        """Return fail-soft adapter status payload."""
        try:
            return self._build_status()
        except Exception as exc:  # pragma: no cover - defensive fail-soft path
            safe_reason = f"status_error:{exc.__class__.__name__}"
            with self._lock:
                self._set_degraded_locked("status_error", safe_reason)
                queue_depth = self._queue.qsize()
                queue_max = self._queue.maxsize
                accepted_count = self._accepted_count
                rejected_count = self._rejected_count
                dropped_count = self._dropped_count
                last_error = self._last_error
            return {
                "available": True,
                "running": False,
                "dry_run": self._config.dry_run,
                "degraded": True,
                "degraded_reason": "status_error",
                "queue_depth": queue_depth,
                "queue_max": queue_max,
                "accepted_count": accepted_count,
                "rejected_count": rejected_count,
                "dropped_count": dropped_count,
                "last_error": last_error,
            }

    def _build_status(self) -> dict:
        provider_payload: Mapping[str, Any]
        try:
            provider_payload = self._status_provider()
            if not isinstance(provider_payload, Mapping):
                raise TypeError("status provider must return a mapping")
        except Exception as exc:
            provider_payload = {"provider_error": exc.__class__.__name__}
            self._set_degraded("status_provider_error", f"status_provider_error:{exc.__class__.__name__}")

        with self._lock:
            queue_depth = self._queue.qsize()
            running = self._worker_thread is not None and self._worker_thread.is_alive()
            payload = LEDAdapterStatus(
                available=True,
                running=running,
                dry_run=self._config.dry_run,
                degraded=bool(self._degraded_reason or self._last_error),
                degraded_reason=self._degraded_reason,
                queue_depth=queue_depth,
                queue_max=self._queue.maxsize,
                accepted_count=self._accepted_count,
                rejected_count=self._rejected_count,
                dropped_count=self._dropped_count,
                last_error=self._last_error,
                queue_full_count=self._queue_full_count,
                deduped_count=self._deduped_count,
                rate_limited_count=self._rate_limited_count,
                send_count=self._send_count,
                send_error_count=self._send_error_count,
                malformed_response_count=self._malformed_response_count,
                consecutive_send_failures=self._consecutive_send_failures,
                circuit_open=self._is_circuit_open_locked(self._time_fn()),
                circuit_open_until=self._circuit_open_until,
            )
            result = asdict(payload)
            result["last_command_at"] = self._last_command_at
            result["last_command_look"] = self._last_command.look if self._last_command else ""
            result["last_command_scene_ref"] = (
                self._last_command.scene_ref if self._last_command else ""
            )
            result["circuit_failure_threshold"] = _CIRCUIT_FAILURE_THRESHOLD
            result["provider"] = dict(provider_payload)
            return result

    def _worker_loop(self) -> None:
        while not self._worker_stop.is_set():
            try:
                queued = self._queue.get(timeout=_POLL_TIMEOUT_S)
            except queue.Empty:
                continue
            with self._lock:
                self._pending_keys.discard(queued.dedupe_key)
                self._inflight_key = queued.dedupe_key
            try:
                result = self._send_live_command(queued.command)
                with self._lock:
                    if result.ok:
                        self._send_count += 1
                        was_failing = self._consecutive_send_failures > 0
                        self._consecutive_send_failures = 0
                        if (
                            self._degraded_reason.startswith("send_")
                            or self._degraded_reason in ("malformed_response", "circuit_open")
                        ):
                            self._degraded_reason = ""
                        if was_failing and bf.log_changed("govee_cloud_ok", True):
                            bridge_log.health("govee.cloud", "recovered", lvl=logging.INFO)
                    else:
                        self._send_error_count += 1
                        if result.malformed:
                            self._malformed_response_count += 1
                        was_failing = self._consecutive_send_failures > 0
                        self._consecutive_send_failures += 1
                        self._set_degraded_locked(result.reason, result.reason)
                        if not was_failing and bf.log_changed("govee_cloud_ok", False):
                            bridge_log.health(
                                "govee.cloud", "send failing (%s)", self._last_error,
                                data={"reason": self._last_error},
                            )
                        if self._consecutive_send_failures >= _CIRCUIT_FAILURE_THRESHOLD:
                            self._circuit_open_until = self._time_fn() + _CIRCUIT_OPEN_SECONDS
                            self._degraded_reason = "circuit_open"
            finally:
                with self._lock:
                    self._inflight_key = None
                self._queue.task_done()

    def _send_live_command(self, command: LEDAdapterCommand) -> _SendResult:
        timeout_s = max(0.001, float(self._config.rate_limits.request_timeout_s))
        try:
            raw = self._send_command(command, timeout_s)
        except TimeoutError:
            return _SendResult(ok=False, reason="send_timeout")
        except Exception as exc:  # pragma: no cover - behavior verified via tests
            return _SendResult(ok=False, reason=f"send_exception:{exc.__class__.__name__}")

        if isinstance(raw, Mapping):
            if bool(raw.get("ok", raw.get("success", False))):
                return _SendResult(ok=True)
            reason = raw.get("error") or raw.get("message") or "send_rejected"
            return _SendResult(ok=False, reason=f"send_rejected:{reason}")
        return _SendResult(ok=False, reason="malformed_response", malformed=True)

    def _start_worker(self) -> None:
        with self._lock:
            if self._worker_thread is not None and self._worker_thread.is_alive():
                return
            self._worker_stop.clear()
            self._worker_thread = threading.Thread(
                target=self._worker_loop,
                name="GoveeSceneAdapterWorker",
                daemon=True,
            )
            self._worker_thread.start()

    def _record_rejection(self, reason: str, **kwargs: bool) -> None:
        with self._lock:
            self._record_rejection_locked(reason, **kwargs)

    def _record_rejection_locked(
        self,
        reason: str,
        *,
        dropped: bool = False,
        deduped: bool = False,
        rate_limited: bool = False,
        queue_full: bool = False,
        degraded: bool = False,
    ) -> None:
        self._rejected_count += 1
        if dropped:
            self._dropped_count += 1
        if deduped:
            self._deduped_count += 1
        if rate_limited:
            self._rate_limited_count += 1
        if queue_full:
            self._queue_full_count += 1
        self._last_error = reason
        if degraded:
            self._degraded_reason = reason

    def _rate_limit_reason_locked(self, command: LEDAdapterCommand, now: float) -> str:
        if self._is_high_impact_command(command):
            cooldown_s = max(0.0, float(self._config.rate_limits.high_impact_cooldown_s))
            if now - self._last_high_impact_at < cooldown_s:
                return "high_impact_rate_limited"
            return ""

        if command.role == "ambient":
            return ""

        if command.action == "scene":
            cooldown_s = max(0.0, float(self._config.rate_limits.scene_retrigger_cooldown_s))
            if now - self._last_scene_at < cooldown_s:
                return "scene_retrigger_rate_limited"
        return ""

    def _is_high_impact_command(self, command: LEDAdapterCommand) -> bool:
        # NOTE: 'off'/blackout is de-escalation, not a high-impact flash. It must
        # NOT consume the high-impact cooldown budget, otherwise the pre-drop
        # blackout would rate-limit the drop look that follows it ~1-2 beats
        # later. Blackout delivery is guaranteed via _is_emergency_blackout().
        if command.role in {"drop", "pre_drop"}:
            return True
        reason_text = command.reason.lower()
        return "drop" in reason_text or "impact" in reason_text

    def _is_emergency_blackout(self, command: LEDAdapterCommand) -> bool:
        # Blackout ("go dark") must always be deliverable: it is the safety kill
        # switch and is idempotent, so it bypasses circuit/dedupe/rate/queue gates.
        return command.action == "off" or command.look == self._config.blackout

    def _make_room_for_emergency_locked(self) -> None:
        """Evict the oldest queued command so a blackout can always enqueue."""
        try:
            dropped = self._queue.get_nowait()
        except queue.Empty:
            return
        self._pending_keys.discard(dropped.dedupe_key)
        self._queue.task_done()
        self._dropped_count += 1

    def _set_degraded(self, reason: str, last_error: str | None = None) -> None:
        with self._lock:
            self._set_degraded_locked(reason, last_error)

    def _set_degraded_locked(self, reason: str, last_error: str | None = None) -> None:
        self._degraded_reason = reason
        self._last_error = last_error or reason

    def _is_circuit_open_locked(self, now: float) -> bool:
        return now < self._circuit_open_until

    def _dedupe_key(self, command: LEDAdapterCommand) -> tuple[str, str, str, str]:
        return (command.target, command.action, command.look, command.scene_ref)

    def _capability_error(self, command: LEDAdapterCommand) -> str:
        target = self._config.targets.get(command.target)
        if target is None:
            return "unknown_target"
        capabilities = tuple(str(value) for value in target.capabilities)
        if command.action == "scene" and not self._has_scene_capability(capabilities):
            return "unsupported_scene_capability"
        if command.action == "diy_scene" and not self._has_diy_scene_capability(capabilities):
            return "unsupported_diy_scene_capability"
        if command.action == "music_mode" and not self._has_music_mode_capability(capabilities):
            return "unsupported_music_mode_capability"
        if command.action == "off" and not self._has_off_capability(capabilities):
            return "unsupported_off_capability"
        return ""

    def _has_scene_capability(self, capabilities: tuple[str, ...]) -> bool:
        for value in capabilities:
            token = self._normalize_capability(value)
            if token == "scene" or "scene" in token:
                return True
        return False

    def _has_diy_scene_capability(self, capabilities: tuple[str, ...]) -> bool:
        for value in capabilities:
            token = self._normalize_capability(value)
            if token in {"diy_scene", "diyscene"}:
                return True
            if "diy" in token and "scene" in token:
                return True
        return False

    def _has_off_capability(self, capabilities: tuple[str, ...]) -> bool:
        for value in capabilities:
            token = self._normalize_capability(value)
            if token == "off":
                return True
            if "powerswitch" in token:
                return True
            if token.startswith("on_off"):
                return True
            if "power" in token and "switch" in token:
                return True
        return False

    def _has_music_mode_capability(self, capabilities: tuple[str, ...]) -> bool:
        for value in capabilities:
            token = self._normalize_capability(value)
            if token in {"music_mode", "musicmode", "music_setting", "musicsetting"}:
                return True
            if "music" in token and ("mode" in token or "setting" in token):
                return True
        return False

    def _normalize_capability(self, value: str) -> str:
        return value.strip().lower().replace(" ", "").replace("-", "_")
