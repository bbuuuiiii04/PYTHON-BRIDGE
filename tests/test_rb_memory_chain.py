"""Unit tests for RBMemoryReader live_pos_per_deck chain snapshots."""
from __future__ import annotations

import logging
import struct
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import rb_memory as mod
from rb_ss_bridge_v2.models import PositionSnapshot
from rb_ss_bridge_v2.rb_offsets import ChainEntry, RBOffsetVersion


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


class FakeMem:
    def __init__(self) -> None:
        self.hop_chain: dict[int, int] = {}
        self.leaf: dict[int, bytes] = {}

    def install_chain(self, base: int, ch: ChainEntry, payload: bytes) -> int:
        addr = base
        for i, hop in enumerate(ch.hops):
            nxt = 0xCAFE_0000_0000 + (i + 1) * 0x10000 + hop
            self.hop_chain[addr + hop] = nxt
            addr = nxt
        endpoint = addr + ch.final_off
        self.leaf[endpoint] = payload
        return endpoint

    def read_bytes(self, task: int, addr: int, size: int) -> bytes:
        if size == 8 and addr in self.hop_chain:
            return self.hop_chain[addr].to_bytes(8, "little")
        if addr in self.leaf:
            data = self.leaf[addr]
            return data[:size] + b"\x00" * max(0, size - len(data))
        raise OSError(f"FakeMem: no mapping at 0x{addr:x}")


def chain(*nums: int) -> ChainEntry:
    return ChainEntry(hops=nums[:-1], final_off=nums[-1])


def offsets() -> RBOffsetVersion:
    zero = chain(0)
    live_pos = (
        chain(0x1000, 0x10),
        chain(0x2000, 0x10),
        chain(0x3000, 0x10),
        chain(0x4000, 0x10),
    )
    return RBOffsetVersion(
        version="test",
        deck_count=4,
        master_deck=zero,
        bpm_per_deck=(zero, zero, zero, zero),
        live_pos_per_deck=live_pos,
        track_info_per_deck=(zero, zero, zero, zero),
        anlz_path_per_deck=(zero, zero, zero, zero),
    )


class LivePosChainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mem = FakeMem()
        self.base = 0x100000000
        self.offs = offsets()
        self.session = mod.RBSession(123, self.base, 0xCAFE, offsets=self.offs)
        self._patch = mock.patch.object(mod, "_read_bytes", side_effect=self.mem.read_bytes)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def test_chain_position_feeds_snapshot_and_preserves_length(self) -> None:
        endpoint = self.mem.install_chain(
            self.base,
            self.offs.live_pos_per_deck[1],
            struct.pack("<q", 44_100),
        )
        previous = PositionSnapshot(deck=2, elapsed_ms=900, playing=False, track_length_ms=180_000)

        snap = self.session.read_live_pos_chain(2, previous)
        self.assertIsNotNone(snap)
        assert snap is not None
        self.assertEqual(snap.deck, 2)
        self.assertEqual(snap.elapsed_ms, 1000)
        self.assertEqual(snap.track_length_ms, 180_000)
        self.assertFalse(snap.playing)

        self.mem.leaf[endpoint] = struct.pack("<q", 88_200)
        snap = self.session.read_live_pos_chain(2, snap)
        self.assertIsNotNone(snap)
        assert snap is not None
        self.assertEqual(snap.elapsed_ms, 2000)
        self.assertTrue(snap.playing)

    def test_chain_rejects_negative_and_large_backward_jump(self) -> None:
        endpoint = self.mem.install_chain(
            self.base,
            self.offs.live_pos_per_deck[0],
            struct.pack("<q", 100_000),
        )
        self.assertIsNotNone(self.session.read_live_pos_chain(1, None))

        self.mem.leaf[endpoint] = struct.pack("<q", -1)
        self.assertIsNone(self.session.read_live_pos_chain(1, None))

        self.mem.leaf[endpoint] = struct.pack("<q", 50_000)
        self.assertIsNone(self.session.read_live_pos_chain(1, None))

    def test_chain_allows_track_reset_to_near_zero(self) -> None:
        endpoint = self.mem.install_chain(
            self.base,
            self.offs.live_pos_per_deck[0],
            struct.pack("<q", 100_000),
        )
        self.assertIsNotNone(self.session.read_live_pos_chain(1, None))

        self.mem.leaf[endpoint] = struct.pack("<q", 1_000)
        snap = self.session.read_live_pos_chain(1, None)
        self.assertIsNotNone(snap)
        assert snap is not None
        self.assertEqual(snap.elapsed_ms, int(1_000 * mod.RB_SCALE))

    def test_out_of_range_read_does_not_poison_next_valid_read(self) -> None:
        endpoint = self.mem.install_chain(
            self.base,
            self.offs.live_pos_per_deck[0],
            struct.pack("<q", 100_000),
        )
        first = self.session.read_live_pos_chain(1, None)
        self.assertIsNotNone(first)

        self.mem.leaf[endpoint] = struct.pack("<q", int((mod.MEM_MAX_ELAPSED_MS + 1000) / mod.RB_SCALE))
        self.assertIsNone(self.session.read_live_pos_chain(1, first))

        self.mem.leaf[endpoint] = struct.pack("<q", 150_000)
        snap = self.session.read_live_pos_chain(1, first)
        self.assertIsNotNone(snap)
        assert snap is not None
        self.assertEqual(snap.elapsed_ms, int(150_000 * mod.RB_SCALE))


