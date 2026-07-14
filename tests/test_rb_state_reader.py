"""Unit tests for RBStateReader using a fake mach-read backend."""
from __future__ import annotations

import logging
import os
import queue
import struct
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import bridge_fmt
from rb_ss_bridge_v2 import rb_state_reader as mod
from rb_ss_bridge_v2.models import BridgeEvent, Ev
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
        mixer_deck1_upfader_raw=chain(0x5000, 0x0, 0x30),
        mixer_deck2_upfader_raw=chain(0x5008, 0x0, 0x30),
        mixer_deck1_low_raw=chain(0x5010, 0x0, 0x38),
        mixer_deck2_low_raw=chain(0x5018, 0x0, 0x38),
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
        bridge_fmt.reset_rate_state()  # AWR-160 phantom-* throttle keys are global
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

    def _install_valid_mixer(
        self,
        *,
        d1_up: float = 1023.0,
        d2_up: float = 0.0,
        d1_low: float = 127.5,
        d2_low: float = 127.5,
    ) -> None:
        assert self.offs.mixer_deck1_upfader_raw is not None
        assert self.offs.mixer_deck2_upfader_raw is not None
        assert self.offs.mixer_deck1_low_raw is not None
        assert self.offs.mixer_deck2_low_raw is not None
        self.mem.install_chain(
            self.base,
            self.offs.mixer_deck1_upfader_raw,
            payload=struct.pack("<f", d1_up),
        )
        self.mem.install_chain(
            self.base,
            self.offs.mixer_deck2_upfader_raw,
            payload=struct.pack("<f", d2_up),
        )
        self.mem.install_chain(
            self.base,
            self.offs.mixer_deck1_low_raw,
            payload=struct.pack("<f", d1_low),
        )
        self.mem.install_chain(
            self.base,
            self.offs.mixer_deck2_low_raw,
            payload=struct.pack("<f", d2_low),
        )

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
        self.assertEqual(ev.payload["rb_raw_deck"], 1)

    def test_mixer_authority_invalidates_raw_deck_c_master(self) -> None:
        auth_q: queue.Queue = queue.Queue()
        reader = mod.RBStateReader(
            self.q,
            self.offs,
            authoritative_queue=auth_q,
            authoritative_kinds={Ev.MASTER_CHANGED, Ev.MIXER_STATE},
            drop_unrouted_events=True,
            shadow_logs_enabled=False,
            rb_pid=12345,
            base_addr=self.base,
        )
        self._install_valid_mixer()
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\x02")

        reader._tick(0xCAFE, self.base)

        masters = [e for e in _drain(auth_q) if e.kind == Ev.MASTER_CHANGED]
        self.assertEqual(len(masters), 1)
        self.assertEqual(masters[0].deck, 0)
        self.assertEqual(masters[0].payload["rb_raw_deck"], 2)
        self.assertEqual(masters[0].payload["reason"], "unsupported_raw_deck")

    def test_mixer_authority_refreshes_same_raw_master_before_stale_timeout(self) -> None:
        auth_q: queue.Queue = queue.Queue()
        now = 10.0
        reader = mod.RBStateReader(
            self.q,
            self.offs,
            authoritative_queue=auth_q,
            authoritative_kinds={Ev.MASTER_CHANGED, Ev.MIXER_STATE},
            drop_unrouted_events=True,
            shadow_logs_enabled=False,
            rb_pid=12345,
            base_addr=self.base,
            clock=lambda: now,
        )
        self._install_valid_mixer()
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\x00")

        reader._tick(0xCAFE, self.base)
        now += mod.RB_MASTER_REFRESH_INTERVAL_S / 2.0
        reader._tick(0xCAFE, self.base)
        now += mod.RB_MASTER_REFRESH_INTERVAL_S
        reader._tick(0xCAFE, self.base)

        masters = [e for e in _drain(auth_q) if e.kind == Ev.MASTER_CHANGED]
        self.assertEqual([(e.deck, e.payload["rb_raw_deck"]) for e in masters], [(1, 0), (1, 0)])

    def test_mixer_authority_invalid_master_events_are_not_per_tick_spam(self) -> None:
        auth_q: queue.Queue = queue.Queue()
        reader = mod.RBStateReader(
            self.q,
            self.offs,
            authoritative_queue=auth_q,
            authoritative_kinds={Ev.MASTER_CHANGED, Ev.MIXER_STATE},
            drop_unrouted_events=True,
            shadow_logs_enabled=False,
            rb_pid=12345,
            base_addr=self.base,
        )
        self._install_valid_mixer()
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")

        reader._tick(0xCAFE, self.base)
        reader._tick(0xCAFE, self.base)

        masters = [e for e in _drain(auth_q) if e.kind == Ev.MASTER_CHANGED]
        self.assertEqual(len(masters), 1)
        self.assertEqual(masters[0].deck, 0)
        self.assertEqual(masters[0].payload["rb_raw_deck"], 255)
        self.assertEqual(masters[0].payload["reason"], "no_master")

    def test_mixer_authority_unreadable_master_invalidates(self) -> None:
        auth_q: queue.Queue = queue.Queue()
        reader = mod.RBStateReader(
            self.q,
            self.offs,
            authoritative_queue=auth_q,
            authoritative_kinds={Ev.MASTER_CHANGED, Ev.MIXER_STATE},
            drop_unrouted_events=True,
            shadow_logs_enabled=False,
            rb_pid=12345,
            base_addr=self.base,
        )
        self._install_valid_mixer()

        reader._tick(0xCAFE, self.base)

        masters = [e for e in _drain(auth_q) if e.kind == Ev.MASTER_CHANGED]
        self.assertEqual(len(masters), 1)
        self.assertEqual(masters[0].deck, 0)
        self.assertEqual(masters[0].payload["reason"], "unreadable")

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

    # ── track loaded (AWR-160 stability gate) ───────────────────────────────
    def test_track_loaded_emits_with_title(self) -> None:
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")
        title = "Some Track - Some Artist"
        # Replace deck 1 (B → bridge 2) leaf with a real title.
        endpoint = self.mem.install_chain(
            self.base, self.offs.track_info_per_deck[1], payload=title.encode("utf-8") + b"\x00")
        for _ in range(mod._LOAD_STABLE_TICKS):
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
        for _ in range(mod._LOAD_STABLE_TICKS):
            self.reader._tick(0xCAFE, self.base)
        loaded = [e for e in _drain(self.q) if e.kind == Ev.TRACK_LOADED]
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].payload["title"], "We Could Be Love (Odd Mob Extended Remix)")

    def test_track_unchanged_does_not_re_emit(self) -> None:
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")
        self.mem.install_chain(
            self.base, self.offs.track_info_per_deck[0],
            payload=b"Steady\x00")
        for _ in range(mod._LOAD_STABLE_TICKS + 2):
            self.reader._tick(0xCAFE, self.base)
        loaded = [e for e in _drain(self.q) if e.kind == Ev.TRACK_LOADED]
        self.assertEqual(len(loaded), 1)

    def test_load_requires_stability_window_not_immediate(self) -> None:
        # Fewer than _LOAD_STABLE_TICKS identical reads must never emit —
        # this is the gate itself, not just a dedup check.
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")
        self.mem.install_chain(
            self.base, self.offs.track_info_per_deck[0],
            payload=b"Almost Stable\x00")
        for _ in range(mod._LOAD_STABLE_TICKS - 1):
            self.reader._tick(0xCAFE, self.base)
        self.assertEqual([e for e in _drain(self.q) if e.kind == Ev.TRACK_LOADED], [])

    def test_browse_storm_of_churning_titles_emits_nothing_and_logs_phantom_suppression(self) -> None:
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")
        endpoint = self.mem.install_chain(
            self.base, self.offs.track_info_per_deck[0], payload=b"Browse 0\x00")
        self.reader._tick(0xCAFE, self.base)  # establishes the first candidate
        # Sub-_LOAD_STABLE_TICKS churn: a new title every tick, never the
        # same identity twice in a row — the real-world "9 tracks in ~2s"
        # browse-cursor bleed from the phantom-load triage.
        with self.assertLogs("rb_state", level="DEBUG") as logs:
            for i in range(1, 10):
                self.mem.update_leaf(endpoint, f"Browse {i}\x00".encode("utf-8"))
                self.reader._tick(0xCAFE, self.base)
        self.assertEqual([e for e in _drain(self.q) if e.kind == Ev.TRACK_LOADED], [])
        self.assertEqual([e for e in _drain(self.q) if e.kind == Ev.ANLZ_PATH], [])
        self.assertTrue(any("phantom-load-suppressed" in m for m in logs.output))
        self.assertTrue(any("phantom-storm" in m for m in logs.output))

    def test_stable_new_track_never_playing_still_emits_fein_case(self) -> None:
        # FEIN case: a track loads and is never played (position never
        # moves). Stability alone must gate the load — readiness/playing
        # must never be a requirement.
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")
        self.mem.install_chain(
            self.base, self.offs.track_info_per_deck[0],
            payload=b"Loaded Never Played\x00")
        # live_pos stays frozen at the setUp default (0) the whole time —
        # play/pause inference never fires for this deck.
        for _ in range(mod._LOAD_STABLE_TICKS + 5):
            self.reader._tick(0xCAFE, self.base)
        loaded = [e for e in _drain(self.q) if e.kind == Ev.TRACK_LOADED]
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].payload["title"], "Loaded Never Played")
        self.assertEqual(
            [e for e in _drain(self.q) if e.kind in (Ev.PLAY, Ev.PAUSE)], [])

    def test_a_then_quickly_b_only_b_emits(self) -> None:
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")
        endpoint = self.mem.install_chain(
            self.base, self.offs.track_info_per_deck[0], payload=b"Track A\x00")
        self.reader._tick(0xCAFE, self.base)
        self.reader._tick(0xCAFE, self.base)  # A only reaches 2 ticks
        self.mem.update_leaf(endpoint, b"Track B\x00")
        for _ in range(mod._LOAD_STABLE_TICKS):
            self.reader._tick(0xCAFE, self.base)
        loaded = [e for e in _drain(self.q) if e.kind == Ev.TRACK_LOADED]
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].payload["title"], "Track B")

    def test_unload_after_stable_load_behaves_as_today(self) -> None:
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")
        endpoint = self.mem.install_chain(
            self.base, self.offs.track_info_per_deck[0], payload=b"Loaded Track\x00")
        for _ in range(mod._LOAD_STABLE_TICKS):
            self.reader._tick(0xCAFE, self.base)
        self.assertEqual(
            len([e for e in _drain(self.q) if e.kind == Ev.TRACK_LOADED]), 1)

        self.mem.update_leaf(endpoint, b"\x00")  # deck ejects, title clears
        self.reader._tick(0xCAFE, self.base)
        self.assertNotIn(0, self.reader._last_track)

        # Reloading the SAME title afterward must emit again immediately
        # once stable — unload cleared the "already loaded" memory exactly
        # as it does today, the gate did not suppress recognition of it.
        self.mem.update_leaf(endpoint, b"Loaded Track\x00")
        for _ in range(mod._LOAD_STABLE_TICKS):
            self.reader._tick(0xCAFE, self.base)
        reloaded = [e for e in _drain(self.q) if e.kind == Ev.TRACK_LOADED]
        self.assertEqual(len(reloaded), 1)
        self.assertEqual(reloaded[0].payload["title"], "Loaded Track")

    def test_deck_1_and_deck_2_stability_gate_symmetric(self) -> None:
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")
        # RB raw deck 0 → bridge 1, RB raw deck 1 → bridge 2. Verified in two
        # phases, not simultaneously: this fixture's track_info chains share
        # their first hop across all decks (_make_offsets uses a constant
        # leading 0x3000 for every d), so installing two decks' non-empty
        # leaves at once clobbers each other in FakeMem, not in the reader.
        self.mem.install_chain(
            self.base, self.offs.track_info_per_deck[0], payload=b"Deck One Track\x00")
        for _ in range(mod._LOAD_STABLE_TICKS):
            self.reader._tick(0xCAFE, self.base)
        deck1_loaded = [e for e in _drain(self.q) if e.kind == Ev.TRACK_LOADED]
        self.assertEqual(len(deck1_loaded), 1)
        self.assertEqual(deck1_loaded[0].deck, 1)
        self.assertEqual(deck1_loaded[0].payload["title"], "Deck One Track")

        self.mem.install_chain(
            self.base, self.offs.track_info_per_deck[1], payload=b"Deck Two Track\x00")
        for _ in range(mod._LOAD_STABLE_TICKS):
            self.reader._tick(0xCAFE, self.base)
        deck2_loaded = [
            e for e in _drain(self.q) if e.kind == Ev.TRACK_LOADED and e.deck == 2]
        self.assertEqual(len(deck2_loaded), 1)
        self.assertEqual(deck2_loaded[0].payload["title"], "Deck Two Track")

    def test_stable_load_emits_exactly_once_per_confirmed_track(self) -> None:
        # Proxy for "load_gen advances only on emission" at the reader
        # level: StateManager bumps load_gen exactly once per TRACK_LOADED
        # it consumes, so one emission per genuine load is the invariant
        # this layer owns.
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")
        self.mem.install_chain(
            self.base, self.offs.track_info_per_deck[0], payload=b"One Load\x00")
        for _ in range(mod._LOAD_STABLE_TICKS * 3):
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

    def test_mixer_authority_suppresses_raw_deck_c_play_pause_support(self) -> None:
        auth_q: queue.Queue = queue.Queue()
        reader = mod.RBStateReader(
            self.q,
            self.offs,
            authoritative_queue=auth_q,
            authoritative_kinds={Ev.PLAY, Ev.PAUSE, Ev.MIXER_STATE},
            drop_unrouted_events=True,
            shadow_logs_enabled=False,
            rb_pid=12345,
            base_addr=self.base,
        )
        self._install_valid_mixer()
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")
        endpoint = self.mem.install_chain(
            self.base,
            self.offs.live_pos_per_deck[2],
            payload=(1000).to_bytes(8, "little"),
        )
        for pos in (1000, 1000, 1000, 1000, 1000, 2000, 3000, 4000):
            self.mem.update_leaf(endpoint, pos.to_bytes(8, "little"))
            reader._tick(0xCAFE, self.base)

        events = [e for e in _drain(auth_q) if e.kind in (Ev.PLAY, Ev.PAUSE)]
        self.assertEqual(events, [])

    def test_lost_mixer_transport_support_emits_fail_closed_pause(self) -> None:
        auth_q: queue.Queue = queue.Queue()
        reader = mod.RBStateReader(
            self.q,
            self.offs,
            authoritative_queue=auth_q,
            authoritative_kinds={Ev.PLAY, Ev.PAUSE, Ev.MIXER_STATE},
            drop_unrouted_events=True,
            shadow_logs_enabled=False,
            rb_pid=12345,
            base_addr=self.base,
        )
        self._install_valid_mixer()
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")
        endpoint = self.mem.install_chain(
            self.base,
            self.offs.live_pos_per_deck[0],
            payload=(1000).to_bytes(8, "little"),
        )
        for _ in range(8):
            reader._tick(0xCAFE, self.base)
        _drain(auth_q)

        del self.mem.leaf[endpoint]
        reader._tick(0xCAFE, self.base)

        pauses = [e for e in _drain(auth_q) if e.kind == Ev.PAUSE]
        self.assertEqual(len(pauses), 1)
        self.assertEqual(pauses[0].deck, 1)
        self.assertEqual(pauses[0].source, "rb_state")
        self.assertEqual(pauses[0].payload["reason"], "transport_unavailable")

    def test_no_startup_pause_noise_for_never_available_mixer_transport(self) -> None:
        auth_q: queue.Queue = queue.Queue()
        reader = mod.RBStateReader(
            self.q,
            self.offs,
            authoritative_queue=auth_q,
            authoritative_kinds={Ev.PLAY, Ev.PAUSE, Ev.MIXER_STATE},
            drop_unrouted_events=True,
            shadow_logs_enabled=False,
            rb_pid=12345,
            base_addr=self.base,
        )
        self._install_valid_mixer()
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")

        reader._tick(0xCAFE, self.base)

        self.assertEqual([e for e in _drain(auth_q) if e.kind == Ev.PAUSE], [])

    def test_mixer_snapshot_accepts_endpoint_values_and_refreshes_time(self) -> None:
        auth_q: queue.Queue = queue.Queue()
        now = 10.0
        reader = mod.RBStateReader(
            self.q,
            self.offs,
            authoritative_queue=auth_q,
            authoritative_kinds={Ev.MIXER_STATE},
            drop_unrouted_events=True,
            shadow_logs_enabled=False,
            rb_pid=12345,
            base_addr=self.base,
            clock=lambda: now,
        )
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")
        self._install_valid_mixer(d1_up=0.0, d2_up=1023.0, d1_low=255.0, d2_low=0.0)

        reader._tick(0xCAFE, self.base)
        first = [e for e in _drain(auth_q) if e.kind == Ev.MIXER_STATE][0].payload["snapshot"]
        now = 11.0
        reader._tick(0xCAFE, self.base)
        second = [e for e in _drain(auth_q) if e.kind == Ev.MIXER_STATE][0].payload["snapshot"]

        self.assertTrue(first.valid)
        self.assertEqual(first.deck[1].upfader_label, "down")
        self.assertEqual(first.deck[2].upfader_label, "top")
        self.assertEqual(first.deck[1].low_label, "high")
        self.assertEqual(first.deck[2].low_label, "low")
        self.assertEqual(second.updated_at, 11.0)

    def test_mixer_snapshot_invalid_on_partial_unreadable_or_non_finite(self) -> None:
        auth_q: queue.Queue = queue.Queue()
        reader = mod.RBStateReader(
            self.q,
            self.offs,
            authoritative_queue=auth_q,
            authoritative_kinds={Ev.MIXER_STATE},
            drop_unrouted_events=True,
            shadow_logs_enabled=False,
            rb_pid=12345,
            base_addr=self.base,
        )
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")
        self._install_valid_mixer()
        assert self.offs.mixer_deck2_low_raw is not None
        self.mem.install_chain(
            self.base,
            self.offs.mixer_deck2_low_raw,
            payload=struct.pack("<f", float("inf")),
        )

        reader._tick(0xCAFE, self.base)

        snapshot = [e for e in _drain(auth_q) if e.kind == Ev.MIXER_STATE][0].payload["snapshot"]
        self.assertFalse(snapshot.valid)
        self.assertEqual(dict(snapshot.deck), {})
        self.assertEqual(snapshot.reason, "non_finite")

    def test_mixer_snapshot_invalid_on_nan_or_out_of_range(self) -> None:
        auth_q: queue.Queue = queue.Queue()
        reader = mod.RBStateReader(
            self.q,
            self.offs,
            authoritative_queue=auth_q,
            authoritative_kinds={Ev.MIXER_STATE},
            drop_unrouted_events=True,
            shadow_logs_enabled=False,
            rb_pid=12345,
            base_addr=self.base,
        )
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")
        assert self.offs.mixer_deck1_upfader_raw is not None

        for bad_value, reason in ((float("nan"), "non_finite"), (1023.1, "out_of_range")):
            self._install_valid_mixer()
            self.mem.install_chain(
                self.base,
                self.offs.mixer_deck1_upfader_raw,
                payload=struct.pack("<f", bad_value),
            )
            reader._tick(0xCAFE, self.base)
            snapshot = [
                e for e in _drain(auth_q) if e.kind == Ev.MIXER_STATE
            ][0].payload["snapshot"]
            self.assertFalse(snapshot.valid)
            self.assertEqual(dict(snapshot.deck), {})
            self.assertEqual(snapshot.reason, reason)

    def test_mixer_snapshot_invalid_reason_unreadable(self) -> None:
        auth_q: queue.Queue = queue.Queue()
        reader = mod.RBStateReader(
            self.q,
            self.offs,
            authoritative_queue=auth_q,
            authoritative_kinds={Ev.MIXER_STATE},
            drop_unrouted_events=True,
            shadow_logs_enabled=False,
            rb_pid=12345,
            base_addr=self.base,
        )
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")
        self._install_valid_mixer()
        assert self.offs.mixer_deck1_low_raw is not None
        endpoint = self.mem.install_chain(
            self.base,
            self.offs.mixer_deck1_low_raw,
            payload=struct.pack("<f", 127.5),
        )
        del self.mem.leaf[endpoint]

        reader._tick(0xCAFE, self.base)

        snapshot = [e for e in _drain(auth_q) if e.kind == Ev.MIXER_STATE][0].payload["snapshot"]
        self.assertFalse(snapshot.valid)
        self.assertEqual(snapshot.reason, "unreadable")

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

        for _ in range(mod._LOAD_STABLE_TICKS):
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

        for _ in range(mod._LOAD_STABLE_TICKS):
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

        for _ in range(mod._LOAD_STABLE_TICKS):
            reader._tick(0xCAFE, self.base)

        events = _drain(auth_q)
        self.assertEqual([e.kind for e in events], [Ev.ANLZ_PATH, Ev.TRACK_LOADED])
        self.assertEqual(events[0].payload["anlz_path"], "/tmp/FRESH_ANLZ.DAT")
        self.assertEqual(events[1].payload["title"], "Fresh Direct Title")

    def test_transient_anlz_read_failure_does_not_poison_recovery_diff(self) -> None:
        # A transient ANLZ read failure during the title's stability window
        # must not block the title from confirming, and a late-resolving
        # ANLZ path must still catch up on its own once the title is already
        # confirmed (AWR-160: ANLZ_PATH is coupled to the load, never lost).
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
        old_path_addr = 0xABCDEF20
        self.mem.update_leaf(endpoint, old_path_addr.to_bytes(8, "little"))
        self.mem.leaf[old_path_addr] = b"/tmp/OLD_ANLZ.DAT\x00"
        self.mem.install_chain(
            self.base,
            self.offs.track_info_per_deck[0],
            payload=b"Steady Title\x00",
        )

        reader._tick(0xCAFE, self.base)  # candidate ticks=1, anlz read ok
        missing_path_addr = 0xABCDEF40
        self.mem.update_leaf(endpoint, missing_path_addr.to_bytes(8, "little"))
        reader._tick(0xCAFE, self.base)  # candidate ticks=2, anlz read fails (unmapped)
        self.assertIsNone(reader._last_anlz.get(0))

        reader._tick(0xCAFE, self.base)  # candidate ticks=3: title confirms
        events = _drain(auth_q)
        self.assertEqual([e.kind for e in events], [Ev.TRACK_LOADED])
        self.assertIsNone(reader._last_anlz.get(0))

        recovered_path_addr = 0xABCDEF60
        self.mem.update_leaf(endpoint, recovered_path_addr.to_bytes(8, "little"))
        self.mem.leaf[recovered_path_addr] = b"/tmp/RECOVERED_ANLZ.DAT\x00"
        reader._tick(0xCAFE, self.base)

        events = _drain(auth_q)
        self.assertEqual([e.kind for e in events], [Ev.ANLZ_PATH])
        self.assertEqual(events[0].payload["anlz_path"], "/tmp/RECOVERED_ANLZ.DAT")

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


