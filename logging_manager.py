"""
Structured, low-overhead logging for rb_ss_bridge_v2.

Default output stays human-readable. JSON, runtime filters, and deeper event
context are opt-in through environment variables or LoggingManager methods.
"""
from __future__ import annotations

import collections
import contextlib
import contextvars
import json
import logging
import os
import queue
import random
import string
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Optional


_TRACE_ID = contextvars.ContextVar("bridge_trace_id", default="")
_DECK = contextvars.ContextVar("bridge_deck", default=0)
_EVENT = contextvars.ContextVar("bridge_event", default="")
_SOURCE = contextvars.ContextVar("bridge_source", default="")
_DEPTH = contextvars.ContextVar("bridge_depth", default=0)
_ANOMALY = contextvars.ContextVar("bridge_anomaly", default="")


def _new_trace_id() -> str:
    return "".join(random.choice(string.hexdigits.lower()) for _ in range(6))


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            key_l = str(key).lower()
            if any(token in key_l for token in ("token", "secret", "password", "key")):
                redacted[key] = "<redacted>"
            else:
                redacted[key] = _redact(item)
        return redacted
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return value


class BridgeLogRecord(logging.LogRecord):
    """LogRecord carrying bridge trace context from contextvars."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.trace_id = _TRACE_ID.get()
        self.deck = _DECK.get()
        self.event = _EVENT.get()
        self.event_source = _SOURCE.get()
        self.scope_depth = _DEPTH.get()
        self.anomaly = _ANOMALY.get()


_OLD_RECORD_FACTORY: Optional[Callable[..., logging.LogRecord]] = None


def install_record_factory() -> None:
    global _OLD_RECORD_FACTORY
    if _OLD_RECORD_FACTORY is not None:
        return
    _OLD_RECORD_FACTORY = logging.getLogRecordFactory()

    def _factory(*args, **kwargs) -> logging.LogRecord:
        return BridgeLogRecord(*args, **kwargs)

    logging.setLogRecordFactory(_factory)


class JsonFormatter(logging.Formatter):
    """Compact JSON formatter for dashboard ingestion."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for attr in ("trace_id", "deck", "event", "event_source", "scope_depth", "anomaly"):
            value = getattr(record, attr, "")
            if value:
                payload[attr] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


@dataclass
class EventSample:
    kind: str
    deck: int
    source: str
    trace_id: str
    mono: float
    latency_ms: float = 0.0
    payload: dict[str, Any] = field(default_factory=dict)


