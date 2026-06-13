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
from rb_ss_bridge_v2.models import BridgeEvent, Ev
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

    def test_master_direct_routes_to_authoritative_queue(self) -> None:
        auth_q: queue.Queue = queue.Queue()
        reader = mod.RBStateReader(
            self.q,
            self.offs,
            authoritative_queue=auth_q,
            authoritative_kinds={Ev.MASTER_CHANGED},
            drop_unrouted_events=True,
            shadow_logs_enabled=False,
            rb_pid=12345,
            base_addr=self.base,
        )
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\x01")

        reader._tick(0xCAFE, self.base)

        self.assertEqual(_drain(self.q), [])
        ev = auth_q.get_nowait()
        self.assertEqual(ev.kind, Ev.MASTER_CHANGED)
        self.assertEqual(ev.deck, 2)
        self.assertEqual(ev.source, "rb_state")

    def test_master_availability_callback_fires_true_on_valid_master(self) -> None:
        states: list[bool] = []
        reader = mod.RBStateReader(
            self.q,
            self.offs,
            authoritative_kinds={Ev.MASTER_CHANGED},
            rb_pid=12345,
            base_addr=self.base,
            master_available_callback=states.append,
        )
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\x00")

        reader._tick(0xCAFE, self.base)

        self.assertIn(True, states)

    def test_master_availability_callback_fires_false_on_sentinel(self) -> None:
        states: list[bool] = []
        reader = mod.RBStateReader(
            self.q,
            self.offs,
            authoritative_kinds={Ev.MASTER_CHANGED},
            rb_pid=12345,
            base_addr=self.base,
            master_available_callback=states.append,
        )
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\x00")
        reader._tick(0xCAFE, self.base)
        states.clear()
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")

        reader._tick(0xCAFE, self.base)

        self.assertIn(False, states)

    def test_master_availability_no_callback_without_authoritative_kind(self) -> None:
        states: list[bool] = []
        reader = mod.RBStateReader(
            self.q,
            self.offs,
            rb_pid=12345,
            base_addr=self.base,
            master_available_callback=states.append,
        )
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\x00")

        reader._tick(0xCAFE, self.base)

        self.assertEqual(states, [])

    def test_sentinel_updates_baseline_emits_no_master_event(self) -> None:
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")
        self.reader._tick(0xCAFE, self.base)

        masters = [e for e in _drain(self.q) if e.kind == Ev.MASTER_CHANGED]
        self.assertEqual(masters, [])
        self.assertEqual(self.reader._last_master, 0xFF)

        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\x01")
        self.reader._tick(0xCAFE, self.base)
        masters = [e for e in _drain(self.q) if e.kind == Ev.MASTER_CHANGED]
        self.assertEqual(len(masters), 1)
        self.assertEqual(masters[0].deck, 2)

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

    def test_track_loaded_extracts_title_from_packed_track_info(self) -> None:
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")
        blob = (
            "k Title: We Could Be Love (Odd Mob Extended Remix)\n"
            "Artist: Hayden James & AR/CO\n"
            "Album: "
        )
        self.mem.install_chain(
            self.base, self.offs.track_info_per_deck[0],
            payload=blob.encode("utf-8") + b"\x00",
        )
        self.reader._tick(0xCAFE, self.base)
        loaded = [e for e in _drain(self.q) if e.kind == Ev.TRACK_LOADED]
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].payload["title"], "We Could Be Love (Odd Mob Extended Remix)")

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
    def _prime_stopped_play_state(self, endpoint: int, pos: int = 1000) -> None:
        # Warmup ticks plus two stable observations initialize "stopped"
        # internally without emitting a startup PAUSE.
        for _ in range(5):
            self.mem.update_leaf(endpoint, pos.to_bytes(8, "little"))
            self.reader._tick(0xCAFE, self.base)
        transitions = [
            e for e in _drain(self.q)
            if e.kind in (Ev.PLAY, Ev.PAUSE)
        ]
        self.assertEqual(transitions, [])

    def test_play_pause_inferred_from_position_movement(self) -> None:
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")
        endpoint = self.mem.install_chain(
            self.base, self.offs.live_pos_per_deck[0],
            payload=(1000).to_bytes(8, "little"))

        self._prime_stopped_play_state(endpoint)
        for pos in (45100, 90200):
            self.mem.update_leaf(endpoint, pos.to_bytes(8, "little"))
            self.reader._tick(0xCAFE, self.base)
        self.reader._tick(0xCAFE, self.base)
        self.reader._tick(0xCAFE, self.base)
        for pos in (135300, 180400):
            self.mem.update_leaf(endpoint, pos.to_bytes(8, "little"))
            self.reader._tick(0xCAFE, self.base)

        transitions = [
            (e.kind, e.deck) for e in _drain(self.q)
            if e.kind in (Ev.PLAY, Ev.PAUSE)
        ]
        self.assertEqual(transitions, [(Ev.PLAY, 1), (Ev.PAUSE, 1), (Ev.PLAY, 1)])

    def test_position_warmup_suppresses_startup_flips(self) -> None:
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")
        endpoint = self.mem.install_chain(
            self.base, self.offs.live_pos_per_deck[0],
            payload=(1000).to_bytes(8, "little"))
        for pos in (1000, 45100, 90200):
            self.mem.update_leaf(endpoint, pos.to_bytes(8, "little"))
            self.reader._tick(0xCAFE, self.base)
        transitions = [
            e for e in _drain(self.q)
            if e.kind in (Ev.PLAY, Ev.PAUSE)
        ]
        self.assertEqual(transitions, [])

    def test_startup_already_moving_emits_initial_play(self) -> None:
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")
        endpoint = self.mem.install_chain(
            self.base, self.offs.live_pos_per_deck[0],
            payload=(1000).to_bytes(8, "little"))
        for pos in (1000, 45100, 90200, 135300, 180400, 225500):
            self.mem.update_leaf(endpoint, pos.to_bytes(8, "little"))
            self.reader._tick(0xCAFE, self.base)

        transitions = [
            (e.kind, e.deck) for e in _drain(self.q)
            if e.kind in (Ev.PLAY, Ev.PAUSE)
        ]
        self.assertEqual(transitions, [(Ev.PLAY, 1)])

    def test_missing_position_read_resets_baseline_before_recovery(self) -> None:
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")
        endpoint = self.mem.install_chain(
            self.base, self.offs.live_pos_per_deck[0],
            payload=(1000).to_bytes(8, "little"))
        self._prime_stopped_play_state(endpoint)

        self.mem.leaf.pop(endpoint)
        self.reader._tick(0xCAFE, self.base)

        self.mem.update_leaf(endpoint, (999999).to_bytes(8, "little"))
        for _ in range(5):
            self.reader._tick(0xCAFE, self.base)
        transitions = [
            e for e in _drain(self.q)
            if e.kind in (Ev.PLAY, Ev.PAUSE)
        ]
        self.assertEqual(transitions, [])

    def test_recovery_requires_consecutive_evidence_before_play(self) -> None:
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")
        endpoint = self.mem.install_chain(
            self.base, self.offs.live_pos_per_deck[0],
            payload=(1000).to_bytes(8, "little"))
        self._prime_stopped_play_state(endpoint)

        self.mem.leaf.pop(endpoint)
        self.reader._tick(0xCAFE, self.base)
        self.mem.update_leaf(endpoint, (50000).to_bytes(8, "little"))
        for _ in range(5):
            self.reader._tick(0xCAFE, self.base)
        self.mem.update_leaf(endpoint, (90000).to_bytes(8, "little"))
        self.reader._tick(0xCAFE, self.base)
        self.assertEqual(
            [e for e in _drain(self.q) if e.kind in (Ev.PLAY, Ev.PAUSE)],
            [],
        )
        self.mem.update_leaf(endpoint, (130000).to_bytes(8, "little"))
        self.reader._tick(0xCAFE, self.base)
        transitions = [
            (e.kind, e.deck) for e in _drain(self.q)
            if e.kind in (Ev.PLAY, Ev.PAUSE)
        ]
        self.assertEqual(transitions, [(Ev.PLAY, 1)])

    # ── chain failure ───────────────────────────────────────────────────────
    def test_unknown_chain_address_does_not_raise(self) -> None:
        # Don't install master chain → first hop reads unknown → OSError
        # → master_raw stays None → no MASTER_CHANGED event but no crash.
        self.reader._tick(0xCAFE, self.base)
        self.assertEqual(
            [e for e in _drain(self.q) if e.kind == Ev.MASTER_CHANGED],
            [],
        )

    def test_authoritative_kinds_route_only_enabled_event(self) -> None:
        auth_q: queue.Queue = queue.Queue()
        reader = mod.RBStateReader(
            self.q,
            self.offs,
            authoritative_queue=auth_q,
            authoritative_kinds={Ev.ANLZ_PATH},
            drop_unrouted_events=True,
            shadow_logs_enabled=False,
            rb_pid=12345,
            base_addr=self.base,
        )
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\x01")
        self.mem.install_chain(
            self.base,
            self.offs.track_info_per_deck[0],
            payload=b"Direct Title\x00",
        )
        endpoint = self.mem.install_chain(
            self.base,
            self.offs.anlz_path_per_deck[0],
            payload=(0).to_bytes(8, "little"),
        )
        path_addr = 0xABCDEF00
        self.mem.update_leaf(endpoint, path_addr.to_bytes(8, "little"))
        self.mem.leaf[path_addr] = b"/tmp/ANLZ0000.DAT\x00"

        reader._tick(0xCAFE, self.base)

        self.assertEqual(_drain(self.q), [])
        events = _drain(auth_q)
        self.assertEqual([e.kind for e in events], [Ev.ANLZ_PATH])
        self.assertEqual(events[0].source, "rb_state")
        self.assertEqual(events[0].payload["anlz_path"], "/tmp/ANLZ0000.DAT")

    def test_bpm_update_is_dropped_when_not_authoritative(self) -> None:
        auth_q: queue.Queue = queue.Queue()
        reader = mod.RBStateReader(
            self.q,
            self.offs,
            authoritative_queue=auth_q,
            authoritative_kinds={Ev.ANLZ_PATH},
            drop_unrouted_events=True,
            shadow_logs_enabled=False,
            rb_pid=12345,
            base_addr=self.base,
        )
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")
        self.mem.install_chain(
            self.base,
            self.offs.bpm_per_deck[0],
            payload=struct.pack("<f", 128.0),
        )

        reader._tick(0xCAFE, self.base)

        self.assertEqual(_drain(self.q), [])
        self.assertEqual(_drain(auth_q), [])

    def test_authoritative_track_loaded_routes_only_load_events(self) -> None:
        auth_q: queue.Queue = queue.Queue()
        reader = mod.RBStateReader(
            self.q,
            self.offs,
            authoritative_queue=auth_q,
            authoritative_kinds={Ev.TRACK_LOADED},
            drop_unrouted_events=True,
            shadow_logs_enabled=False,
            rb_pid=12345,
            base_addr=self.base,
        )
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\x01")
        self.mem.install_chain(
            self.base,
            self.offs.track_info_per_deck[0],
            payload=b"Direct Loaded Title\x00",
        )

        reader._tick(0xCAFE, self.base)

        self.assertEqual(_drain(self.q), [])
        events = _drain(auth_q)
        self.assertEqual([(e.kind, e.deck, e.source) for e in events], [
            (Ev.TRACK_LOADED, 1, "rb_state"),
        ])
        self.assertEqual(events[0].payload["title"], "Direct Loaded Title")

    def test_authoritative_anlz_precedes_track_loaded_in_same_tick(self) -> None:
        auth_q: queue.Queue = queue.Queue()
        reader = mod.RBStateReader(
            self.q,
            self.offs,
            authoritative_queue=auth_q,
            authoritative_kinds={Ev.ANLZ_PATH, Ev.TRACK_LOADED},
            drop_unrouted_events=True,
            shadow_logs_enabled=False,
            rb_pid=12345,
            base_addr=self.base,
        )
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")
        endpoint = self.mem.install_chain(
            self.base,
            self.offs.anlz_path_per_deck[0],
            payload=(0).to_bytes(8, "little"),
        )
        path_addr = 0xABCDEF00
        self.mem.update_leaf(endpoint, path_addr.to_bytes(8, "little"))
        self.mem.leaf[path_addr] = b"/tmp/FRESH_ANLZ.DAT\x00"
        self.mem.install_chain(
            self.base,
            self.offs.track_info_per_deck[0],
            payload=b"Fresh Direct Title\x00",
        )

        reader._tick(0xCAFE, self.base)

        events = _drain(auth_q)
        self.assertEqual([e.kind for e in events], [Ev.ANLZ_PATH, Ev.TRACK_LOADED])
        self.assertEqual(events[0].payload["anlz_path"], "/tmp/FRESH_ANLZ.DAT")
        self.assertEqual(events[1].payload["title"], "Fresh Direct Title")

    def test_anlz_availability_sets_and_clears_with_direct_readability(self) -> None:
        states: list[tuple[int, bool]] = []
        reader = mod.RBStateReader(
            self.q,
            self.offs,
            authoritative_kinds={Ev.ANLZ_PATH},
            drop_unrouted_events=True,
            shadow_logs_enabled=False,
            rb_pid=12345,
            base_addr=self.base,
            anlz_available_callback=lambda deck, ready: states.append((deck, ready)),
        )
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")
        endpoint = self.mem.install_chain(
            self.base,
            self.offs.anlz_path_per_deck[0],
            payload=(0).to_bytes(8, "little"),
        )
        path_addr = 0xABCDEF00
        self.mem.update_leaf(endpoint, path_addr.to_bytes(8, "little"))
        self.mem.leaf[path_addr] = b"/tmp/ANLZ0000.DAT\x00"

        reader._tick(0xCAFE, self.base)
        self.assertEqual(states, [(1, True)])

        self.mem.update_leaf(endpoint, (0).to_bytes(8, "little"))
        reader._tick(0xCAFE, self.base)
        self.assertEqual(states, [(1, True), (1, False)])

    def test_track_load_availability_sets_and_clears_with_direct_readability(self) -> None:
        states: list[tuple[int, bool]] = []
        reader = mod.RBStateReader(
            self.q,
            self.offs,
            authoritative_kinds={Ev.TRACK_LOADED},
            drop_unrouted_events=True,
            shadow_logs_enabled=False,
            rb_pid=12345,
            base_addr=self.base,
            track_load_available_callback=lambda deck, ready: states.append((deck, ready)),
        )
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")
        endpoint = self.mem.install_chain(
            self.base,
            self.offs.track_info_per_deck[0],
            payload=b"Readable Title\x00",
        )

        reader._tick(0xCAFE, self.base)
        self.assertEqual(states, [(1, True)])

        self.mem.leaf.pop(endpoint)
        reader._tick(0xCAFE, self.base)
        self.assertEqual(states, [(1, True), (1, False)])

    def test_track_load_availability_ignores_empty_title_buffer(self) -> None:
        states: list[tuple[int, bool]] = []
        reader = mod.RBStateReader(
            self.q,
            self.offs,
            authoritative_kinds={Ev.TRACK_LOADED},
            drop_unrouted_events=True,
            shadow_logs_enabled=False,
            rb_pid=12345,
            base_addr=self.base,
            track_load_available_callback=lambda deck, ready: states.append((deck, ready)),
        )
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")

        reader._tick(0xCAFE, self.base)

        self.assertEqual(states, [])

    def test_authoritative_play_pause_routes_only_transport_events(self) -> None:
        auth_q: queue.Queue = queue.Queue()
        reader = mod.RBStateReader(
            self.q,
            self.offs,
            authoritative_queue=auth_q,
            authoritative_kinds={Ev.PLAY, Ev.PAUSE},
            drop_unrouted_events=True,
            shadow_logs_enabled=False,
            rb_pid=12345,
            base_addr=self.base,
        )
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\x01")
        endpoint = self.mem.install_chain(
            self.base,
            self.offs.live_pos_per_deck[0],
            payload=(1000).to_bytes(8, "little"),
        )

        # Warm up a stopped baseline without forwarding startup state.
        for _ in range(5):
            self.mem.update_leaf(endpoint, (1000).to_bytes(8, "little"))
            reader._tick(0xCAFE, self.base)
        self.assertEqual(_drain(self.q), [])
        self.assertEqual(_drain(auth_q), [])

        for pos in (45_100, 90_200):
            self.mem.update_leaf(endpoint, pos.to_bytes(8, "little"))
            reader._tick(0xCAFE, self.base)
        self.assertEqual(_drain(self.q), [])
        events = _drain(auth_q)
        self.assertEqual([(e.kind, e.deck, e.source) for e in events], [(Ev.PLAY, 1, "rb_state")])

    def test_transport_availability_requires_baseline_and_clears_on_unreadable(self) -> None:
        states: list[tuple[int, bool]] = []
        reader = mod.RBStateReader(
            self.q,
            self.offs,
            authoritative_kinds={Ev.PLAY, Ev.PAUSE},
            drop_unrouted_events=True,
            shadow_logs_enabled=False,
            rb_pid=12345,
            base_addr=self.base,
            transport_available_callback=lambda deck, ready: states.append((deck, ready)),
        )
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")
        endpoint = self.mem.install_chain(
            self.base,
            self.offs.live_pos_per_deck[0],
            payload=(1000).to_bytes(8, "little"),
        )

        for _ in range(4):
            reader._tick(0xCAFE, self.base)
        self.assertEqual(states, [])

        for _ in range(4):
            reader._tick(0xCAFE, self.base)
            if states:
                break
        self.assertEqual(states, [(1, True)])

        del self.mem.leaf[endpoint]
        reader._tick(0xCAFE, self.base)
        self.assertEqual(states, [(1, True), (1, False)])


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


class DirectMasterStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mem = FakeMem()
        self.offs = _make_offsets()
        self.base = 0x100000000
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

    def _stop_patches(self) -> None:
        for p in self._patches:
            p.stop()

    def test_supported_version_direct_master_status_reads_bridge_deck(self) -> None:
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\x01")
        with mock.patch.object(mod, "load_offsets_for_version", return_value=self.offs):
            with self.assertLogs("rb_state", level="INFO") as logs:
                status = mod.read_direct_master_status("7.2.11", rb_pid=12345, base_addr=self.base)

        self.assertTrue(status.attempted)
        self.assertTrue(status.supported)
        self.assertTrue(status.available)
        self.assertTrue(status.readable)
        self.assertEqual(status.source, mod.RB_MASTER_DIRECT_SOURCE)
        self.assertEqual(status.reason, "ok")
        self.assertEqual(status.rb_raw, 1)
        self.assertEqual(status.bridge_deck, 2)
        self.assertEqual(status.pid, 12345)
        self.assertEqual(status.base, self.base)
        self.assertTrue(any(
            "[RBMASTER][DIRECT]" in line
            and "attempted=1" in line
            and "supported_version=1" in line
            and "readable=1" in line
            and "direct_master=deck2" in line
            for line in logs.output
        ))

    def test_direct_master_status_no_master_sentinel_is_available_but_no_deck(self) -> None:
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")
        with mock.patch.object(mod, "load_offsets_for_version", return_value=self.offs):
            status = mod.read_direct_master_status("7.2.11", rb_pid=12345, base_addr=self.base)

        self.assertTrue(status.attempted)
        self.assertTrue(status.supported)
        self.assertTrue(status.available)
        self.assertTrue(status.readable)
        self.assertEqual(status.source, mod.RB_MASTER_DIRECT_SOURCE)
        self.assertEqual(status.reason, "no_master")
        self.assertEqual(status.rb_raw, 255)
        self.assertIsNone(status.bridge_deck)

    def test_unsupported_version_direct_master_status_fails_closed(self) -> None:
        with mock.patch.object(mod, "load_offsets_for_version", return_value=None):
            with self.assertLogs("rb_state", level="INFO") as logs:
                status = mod.read_direct_master_status("unsupported", rb_pid=12345, base_addr=self.base)

        self.assertTrue(status.attempted)
        self.assertFalse(status.supported)
        self.assertFalse(status.available)
        self.assertFalse(status.readable)
        self.assertEqual(status.source, mod.RB_MASTER_UNAVAILABLE_SOURCE)
        self.assertEqual(status.reason, "unsupported_version")
        self.assertIsNone(status.bridge_deck)
        self.assertTrue(any(
            "[RBMASTER][DIRECT]" in line
            and "attempted=1" in line
            and "supported_version=0" in line
            and "readable=0" in line
            and "fail_closed_reason=unsupported_version" in line
            for line in logs.output
        ))

    def test_unreadable_direct_master_status_fails_closed(self) -> None:
        with mock.patch.object(mod, "load_offsets_for_version", return_value=self.offs):
            with self.assertLogs("rb_state", level="INFO") as logs:
                status = mod.read_direct_master_status("7.2.11", rb_pid=12345, base_addr=self.base)

        self.assertTrue(status.attempted)
        self.assertTrue(status.supported)
        self.assertFalse(status.available)
        self.assertFalse(status.readable)
        self.assertEqual(status.source, mod.RB_MASTER_UNAVAILABLE_SOURCE)
        self.assertEqual(status.reason, "unreadable")
        self.assertIsNone(status.bridge_deck)
        self.assertTrue(any(
            "[RBMASTER][DIRECT]" in line
            and "supported_version=1" in line
            and "readable=0" in line
            and "fail_closed_reason=unreadable" in line
            for line in logs.output
        ))


class TrackInfoParserTests(unittest.TestCase):
    def test_extract_track_title_from_plain_title(self) -> None:
        self.assertEqual(mod.extract_track_title("Plain Title"), "Plain Title")

    def test_extract_track_title_from_labeled_blob(self) -> None:
        self.assertEqual(
            mod.extract_track_title("k Title: Percolator (Cazes Edit)\nArtist: Green Velvet"),
            "Percolator (Cazes Edit)",
        )

    def test_extract_track_title_empty_on_blank(self) -> None:
        self.assertEqual(mod.extract_track_title(""), "")


if __name__ == "__main__":
    unittest.main()