class HealthTransitionTests(unittest.TestCase):
    """AWR-125 W4: health.rb / health.queue emits in RBStateReader.run()/_enqueue()."""

    def setUp(self) -> None:
        bridge_fmt.reset_rate_state()

    def test_no_offsets_emits_health_rb_warning(self) -> None:
        q: queue.Queue = queue.Queue()
        reader = mod.RBStateReader(q, None)
        logger, handler, prior_level, records = _capture("health.rb")
        self.addCleanup(logger.setLevel, prior_level)
        self.addCleanup(logger.removeHandler, handler)

        reader.start()
        reader.join(timeout=1.0)

        self.assertFalse(reader.is_alive())
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].levelname, "WARNING")
        self.assertIn("no offsets", records[0].getMessage())

    def test_attach_failure_waits_and_retries(self) -> None:
        q: queue.Queue = queue.Queue()
        reader = mod.RBStateReader(q, _make_offsets(), sleeper=lambda _s: None)
        reader._attach = mock.Mock(side_effect=RuntimeError("synthetic attach failure"))
        # First wait interrupt: stop so the outer loop exits promptly.
        reader._stop_event.wait = mock.Mock(side_effect=lambda _t=None: reader._stop_event.set() or True)
        logger, handler, prior_level, records = _capture("health.rb")
        self.addCleanup(logger.setLevel, prior_level)
        self.addCleanup(logger.removeHandler, handler)

        reader.run()

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].levelname, "WARNING")
        self.assertIn("waiting for rekordbox", records[0].getMessage())
        self.assertGreaterEqual(reader._attach.call_count, 1)
        self.assertFalse(reader.attach_health()["attached"])

    def test_attached_emits_health_rb_info(self) -> None:
        q: queue.Queue = queue.Queue()
        reader = mod.RBStateReader(q, _make_offsets(), sleeper=lambda _s: None)
        reader._attach = mock.Mock(return_value=(0xCAFE, 0x100000000))
        reader._tick = mock.Mock(side_effect=lambda *_a: reader._stop_event.set())
        logger, handler, prior_level, records = _capture("health.rb")
        self.addCleanup(logger.setLevel, prior_level)
        self.addCleanup(logger.removeHandler, handler)

        reader.run()

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].levelname, "INFO")
        self.assertIn("attached", records[0].getMessage())

    def test_attach_retries_then_ticks(self) -> None:
        """Bridge-before-RB: attach fails twice, then succeeds and ticks."""
        q: queue.Queue = queue.Queue()
        reader = mod.RBStateReader(q, _make_offsets(), sleeper=lambda _s: None)
        reader._stop_event.wait = mock.Mock(return_value=False)
        attempts = {"n": 0}
        ticks: list[tuple[int, int]] = []

        def _attach() -> tuple[int, int]:
            attempts["n"] += 1
            if attempts["n"] <= 2:
                raise RuntimeError("rekordbox not up yet")
            reader._rb_pid = 4242
            reader._base = 0x100000000
            return (0xCAFE, 0x100000000)

        def _tick(task: int, base: int) -> None:
            ticks.append((task, base))
            reader._stop_event.set()

        reader._attach = _attach
        reader._tick = _tick
        reader.run()

        self.assertEqual(attempts["n"], 3)
        self.assertEqual(ticks, [(0xCAFE, 0x100000000)])
        self.assertFalse(reader.attach_health()["attached"])  # cleared on exit

    def test_pid_gone_mid_run_detaches_and_reattaches(self) -> None:
        q: queue.Queue = queue.Queue()
        reader = mod.RBStateReader(q, _make_offsets(), sleeper=lambda _s: None)
        reader._stop_event.wait = mock.Mock(return_value=False)
        attaches = {"n": 0}
        ticks = {"n": 0}
        unavailable_marks = {"n": 0}
        orig_mark = reader._mark_all_unavailable

        def _mark() -> None:
            unavailable_marks["n"] += 1
            orig_mark()

        def _attach() -> tuple[int, int]:
            attaches["n"] += 1
            reader._rb_pid = 5000 + attaches["n"]
            reader._base = 0x100000000
            return (0xCAFE, 0x100000000)

        def _tick(task: int, base: int) -> None:
            ticks["n"] += 1
            if ticks["n"] == 1:
                raise OSError("mach_vm_read_overwrite failed")
            reader._stop_event.set()

        reader._attach = _attach
        reader._tick = _tick
        reader._mark_all_unavailable = _mark
        with mock.patch.object(mod.os, "kill", side_effect=OSError(3, "No such process")):
            reader.run()

        self.assertGreaterEqual(attaches["n"], 2)
        self.assertGreaterEqual(ticks["n"], 2)
        self.assertGreaterEqual(unavailable_marks["n"], 1)
        self.assertIsNone(reader._rb_pid)
        self.assertIsNone(reader._base)

    def test_stop_during_waiting_exits_promptly(self) -> None:
        import threading
        import time

        q: queue.Queue = queue.Queue()
        reader = mod.RBStateReader(q, _make_offsets())
        reader._attach = mock.Mock(side_effect=RuntimeError("no rekordbox yet"))

        def _stop_soon() -> None:
            time.sleep(0.05)
            reader.stop()

        stopper = threading.Thread(target=_stop_soon, daemon=True)
        stopper.start()
        t0 = time.monotonic()
        reader.run()
        elapsed = time.monotonic() - t0
        stopper.join(timeout=1.0)
        self.assertLess(elapsed, 2.0, f"stop() should interrupt the 5s wait; took {elapsed:.2f}s")

    def test_status_merge_waiting_when_event_reader_not_attached(self) -> None:
        from rb_ss_bridge_v2.runtime_status import (
            apply_event_reader_waiting_reason,
            rekordbox_status,
        )

        waiting = apply_event_reader_waiting_reason(
            {"reads_ok": True, "reason": ""}, attached=False,
        )
        status = rekordbox_status("7.2.16", True, waiting)
        self.assertEqual(status["reason"], "waiting_for_rekordbox")
        self.assertTrue(status["reads_ok"])

        attached = apply_event_reader_waiting_reason(
            {"reads_ok": True, "reason": ""}, attached=True,
        )
        self.assertEqual(attached.get("reason") or "", "")
        self.assertEqual(
            rekordbox_status("7.2.16", True, attached)["reason"], "",
        )

        # Memory health reason still wins over the waiting overlay.
        blocked = apply_event_reader_waiting_reason(
            {"reads_ok": False, "reason": "reads_blocked"}, attached=False,
        )
        self.assertEqual(blocked["reason"], "reads_blocked")
        self.assertFalse(blocked["reads_ok"])

    def test_enqueue_full_emits_health_queue_throttled(self) -> None:
        q: queue.Queue = queue.Queue(maxsize=1)
        reader = mod.RBStateReader(q, _make_offsets())
        q.put_nowait(object())  # fill the bounded queue
        logger, handler, prior_level, records = _capture("health.queue")
        self.addCleanup(logger.setLevel, prior_level)
        self.addCleanup(logger.removeHandler, handler)

        ev = BridgeEvent(kind=Ev.BPM_UPDATE, deck=1, payload={"bpm": 128.0})
        reader._enqueue(ev)
        reader._enqueue(ev)  # second consecutive drop must not re-log (throttled)

        self.assertEqual(len(records), 1, f"expected exactly one throttled record, got {records!r}")
        self.assertEqual(records[0].levelname, "WARNING")
        self.assertIn("queue full", records[0].getMessage())


