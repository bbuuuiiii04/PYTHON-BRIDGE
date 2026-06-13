import queue
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.laser_models import LaserPersonality  # noqa: E402
from rb_ss_bridge_v2.models import Ev  # noqa: E402
from rb_ss_bridge_v2.personality_resolver import (  # noqa: E402
    PersonalityResolution,
    PersonalityResolver,
)
from rb_ss_bridge_v2.rb_memory import PositionCache  # noqa: E402
from rb_ss_bridge_v2.state_manager import StateManager  # noqa: E402


def _personality(name: str = "dubstep") -> LaserPersonality:
    return LaserPersonality(
        name=name,
        safe_scene="safe_static",
        default_scene="default",
        phrase_scene="phrase",
        buildup_scene="buildup",
        pre_drop_scene="pre",
        drop_scene="drop",
        post_drop_scene="post",
        breakdown_scene="breakdown",
        transition_scene="transition",
    )


def _payload(*, ssid: str = "", content_id: str = "123", bpm: float = 145.0) -> dict:
    return {
        "filepath": "/music/test.mp3",
        "bpm": bpm,
        "content_id": content_id,
        "first_beat_ms": 0.0,
        "beatgrid_times_ms": [],
        "beatgrid_bpms": [],
        "beatgrid_source": "",
        "soundswitch_id": ssid,
        "total_ms": 180000.0,
        "load_gen": 0,
    }


class _Resolver:
    def resolve(self, *, playlists, bpm):  # type: ignore[no-untyped-def]
        return PersonalityResolution(
            name="dubstep",
            reason="playlist_match",
            matched="dubstep",
        )


class _RecordingResolver:
    def __init__(self) -> None:
        self.playlists = None

    def resolve(self, *, playlists, bpm):  # type: ignore[no-untyped-def]
        self.playlists = playlists
        return PersonalityResolution(
            name="dubstep",
            reason="default",
            matched="",
        )


class _Cache:
    def __init__(self) -> None:
        self.refresh_count = 0

    def get(self, content_id: str):  # type: ignore[no-untyped-def]
        return frozenset({"Dubstep"})

    def refresh(self) -> int:
        self.refresh_count += 1
        return 1


class _MissCache:
    def __init__(self) -> None:
        self.get_count = 0
        self.refresh_count = 0

    def get(self, content_id: str):  # type: ignore[no-untyped-def]
        self.get_count += 1
        return None

    def refresh(self) -> int:
        self.refresh_count += 1
        return 0


class _LoadedNegativeCache:
    def __init__(self) -> None:
        self.refresh_count = 0

    def get(self, content_id: str):  # type: ignore[no-untyped-def]
        return frozenset()

    def refresh(self) -> int:
        self.refresh_count += 1
        return 0


def _make_sm(director: MagicMock, *, provider=None) -> StateManager:
    if provider is None:
        provider = lambda name: _personality(name)
    return StateManager(
        queue.Queue(maxsize=256),
        PositionCache(),
        MagicMock(),
        laser_director=director,
        laser_personality_provider=provider,
    )


