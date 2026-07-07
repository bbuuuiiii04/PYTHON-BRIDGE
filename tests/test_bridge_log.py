from __future__ import annotations

import contextlib
import io
import json
import logging
import os
import queue
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import bridge_log  # noqa: E402
from rb_ss_bridge_v2.models import BridgeEvent  # noqa: E402


class RedactTest(unittest.TestCase):
    def test_masks_secret_key_names(self) -> None:
        data = {
            "token": "abc", "secret": "s3cr3t", "password": "hunter2",
            "api_key": "k123", "foo_key": "not-allowlisted", "safe": "ok",
        }
        redacted = bridge_log._redact(data)
        self.assertEqual(redacted["token"], "<redacted>")
        self.assertEqual(redacted["secret"], "<redacted>")
        self.assertEqual(redacted["password"], "<redacted>")
        self.assertEqual(redacted["api_key"], "<redacted>")
        self.assertEqual(redacted["foo_key"], "<redacted>")
        self.assertEqual(redacted["safe"], "ok")

    def test_allowlisted_structural_key_names_pass_through(self) -> None:
        data = {
            "role_key": "role:drop:1",
            "track_key": "deck1:gen7",
            "armed_key": "manual",
            "section_key": "chorus:2",
            "cache_key": "digest",
            "automation_last_role_key": "ambient:4",
            "nested": {"role_key": "nested-role", "api_key": "secret"},
            "items": [{"section_key": "drop:1"}, {"foo_key": "masked"}],
        }
        redacted = bridge_log._redact(data)
        self.assertEqual(redacted["role_key"], "role:drop:1")
        self.assertEqual(redacted["track_key"], "deck1:gen7")
        self.assertEqual(redacted["armed_key"], "manual")
        self.assertEqual(redacted["section_key"], "chorus:2")
        self.assertEqual(redacted["cache_key"], "digest")
        self.assertEqual(redacted["automation_last_role_key"], "ambient:4")
        self.assertEqual(redacted["nested"]["role_key"], "nested-role")
        self.assertEqual(redacted["nested"]["api_key"], "<redacted>")
        self.assertEqual(redacted["items"][0]["section_key"], "drop:1")
        self.assertEqual(redacted["items"][1]["foo_key"], "<redacted>")

    def test_recurses_into_nested_dicts_and_lists(self) -> None:
        data = {"outer": {"token": "x"}, "items": [{"secret": "y"}, "plain"]}
        redacted = bridge_log._redact(data)
        self.assertEqual(redacted["outer"]["token"], "<redacted>")
        self.assertEqual(redacted["items"][0]["secret"], "<redacted>")
        self.assertEqual(redacted["items"][1], "plain")

    def test_non_dict_values_pass_through(self) -> None:
        self.assertEqual(bridge_log._redact(42), 42)
        self.assertEqual(bridge_log._redact("plain"), "plain")


class BuildRecordTest(unittest.TestCase):
    @staticmethod
    def _record(**extra: object) -> logging.LogRecord:
        rec = logging.LogRecord("test.src", logging.INFO, __file__, 1, "hello %s", ("world",), None)
        for key, value in extra.items():
            setattr(rec, key, value)
        return rec

    def test_minimal_record_key_order_and_omission(self) -> None:
        d = bridge_log.build_record(self._record())
        self.assertEqual(list(d.keys()), ["ts", "mono", "lvl", "cat", "msg", "src"])
        self.assertEqual(d["lvl"], "INFO")
        self.assertEqual(d["cat"], "test.src")
        self.assertEqual(d["msg"], "hello world")
        self.assertEqual(d["src"], "test.src")

    def test_explicit_cat_deck_beat_data_present_in_order(self) -> None:
        rec = self._record(cat="perf.laser", deck=2, beat=64.5, data={"x": 1})
        d = bridge_log.build_record(rec)
        self.assertEqual(list(d.keys()), ["ts", "mono", "lvl", "cat", "msg", "src", "deck", "beat", "data"])
        self.assertEqual(d["cat"], "perf.laser")
        self.assertEqual(d["deck"], 2)
        self.assertEqual(d["beat"], 64.5)
        self.assertEqual(d["data"], {"x": 1})

    def test_explicit_deck_zero_is_kept(self) -> None:
        d = bridge_log.build_record(self._record(deck=0))
        self.assertEqual(d["deck"], 0)

    def test_no_deck_key_when_absent_and_context_zero(self) -> None:
        d = bridge_log.build_record(self._record())
        self.assertNotIn("deck", d)

    def test_deck_falls_back_to_contextvar_when_not_explicit(self) -> None:
        with bridge_log.event_scope("test", deck=3):
            d = bridge_log.build_record(self._record())
        self.assertEqual(d["deck"], 3)

    def test_explicit_deck_wins_over_contextvar(self) -> None:
        with bridge_log.event_scope("test", deck=3):
            d = bridge_log.build_record(self._record(deck=9))
        self.assertEqual(d["deck"], 9)

    def test_trace_comes_from_contextvar_only(self) -> None:
        with bridge_log.event_scope("test", trace_id="abcdef") as trace_id:
            self.assertEqual(trace_id, "abcdef")
            d = bridge_log.build_record(self._record())
        self.assertEqual(d["trace"], "abcdef")

    def test_no_trace_key_when_unset(self) -> None:
        d = bridge_log.build_record(self._record())
        self.assertNotIn("trace", d)

    def test_exc_formatted_via_traceback(self) -> None:
        try:
            raise ValueError("boom")
        except ValueError:
            exc_info = sys.exc_info()
        rec = logging.LogRecord("test.src", logging.ERROR, __file__, 1, "failed", (), exc_info)
        d = bridge_log.build_record(rec)
        self.assertIn("exc", d)
        self.assertIn("ValueError", d["exc"])
        self.assertIn("boom", d["exc"])

    def test_no_exc_key_when_no_exc_info(self) -> None:
        d = bridge_log.build_record(self._record())
        self.assertNotIn("exc", d)


