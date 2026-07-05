"""
Structured JSONL event logging for rb_ss_bridge_v2 (AWR-125).

One authoritative event stream per run. The hot path does only a level check,
a `build_record()` dict build, and a non-blocking `put_nowait` onto a bounded
in-memory queue; everything slow (JSON, disk, redaction, stderr mirroring)
belongs to one background writer thread. stdlib `logging` stays the ordinary
API for all call sites — this module supplies the queue handler, the writer
thread, and the `perf()`/`health()` intent helpers on top of it.

Importing this module has no side effects; all setup happens in `init()`.
See docs/architecture/logging_authority.md for the intent contract.
"""
from __future__ import annotations

import atexit
import contextlib
import contextvars
import json
import logging
import os
import queue
import random
import string
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Optional


_DECK = contextvars.ContextVar("deck", default=0)
_TRACE = contextvars.ContextVar("trace", default="")


def _new_trace_id() -> str:
    return "".join(random.choice(string.hexdigits.lower()) for _ in range(6))


def _redact(value: Any) -> Any:
    """Mask dict keys naming secrets. Ported verbatim from logging_manager.py:36-48."""
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


# ── Trace context: bind deck + trace id for an event's lifetime ───────────────

@contextlib.contextmanager
def event_scope(kind: str, *, deck: int = 0, trace_id: str = "") -> Iterator[str]:
    """Bind deck + trace id for the duration of the block; yields the trace id.

    *kind* is accepted for call-site parity with the event being scoped; it is
    not stored (a record's category comes from its `perf`/`health`/`emit` cat,
    never from a lens/scope field).
    """
    _ = kind
    old_deck = _DECK.set(deck or _DECK.get())
    old_trace = _TRACE.set(trace_id or _TRACE.get() or _new_trace_id())
    try:
        yield _TRACE.get()
    finally:
        _DECK.reset(old_deck)
        _TRACE.reset(old_trace)


def stamp_trace(ev: Any) -> str:
    """Ensure ev.payload carries a trace id + enqueue timestamp; return the id.

    Mirrors logging_manager.LoggingEventQueue.put_nowait (logging_manager.py:
    216-225), minus LogStats bookkeeping. Preserves an existing trace id;
    never touches any other payload key.
    """
    payload = getattr(ev, "payload", None)
    if payload is None:
        payload = {}
        setattr(ev, "payload", payload)
    trace_id = payload.get("__trace_id") or _TRACE.get() or _new_trace_id()
    payload["__trace_id"] = trace_id
    payload["__enqueue_mono"] = time.monotonic()
    return trace_id


class TraceQueue:
    """Thin queue.Queue wrapper that stamps BridgeEvent payloads on enqueue."""

    def __init__(
        self,
        inner: "queue.Queue[Any]",
        enqueue_callback: Optional[Callable[[Any], None]] = None,
    ) -> None:
        self._inner = inner
        self._enqueue_callback = enqueue_callback

    def put_nowait(self, ev: Any) -> None:
        stamp_trace(ev)
        self._inner.put_nowait(ev)
        if self._enqueue_callback is not None:
            try:
                self._enqueue_callback(ev)
            except Exception:
                logging.getLogger("bridge_log").debug(
                    "enqueue callback failed", exc_info=True
                )

    def get(self, *args: Any, **kwargs: Any) -> Any:
        return self._inner.get(*args, **kwargs)

    def get_nowait(self) -> Any:
        return self._inner.get_nowait()

    def qsize(self) -> int:
        return self._inner.qsize()


# ── Intent/health emit helpers (the only way to reach PERFORMANCE/OPERATOR) ───

