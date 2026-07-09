"""Unit tests for the skip-ObjC chain-first reader path (RBSS_POS_CHAIN_SKIP_OBJC).

Covers RBMemoryReader._read_decks_chain_first / _refresh_deck1_length: when the
live_pos chain is healthy the redundant ObjC read_deck() is skipped, deck-1
track_length_ms is refreshed on a slow cadence, and read_deck() still runs as a
per-tick fallback when the chain misses.
"""
from __future__ import annotations

import logging
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import bridge_fmt
from rb_ss_bridge_v2 import rb_memory as mod
from rb_ss_bridge_v2.models import PositionSnapshot


def _capture(logger_name: str):
    logger = logging.getLogger(logger_name)
    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Capture()
    logger.addHandler(handler)
    prior_level = logger.level
    logger.setLevel(logging.DEBUG)
    return logger, handler, prior_level, records


def snap(deck: int, elapsed_ms: int, *, playing=False, length=0, updated_at=1.0):
    return PositionSnapshot(
        deck=deck,
        elapsed_ms=elapsed_ms,
        playing=playing,
        track_length_ms=length,
        updated_at=updated_at,
    )


class FakeSession:
    """Stands in for RBSession; records read_deck / chain calls."""

    def __init__(self):
        self.chain_returns: dict[int, object] = {}
        self.deck_returns: dict[int, object] = {}
        self.read_deck_calls: list[int] = []
        self.chain_calls: list[int] = []

    def read_live_pos_chain(self, deck, previous, *, playing_hint=None, recent_play_start=False):
        self.chain_calls.append(deck)
        r = self.chain_returns.get(deck)
        return r(previous) if callable(r) else r

    def read_deck(self, deck):
        self.read_deck_calls.append(deck)
        r = self.deck_returns.get(deck)
        return r() if callable(r) else r

    def chain_raw_fresh(self, deck):
        return True


def make_reader() -> mod.RBMemoryReader:
    return mod.RBMemoryReader(mod.PositionCache())


