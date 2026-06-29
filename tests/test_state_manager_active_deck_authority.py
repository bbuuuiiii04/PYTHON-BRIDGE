from __future__ import annotations

import queue
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.active_deck_resolver import ACTIVE_DECK_STABILITY_S
from rb_ss_bridge_v2.models import BridgeEvent, Ev, MixerAuthoritySnapshot, MixerDeckReading
from rb_ss_bridge_v2.rb_memory import PositionCache
from rb_ss_bridge_v2.state_manager import StateManager


def _reading(deck: int, *, fader: str = "top", low: str = "neutral", low_norm: float = 0.5):
    fader_norm = {"down": 0.0, "audible": 0.5, "top": 1.0}[fader]
    return MixerDeckReading(
        deck=deck,
        upfader_raw=fader_norm * 1023.0,
        upfader_norm=fader_norm,
        upfader_label=fader,
        low_raw=low_norm * 255.0,
        low_norm=low_norm,
        low_label=low,
    )


def _snapshot(
    *,
    valid: bool = True,
    updated_at: float = 100.0,
    reason: str = "ok",
    d1=None,
    d2=None,
):
    return MixerAuthoritySnapshot(
        valid=valid,
        updated_at=updated_at,
        reason=reason,
        deck={} if not valid else {1: d1 or _reading(1), 2: d2 or _reading(2, fader="down")},
    )


class StateManagerActiveDeckAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.clock = mock.patch(
            "rb_ss_bridge_v2.state_manager.time.monotonic",
            side_effect=lambda: self.now,
        )
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.sm = StateManager(
            queue.Queue(),
            PositionCache(),
            mock.Mock(),
            mixer_authority_enabled=True,
        )

    def _event(self, kind, deck=0, payload=None, source="test"):
        self.sm._handle_event(BridgeEvent(kind, deck, payload or {}, source=source))

    def _stabilize(self):
        self.now += ACTIVE_DECK_STABILITY_S + 0.001
        self.sm._rerun_active_deck_resolver("test")

    def test_startup_idle_does_not_default_rb_master_to_deck1(self):
        self.sm.set_initial_state(0, source="default startup")

        self.assertEqual(self.sm._os.active_deck, 0)
        self.assertIsNone(self.sm._os.rb_master_deck)
        self.assertFalse(self.sm._os.rb_master_deck_valid)

    def test_direct_master_startup_seed_sets_rb_master_fallback_truth(self):
        self.sm.set_initial_state(2, source="direct master seed", rb_master_valid=True)

        self.assertEqual(self.sm._os.active_deck, 2)
        self.assertEqual(self.sm._os.rb_master_deck, 2)
        self.assertTrue(self.sm._os.rb_master_deck_valid)

    def test_master_changed_updates_rb_master_without_bypassing_valid_mixer(self):
        self.sm._deck[1].playing = True
        self.sm._deck[2].playing = True
        self.sm._os.active_deck = 1
        self._event(Ev.MIXER_STATE, payload={"snapshot": _snapshot(
            d1=_reading(1, fader="top", low="high", low_norm=0.8),
            d2=_reading(2, fader="top", low="low", low_norm=0.2),
        )}, source="rb_state")

        self._event(Ev.MASTER_CHANGED, 2, {"rb_raw_deck": 1}, source="rb_state")

        self.assertEqual(self.sm._os.rb_master_deck, 2)
        self.assertEqual(self.sm._os.active_deck, 1)

    def test_osc_legacy_active_deck_cannot_rewrite_master_or_bypass_valid_mixer(self):
        self.sm._deck[1].playing = True
        self.sm._deck[2].playing = True
        self.sm._os.active_deck = 1
        self._event(Ev.MIXER_STATE, payload={"snapshot": _snapshot()}, source="rb_state")

        self._event(Ev.LEGACY_ACTIVE_DECK, 2, source="osc")

        self.assertIsNone(self.sm._os.rb_master_deck)
        self.assertEqual(self.sm._os.active_deck, 1)

    def test_raw_deck_c_direct_master_is_rejected_for_rb_master(self):
        self._event(Ev.MASTER_CHANGED, 1, {"rb_raw_deck": 2}, source="rb_state")

        self.assertIsNone(self.sm._os.rb_master_deck)
        self.assertFalse(self.sm._os.rb_master_deck_valid)
        self.assertEqual(self.sm._os.rb_master_fallback_reason, "unsupported_raw_deck")

    def test_pause_reruns_resolver_and_enters_idle_when_no_audible_deck(self):
        self.sm._deck[1].playing = True
        self.sm._os.active_deck = 1
        self._event(Ev.MIXER_STATE, payload={"snapshot": _snapshot()}, source="rb_state")

        self._event(Ev.PAUSE, 1, source="rb_state")

        self.assertEqual(self.sm._os.active_deck, 0)
        self.assertEqual(self.sm._os.active_deck_authority_reason, "idle_no_audible")

    def test_invalid_mixer_uses_rb_master_fallback_and_does_not_default_to_deck1(self):
        self._event(Ev.MIXER_STATE, payload={"snapshot": _snapshot(valid=False, reason="unreadable")})
        self.assertEqual(self.sm._os.active_deck, 0)

        self._event(Ev.MASTER_CHANGED, 2, {"rb_raw_deck": 1}, source="rb_state")
        self._stabilize()

        self.assertEqual(self.sm._os.active_deck, 2)
        self.assertEqual(self.sm._os.active_deck_authority_reason, "mixer_invalid_fallback")

    def test_legacy_active_deck_cannot_select_show_deck_when_mixer_invalid(self):
        self._event(Ev.MIXER_STATE, payload={"snapshot": _snapshot(valid=False, reason="unreadable")})
        self.assertEqual(self.sm._os.active_deck, 0)

        self._event(Ev.LEGACY_ACTIVE_DECK, 2, source="osc")
        self._event(Ev.MASTER_CHANGED, 2, source="auto-detect")

        self.assertEqual(self.sm._os.active_deck, 0)
        self.assertIsNone(self.sm._os.rb_master_deck)

    def test_valid_recovery_returns_to_fader_dominance(self):
        self.sm._deck[1].playing = True
        self.sm._deck[2].playing = True
        self.sm._os.active_deck = 1
        self._event(Ev.MASTER_CHANGED, 1, {"rb_raw_deck": 0}, source="rb_state")
        self._event(Ev.MIXER_STATE, payload={"snapshot": _snapshot(
            d1=_reading(1, fader="top", low="low", low_norm=0.2),
            d2=_reading(2, fader="top", low="high", low_norm=0.9),
        )})
        self._stabilize()

        self.assertEqual(self.sm._os.active_deck, 2)
        self.assertEqual(self.sm._os.active_deck_authority_reason, "bass_dominance")

    def test_snapshot_copy_blocks_reader_side_mutation_after_enqueue(self):
        readings = {1: _reading(1), 2: _reading(2)}
        snapshot = MixerAuthoritySnapshot(True, readings, self.now, "ok")
        self._event(Ev.MIXER_STATE, payload={"snapshot": snapshot})
        readings[1] = _reading(1, fader="down")

        self.assertEqual(self.sm._mixer_snapshot.deck[1].upfader_label, "top")
        with self.assertRaises(TypeError):
            self.sm._mixer_snapshot.deck[1] = _reading(1, fader="down")  # type: ignore[index]

    def test_scripted_deck_zero_events_are_ignored(self):
        self._event(Ev.SCRIPTED_ARM, 0, {"scripted_id": 7})
        self._event(Ev.SCRIPTED_CLEAR, 0)
        self.assertEqual(self.sm._deck[1].scripted_id, 0)
        self.assertEqual(self.sm._deck[2].scripted_id, 0)

    def test_deck_zero_state_events_are_ignored_before_indexing(self):
        self.sm._os.active_deck = 0

        self._event(Ev.TRACK_LOADED, 0, {"title": "ignored"})
        self._event(Ev.FILEPATH_RESOLVED, 0, {
            "load_gen": 0,
            "filepath": "/tmp/ignored.wav",
            "bpm": 128.0,
            "content_id": "ignored",
            "first_beat_ms": 0.0,
            "soundswitch_id": "",
            "total_ms": 1000.0,
        })
        self._event(Ev.ANLZ_PATH, 0, {"anlz_path": "/tmp/ignored.DAT"})
        self._event(Ev.BPM_UPDATE, 0, {"bpm": 128.0})

        self.assertEqual(self.sm._os.active_deck, 0)
        self.assertEqual(self.sm._last_loaded_deck, 0)
        self.assertNotIn(0, self.sm._pending_anlz_path)

    def test_idle_push_does_not_route_deck_zero(self):
        self.sm._os.active_deck = 0
        self.sm._sse.deck_route = mock.Mock(side_effect=AssertionError("deck_route called"))

        self.sm._push_tick_inner()

        self.sm._sse.deck_route.assert_not_called()

    def test_rb_restarted_while_idle_does_not_index_deck_zero(self):
        self.sm._os.active_deck = 0
        self.sm._os.was_playing = True

        self._event(Ev.RB_RESTARTED, 0, {"pid": 123})

        self.assertEqual(self.sm._os.active_deck, 0)

    def test_do_resume_empty_deck_does_not_direct_write_during_valid_mixer(self):
        self.sm._deck[1].playing = True
        self.sm._deck[2].meta.filepath = "/music/deck2.wav"
        self.sm._os.active_deck = 1
        self._event(Ev.MIXER_STATE, payload={"snapshot": _snapshot(
            d1=_reading(1, fader="top"),
            d2=_reading(2, fader="down"),
        )})

        self.sm._do_resume(1, 1000, 128.0)

        self.assertEqual(self.sm._os.active_deck, 1)


if __name__ == "__main__":
    unittest.main()