class EventScopeTest(unittest.TestCase):
    def test_restores_deck_and_trace_after_block(self) -> None:
        self.assertEqual(bridge_log._DECK.get(), 0)
        self.assertEqual(bridge_log._TRACE.get(), "")
        with bridge_log.event_scope("kind", deck=5, trace_id="beef42") as trace:
            self.assertEqual(trace, "beef42")
            self.assertEqual(bridge_log._DECK.get(), 5)
            self.assertEqual(bridge_log._TRACE.get(), "beef42")
        self.assertEqual(bridge_log._DECK.get(), 0)
        self.assertEqual(bridge_log._TRACE.get(), "")

    def test_generates_trace_id_when_empty(self) -> None:
        with bridge_log.event_scope("kind") as trace:
            self.assertEqual(len(trace), 6)
            int(trace, 16)  # must be valid hex; raises ValueError otherwise

    def test_nested_scopes_restore_outer_values(self) -> None:
        with bridge_log.event_scope("outer", deck=1, trace_id="outer1"):
            with bridge_log.event_scope("inner", deck=2, trace_id="inner1"):
                self.assertEqual(bridge_log._DECK.get(), 2)
                self.assertEqual(bridge_log._TRACE.get(), "inner1")
            self.assertEqual(bridge_log._DECK.get(), 1)
            self.assertEqual(bridge_log._TRACE.get(), "outer1")
        self.assertEqual(bridge_log._DECK.get(), 0)

    def test_restores_on_exception(self) -> None:
        with self.assertRaises(RuntimeError):
            with bridge_log.event_scope("kind", deck=7, trace_id="deadbe"):
                raise RuntimeError("boom")
        self.assertEqual(bridge_log._DECK.get(), 0)
        self.assertEqual(bridge_log._TRACE.get(), "")


class StampTraceTest(unittest.TestCase):
    def test_creates_payload_dict_when_none(self) -> None:
        ev = BridgeEvent(kind="TEST", deck=1)
        ev.payload = None
        trace_id = bridge_log.stamp_trace(ev)
        self.assertIsInstance(ev.payload, dict)
        self.assertEqual(ev.payload["__trace_id"], trace_id)
        self.assertIn("__enqueue_mono", ev.payload)

    def test_preserves_existing_trace_id_and_other_keys(self) -> None:
        ev = BridgeEvent(kind="TEST", deck=1, payload={"__trace_id": "abc123", "other": "value"})
        trace_id = bridge_log.stamp_trace(ev)
        self.assertEqual(trace_id, "abc123")
        self.assertEqual(ev.payload["__trace_id"], "abc123")
        self.assertEqual(ev.payload["other"], "value")
        self.assertIn("__enqueue_mono", ev.payload)

    def test_generates_new_trace_id_when_absent(self) -> None:
        ev = BridgeEvent(kind="TEST", deck=1, payload={"other": "value"})
        trace_id = bridge_log.stamp_trace(ev)
        self.assertEqual(len(trace_id), 6)
        self.assertEqual(ev.payload["__trace_id"], trace_id)
        self.assertEqual(ev.payload["other"], "value")

    def test_picks_up_ambient_trace_from_context(self) -> None:
        with bridge_log.event_scope("kind", trace_id="ambient1"):
            ev = BridgeEvent(kind="TEST", deck=1)
            trace_id = bridge_log.stamp_trace(ev)
        self.assertEqual(trace_id, "ambient1")