def emit(
    cat: str,
    msg: str,
    *args: Any,
    lvl: int = logging.INFO,
    deck: Optional[int] = None,
    beat: Optional[float] = None,
    data: Optional[dict[str, Any]] = None,
    exc_info: Any = None,
) -> None:
    logger = logging.getLogger(cat)
    if not logger.isEnabledFor(lvl):
        return
    # exc_info normalization mirrors Logger._log(): True -> current
    # sys.exc_info(); a bare exception -> its (type, value, traceback).
    # makeRecord()/LogRecord store exc_info as-is with no such conversion,
    # and we bypass Logger._log() itself (see below), so it must happen here.
    if exc_info:
        if isinstance(exc_info, BaseException):
            exc_info = (type(exc_info), exc_info, exc_info.__traceback__)
        elif not isinstance(exc_info, tuple):
            exc_info = sys.exc_info()
    # Built manually rather than via Logger.log(extra={...}): stdlib's
    # makeRecord() raises KeyError if an extra key already exists on the
    # record, which happens whenever some other loaded module has installed
    # a custom LogRecord factory carrying same-named attributes (e.g.
    # logging_manager.BridgeLogRecord's own `.deck`). Setting attributes
    # directly after the record exists always overwrites, never raises, and
    # is exactly what Logger._log() does with extra internally anyway.
    record = logger.makeRecord(logger.name, lvl, __file__, 0, msg, args, exc_info)
    record.cat = cat
    record.deck = deck
    record.beat = beat
    record.data = data
    logger.handle(record)


def perf(sub: str, msg: str, *args: Any, **kw: Any) -> None:
    """Intent: what the rig should be doing right now. cat = 'perf.<sub>'."""
    emit(f"perf.{sub}", msg, *args, **kw)


def health(sub: str, msg: str, *args: Any, lvl: int = logging.WARNING, **kw: Any) -> None:
    """Edge-triggered health transition. cat = 'health.<sub>'; default WARNING."""
    emit(f"health.{sub}", msg, *args, lvl=lvl, **kw)


# ── build_record: pure function, the JSONL schema in one place ───────────────

def build_record(record: logging.LogRecord) -> dict[str, Any]:
    """Turn a stdlib LogRecord into the JSONL record dict. Pure; no I/O."""
    d: dict[str, Any] = {
        "ts": record.created,
        "mono": time.monotonic(),
        "lvl": record.levelname,
        "cat": getattr(record, "cat", None) or record.name,
        "msg": record.getMessage(),
        "src": record.name,
    }
    deck_extra = getattr(record, "deck", None)
    if deck_extra is not None:
        d["deck"] = deck_extra
    else:
        ctx_deck = _DECK.get()
        if ctx_deck:
            d["deck"] = ctx_deck
    beat = getattr(record, "beat", None)
    if beat is not None:
        d["beat"] = beat
    trace = _TRACE.get()
    if trace:
        d["trace"] = trace
    data = getattr(record, "data", None)
    if data is not None:
        d["data"] = data
    if record.exc_info:
        d["exc"] = "".join(traceback.format_exception(*record.exc_info))
    return d


# ── Hot-path handler: build_record + put_nowait only, never raises, no I/O ───

_RECORD_QUEUE: "queue.Queue[dict[str, Any]]" = queue.Queue(maxsize=8192)
_WARN_PLUS = frozenset({"WARNING", "ERROR", "CRITICAL"})
_STOP = object()  # writer-thread sentinel

_dropped_count = 0


def _bump_dropped() -> None:
    # Deliberately lock-free (approximate diagnostic counter only) so the
    # queue.Full path never adds a lock beyond the queue's own.
    global _dropped_count
    _dropped_count += 1


class _QueueRecordHandler(logging.Handler):
    """Non-blocking log handler: build_record + put_nowait only.

    Hot-path rule (absolute): emit() never raises and never performs I/O.
    A full queue increments an in-memory drop counter; any other exception
    is swallowed. All slow work (JSON, disk, redaction, stderr mirroring) is
    the writer thread's job, never this handler's.
    """

    def __init__(self, q: Optional["queue.Queue[dict[str, Any]]"] = None) -> None:
        super().__init__()
        self._queue = q if q is not None else _RECORD_QUEUE

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._queue.put_nowait(build_record(record))
        except queue.Full:
            _bump_dropped()
        except Exception:
            pass


# ── Writer thread: all the slow work lives here ───────────────────────────────

