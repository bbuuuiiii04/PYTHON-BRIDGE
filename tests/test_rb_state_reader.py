"""Unit tests for RBStateReader using a fake mach-read backend."""
from __future__ import annotations

import os
import queue
import struct
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import rb_state_reader as mod
from rb_ss_bridge_v2.models import Ev
from rb_ss_bridge_v2.rb_offsets import ChainEntry, RBOffsetVersion


class FakeMem:
    """Trivial in-memory model used to simulate ``mach_vm_read_overwrite``."""

    def __init__(self) -> None:
        self.hop_chain: dict[int, int] = {}
        self.leaf: dict[int, bytes] = {}

    def install_chain(self, base: int, ch: ChainEntry, payload: bytes) -> int:
        addr = base
        for i, hop in enumerate(ch.hops):
            nxt = 0xC0FFEE_0000_0000 + (i + 1) * 0x10000 + (hash((base, i, ch)) & 0xFFFF)
            self.hop_chain[addr + hop] = nxt
            addr = nxt
        endpoint = addr + ch.final_off
        self.leaf[endpoint] = payload
        return endpoint

    def update_leaf(self, endpoint: int, payload: bytes) -> None:
        self.leaf[endpoint] = payload

    def read_bytes(self, task: int, addr: int, size: int) -> bytes:
        if size == 8 and addr in self.hop_chain:
            return self.hop_chain[addr].to_bytes(8, "little")
        if addr in self.leaf:
            data = self.leaf[addr]
            if len(data) < size:
                return data + b"\x00" * (size - len(data))
            return data[:size]
        raise OSError(f"FakeMem: no mapping at 0x{addr:x} size={size}")


def _make_offsets() -> RBOffsetVersion:
    def chain(*nums: int) -> ChainEntry:
        return ChainEntry(hops=nums[:-1], final_off=nums[-1])

    return RBOffsetVersion(
        version="test",
        deck_count=4,
        master_deck=chain(0x1000, 0x10, 0x20, 0x4),
        bpm_per_deck=tuple(chain(0x2000, 0x10 * d, 0x30, 0x100) for d in range(4)),
        live_pos_per_deck=tuple(chain(0x2000, 0x10 * d, 0x30, 0x108) for d in range(4)),
        track_info_per_deck=tuple(chain(0x3000, 0x10 * d, 0x40, 0x0) for d in range(4)),
        anlz_path_per_deck=tuple(chain(0x4000, 0x10 * d, 0x200) for d in range(4)),
    )


def _drain(q: "queue.Queue") -> list:
    out = []
    try:
        while True:
            out.append(q.get_nowait())
    except queue.Empty:
        return out


