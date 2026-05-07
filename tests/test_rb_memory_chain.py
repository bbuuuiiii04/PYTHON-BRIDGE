"""Unit tests for RBMemoryReader live_pos_per_deck chain snapshots."""
from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import rb_memory as mod
from rb_ss_bridge_v2.models import PositionSnapshot
from rb_ss_bridge_v2.rb_offsets import ChainEntry, RBOffsetVersion


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


if __name__ == "__main__":
    unittest.main()