def _system_record(cat: str, msg: str, data: dict[str, Any], lvl: str = "INFO") -> dict[str, Any]:
    return {
        "ts": time.time(),
        "mono": time.monotonic(),
        "lvl": lvl,
        "cat": cat,
        "msg": msg,
        "src": "bridge_log",
        "data": data,
    }


def _write_line(file_obj: Any, record: dict[str, Any]) -> None:
    record = dict(record)
    if record.get("data") is not None:
        record["data"] = _redact(record["data"])
    line = json.dumps(record, separators=(",", ":"), ensure_ascii=False, default=str)
    file_obj.write(line + "\n")


def _mirror_stderr(d: dict[str, Any]) -> None:
    ts = d.get("ts") or time.time()
    stamp = time.strftime("%H:%M:%S", time.localtime(ts))
    msec = int((ts - int(ts)) * 1000)
    print(f"{stamp}.{msec:03d} [{d.get('lvl', '')}] {d.get('msg', '')}", file=sys.stderr)


def _writer_loop(file_obj: Any) -> None:
    """Daemon loop: drain _RECORD_QUEUE, append JSONL, mirror WARNING+, report drops."""
    last_reported = 0
    while True:
        try:
            d = _RECORD_QUEUE.get(timeout=0.5)
        except queue.Empty:
            d = None
        try:
            if d is _STOP:
                break
            if d is not None:
                _write_line(file_obj, d)
                if d.get("lvl") in _WARN_PLUS:
                    _mirror_stderr(d)
                if _RECORD_QUEUE.empty():
                    file_obj.flush()
            dropped_now = _dropped_count
            if dropped_now != last_reported:
                delta = dropped_now - last_reported
                last_reported = dropped_now
                _write_line(file_obj, _system_record("sys.log", "records dropped", {"dropped": delta}))
                file_obj.flush()
        except Exception:
            # The logging pipeline itself must never die from a bad record.
            continue


# ── File/dir resolution (pure) ────────────────────────────────────────────────

def resolve_log_dir(env: Mapping[str, str]) -> Path:
    """Pure: $RBSS_RUNTIME_DIR/logs when set, else ~/Library/Logs/rb_ss_bridge."""
    runtime_dir = env.get("RBSS_RUNTIME_DIR")
    if runtime_dir:
        return Path(runtime_dir) / "logs"
    return Path.home() / "Library" / "Logs" / "rb_ss_bridge"


def prune_runs(dir: Path, keep: int = 20) -> None:
    """Delete the oldest bridge-*.jsonl files in *dir* beyond *keep*."""
    try:
        runs = sorted(dir.glob("bridge-*.jsonl"))
    except OSError:
        return
    excess = len(runs) - keep
    if excess <= 0:
        return
    for path in runs[:excess]:
        try:
            path.unlink()
        except OSError:
            pass


def _relink(link_path: Path, target: Path) -> None:
    try:
        if link_path.is_symlink() or link_path.exists():
            link_path.unlink()
    except OSError:
        pass
    try:
        link_path.symlink_to(target)
    except OSError:
        pass


# ── Lifecycle: init() / shutdown() ────────────────────────────────────────────

