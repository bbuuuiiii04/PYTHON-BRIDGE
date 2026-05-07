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
        self.assertEqual(status.source, mod.RB_MASTER_TL_SOURCE)
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
        self.assertEqual(status.source, mod.RB_MASTER_TL_SOURCE)
        self.assertEqual(status.reason, "unreadable")
        self.assertIsNone(status.bridge_deck)
        self.assertTrue(any(
            "[RBMASTER][DIRECT]" in line
            and "supported_version=1" in line
            and "readable=0" in line
            and "fail_closed_reason=unreadable" in line
            for line in logs.output
        ))

    def test_direct_master_summary_fields_agree(self) -> None:
        status = mod.DirectMasterStatus(
            attempted=True,
            supported=True,
            available=True,
            readable=True,
            source=mod.RB_MASTER_DIRECT_SOURCE,
            reason="ok",
            rb_version="7.2.11",
            rb_raw=0,
            bridge_deck=1,
        )

        fields = mod.direct_master_summary_fields(status, 1)

        self.assertEqual(fields["direct_probe_attempted"], "1")
        self.assertEqual(fields["supported_version"], "1")
        self.assertEqual(fields["readable"], "1")
        self.assertEqual(fields["direct_master"], "deck1")
        self.assertEqual(fields["direct_raw"], "0")
        self.assertEqual(fields["tl_startup_master"], "deck1")
        self.assertEqual(fields["corroboration"], "agree")
        self.assertEqual(fields["fail_closed_reason"], "-")

    def test_direct_master_summary_fields_disagree(self) -> None:
        status = mod.DirectMasterStatus(
            attempted=True,
            supported=True,
            available=True,
            readable=True,
            source=mod.RB_MASTER_DIRECT_SOURCE,
            reason="ok",
            rb_version="7.2.11",
            rb_raw=1,
            bridge_deck=2,
        )

        fields = mod.direct_master_summary_fields(status, 1)

        self.assertEqual(fields["direct_master"], "deck2")
        self.assertEqual(fields["tl_startup_master"], "deck1")
        self.assertEqual(fields["corroboration"], "disagree")

    def test_direct_master_summary_fields_fail_closed(self) -> None:
        status = mod.DirectMasterStatus(
            attempted=True,
            supported=False,
            available=False,
            readable=False,
            source=mod.RB_MASTER_TL_SOURCE,
            reason="unsupported_version",
            rb_version="unsupported",
        )

        fields = mod.direct_master_summary_fields(status, 1)

        self.assertEqual(fields["direct_probe_attempted"], "1")
        self.assertEqual(fields["supported_version"], "0")
        self.assertEqual(fields["readable"], "0")
        self.assertEqual(fields["direct_master"], "unavailable")
        self.assertEqual(fields["corroboration"], "no_direct")
        self.assertEqual(fields["fail_closed_reason"], "unsupported_version")

    def test_direct_master_summary_fields_version_lookup_not_attempted(self) -> None:
        status = mod.DirectMasterStatus(
            attempted=False,
            supported=False,
            available=False,
            readable=False,
            source=mod.RB_MASTER_TL_SOURCE,
            reason="version_lookup_failed",
        )

        fields = mod.direct_master_summary_fields(status, 0)

        self.assertEqual(fields["direct_probe_attempted"], "0")
        self.assertEqual(fields["tl_startup_master"], "none")
        self.assertEqual(fields["corroboration"], "no_direct")

    def test_startup_observation_settles_after_initial_no_master(self) -> None:
        endpoint = self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")
        now = [0.0]

        def sleeper(seconds: float) -> None:
            now[0] += seconds
            self.mem.update_leaf(endpoint, b"\x00")

        with mock.patch.object(mod, "load_offsets_for_version", return_value=self.offs):
            with self.assertLogs("rb_state", level="INFO") as logs:
                observation = mod.observe_direct_master_startup(
                    "7.2.11",
                    rb_pid=12345,
                    base_addr=self.base,
                    settle_s=1.0,
                    interval_s=0.25,
                    clock=lambda: now[0],
                    sleeper=sleeper,
                )

        self.assertEqual(observation.initial.reason, "no_master")
        self.assertEqual(observation.initial.rb_raw, 255)
        self.assertEqual(observation.final.bridge_deck, 1)
        self.assertEqual(observation.final.reason, "ok")
        self.assertEqual(observation.attempts, 2)
        self.assertEqual(observation.outcome, "settled")
        self.assertTrue(any(
            "[RBMASTER][DIRECT]" in line
            and "phase=initial" in line
            and "raw=255" in line
            and "direct_master=none" in line
            for line in logs.output
        ))
        self.assertTrue(any(
            "[RBMASTER][DIRECT]" in line
            and "phase=settled" in line
            and "attempts=2" in line
            and "direct_master=deck1" in line
            for line in logs.output
        ))

    def test_startup_observation_no_master_persists_until_expiry(self) -> None:
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")
        now = [0.0]

        def sleeper(seconds: float) -> None:
            now[0] += seconds

        with mock.patch.object(mod, "load_offsets_for_version", return_value=self.offs):
            with self.assertLogs("rb_state", level="INFO") as logs:
                observation = mod.observe_direct_master_startup(
                    "7.2.11",
                    rb_pid=12345,
                    base_addr=self.base,
                    settle_s=0.5,
                    interval_s=0.25,
                    clock=lambda: now[0],
                    sleeper=sleeper,
                )

        self.assertEqual(observation.initial.reason, "no_master")
        self.assertEqual(observation.final.reason, "no_master")
        self.assertIsNone(observation.final.bridge_deck)
        self.assertEqual(observation.outcome, "no_master_persisted")
        self.assertGreaterEqual(observation.attempts, 2)
        self.assertTrue(any(
            "[RBMASTER][DIRECT]" in line
            and "phase=expired" in line
            and "direct_master=none" in line
            and "reason=no_master" in line
            for line in logs.output
        ))

    def test_startup_observation_unreadable_fails_closed(self) -> None:
        now = [0.0]

        with mock.patch.object(mod, "load_offsets_for_version", return_value=self.offs):
            with self.assertLogs("rb_state", level="INFO") as logs:
                observation = mod.observe_direct_master_startup(
                    "7.2.11",
                    rb_pid=12345,
                    base_addr=self.base,
                    settle_s=1.0,
                    interval_s=0.25,
                    clock=lambda: now[0],
                    sleeper=lambda seconds: None,
                )

        self.assertFalse(observation.final.readable)
        self.assertEqual(observation.final.reason, "unreadable")
        self.assertEqual(observation.outcome, "fail_closed")
        self.assertEqual(observation.attempts, 1)
        self.assertTrue(any(
            "[RBMASTER][DIRECT]" in line
            and "phase=expired" in line
            and "readable=0" in line
            and "fail_closed_reason=unreadable" in line
            for line in logs.output
        ))

    def test_startup_observation_unsupported_version_fails_closed(self) -> None:
        with mock.patch.object(mod, "load_offsets_for_version", return_value=None):
            observation = mod.observe_direct_master_startup("unsupported")

        self.assertFalse(observation.final.supported)
        self.assertFalse(observation.final.readable)
        self.assertEqual(observation.final.reason, "unsupported_version")
        self.assertEqual(observation.outcome, "fail_closed")
        self.assertEqual(observation.attempts, 1)

    def test_direct_master_observation_summary_fields(self) -> None:
        initial = mod.DirectMasterStatus(
            attempted=True,
            supported=True,
            available=True,
            readable=True,
            source=mod.RB_MASTER_DIRECT_SOURCE,
            reason="no_master",
            rb_version="7.2.11",
            rb_raw=255,
            bridge_deck=None,
        )
        final = mod.DirectMasterStatus(
            attempted=True,
            supported=True,
            available=True,
            readable=True,
            source=mod.RB_MASTER_DIRECT_SOURCE,
            reason="ok",
            rb_version="7.2.11",
            rb_raw=0,
            bridge_deck=1,
        )
        observation = mod.DirectMasterObservation(
            initial=initial,
            final=final,
            attempts=2,
            outcome="settled",
        )

        fields = mod.direct_master_observation_summary_fields(observation, 1)

        self.assertEqual(fields["initial_direct_master"], "none")
        self.assertEqual(fields["initial_raw"], "255")
        self.assertEqual(fields["direct_master"], "deck1")
        self.assertEqual(fields["corroboration"], "agree")
        self.assertEqual(fields["attempts"], "2")
        self.assertEqual(fields["outcome"], "settled")

    def test_runtime_observation_detects_first_valid_after_no_master(self) -> None:
        endpoint = self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")
        now = [0.0]

        def sleeper(seconds: float) -> None:
            now[0] += seconds
            self.mem.update_leaf(endpoint, b"\x00")

        with mock.patch.object(mod, "load_offsets_for_version", return_value=self.offs):
            with self.assertLogs("rb_state", level="INFO") as logs:
                observation = mod.observe_direct_master_runtime(
                    "7.2.11",
                    lambda: 1,
                    rb_pid=12345,
                    base_addr=self.base,
                    start_delay_s=0.0,
                    window_s=0.25,
                    interval_s=0.25,
                    clock=lambda: now[0],
                    sleeper=sleeper,
                )

        self.assertEqual(observation.initial.reason, "no_master")
        self.assertIsNotNone(observation.first_valid)
        assert observation.first_valid is not None
        self.assertEqual(observation.first_valid.bridge_deck, 1)
        self.assertEqual(observation.outcome, "became_valid_and_matched_tl")
        self.assertEqual(observation.tl_master_at_first_valid, 1)
        self.assertEqual(observation.final_tl_master, 1)
        self.assertEqual(observation.mismatches, 0)
        self.assertEqual(observation.attempts, 2)
        self.assertTrue(any(
            "[RBMASTER][RUNTIME]" in line
            and "phase=first_valid" in line
            and "transition=no_master->deck1" in line
            and "corroboration=agree" in line
            for line in logs.output
        ))
        self.assertTrue(any(
            "[RBMASTER][RUNTIME]" in line
            and "phase=summary" in line
            and "outcome=became_valid_and_matched_tl" in line
            and "final_direct_master=deck1" in line
            and "final_tl_master=deck1" in line
            and "tl_master_at_first_valid=deck1" in line
            and "first_valid_elapsed_s=0.25" in line
            and "transition_count=1" in line
            and "mismatches=0" in line
            and "comparison_source=tl_master_snapshot" in line
            for line in logs.output
        ))

    def test_runtime_observation_no_master_persists_across_window(self) -> None:
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\xff")
        now = [0.0]

        def sleeper(seconds: float) -> None:
            now[0] += seconds

        with mock.patch.object(mod, "load_offsets_for_version", return_value=self.offs):
            with self.assertLogs("rb_state", level="INFO") as logs:
                observation = mod.observe_direct_master_runtime(
                    "7.2.11",
                    lambda: 1,
                    rb_pid=12345,
                    base_addr=self.base,
                    start_delay_s=0.0,
                    window_s=0.50,
                    interval_s=0.25,
                    clock=lambda: now[0],
                    sleeper=sleeper,
                )

        self.assertEqual(observation.outcome, "never_became_valid")
        self.assertIsNone(observation.first_valid)
        self.assertEqual(observation.final.reason, "no_master")
        self.assertEqual(observation.final_tl_master, 1)
        self.assertGreaterEqual(observation.attempts, 2)
        self.assertTrue(any(
            "[RBMASTER][RUNTIME]" in line
            and "phase=summary" in line
            and "outcome=never_became_valid" in line
            and "final_direct_master=none" in line
            and "final_tl_master=deck1" in line
            and "tl_master_at_first_valid=none" in line
            and "first_valid_elapsed_s=-" in line
            and "transition_count=0" in line
            and "mismatches=0" in line
            for line in logs.output
        ))

    def test_runtime_observation_classifies_mismatch_vs_tl(self) -> None:
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\x01")
        now = [0.0]
        tl_master = {"deck": 1}

        def sleeper(seconds: float) -> None:
            now[0] += seconds

        with mock.patch.object(mod, "load_offsets_for_version", return_value=self.offs):
            with self.assertLogs("rb_state", level="INFO") as logs:
                observation = mod.observe_direct_master_runtime(
                    "7.2.11",
                    lambda: tl_master["deck"],
                    rb_pid=12345,
                    base_addr=self.base,
                    start_delay_s=0.0,
                    window_s=0.25,
                    interval_s=0.25,
                    clock=lambda: now[0],
                    sleeper=sleeper,
                )

        self.assertEqual(tl_master["deck"], 1)
        self.assertEqual(observation.outcome, "became_valid_but_mismatched_tl")
        self.assertIsNotNone(observation.first_valid)
        assert observation.first_valid is not None
        self.assertEqual(observation.first_valid.bridge_deck, 2)
        self.assertEqual(observation.tl_master_at_first_valid, 1)
        self.assertEqual(observation.final_tl_master, 1)
        self.assertGreater(observation.mismatches, 0)
        self.assertTrue(any(
            "[RBMASTER][RUNTIME]" in line
            and "phase=mismatch" in line
            and "direct_master=deck2" in line
            and "tl_master=deck1" in line
            for line in logs.output
        ))

    def test_runtime_observation_unsupported_version_fails_closed(self) -> None:
        with mock.patch.object(mod, "load_offsets_for_version", return_value=None):
            with self.assertLogs("rb_state", level="INFO") as logs:
                observation = mod.observe_direct_master_runtime("unsupported", lambda: 1)

        self.assertEqual(observation.outcome, "read_failed")
        self.assertFalse(observation.final.supported)
        self.assertFalse(observation.final.readable)
        self.assertIsNone(observation.first_valid)
        self.assertEqual(observation.final_tl_master, 1)
        self.assertTrue(any(
            "[RBMASTER][RUNTIME]" in line
            and "phase=summary" in line
            and "outcome=read_failed" in line
            and "direct_master=unavailable" in line
            and "final_tl_master=deck1" in line
            and "transition_count=0" in line
            and "mismatches=0" in line
            and "comparison_source=tl_master_snapshot" in line
            and "fail_closed_reason=unsupported_version" in line
            for line in logs.output
        ))

    def test_runtime_observation_unreadable_fails_closed(self) -> None:
        now = [0.0]

        with mock.patch.object(mod, "load_offsets_for_version", return_value=self.offs):
            observation = mod.observe_direct_master_runtime(
                "7.2.11",
                lambda: 1,
                rb_pid=12345,
                base_addr=self.base,
                start_delay_s=0.0,
                window_s=1.0,
                interval_s=0.25,
                clock=lambda: now[0],
                sleeper=lambda seconds: None,
            )

        self.assertEqual(observation.outcome, "read_failed")
        self.assertFalse(observation.final.readable)
        self.assertEqual(observation.final.reason, "unreadable")
        self.assertIsNone(observation.first_valid)

    def test_runtime_observation_without_tl_available(self) -> None:
        self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\x00")
        now = [0.0]

        def sleeper(seconds: float) -> None:
            now[0] += seconds

        with mock.patch.object(mod, "load_offsets_for_version", return_value=self.offs):
            observation = mod.observe_direct_master_runtime(
                "7.2.11",
                lambda: 0,
                rb_pid=12345,
                base_addr=self.base,
                start_delay_s=0.0,
                window_s=0.25,
                interval_s=0.25,
                clock=lambda: now[0],
                sleeper=sleeper,
            )

        self.assertEqual(observation.outcome, "became_valid_without_tl_available")
        self.assertIsNone(observation.tl_master_at_first_valid)
        self.assertIsNone(observation.final_tl_master)
        self.assertEqual(observation.mismatches, 0)

    def test_tl_master_snapshot_tracks_only_tl_master_sources(self) -> None:
        snapshot = mod.TLMasterSnapshot()
        snapshot.set_initial(1)
        snapshot.observe_event(BridgeEvent(Ev.MASTER_CHANGED, 2, source="auto-detect"))
        snapshot.observe_event(BridgeEvent(Ev.MASTER_CHANGED, 2, source="osc"))
        self.assertEqual(snapshot.get_master(), 1)

        snapshot.observe_event(BridgeEvent(Ev.MASTER_CHANGED, 2, source="tl_log"))
        self.assertEqual(snapshot.get_master(), 2)
        self.assertEqual(snapshot.source(), "tl_log")

        snapshot.observe_event(BridgeEvent(Ev.MASTER_CHANGED, 1, source="engine_state"))
        self.assertEqual(snapshot.get_master(), 1)
        self.assertEqual(snapshot.source(), "engine_state")

    def test_runtime_observation_single_legitimate_transition_is_not_flap(self) -> None:
        endpoint = self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\x00")
        now = [0.0]

        def sleeper(seconds: float) -> None:
            now[0] += seconds
            if now[0] >= 0.25:
                self.mem.update_leaf(endpoint, b"\x01")

        def tl_master() -> int:
            return 2 if now[0] >= 0.25 else 1

        with mock.patch.object(mod, "load_offsets_for_version", return_value=self.offs):
            observation = mod.observe_direct_master_runtime(
                "7.2.11",
                tl_master,
                rb_pid=12345,
                base_addr=self.base,
                start_delay_s=0.0,
                window_s=0.50,
                interval_s=0.25,
                clock=lambda: now[0],
                sleeper=sleeper,
            )

        self.assertEqual(observation.outcome, "became_valid_and_matched_tl")
        self.assertEqual(observation.transition_count, 2)
        self.assertEqual(observation.final_tl_master, 2)
        self.assertEqual(observation.mismatches, 0)

    def test_runtime_observation_flap_requires_repeated_valid_instability(self) -> None:
        endpoint = self.mem.install_chain(self.base, self.offs.master_deck, payload=b"\x00")
        now = [0.0]

        def sleeper(seconds: float) -> None:
            now[0] += seconds
            if now[0] >= 0.50:
                self.mem.update_leaf(endpoint, b"\x00")
            elif now[0] >= 0.25:
                self.mem.update_leaf(endpoint, b"\x01")

        def tl_master() -> int:
            if now[0] >= 0.50:
                return 1
            if now[0] >= 0.25:
                return 2
            return 1

        with mock.patch.object(mod, "load_offsets_for_version", return_value=self.offs):
            observation = mod.observe_direct_master_runtime(
                "7.2.11",
                tl_master,
                rb_pid=12345,
                base_addr=self.base,
                start_delay_s=0.0,
                window_s=0.50,
                interval_s=0.25,
                clock=lambda: now[0],
                sleeper=sleeper,
            )

        self.assertEqual(observation.outcome, "flapped")
        self.assertEqual(observation.transition_count, 3)
        self.assertEqual(observation.mismatches, 0)


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