class LogStats:
    """Bounded counters and samples for on-demand diagnostics."""

    def __init__(self, max_samples: int = 512) -> None:
        self._lock = threading.Lock()
        self._event_counts: collections.Counter[str] = collections.Counter()
        self._error_counts: collections.Counter[str] = collections.Counter()
        self._transition_counts: collections.Counter[str] = collections.Counter()
        self._latencies: collections.deque[float] = collections.deque(maxlen=max_samples)
        self._recent_events: collections.deque[EventSample] = collections.deque(maxlen=max_samples)
        self._last_event_by_deck: dict[int, EventSample] = {}
        self._last_event_global: Optional[EventSample] = None

    def record_enqueue(self, ev: Any, trace_id: str) -> None:
        sample = EventSample(
            kind=str(getattr(ev, "kind", "")),
            deck=int(getattr(ev, "deck", 0) or 0),
            source=str(getattr(ev, "source", "")),
            trace_id=trace_id,
            mono=time.monotonic(),
            payload=dict(getattr(ev, "payload", {}) or {}),
        )
        with self._lock:
            self._event_counts[sample.kind] += 1
            self._recent_events.append(sample)
            if sample.deck:
                self._last_event_by_deck[sample.deck] = sample

    def record_process(self, ev: Any, latency_ms: float) -> Optional[EventSample]:
        deck = int(getattr(ev, "deck", 0) or 0)
        sample = EventSample(
            kind=str(getattr(ev, "kind", "")),
            deck=deck,
            source=str(getattr(ev, "source", "")),
            trace_id=str((getattr(ev, "payload", {}) or {}).get("__trace_id", "")),
            mono=time.monotonic(),
            latency_ms=latency_ms,
            payload=dict(getattr(ev, "payload", {}) or {}),
        )
        with self._lock:
            if latency_ms:
                self._latencies.append(latency_ms)
            prev = self._last_event_global
            self._recent_events.append(sample)
            if deck:
                self._last_event_by_deck[deck] = sample
            self._last_event_global = sample
            return prev

    def record_transition(self, deck: int, field_name: str) -> None:
        with self._lock:
            self._transition_counts[f"deck{deck}.{field_name}"] += 1

    def record_error(self, logger_name: str, message: str) -> None:
        with self._lock:
            key = f"{logger_name}:{message[:80]}"
            self._error_counts[key] += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            latencies = sorted(self._latencies)
            n = len(latencies)
            pct = {}
            if n:
                pct = {
                    "p50": latencies[n // 2],
                    "p95": latencies[min(int(n * 0.95), n - 1)],
                    "p99": latencies[min(int(n * 0.99), n - 1)],
                    "max": latencies[-1],
                    "n": n,
                }
            return {
                "latency_ms": pct,
                "event_counts": dict(self._event_counts.most_common(12)),
                "transition_counts": dict(self._transition_counts.most_common(12)),
                "errors": dict(self._error_counts.most_common(8)),
                "recent_events": list(self._recent_events)[-12:],
            }


class RuntimeLogFilter(logging.Filter):
    """Runtime module/deck/event filter controlled by LoggingManager."""

    def __init__(self, manager: "LoggingManager") -> None:
        super().__init__()
        self._manager = manager

    def filter(self, record: logging.LogRecord) -> bool:
        return self._manager.should_emit(record)


class LoggingEventQueue:
    """Queue wrapper that stamps BridgeEvent payloads with trace and timing data."""

    _TS_KEY = "__enqueue_mono"
    _TRACE_KEY = "__trace_id"

    def __init__(
        self,
        inner: queue.Queue,
        manager: "LoggingManager",
        enqueue_callback: Optional[Callable[[Any], None]] = None,
    ) -> None:
        self._inner = inner
        self._manager = manager
        self._enqueue_callback = enqueue_callback

    def put_nowait(self, ev: Any) -> None:
        payload = getattr(ev, "payload", None)
        if payload is None:
            payload = {}
            setattr(ev, "payload", payload)
        trace_id = payload.get(self._TRACE_KEY) or _TRACE_ID.get() or _new_trace_id()
        payload[self._TRACE_KEY] = trace_id
        payload[self._TS_KEY] = time.monotonic()
        self._manager.stats.record_enqueue(ev, trace_id)
        self._inner.put_nowait(ev)
        if self._enqueue_callback is not None:
            try:
                self._enqueue_callback(ev)
            except Exception:
                logging.getLogger("logging_manager").debug(
                    "enqueue callback failed", exc_info=True
                )

    def get_nowait(self) -> Any:
        return self._inner.get_nowait()

    def get(self, *args, **kwargs):
        return self._inner.get(*args, **kwargs)

    def qsize(self) -> int:
        return self._inner.qsize()


class LoggingManager:
    """Practical bridge logging facade."""

    _COMMON_HINTS = (
        ("OSC listener failed", "check UDP port 7001 availability and competing bridge instances"),
        ("python-osc not installed", "install python-osc or disable scripted OSC triggers"),
        ("RB pid", "Rekordbox likely restarted or exited; wait for re-attach before trusting memory"),
        ("attach failed", "check Rekordbox process, task_for_pid entitlement, and macOS privacy prompts"),
        ("memory stale", "check RB memory reader attachment and recent RB restart logs"),
        ("unknown id", "verify TimecodeLink playlist.yaml values and scripted track registry"),
        ("queue full", "reduce producer burst rate or increase queue capacity"),
        ("lsof", "check Rekordbox file handles and LSOF_LEN_TOLERANCE_MS in config.py"),
    )

    def __init__(self) -> None:
        self.stats = LogStats()
        self._filters: dict[str, set[str]] = {
            "modules": set(),
            "decks": set(),
            "events": set(),
        }
        self._anomaly_mode = bool(os.environ.get("BRIDGE_LOG_ANOMALIES"))
        self._master_switch_times: collections.deque[float] = collections.deque(maxlen=8)
        self._control_path = os.environ.get("BRIDGE_LOG_CONTROL", "/tmp/rb_ss_bridge_v2_logging.json")
        self._watch_stop = threading.Event()
        self._watch_thread: Optional[threading.Thread] = None

    def configure(self, *, json_output: bool = False, root_level: int = logging.INFO) -> None:
        install_record_factory()
        logging.basicConfig(level=root_level)
        root = logging.getLogger()
        root.setLevel(root_level)
        if not root.handlers:
            handler = logging.StreamHandler()
            root.addHandler(handler)
        formatter: logging.Formatter
        if json_output:
            formatter = JsonFormatter()
        else:
            formatter = logging.Formatter(
                "%(asctime)s [%(levelname)-7s] %(message)s",
                datefmt="%H:%M:%S",
            )
        for handler in root.handlers:
            handler.setFormatter(formatter)
            if not any(isinstance(f, RuntimeLogFilter) for f in handler.filters):
                handler.addFilter(RuntimeLogFilter(self))

    def wrap_queue(
        self,
        inner: queue.Queue,
        enqueue_callback: Optional[Callable[[Any], None]] = None,
    ) -> LoggingEventQueue:
        return LoggingEventQueue(inner, self, enqueue_callback=enqueue_callback)

    @contextlib.contextmanager
    def event_scope(
        self,
        event: str,
        *,
        deck: int = 0,
        source: str = "",
        trace_id: str = "",
        anomaly: str = "",
    ) -> Iterator[str]:
        old_trace = _TRACE_ID.set(trace_id or _TRACE_ID.get() or _new_trace_id())
        old_deck = _DECK.set(deck or _DECK.get())
        old_event = _EVENT.set(event)
        old_source = _SOURCE.set(source or _SOURCE.get())
        old_depth = _DEPTH.set(_DEPTH.get() + 1)
        old_anomaly = _ANOMALY.set(anomaly or _ANOMALY.get())
        try:
            yield _TRACE_ID.get()
        finally:
            _TRACE_ID.reset(old_trace)
            _DECK.reset(old_deck)
            _EVENT.reset(old_event)
            _SOURCE.reset(old_source)
            _DEPTH.reset(old_depth)
            _ANOMALY.reset(old_anomaly)

    def bind_event(self, ev: Any) -> contextlib.AbstractContextManager[str]:
        payload = getattr(ev, "payload", {}) or {}
        return self.event_scope(
            str(getattr(ev, "kind", "")),
            deck=int(getattr(ev, "deck", 0) or 0),
            source=str(getattr(ev, "source", "")),
            trace_id=str(payload.get(LoggingEventQueue._TRACE_KEY, "")),
        )

    def finish_event(self, ev: Any) -> tuple[float, Optional[EventSample]]:
        payload = getattr(ev, "payload", {}) or {}
        enqueue_t = payload.pop(LoggingEventQueue._TS_KEY, None)
        latency_ms = 0.0
        if enqueue_t is not None:
            latency_ms = (time.monotonic() - float(enqueue_t)) * 1000.0
        prev = self.stats.record_process(ev, latency_ms)
        return latency_ms, prev

    def annotate(self, record: logging.LogRecord) -> str:
        parts = []
        deck = getattr(record, "deck", 0)
        if deck:
            parts.append(f"deck={deck}")
        source = getattr(record, "event_source", "")
        if source:
            parts.append(f"src={source}")
        trace_id = getattr(record, "trace_id", "")
        if trace_id:
            parts.append(f"tr:{trace_id}")
        anomaly = getattr(record, "anomaly", "")
        if anomaly:
            parts.append(f"anomaly={anomaly}")
        return f" [{' '.join(parts)}]" if parts else ""

    def indent(self, record: logging.LogRecord) -> str:
        depth = max(int(getattr(record, "scope_depth", 0) or 0) - 1, 0)
        return "  " * min(depth, 6)

    def should_emit(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.ERROR:
            return True
        if not self._filters["modules"] and not self._filters["decks"] and not self._filters["events"]:
            return True
        if self._filters["modules"] and record.name not in self._filters["modules"]:
            return False
        deck = str(getattr(record, "deck", "") or "")
        if self._filters["decks"] and deck not in self._filters["decks"]:
            return False
        event = str(getattr(record, "event", "") or "")
        if self._filters["events"] and event not in self._filters["events"]:
            return False
        return True

    def set_runtime_filter(
        self,
        *,
        modules: Optional[set[str]] = None,
        decks: Optional[set[int]] = None,
        events: Optional[set[str]] = None,
    ) -> None:
        self._filters["modules"] = set(modules or [])
        self._filters["decks"] = {str(d) for d in (decks or set())}
        self._filters["events"] = set(events or [])

    def set_level(self, logger_name: str, level: int) -> None:
        logging.getLogger(logger_name).setLevel(level)

    def reload_from_env(self) -> None:
        modules = {m.strip() for m in os.environ.get("BRIDGE_LOG_MODULES", "").split(",") if m.strip()}
        decks = {
            int(d.strip())
            for d in os.environ.get("BRIDGE_LOG_DECKS", "").split(",")
            if d.strip().isdigit()
        }
        events = {e.strip() for e in os.environ.get("BRIDGE_LOG_EVENTS", "").split(",") if e.strip()}
        self.set_runtime_filter(modules=modules, decks=decks, events=events)
        self._anomaly_mode = bool(os.environ.get("BRIDGE_LOG_ANOMALIES"))
        for item in os.environ.get("BRIDGE_LOG_LEVELS", "").split(","):
            if "=" not in item:
                continue
            name, level_name = (part.strip() for part in item.split("=", 1))
            level = getattr(logging, level_name.upper(), None)
            if name and isinstance(level, int):
                self.set_level(name, level)
        self.reload_from_file(self._control_path)

    def reload_from_file(self, path: str) -> None:
        if not path or not os.path.exists(path):
            return
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            return
        modules = set(data.get("modules", []))
        decks = {int(deck) for deck in data.get("decks", []) if str(deck).isdigit()}
        events = set(data.get("events", []))
        if any(key in data for key in ("modules", "decks", "events")):
            self.set_runtime_filter(modules=modules, decks=decks, events=events)
        self._anomaly_mode = bool(data.get("anomalies", self._anomaly_mode))
        if "debug" in data:
            if data.get("debug"):
                self.enable_debug()
            else:
                self.disable_debug()
        for name, level_name in data.get("levels", {}).items():
            level = getattr(logging, str(level_name).upper(), None)
            if isinstance(level, int):
                self.set_level(str(name), level)

    def enable_debug(self) -> None:
        for name in ("tl_tailer", "rb_memory", "filepath_resolver",
                     "scripted_tracks", "osl_output", "state_manager",
                     "diagnostics", "bridge", "logging_manager",
                     "mtc_reader"):
            logging.getLogger(name).setLevel(logging.DEBUG)

    def disable_debug(self) -> None:
        for name in ("tl_tailer", "rb_memory", "filepath_resolver",
                     "scripted_tracks", "osl_output", "state_manager",
                     "diagnostics", "bridge", "logging_manager",
                     "mtc_reader"):
            logging.getLogger(name).setLevel(logging.INFO)

    def start_control_watcher(self, logger: logging.Logger, interval_s: float = 1.0) -> None:
        if self._watch_thread is not None:
            return

        def _watch() -> None:
            last_mtime = 0.0
            while not self._watch_stop.is_set():
                try:
                    mtime = os.path.getmtime(self._control_path)
                except OSError:
                    time.sleep(interval_s)
                    continue
                if mtime != last_mtime:
                    last_mtime = mtime
                    self.reload_from_file(self._control_path)
                    logger.info("logging control reloaded from %s", self._control_path)
                time.sleep(interval_s)

        self._watch_thread = threading.Thread(
            target=_watch,
            name="logging-control",
            daemon=True,
        )
        self._watch_thread.start()

    def stop_control_watcher(self) -> None:
        self._watch_stop.set()

    def detect_anomaly(self, ev: Any) -> str:
        if not self._anomaly_mode:
            return ""
        kind = str(getattr(ev, "kind", ""))
        now = time.monotonic()
        if kind == "master_changed":
            self._master_switch_times.append(now)
            recent = [t for t in self._master_switch_times if now - t <= 5.0]
            if len(recent) >= 4:
                return "rapid_master_switches"
        return ""

    def remediation_hint(self, message: str) -> str:
        for needle, hint in self._COMMON_HINTS:
            if needle.lower() in message.lower():
                return hint
        return ""

    def log_error(
        self,
        logger: logging.Logger,
        message: str,
        *args,
        payload: Optional[dict[str, Any]] = None,
        exc_info: bool = False,
    ) -> None:
        rendered = message % args if args else message
        hint = self.remediation_hint(rendered)
        if payload:
            rendered = f"{rendered} payload={_redact(payload)}"
        if hint:
            rendered = f"{rendered} hint={hint}"
        self.stats.record_error(logger.name, rendered)
        logger.error(rendered, exc_info=exc_info)

    def log_stats(self, logger: logging.Logger) -> None:
        snap = self.stats.snapshot()
        logger.info(
            "log stats latency_ms=%s events=%s transitions=%s errors=%s",
            snap["latency_ms"],
            snap["event_counts"],
            snap["transition_counts"],
            snap["errors"],
        )


manager = LoggingManager()


def get_logging_manager() -> LoggingManager:
    return manager


@contextlib.contextmanager
def log_event_scope(
    event: str,
    *,
    deck: int = 0,
    source: str = "",
    trace_id: str = "",
    anomaly: str = "",
) -> Iterator[str]:
    with manager.event_scope(event, deck=deck, source=source, trace_id=trace_id, anomaly=anomaly) as trace:
        yield trace