class StateManagerPersonalityTests(unittest.TestCase):
    def test_scripted_match_does_not_queue_personality(self) -> None:
        director = MagicMock()
        sm = _make_sm(director)
        sm.attach_personality_resolver(_Resolver())  # type: ignore[arg-type]
        sm.attach_personality_playlist_cache(_Cache())  # type: ignore[arg-type]

        with patch.dict(
            "rb_ss_bridge_v2.state_manager.SCRIPTED_TRACKS",
            {999: {"ssid": "scripted-ssid"}},
            clear=False,
        ):
            sm._on_filepath_resolved(1, _payload(ssid="scripted-ssid"))

        director.queue_personality_change.assert_not_called()
        self.assertFalse(sm._personality_eligible_deck[1])

    def test_unscripted_clear_queues_personality_for_active_deck(self) -> None:
        director = MagicMock()
        sm = _make_sm(director)
        sm.attach_personality_resolver(_Resolver())  # type: ignore[arg-type]
        sm.attach_personality_playlist_cache(_Cache())  # type: ignore[arg-type]
        sm._os.active_deck = 1

        sm._on_filepath_resolved(1, _payload(ssid=""))

        director.queue_personality_change.assert_called_once()
        name, cfg = director.queue_personality_change.call_args.args
        self.assertEqual(name, "dubstep")
        self.assertEqual(cfg.name, "dubstep")
        self.assertTrue(sm._personality_eligible_deck[1])

    def test_master_change_reresolves_eligible_loaded_deck(self) -> None:
        director = MagicMock()
        sm = _make_sm(director)
        sm.attach_personality_resolver(_Resolver())  # type: ignore[arg-type]
        sm.attach_personality_playlist_cache(_Cache())  # type: ignore[arg-type]
        sm._os.active_deck = 1
        sm._deck[2].meta.content_id = "222"
        sm._deck[2].meta.filepath = "/music/next.mp3"
        sm._deck[2].meta.bpm = 145.0
        sm._personality_eligible_deck[2] = True

        sm._on_master_changed(2, "test")

        director.queue_personality_change.assert_called_once()

    def test_empty_content_id_skips_playlist_cache_refresh(self) -> None:
        director = MagicMock()
        sm = _make_sm(director)
        resolver = _RecordingResolver()
        cache = _MissCache()
        sm.attach_personality_resolver(resolver)  # type: ignore[arg-type]
        sm.attach_personality_playlist_cache(cache)  # type: ignore[arg-type]
        sm._os.active_deck = 1

        sm._on_filepath_resolved(1, _payload(content_id=""))

        self.assertEqual(cache.get_count, 0)
        self.assertEqual(cache.refresh_count, 0)
        self.assertEqual(resolver.playlists, frozenset())

    def test_known_negative_playlist_membership_does_not_refresh(self) -> None:
        director = MagicMock()
        sm = _make_sm(director)
        resolver = _RecordingResolver()
        cache = _LoadedNegativeCache()
        sm.attach_personality_resolver(resolver)  # type: ignore[arg-type]
        sm.attach_personality_playlist_cache(cache)  # type: ignore[arg-type]
        sm._os.active_deck = 1

        sm._on_filepath_resolved(1, _payload(content_id="missing"))

        self.assertEqual(cache.refresh_count, 0)
        self.assertEqual(resolver.playlists, frozenset())

    def test_resolve_personality_recaches_timing_before_boundary_apply(self) -> None:
        director = MagicMock()
        house = LaserPersonality(
            name="house",
            safe_scene="safe_static",
            default_scene="d",
            phrase_scene="p",
            buildup_scene="up",
            pre_drop_scene="pre",
            drop_scene="drop",
            post_drop_scene="post",
            breakdown_scene="bd",
            transition_scene="t",
            pre_drop_blackout_beats=6,
            post_drop_hold_beats=16,
            breakdown_default_restore_beats=48,
            buildup_lookahead_beats=40,
        )
        sm = _make_sm(director, provider=lambda _name: house)
        sm.attach_personality_resolver(_Resolver())  # type: ignore[arg-type]
        sm.attach_personality_playlist_cache(_Cache())  # type: ignore[arg-type]
        sm._os.active_deck = 1
        sm._sp_post_drop = 8.0
        sm._sp_drop_window = 4.0
        sm._sp_breakdown_default_restore = 16

        sm._on_filepath_resolved(1, _payload(ssid=""))

        director.queue_personality_change.assert_called_once()
        director.set_personality_config.assert_not_called()
        self.assertEqual(sm._sp_post_drop, 16.0)
        self.assertEqual(sm._sp_drop_window, 6.0)
        self.assertEqual(sm._sp_transition_window, 6.0)
        self.assertEqual(sm._sp_breakdown_default_restore, 48)
        self.assertEqual(sm._sp_phrase_lookahead, 40.0)
        self.assertIs(sm._active_personality_for_timing, house)

    def test_apply_personality_change_updates_director_executor_and_timing_cache(self) -> None:
        director = MagicMock()
        executor = MagicMock()
        sm = _make_sm(director)
        sm._laser_executor = executor

        personality = LaserPersonality(
            name="hard_techno",
            safe_scene="safe_static",
            default_scene="d",
            phrase_scene="p",
            buildup_scene="up",
            pre_drop_scene="pre",
            drop_scene="drop",
            post_drop_scene="post",
            breakdown_scene="bd",
            transition_scene="t",
            pre_drop_blackout_beats=8,
            post_drop_hold_beats=4,
            breakdown_default_restore_beats=32,
        )

        sm._apply_personality_change("hard_techno", personality)

        director.set_personality.assert_called_once_with("hard_techno")
        director.set_personality_config.assert_called_once_with(personality)
        executor.set_personality.assert_called_once_with(personality)
        self.assertEqual(sm._sp_drop_window, 8.0)
        self.assertEqual(sm._sp_transition_window, 8.0)
        self.assertEqual(sm._sp_post_drop, 4.0)
        self.assertEqual(sm._sp_breakdown_default_restore, 32)


if __name__ == "__main__":
    unittest.main()