class TraceQueueTest(unittest.TestCase):
    def test_put_nowait_stamps_and_forwards(self) -> None:
        inner: "queue.Queue[BridgeEvent]" = queue.Queue()
        tq = bridge_log.TraceQueue(inner)
        ev = BridgeEvent(kind="TEST", deck=1)
        tq.put_nowait(ev)
        self.assertEqual(inner.qsize(), 1)
        self.assertIn("__trace_id", ev.payload)
        self.assertIn("__enqueue_mono", ev.payload)
        self.assertIs(tq.get_nowait(), ev)

    def test_enqueue_callback_invoked(self) -> None:
        inner: "queue.Queue[BridgeEvent]" = queue.Queue()
        seen: list[BridgeEvent] = []
        tq = bridge_log.TraceQueue(inner, enqueue_callback=seen.append)
        ev = BridgeEvent(kind="TEST", deck=1)
        tq.put_nowait(ev)
        self.assertEqual(seen, [ev])

    def test_enqueue_callback_exception_is_swallowed(self) -> None:
        inner: "queue.Queue[BridgeEvent]" = queue.Queue()

        def _boom(_ev: BridgeEvent) -> None:
            raise RuntimeError("callback exploded")

        tq = bridge_log.TraceQueue(inner, enqueue_callback=_boom)
        tq.put_nowait(BridgeEvent(kind="TEST", deck=1))  # must not raise
        self.assertEqual(inner.qsize(), 1)

    def test_qsize_and_get(self) -> None:
        inner: "queue.Queue[BridgeEvent]" = queue.Queue()
        tq = bridge_log.TraceQueue(inner)
        tq.put_nowait(BridgeEvent(kind="A", deck=1))
        tq.put_nowait(BridgeEvent(kind="B", deck=2))
        self.assertEqual(tq.qsize(), 2)
        self.assertEqual(tq.get().kind, "A")


class EmitHelpersTest(unittest.TestCase):
    @staticmethod
    def _capture(logger_name: str) -> tuple[logging.Logger, logging.Handler, list[logging.LogRecord]]:
        logger = logging.getLogger(logger_name)
        records: list[logging.LogRecord] = []

        class _Capture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record)

        handler = _Capture()
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        return logger, handler, records

    def test_perf_uses_perf_prefixed_logger_and_cat(self) -> None:
        logger, handler, records = self._capture("perf.demo")
        try:
            bridge_log.perf("demo", "scene %s", "on", deck=1, data={"a": 1})
        finally:
            logger.removeHandler(handler)
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec.cat, "perf.demo")
        self.assertEqual(rec.deck, 1)
        self.assertEqual(rec.getMessage(), "scene on")

    def test_health_defaults_to_warning(self) -> None:
        logger, handler, records = self._capture("health.demo")
        try:
            bridge_log.health("demo", "degraded")
        finally:
            logger.removeHandler(handler)
        self.assertEqual(records[0].levelno, logging.WARNING)
        self.assertEqual(records[0].cat, "health.demo")

    def test_health_lvl_override(self) -> None:
        logger, handler, records = self._capture("health.demo2")
        try:
            bridge_log.health("demo2", "cleared", lvl=logging.INFO)
        finally:
            logger.removeHandler(handler)
        self.assertEqual(records[0].levelno, logging.INFO)


class QueueRecordHandlerTest(unittest.TestCase):
    @staticmethod
    def _record() -> logging.LogRecord:
        return logging.LogRecord("t", logging.INFO, __file__, 1, "msg", (), None)

    def test_drop_on_full_increments_counter_and_never_raises(self) -> None:
        q: "queue.Queue[dict]" = queue.Queue(maxsize=2)
        handler = bridge_log._QueueRecordHandler(q)
        before = bridge_log._dropped_count
        handler.emit(self._record())
        handler.emit(self._record())
        self.assertEqual(q.qsize(), 2)
        handler.emit(self._record())  # queue full; must not raise
        self.assertEqual(q.qsize(), 2)
        self.assertEqual(bridge_log._dropped_count, before + 1)

    def test_emit_puts_build_record_shaped_dict(self) -> None:
        q: "queue.Queue[dict]" = queue.Queue(maxsize=4)
        handler = bridge_log._QueueRecordHandler(q)
        handler.emit(self._record())
        d = q.get_nowait()
        self.assertEqual(d["msg"], "msg")
        self.assertEqual(d["src"], "t")