class SkipObjcFlagTests(unittest.TestCase):
    def test_flag_defaults_off(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(mod.POS_CHAIN_SKIP_OBJC_ENV, None)
            self.assertFalse(make_reader()._skip_objc_when_chain)

    def test_flag_inert_without_chain_mode(self):
        # Flag on but chain mode off / no offsets → optimization stays disabled.
        with mock.patch.dict(os.environ, {mod.POS_CHAIN_SKIP_OBJC_ENV: "1"}):
            os.environ.pop(mod.POS_CHAIN_DIRECT_ENV, None)
            self.assertFalse(make_reader()._skip_objc_when_chain)


class ChainFirstReadTests(unittest.TestCase):
    def setUp(self):
        self.reader = make_reader()

    def test_chain_valid_skips_redundant_read_deck(self):
        s = FakeSession()
        s.chain_returns = {1: snap(1, 1000, playing=True), 2: snap(2, 2000, playing=True)}
        s.deck_returns = {1: snap(1, 999, length=180_000)}  # length seeder

        # Second tick (length already fresh) is what proves the redundant read
        # is gone; do an initial tick to consume the first-time length refresh.
        self.reader._read_decks_chain_first(s, now_t=100.0)
        s.read_deck_calls.clear()
        self.reader._read_decks_chain_first(s, now_t=100.4)  # < 1.0s later

        self.assertEqual(s.read_deck_calls, [])  # no ObjC reads at all this tick
        self.assertEqual(self.reader._cache.get(1).elapsed_ms, 1000)
        self.assertEqual(self.reader._cache.get(2).elapsed_ms, 2000)
        self.assertEqual(self.reader._chain_ok_last, {1: True, 2: True})

    def test_length_refresh_cadence(self):
        s = FakeSession()
        s.chain_returns = {1: snap(1, 1000), 2: snap(2, 2000)}
        s.deck_returns = {1: snap(1, 0, length=180_000)}

        self.reader._read_decks_chain_first(s, now_t=100.0)   # due (init 0.0)
        self.reader._read_decks_chain_first(s, now_t=100.5)   # within interval
        self.reader._read_decks_chain_first(s, now_t=101.2)   # >= 1.0s → due again

        self.assertEqual(s.read_deck_calls, [1, 1])
        self.assertEqual(self.reader._cache.get(1).track_length_ms, 180_000)

    def test_chain_miss_falls_back_to_read_deck(self):
        s = FakeSession()
        s.chain_returns = {1: snap(1, 1000), 2: None}  # deck-2 chain misses
        s.deck_returns = {1: snap(1, 0, length=180_000), 2: snap(2, 2222, playing=True)}

        self.reader._read_decks_chain_first(s, now_t=100.0)

        self.assertIn(2, s.read_deck_calls)                       # fallback fired
        self.assertEqual(self.reader._cache.get(2).elapsed_ms, 2222)
        self.assertFalse(self.reader._chain_ok_last[2])
        self.assertTrue(self.reader._chain_ok_last[1])

    def test_refresh_preserves_chain_position(self):
        # A chain snapshot is live in the cache; length refresh must change ONLY
        # track_length_ms, never elapsed/playing/updated_at.
        self.reader._cache.update(snap(1, 5000, playing=True, length=0, updated_at=42.0))
        s = FakeSession()
        s.deck_returns = {1: snap(1, 99, playing=False, length=200_000)}

        self.reader._refresh_deck1_length(s, now_t=100.0)

        cur = self.reader._cache.get(1)
        self.assertEqual(cur.elapsed_ms, 5000)
        self.assertTrue(cur.playing)
        self.assertEqual(cur.updated_at, 42.0)
        self.assertEqual(cur.track_length_ms, 200_000)

    def test_refresh_noop_when_length_unavailable(self):
        self.reader._cache.update(snap(1, 5000, playing=True, length=123, updated_at=42.0))
        s = FakeSession()
        s.deck_returns = {1: None}  # read_deck failed

        self.reader._refresh_deck1_length(s, now_t=100.0)

        cur = self.reader._cache.get(1)
        self.assertEqual(cur.track_length_ms, 123)   # unchanged
        self.assertEqual(cur.elapsed_ms, 5000)


class HealthTransitionTests(unittest.TestCase):
    """AWR-125 W4: health.rb / health.reader edge-triggered emits + bounded warning."""

    def setUp(self) -> None:
        bridge_fmt.reset_rate_state()
        self.reader = make_reader()

    def test_log_drift_emits_once_per_failure_streak(self) -> None:
        logger, handler, prior_level, records = _capture("health.reader")
        self.addCleanup(logger.setLevel, prior_level)
        self.addCleanup(logger.removeHandler, handler)

        self.reader._log_drift(1, "deck 1: backward jump 1000->500 ms (-500 ms)")
        self.reader._log_drift(1, "deck 1: backward jump 1000->500 ms (-500 ms)")  # repeat: silent

        self.assertEqual(len(records), 1, f"expected exactly one drift record, got {records!r}")
        self.assertEqual(records[0].levelname, "WARNING")
        self.assertEqual(records[0].deck, 1)
        self.assertIn("backward jump", records[0].getMessage())

    def test_log_drift_clear_then_new_streak_relogs(self) -> None:
        logger, handler, prior_level, records = _capture("health.reader")
        self.addCleanup(logger.setLevel, prior_level)
        self.addCleanup(logger.removeHandler, handler)

        self.reader._log_drift(1, "deck 1: backward jump")
        self.reader._log_drift(1, None)  # DriftDetector reports healthy again
        self.reader._log_drift(1, "deck 1: backward jump (2nd incident)")

        self.assertEqual(len(records), 2, f"expected two distinct incidents, got {records!r}")
        self.assertEqual(records[0].levelname, "WARNING")
        self.assertEqual(records[1].levelname, "WARNING")

    def test_log_drift_is_per_deck(self) -> None:
        logger, handler, prior_level, records = _capture("health.reader")
        self.addCleanup(logger.setLevel, prior_level)
        self.addCleanup(logger.removeHandler, handler)

        self.reader._log_drift(1, "deck 1 drift")
        self.reader._log_drift(2, "deck 2 drift")

        self.assertEqual(len(records), 2)
        self.assertEqual({r.deck for r in records}, {1, 2})

    def test_rb_gone_emits_health_rb(self) -> None:
        self.reader._session = SimpleNamespace(pid=999999)
        logger, handler, prior_level, records = _capture("health.rb")
        self.addCleanup(logger.setLevel, prior_level)
        self.addCleanup(logger.removeHandler, handler)

        with mock.patch("os.kill", side_effect=ProcessLookupError()):
            self.reader._tick()

        self.assertIsNone(self.reader._session)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].levelname, "WARNING")
        self.assertIn("gone; detaching", records[0].getMessage())

    def test_rb_restart_enqueue_failure_gets_bounded_warning(self) -> None:
        class _BoomQueue:
            def put_nowait(self, _item) -> None:
                raise RuntimeError("synthetic enqueue failure")

        self.reader._session = SimpleNamespace(pid=999999)
        self.reader._eq = _BoomQueue()

        with mock.patch("os.kill", side_effect=ProcessLookupError()):
            with self.assertLogs("rb_memory", level="WARNING") as captured:
                self.reader._tick()

        self.assertTrue(
            any("rb-restart enqueue failed" in line for line in captured.output),
            captured.output,
        )


if __name__ == "__main__":
    unittest.main()