class ChainFreshnessTests(unittest.TestCase):
    """AWR-157 T6: freshness-aware deck-2 chain health (rb_memory.py T3/T4)."""

    def setUp(self) -> None:
        self.mem = FakeMem()
        self.base = 0x100000000
        self.offs = offsets()
        self.session = mod.RBSession(123, self.base, 0xCAFE, offsets=self.offs)
        self._patch = mock.patch.object(mod, "_read_bytes", side_effect=self.mem.read_bytes)
        self._patch.start()
        self.addCleanup(self._patch.stop)
        self.reader = mod.RBMemoryReader(mod.PositionCache())

    def test_frozen_raw_while_playing_hint_goes_stale_after_five_identical_reads(self) -> None:
        endpoint = self.mem.install_chain(
            self.base, self.offs.live_pos_per_deck[1], struct.pack("<q", 100_000)
        )
        del endpoint
        # First read establishes the baseline raw (nothing to compare against
        # yet, so it can't itself be "unchanged"); each read after that with
        # the same raw is one identical-read tick.
        snap = self.session.read_live_pos_chain(2, None)
        self.assertTrue(self.session.chain_raw_fresh(2))
        for _ in range(4):
            snap = self.session.read_live_pos_chain(2, snap)
            self.assertTrue(self.session.chain_raw_fresh(2))
        # 5th consecutive identical-raw read crosses _CHAIN_FRESH_TICKS.
        self.session.read_live_pos_chain(2, snap)
        self.assertFalse(self.session.chain_raw_fresh(2))

    def test_advancing_raw_stays_fresh(self) -> None:
        endpoint = self.mem.install_chain(
            self.base, self.offs.live_pos_per_deck[1], struct.pack("<q", 100_000)
        )
        snap = None
        for i in range(8):
            self.mem.leaf[endpoint] = struct.pack("<q", 100_000 + i * 50)
            snap = self.session.read_live_pos_chain(2, snap)
            self.assertTrue(self.session.chain_raw_fresh(2))

    def test_frozen_raw_while_paused_hint_stays_healthy(self) -> None:
        """The FEIN case: a real pause reads frozen legitimately, never stale."""
        self.mem.install_chain(
            self.base, self.offs.live_pos_per_deck[1], struct.pack("<q", 100_000)
        )
        for _ in range(8):
            self.reader._read_decks_chain_first(
                self.session, now_t=100.0, deck2_playing_hint=False
            )
            self.assertTrue(self.reader._chain_ok_last[2])

    def test_fallback_engages_when_stale_while_playing(self) -> None:
        self.mem.install_chain(
            self.base, self.offs.live_pos_per_deck[1], struct.pack("<q", 100_000)
        )
        deck_reads: list[int] = []
        self.session.read_deck = lambda deck: deck_reads.append(deck) or None  # type: ignore[method-assign]

        for _ in range(6):
            self.reader._read_decks_chain_first(
                self.session, now_t=100.0, deck2_playing_hint=True
            )

        self.assertFalse(self.reader._chain_ok_last[2])
        self.assertIn(2, deck_reads)

    def test_deck1_path_untouched_by_freshness_gate(self) -> None:
        self.mem.install_chain(
            self.base, self.offs.live_pos_per_deck[0], struct.pack("<q", 100_000)
        )
        deck_reads: list[int] = []
        self.session.read_deck = lambda deck: deck_reads.append(deck) or None  # type: ignore[method-assign]

        for _ in range(8):
            self.reader._read_decks_chain_first(
                self.session, now_t=100.0, deck2_playing_hint=True
            )

        self.assertTrue(self.reader._chain_ok_last[1])
        # deck 1 hits read_deck() exactly once, from the pre-existing slow-cadence
        # length refresh (now_t fixed, so it only fires on the first tick) -- never
        # from the freshness-staleness fallback, which is deck-2-only.
        self.assertEqual(deck_reads.count(1), 1)

    def test_stale_fallback_log_is_edge_triggered_not_per_tick_spam(self) -> None:
        endpoint = self.mem.install_chain(
            self.base, self.offs.live_pos_per_deck[1], struct.pack("<q", 100_000)
        )
        logger, handler, prior_level, records = _capture("rb_memory")
        self.addCleanup(logger.setLevel, prior_level)
        self.addCleanup(logger.removeHandler, handler)

        # Frozen for 8 ticks while "playing" -> goes stale once, not per tick.
        for _ in range(8):
            self.reader._read_decks_chain_first(
                self.session, now_t=100.0, deck2_playing_hint=True
            )
        # Raw starts advancing again -> recovers once.
        for i in range(3):
            self.mem.leaf[endpoint] = struct.pack("<q", 100_000 + (i + 1) * 50)
            self.reader._read_decks_chain_first(
                self.session, now_t=100.0, deck2_playing_hint=True
            )

        stale_logs = [r for r in records if "chain-stale" in r.getMessage()]
        engaged = [r for r in stale_logs if "fallback-engaged" in r.getMessage()]
        idle = [r for r in stale_logs if "fallback-idle" in r.getMessage()]
        self.assertEqual(len(engaged), 1)
        self.assertEqual(len(idle), 1)

    def test_pause_vs_freeze_debug_log_is_edge_triggered(self) -> None:
        self.mem.install_chain(
            self.base, self.offs.live_pos_per_deck[1], struct.pack("<q", 100_000)
        )
        logger, handler, prior_level, records = _capture("rb_memory")
        self.addCleanup(logger.setLevel, prior_level)
        self.addCleanup(logger.removeHandler, handler)

        # Playing, then flips to not-playing within the recent-play-start window,
        # then stays not-playing (frozen raw) for several more reads.
        snap = self.session.read_live_pos_chain(
            2, None, playing_hint=True, recent_play_start=True
        )
        snap = PositionSnapshot(
            deck=2, elapsed_ms=snap.elapsed_ms, playing=True, track_length_ms=0
        )
        for _ in range(4):
            snap = self.session.read_live_pos_chain(
                2, snap, playing_hint=False, recent_play_start=True
            )

        pause_logs = [r for r in records if "pause-vs-freeze" in r.getMessage()]
        self.assertEqual(len(pause_logs), 1)
        self.assertEqual(pause_logs[0].levelno, logging.DEBUG)


if __name__ == "__main__":
    unittest.main()