class ResolveLogDirTest(unittest.TestCase):
    def test_uses_runtime_dir_when_set(self) -> None:
        d = bridge_log.resolve_log_dir({"RBSS_RUNTIME_DIR": "/tmp/example_runtime"})
        self.assertEqual(d, Path("/tmp/example_runtime") / "logs")

    def test_falls_back_to_library_logs_when_unset(self) -> None:
        d = bridge_log.resolve_log_dir({})
        self.assertEqual(d, Path.home() / "Library" / "Logs" / "rb_ss_bridge")


class PruneRunsTest(unittest.TestCase):
    def test_deletes_oldest_beyond_keep(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            names = [f"bridge-2026070{i}-000000.jsonl" for i in range(1, 6)]
            for name in names:
                (d / name).write_text("{}\n", encoding="utf-8")
            bridge_log.prune_runs(d, keep=3)
            remaining = sorted(p.name for p in d.glob("bridge-*.jsonl"))
            self.assertEqual(remaining, names[-3:])

    def test_noop_when_within_keep(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "bridge-20260701-000000.jsonl").write_text("{}\n", encoding="utf-8")
            bridge_log.prune_runs(d, keep=20)
            self.assertEqual(len(list(d.glob("bridge-*.jsonl"))), 1)

    def test_missing_dir_does_not_raise(self) -> None:
        bridge_log.prune_runs(Path("/nonexistent/definitely/not/here"), keep=5)


class InitShutdownTest(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_handlers = list(logging.root.handlers)
        self._orig_level = logging.root.level
        self._tmp = tempfile.TemporaryDirectory()
        self._env_patch = mock.patch.dict(os.environ, {"RBSS_RUNTIME_DIR": self._tmp.name})
        self._env_patch.start()

    def tearDown(self) -> None:
        bridge_log.shutdown()
        self._env_patch.stop()
        self._tmp.cleanup()
        logging.root.handlers = self._orig_handlers
        logging.root.setLevel(self._orig_level)

    def test_init_shutdown_produce_header_and_footer(self) -> None:
        bridge_log.init()
        log_dir = Path(self._tmp.name) / "logs"
        current = log_dir / "current.jsonl"
        self.assertTrue(current.is_symlink())

        bridge_log.shutdown()

        lines = current.resolve().read_text(encoding="utf-8").splitlines()
        records = [json.loads(line) for line in lines if line.strip()]
        self.assertEqual(records[0]["cat"], "sys.boot")
        self.assertEqual(records[0]["data"]["schema"], 1)
        self.assertEqual(records[-1]["cat"], "sys.shutdown")
        self.assertIn("dropped", records[-1]["data"])
        for key in ("ts", "mono", "lvl", "cat", "msg", "src"):
            self.assertIn(key, records[0])
            self.assertIn(key, records[-1])

    def test_tmp_symlink_skipped_when_runtime_dir_set(self) -> None:
        with mock.patch.object(bridge_log, "_relink") as relink_mock:
            bridge_log.init()
        called_paths = [call.args[0] for call in relink_mock.call_args_list]
        self.assertNotIn(Path("/tmp/bridge-events.jsonl"), called_paths)

    def test_double_init_is_idempotent(self) -> None:
        bridge_log.init()
        log_dir = Path(self._tmp.name) / "logs"
        first_target = (log_dir / "current.jsonl").resolve()

        bridge_log.init()  # second call: must be a no-op

        second_target = (log_dir / "current.jsonl").resolve()
        self.assertEqual(first_target, second_target)
        self.assertEqual(len(list(log_dir.glob("bridge-*.jsonl"))), 1)

    def test_double_shutdown_is_idempotent(self) -> None:
        bridge_log.init()
        bridge_log.shutdown()
        bridge_log.shutdown()  # must not raise or double-write the footer

    def test_warning_emit_mirrors_to_stderr(self) -> None:
        bridge_log.init()
        captured = io.StringIO()
        with contextlib.redirect_stderr(captured):
            bridge_log.health("test", "something broke")
            bridge_log.shutdown()
        self.assertIn("something broke", captured.getvalue())

    def test_info_emit_does_not_mirror_to_stderr(self) -> None:
        bridge_log.init()
        captured = io.StringIO()
        with contextlib.redirect_stderr(captured):
            bridge_log.perf("demo", "just fyi")
            bridge_log.shutdown()
        self.assertEqual(captured.getvalue(), "")


class ExcepthookChainingTest(unittest.TestCase):
    """init() chain-installs sys.excepthook/threading.excepthook (Task W1)."""

    def setUp(self) -> None:
        self._orig_handlers = list(logging.root.handlers)
        self._orig_level = logging.root.level
        self._orig_excepthook = sys.excepthook
        self._orig_threading_excepthook = threading.excepthook
        self._tmp = tempfile.TemporaryDirectory()
        self._env_patch = mock.patch.dict(os.environ, {"RBSS_RUNTIME_DIR": self._tmp.name})
        self._env_patch.start()

    def tearDown(self) -> None:
        bridge_log.shutdown()
        self._env_patch.stop()
        self._tmp.cleanup()
        logging.root.handlers = self._orig_handlers
        logging.root.setLevel(self._orig_level)
        sys.excepthook = self._orig_excepthook
        threading.excepthook = self._orig_threading_excepthook

    def _crash_records(self) -> list[dict]:
        current = (Path(self._tmp.name) / "logs" / "current.jsonl").resolve()
        records = [json.loads(line) for line in current.read_text(encoding="utf-8").splitlines() if line.strip()]
        return [r for r in records if r["cat"] == "sys.crash"]

    def test_sys_excepthook_emits_crash_record_and_calls_prior(self) -> None:
        prior_calls = []
        sys.excepthook = lambda *a: prior_calls.append(a)
        bridge_log.init()
        installed_hook = sys.excepthook
        self.assertIsNot(installed_hook, self._orig_excepthook)

        try:
            raise ValueError("crash-test")
        except ValueError:
            exc_info = sys.exc_info()
        installed_hook(*exc_info)
        self.assertEqual(len(prior_calls), 1)

        bridge_log.shutdown()
        crash_records = self._crash_records()
        self.assertEqual(len(crash_records), 1)
        self.assertIn("ValueError", crash_records[0]["exc"])
        self.assertIn("crash-test", crash_records[0]["exc"])

    def test_threading_excepthook_emits_crash_record_and_calls_prior(self) -> None:
        prior_calls = []
        threading.excepthook = lambda args: prior_calls.append(args)
        bridge_log.init()
        installed_hook = threading.excepthook

        try:
            raise RuntimeError("thread-crash-test")
        except RuntimeError:
            exc_type, exc_value, exc_tb = sys.exc_info()

        args = threading.ExceptHookArgs([exc_type, exc_value, exc_tb, threading.current_thread()])
        installed_hook(args)
        self.assertEqual(len(prior_calls), 1)

        bridge_log.shutdown()
        crash_records = self._crash_records()
        self.assertEqual(len(crash_records), 1)
        self.assertIn("RuntimeError", crash_records[0]["exc"])
        self.assertIn("thread-crash-test", crash_records[0]["exc"])


class ThreadGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.logger = logging.getLogger("sys.thread")
        self.records: list[logging.LogRecord] = []
        outer = self

        class _Capture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                outer.records.append(record)

        self.handler = _Capture()
        self.logger.addHandler(self.handler)
        self.logger.setLevel(logging.DEBUG)

    def tearDown(self) -> None:
        self.logger.removeHandler(self.handler)

    def test_started_and_exited_on_clean_run(self) -> None:
        with bridge_log.thread_guard("worker"):
            pass
        msgs = [r.getMessage() for r in self.records]
        self.assertEqual(msgs, ["worker started", "worker exited"])

    def test_crash_emits_error_and_reraises(self) -> None:
        with self.assertRaises(RuntimeError):
            with bridge_log.thread_guard("worker"):
                raise RuntimeError("kaboom")
        msgs = [r.getMessage() for r in self.records]
        self.assertEqual(msgs, ["worker started", "worker crashed"])
        self.assertEqual(self.records[-1].levelno, logging.ERROR)
        # exc_info=True must be normalized to a real (type, value, tb) tuple
        # (mirrors Logger._log()) so build_record's traceback formatting
        # actually works, not just "is not None".
        crash_record = self.records[-1]
        self.assertIsInstance(crash_record.exc_info, tuple)
        d = bridge_log.build_record(crash_record)
        self.assertIn("exc", d)
        self.assertIn("RuntimeError", d["exc"])
        self.assertIn("kaboom", d["exc"])


if __name__ == "__main__":
    unittest.main()
