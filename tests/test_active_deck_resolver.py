from __future__ import annotations

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.active_deck_resolver import (
    ACTIVE_DECK_STABILITY_S,
    ResolverDeckInput,
    ResolverState,
    resolve_active_deck,
)


def _deck(*, playing: bool, fader: str, low: str = "neutral", low_norm: float = 0.5):
    fader_norm = {"down": 0.0, "audible": 0.5, "top": 1.0}[fader]
    return ResolverDeckInput(
        playing=playing,
        upfader_raw=fader_norm * 1023.0,
        upfader_norm=fader_norm,
        upfader_label=fader,
        low_raw=low_norm * 255.0,
        low_norm=low_norm,
        low_label=low,
    )


def _resolve(
    *,
    current=1,
    master=1,
    master_valid=True,
    deck=None,
    mixer_valid=True,
    mixer_updated_at=100.0,
    state=ResolverState(),
    now=100.0,
):
    return resolve_active_deck(
        current_active_deck=current,
        rb_master_deck=master,
        rb_master_deck_valid=master_valid,
        rb_master_deck_source="rb_state" if master_valid else "unknown",
        rb_master_deck_updated_at=now if master_valid else 0.0,
        rb_master_fallback_reason="" if master_valid else "rb_master_unavailable_fallback",
        deck=deck or {
            1: _deck(playing=True, fader="top"),
            2: _deck(playing=False, fader="down"),
        },
        mixer_valid=mixer_valid,
        mixer_updated_at=mixer_updated_at,
        mixer_reason="ok" if mixer_valid else "unreadable",
        state=state,
        now=now,
    )


def _stable(**kwargs):
    first = _resolve(**kwargs)
    return _resolve(
        **{
            **kwargs,
            "state": first.state,
            "now": kwargs.get("now", 100.0) + ACTIVE_DECK_STABILITY_S + 0.001,
        }
    )


class ActiveDeckResolverTests(unittest.TestCase):
    def test_fader_down_playing_deck_does_not_steal_from_paused_master(self):
        result = _resolve(
            current=1,
            master=2,
            deck={
                1: _deck(playing=True, fader="down"),
                2: _deck(playing=False, fader="top"),
            },
        )
        self.assertEqual(result.active_deck, 0)
        self.assertEqual(result.authority_reason, "idle_no_audible")

    def test_paused_top_fader_is_not_eligible(self):
        result = _stable(
            current=1,
            master=2,
            deck={
                1: _deck(playing=True, fader="audible"),
                2: _deck(playing=False, fader="top"),
            },
        )
        self.assertEqual(result.active_deck, 1)
        self.assertEqual(result.authority_reason, "only_audible")

    def test_bass_cannot_make_fader_down_deck_eligible(self):
        result = _stable(
            current=1,
            master=1,
            deck={
                1: _deck(playing=True, fader="down", low="high", low_norm=1.0),
                2: _deck(playing=True, fader="audible", low="low", low_norm=0.0),
            },
        )
        self.assertEqual(result.active_deck, 2)
        self.assertEqual(result.authority_reason, "only_audible")

    def test_top_neutral_tie_uses_rb_master_even_when_current_is_other_deck(self):
        result = _stable(
            current=1,
            master=2,
            deck={
                1: _deck(playing=True, fader="top", low="neutral", low_norm=0.5),
                2: _deck(playing=True, fader="top", low="neutral", low_norm=0.5),
            },
        )
        self.assertEqual(result.active_deck, 2)
        self.assertEqual(result.authority_reason, "rb_master_tie")

    def test_higher_bass_wins_after_stability(self):
        first = _resolve(
            current=1,
            master=1,
            deck={
                1: _deck(playing=True, fader="top", low="low", low_norm=0.2),
                2: _deck(playing=True, fader="top", low="high", low_norm=0.8),
            },
        )
        self.assertEqual(first.active_deck, 1)
        self.assertFalse(first.stable)
        second = _resolve(
            current=1,
            master=1,
            deck={
                1: _deck(playing=True, fader="top", low="low", low_norm=0.2),
                2: _deck(playing=True, fader="top", low="high", low_norm=0.8),
            },
            state=first.state,
            now=100.0 + ACTIVE_DECK_STABILITY_S + 0.001,
        )
        self.assertEqual(second.active_deck, 2)
        self.assertEqual(second.authority_reason, "bass_dominance")

    def test_equal_non_neutral_holds_current_else_master(self):
        hold = _resolve(
            current=1,
            master=2,
            deck={
                1: _deck(playing=True, fader="top", low="high", low_norm=0.7),
                2: _deck(playing=True, fader="top", low="high", low_norm=0.705),
            },
        )
        self.assertEqual(hold.active_deck, 1)
        self.assertEqual(hold.authority_reason, "hold_current")

        use_master = _stable(
            current=0,
            master=2,
            deck={
                1: _deck(playing=True, fader="top", low="high", low_norm=0.7),
                2: _deck(playing=True, fader="top", low="high", low_norm=0.705),
            },
        )
        self.assertEqual(use_master.active_deck, 2)

    def test_neither_top_holds_current_else_master_or_idle(self):
        hold = _resolve(
            current=1,
            master=2,
            deck={
                1: _deck(playing=True, fader="audible"),
                2: _deck(playing=True, fader="audible"),
            },
        )
        self.assertEqual(hold.active_deck, 1)

        idle = _resolve(
            current=0,
            master=None,
            master_valid=False,
            deck={
                1: _deck(playing=True, fader="audible"),
                2: _deck(playing=True, fader="audible"),
            },
        )
        self.assertEqual(idle.active_deck, 0)
        self.assertEqual(idle.fallback_reason, "rb_master_unavailable_tie")

    def test_invalid_mixer_fallback_never_defaults_to_deck1(self):
        result = _resolve(
            current=0,
            master=None,
            master_valid=False,
            mixer_valid=False,
            mixer_updated_at=100.0,
            deck={
                1: _deck(playing=True, fader="top"),
                2: _deck(playing=False, fader="down"),
            },
        )
        self.assertEqual(result.active_deck, 0)
        self.assertEqual(result.authority_reason, "mixer_invalid_fallback")

    def test_invalid_to_valid_recovery_returns_to_fader_dominance(self):
        result = _stable(
            current=1,
            master=1,
            deck={
                1: _deck(playing=True, fader="top", low="low", low_norm=0.2),
                2: _deck(playing=True, fader="top", low="high", low_norm=0.9),
            },
        )
        self.assertEqual(result.active_deck, 2)
        self.assertEqual(result.authority_reason, "bass_dominance")

    def test_stale_mixer_uses_visible_fallback(self):
        result = _stable(
            current=1,
            master=2,
            mixer_valid=True,
            mixer_updated_at=90.0,
            deck={
                1: _deck(playing=True, fader="top"),
                2: _deck(playing=True, fader="top"),
            },
        )
        self.assertEqual(result.active_deck, 2)
        self.assertEqual(result.authority_reason, "mixer_invalid_fallback")
        self.assertEqual(result.fallback_reason, "stale")


if __name__ == "__main__":
    unittest.main()