class _State:
    """Mutable process-wide init()/shutdown() state. Not part of the public API."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.initialized = False
        self.file: Optional[Any] = None
        self.writer_thread: Optional[threading.Thread] = None
        self.prior_excepthook: Optional[Callable[..., Any]] = None
        self.prior_threading_excepthook: Optional[Callable[..., Any]] = None
        self.prior_handlers: Optional[list[logging.Handler]] = None


_state = _State()


def init() -> None:
    """Idempotent: open the run file, install the handler, start the writer."""
    with _state.lock:
        if _state.initialized:
            return

        log_dir = resolve_log_dir(os.environ)
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        log_path = log_dir / f"bridge-{stamp}.jsonl"
        file_obj = open(log_path, "a", encoding="utf-8")

        _relink(log_dir / "current.jsonl", log_path)
        if not os.environ.get("RBSS_RUNTIME_DIR"):
            _relink(Path("/tmp/bridge-events.jsonl"), log_path)

        prune_runs(log_dir)

        _write_line(file_obj, _system_record("sys.boot", "bridge log opened", {
            "schema": 1, "pid": os.getpid(),
        }))
        file_obj.flush()

        handler = _QueueRecordHandler()
        prior_handlers = logging.root.handlers[:]
        logging.root.handlers = [handler]
        logging.root.setLevel(logging.INFO)

        if os.environ.get("BRIDGE_DEBUG"):
            logging.root.setLevel(logging.DEBUG)
        for item in os.environ.get("BRIDGE_LOG_LEVELS", "").split(","):
            if "=" not in item:
                continue
            name, level_name = (part.strip() for part in item.split("=", 1))
            level = getattr(logging, level_name.upper(), None)
            if name and isinstance(level, int):
                logging.getLogger(name).setLevel(level)

        prior_excepthook = sys.excepthook
        prior_threading_excepthook = threading.excepthook

        def _excepthook(exc_type: Any, exc_value: Any, exc_tb: Any) -> None:
            emit("sys.crash", "unhandled exception", lvl=logging.ERROR,
                 exc_info=(exc_type, exc_value, exc_tb))
            prior_excepthook(exc_type, exc_value, exc_tb)

        def _threading_excepthook(args: Any) -> None:
            emit("sys.crash", "unhandled thread exception in %s",
                 getattr(args.thread, "name", "?"), lvl=logging.ERROR,
                 exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
            prior_threading_excepthook(args)

        sys.excepthook = _excepthook
        threading.excepthook = _threading_excepthook

        writer_thread = threading.Thread(
            target=_writer_loop, args=(file_obj,),
            name="bridge-log-writer", daemon=True,
        )

        _state.file = file_obj
        _state.writer_thread = writer_thread
        _state.prior_excepthook = prior_excepthook
        _state.prior_threading_excepthook = prior_threading_excepthook
        _state.prior_handlers = prior_handlers
        _state.initialized = True

        writer_thread.start()
        atexit.register(shutdown)


def shutdown(timeout: float = 2.0) -> None:
    """Idempotent: sentinel-stop the writer, drain, write the footer, close the file."""
    with _state.lock:
        if not _state.initialized:
            return
        _state.initialized = False
        file_obj = _state.file
        writer_thread = _state.writer_thread
        prior_excepthook = _state.prior_excepthook
        prior_threading_excepthook = _state.prior_threading_excepthook
        prior_handlers = _state.prior_handlers
        _state.file = None
        _state.writer_thread = None
        _state.prior_handlers = None

    # Uninstall our handler BEFORE the sentinel: no new records can enqueue
    # behind the STOP marker, so the FIFO drain below is complete. Late log
    # calls fall back to stdlib's lastResort stderr handler for WARNING+.
    if prior_handlers is not None:
        logging.root.handlers = prior_handlers

    if prior_excepthook is not None:
        sys.excepthook = prior_excepthook
    if prior_threading_excepthook is not None:
        threading.excepthook = prior_threading_excepthook

    if writer_thread is not None:
        try:
            _RECORD_QUEUE.put(_STOP, timeout=timeout)
        except queue.Full:
            pass
        writer_thread.join(timeout=timeout)

    if file_obj is not None and (writer_thread is None or not writer_thread.is_alive()):
        try:
            _write_line(file_obj, _system_record("sys.shutdown", "bridge log closed", {
                "dropped": _dropped_count,
            }))
            file_obj.flush()
        except Exception:
            pass
        finally:
            try:
                file_obj.close()
            except Exception:
                pass


@contextlib.contextmanager
def thread_guard(name: str) -> Iterator[None]:
    """Wrap a thread run-loop body: sys.thread started/exited/crashed records.

    On an escaping exception, emits an ERROR record with traceback and
    re-raises the original exception unchanged.
    """
    emit("sys.thread", "%s started", name, data={"thread": name})
    try:
        yield
    except Exception:
        emit("sys.thread", "%s crashed", name, lvl=logging.ERROR,
             data={"thread": name}, exc_info=True)
        raise
    else:
        emit("sys.thread", "%s exited", name, data={"thread": name})