def _offsets_with_cfx() -> RBOffsetVersion:
    import dataclasses

    def chain(*nums: int) -> ChainEntry:
        return ChainEntry(hops=nums[:-1], final_off=nums[-1])

    # Distinct FIRST hop per chain so FakeMem.install_chain doesn't collide on a
    # shared hop address (the mixer chains do the same, 0x5000/0x5008/...).
    return dataclasses.replace(
        _make_offsets(),
        cfx_deck1_filter_param0=chain(0x6000, 0x0),
        cfx_deck1_selected_id=chain(0x6010, 0x0),
        cfx_deck1_unit_channel=chain(0x6020, 0x0),
        cfx_deck2_filter_param0=chain(0x6100, 0x0),
        cfx_deck2_selected_id=chain(0x6110, 0x0),
        cfx_deck2_unit_channel=chain(0x6120, 0x0),
    )


class CfxTickTests(unittest.TestCase):
    """AWR-173: _tick_cfx publishes a CfxFilterSnapshot; tracking-only, isolated
    from mixer authority."""

    def setUp(self) -> None:
        bridge_fmt.reset_rate_state()
        self.mem = FakeMem()
        self.offs = _offsets_with_cfx()
        self.base = 0x100000000
        self.q: queue.Queue = queue.Queue()
        self.auth_q: queue.Queue = queue.Queue()
        self._patches = [
            mock.patch.object(mod, "_read_bytes", side_effect=self.mem.read_bytes),
            mock.patch.object(mod, "_task_for_pid", return_value=0xCAFE),
            mock.patch.object(mod, "get_rb_pid", return_value=12345),
            mock.patch.object(mod, "_get_vmmap_output", return_value=""),
            mock.patch.object(mod, "_base_from_vmmap", return_value=self.base),
        ]
        for p in self._patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in self._patches])
        # master + per-deck nulls so the tick body is reachable.
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")
        for d in range(4):
            self.mem.install_chain(self.base, self.offs.bpm_per_deck[d], payload=struct.pack("<f", 0.0))
            self.mem.install_chain(self.base, self.offs.live_pos_per_deck[d], payload=(0).to_bytes(8, "little"))
            self.mem.install_chain(self.base, self.offs.track_info_per_deck[d], payload=b"")

    def _install_cfx(self, deck, *, param0=0.5, selected_id=0, unit_channel=None):
        if unit_channel is None:
            unit_channel = deck - 1
        param_ch = self.offs.cfx_deck1_filter_param0 if deck == 1 else self.offs.cfx_deck2_filter_param0
        id_ch = self.offs.cfx_deck1_selected_id if deck == 1 else self.offs.cfx_deck2_selected_id
        unit_ch = self.offs.cfx_deck1_unit_channel if deck == 1 else self.offs.cfx_deck2_unit_channel
        self.mem.install_chain(self.base, param_ch, payload=struct.pack("<f", param0))
        self.mem.install_chain(self.base, id_ch, payload=struct.pack("<i", selected_id))
        self.mem.install_chain(self.base, unit_ch, payload=struct.pack("<i", unit_channel))

    def _reader(self, **kw):
        return mod.RBStateReader(
            self.q, self.offs,
            authoritative_queue=self.auth_q,
            drop_unrouted_events=True,
            rb_pid=12345, base_addr=self.base,
            clock=lambda: 10.0,
            **kw,
        )

    def _cfx_snap(self, reader):
        reader._tick(0xCAFE, self.base)
        events = [e for e in _drain(self.auth_q) if e.kind == Ev.CFX_STATE]
        self.assertEqual(len(events), 1)
        return events[0].payload["snapshot"]

    def test_cfx_state_never_authoritative(self) -> None:
        reader = self._reader(authoritative_kinds={Ev.MIXER_STATE})
        self.assertNotIn(Ev.CFX_STATE, reader._authoritative_kinds)

    def test_valid_reading(self) -> None:
        self._install_cfx(1, param0=0.732, selected_id=0, unit_channel=0)
        self._install_cfx(2, param0=0.4, selected_id=0, unit_channel=1)
        snap = self._cfx_snap(self._reader())
        self.assertTrue(snap.valid)
        self.assertTrue(snap.deck[1].valid)
        self.assertEqual(snap.deck[1].reason, "ok")
        self.assertAlmostEqual(snap.deck[1].filter_norm, 0.732, places=5)
        self.assertTrue(snap.deck[2].valid)

    def test_wrong_effect(self) -> None:
        self._install_cfx(1, selected_id=7)  # not FILTER
        self._install_cfx(2)
        snap = self._cfx_snap(self._reader())
        self.assertFalse(snap.deck[1].valid)
        self.assertEqual(snap.deck[1].reason, "wrong_effect")

    def test_unit_channel_mismatch(self) -> None:
        self._install_cfx(1, selected_id=0, unit_channel=1)  # deck 1 expects 0
        self._install_cfx(2)
        snap = self._cfx_snap(self._reader())
        self.assertFalse(snap.deck[1].valid)
        self.assertEqual(snap.deck[1].reason, "unit_channel_mismatch")

    def test_non_finite_and_out_of_range(self) -> None:
        for bad, reason in ((float("nan"), "non_finite"), (1.5, "out_of_range")):
            self._install_cfx(1, param0=bad, selected_id=0, unit_channel=0)
            self._install_cfx(2)
            snap = self._cfx_snap(self._reader())
            self.assertFalse(snap.deck[1].valid)
            self.assertEqual(snap.deck[1].reason, reason)

    def test_per_deck_independence(self) -> None:
        # Deck 1 valid; deck 2 chains unreadable (leaves not installed).
        self._install_cfx(1, param0=0.9, selected_id=0, unit_channel=0)
        snap = self._cfx_snap(self._reader())
        self.assertTrue(snap.deck[1].valid)
        self.assertFalse(snap.deck[2].valid)
        self.assertEqual(snap.deck[2].reason, "unreadable")

    def test_isolation_broken_cfx_keeps_mixer_valid(self) -> None:
        # The pin: broken CFX chains + healthy mixer chains ⇒ MIXER_STATE valid.
        mixer_reader = mod.RBStateReader(
            self.q, self.offs,
            authoritative_queue=self.auth_q,
            authoritative_kinds={Ev.MASTER_CHANGED, Ev.MIXER_STATE},
            drop_unrouted_events=True,
            rb_pid=12345, base_addr=self.base,
            clock=lambda: 10.0,
        )
        # Healthy mixer reads.
        self.mem.install_chain(self.base, self.offs.mixer_deck1_upfader_raw, payload=struct.pack("<f", 512.0))
        self.mem.install_chain(self.base, self.offs.mixer_deck2_upfader_raw, payload=struct.pack("<f", 0.0))
        self.mem.install_chain(self.base, self.offs.mixer_deck1_low_raw, payload=struct.pack("<f", 128.0))
        self.mem.install_chain(self.base, self.offs.mixer_deck2_low_raw, payload=struct.pack("<f", 128.0))
        # CFX left broken (no leaves installed) -> unreadable.
        mixer_reader._tick(0xCAFE, self.base)
        events = _drain(self.auth_q)
        mixer_snap = [e for e in events if e.kind == Ev.MIXER_STATE][0].payload["snapshot"]
        cfx_snap = [e for e in events if e.kind == Ev.CFX_STATE][0].payload["snapshot"]
        self.assertTrue(mixer_snap.valid)            # mixer authority untouched
        self.assertFalse(cfx_snap.deck[1].valid)     # cfx independently invalid


if __name__ == "__main__":
    unittest.main()