class TickEventTests(unittest.TestCase):
    """Single-tick event emission verified against a stubbed mach backend."""

    def setUp(self) -> None:
        self.mem = FakeMem()
        self.offs = _make_offsets()
        self.base = 0x100000000
        self.q: queue.Queue = queue.Queue()

        # Patch the module-level mach helpers used by RBStateReader.
        self._patches = [
            mock.patch.object(mod, "_read_bytes", side_effect=self.mem.read_bytes),
            mock.patch.object(mod, "_task_for_pid", return_value=0xCAFE),
            mock.patch.object(mod, "get_rb_pid", return_value=12345),
            mock.patch.object(mod, "_get_vmmap_output", return_value=""),
            mock.patch.object(mod, "_base_from_vmmap", return_value=self.base),
        ]
        for p in self._patches:
            p.start()
        self.addCleanup(self._stop_patches)

        # Install null defaults so each per-deck branch is reachable but inert.
        for d in range(4):
            self.mem.install_chain(self.base, self.offs.bpm_per_deck[d],
                                   payload=struct.pack("<f", 0.0))
            self.mem.install_chain(self.base, self.offs.live_pos_per_deck[d],
                                   payload=(0).to_bytes(8, "little"))
            self.mem.install_chain(self.base, self.offs.track_info_per_deck[d],
                                   payload=b"")

        self.reader = mod.RBStateReader(self.q, self.offs, rb_pid=12345, base_addr=self.base)

    def _stop_patches(self) -> None:
        for p in self._patches:
            p.stop()

    # ── master deck ─────────────────────────────────────────────────────────
    def test_master_byte_2_emits_master_changed_for_deck_C(self) -> None:
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\x02")
        self.reader._tick(0xCAFE, self.base)
        masters = [e for e in _drain(self.q) if e.kind == Ev.MASTER_CHANGED]
        self.assertEqual(len(masters), 1)
        # RB deck idx 2 (C) → bridge deck (2 % 2) + 1 = 1
        self.assertEqual(masters[0].deck, 1)
        self.assertEqual(masters[0].source, "rb_state")

    def test_master_byte_0xff_no_master_event(self) -> None:
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")
        self.reader._tick(0xCAFE, self.base)
        self.assertEqual(
            [e for e in _drain(self.q) if e.kind == Ev.MASTER_CHANGED],
            [],
        )

    def test_master_unchanged_does_not_re_emit(self) -> None:
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\x01")
        self.reader._tick(0xCAFE, self.base)
        self.reader._tick(0xCAFE, self.base)
        masters = [e for e in _drain(self.q) if e.kind == Ev.MASTER_CHANGED]
        self.assertEqual(len(masters), 1)

    # ── track loaded ────────────────────────────────────────────────────────
    def test_track_loaded_emits_with_title(self) -> None:
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")
        title = "Some Track - Some Artist"
        # Replace deck 1 (B → bridge 2) leaf with a real title.
        endpoint = self.mem.install_chain(
            self.base, self.offs.track_info_per_deck[1], payload=title.encode("utf-8") + b"\x00")
        self.reader._tick(0xCAFE, self.base)
        loaded = [e for e in _drain(self.q) if e.kind == Ev.TRACK_LOADED]
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].deck, 2)
        self.assertEqual(loaded[0].payload["title"], title)
        self.assertEqual(loaded[0].source, "rb_state")
        self.assertGreater(endpoint, 0)

    def test_track_unchanged_does_not_re_emit(self) -> None:
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")
        self.mem.install_chain(
            self.base, self.offs.track_info_per_deck[0],
            payload=b"Steady\x00")
        self.reader._tick(0xCAFE, self.base)
        self.reader._tick(0xCAFE, self.base)
        loaded = [e for e in _drain(self.q) if e.kind == Ev.TRACK_LOADED]
        self.assertEqual(len(loaded), 1)

    # ── BPM ──────────────────────────────────────────────────────────────────
    def test_bpm_above_threshold_emits(self) -> None:
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")
        endpoint = self.mem.install_chain(
            self.base, self.offs.bpm_per_deck[0], payload=struct.pack("<f", 128.0))
        self.reader._tick(0xCAFE, self.base)
        self.mem.update_leaf(endpoint, struct.pack("<f", 128.5))
        self.reader._tick(0xCAFE, self.base)
        self.mem.update_leaf(endpoint, struct.pack("<f", 128.51))   # delta < threshold
        self.reader._tick(0xCAFE, self.base)
        bpms = [e for e in _drain(self.q) if e.kind == Ev.BPM_UPDATE]
        self.assertEqual(len(bpms), 2)
        self.assertAlmostEqual(bpms[0].payload["bpm"], 128.0, places=4)
        self.assertAlmostEqual(bpms[1].payload["bpm"], 128.5, places=4)
        self.assertTrue(all(e.deck == 1 for e in bpms))

    def test_bpm_zero_suppressed(self) -> None:
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")
        # All bpm chains already installed with 0.0 in setUp.
        self.reader._tick(0xCAFE, self.base)
        bpms = [e for e in _drain(self.q) if e.kind == Ev.BPM_UPDATE]
        self.assertEqual(bpms, [])

    # ── play / pause inferred from position ─────────────────────────────────
    def test_play_pause_inferred_from_position_movement(self) -> None:
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")
        endpoint = self.mem.install_chain(
            self.base, self.offs.live_pos_per_deck[0],
            payload=(1000).to_bytes(8, "little"))

        # Tick 1: first observation, no inference possible
        self.reader._tick(0xCAFE, self.base)
        # Tick 2: position advanced → playing
        self.mem.update_leaf(endpoint, (45100).to_bytes(8, "little"))
        self.reader._tick(0xCAFE, self.base)
        # Tick 3: position unchanged → paused
        self.reader._tick(0xCAFE, self.base)
        # Tick 4: position unchanged → no event (state unchanged)
        self.reader._tick(0xCAFE, self.base)
        # Tick 5: position advances again → playing
        self.mem.update_leaf(endpoint, (90200).to_bytes(8, "little"))
        self.reader._tick(0xCAFE, self.base)

        transitions = [
            (e.kind, e.deck) for e in _drain(self.q)
            if e.kind in (Ev.PLAY, Ev.PAUSE)
        ]
        self.assertEqual(transitions, [(Ev.PLAY, 1), (Ev.PAUSE, 1), (Ev.PLAY, 1)])

    # ── chain failure ───────────────────────────────────────────────────────
    def test_unknown_chain_address_does_not_raise(self) -> None:
        # Don't install master chain → first hop reads unknown → OSError
        # → master_raw stays None → no MASTER_CHANGED event but no crash.
        self.reader._tick(0xCAFE, self.base)
        self.assertEqual(
            [e for e in _drain(self.q) if e.kind == Ev.MASTER_CHANGED],
            [],
        )


# ── Constructor / no-op behaviour ────────────────────────────────────────────

class FactoryTests(unittest.TestCase):
    def test_make_reader_for_unsupported_version_returns_noop(self) -> None:
        q: queue.Queue = queue.Queue()
        reader = mod.make_rb_state_reader(q, "unsupported")
        self.assertIsNone(reader._offs)
        reader.start()
        reader.join(timeout=1.0)
        self.assertFalse(reader.is_alive())
        self.assertTrue(q.empty())

    def test_make_reader_for_supported_version_loads_offsets(self) -> None:
        q: queue.Queue = queue.Queue()
        reader = mod.make_rb_state_reader(q, "7.2.11")
        self.assertIsNotNone(reader._offs)
        assert reader._offs is not None
        self.assertEqual(reader._offs.version, "7.2.11")

    def test_disabled_via_env_exits_immediately(self) -> None:
        os.environ[mod._RB_STATE_DISABLE_ENV] = "1"
        try:
            q: queue.Queue = queue.Queue()
            reader = mod.RBStateReader(q, _make_offsets())
            reader.start()
            reader.join(timeout=1.0)
            self.assertFalse(reader.is_alive())
            self.assertTrue(q.empty())
        finally:
            os.environ.pop(mod._RB_STATE_DISABLE_ENV, None)


if __name__ == "__main__":
    unittest.main()
