import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.personality_resolver import PersonalityResolver  # noqa: E402


def _resolver() -> PersonalityResolver:
    return PersonalityResolver(
        alias_index={
            "house": "house",
            "tech house": "tech_house",
            "bass house": "bass_house",
            "bass": "dubstep",
            "dubstep": "dubstep",
            "hard techno": "hard_techno",
            "trap": "trap",
        },
        bpm_priority=(
            "hard_techno",
            "dubstep",
            "trap",
            "bass_house",
            "tech_house",
            "house",
        ),
        bpm_bands={
            "house": (120.0, 130.0),
            "tech_house": (125.0, 138.0),
            "bass_house": (126.0, 140.0),
            "trap": (134.0, 155.0),
            "dubstep": (140.0, 155.0),
            "hard_techno": (140.0, 160.0),
        },
        known_personalities={
            "house",
            "tech_house",
            "bass_house",
            "trap",
            "dubstep",
            "hard_techno",
        },
        default="house",
    )


class PersonalityResolverTests(unittest.TestCase):
    def test_playlist_alias_wins_over_bpm(self) -> None:
        result = _resolver().resolve(playlists=frozenset({"Trap Crates"}), bpm=128.0)
        self.assertEqual(result.name, "trap")
        self.assertEqual(result.reason, "playlist_match")
        self.assertEqual(result.matched, "trap")

    def test_longest_alias_wins(self) -> None:
        result = _resolver().resolve(
            playlists=frozenset({"Bass House Selects"}),
            bpm=145.0,
        )
        self.assertEqual(result.name, "bass_house")
        self.assertEqual(result.matched, "bass house")

    def test_word_boundary_prevents_substring_match(self) -> None:
        result = _resolver().resolve(playlists=frozenset({"warehouse"}), bpm=118.0)
        self.assertEqual(result.name, "house")
        self.assertEqual(result.reason, "default")

    def test_bpm_priority_first_match_wins(self) -> None:
        result = _resolver().resolve(playlists=frozenset(), bpm=145.0)
        self.assertEqual(result.name, "hard_techno")
        self.assertEqual(result.reason, "bpm_range_match")
        self.assertEqual(result.matched, "140-160")

    def test_bpm_band_max_is_exclusive(self) -> None:
        result = _resolver().resolve(playlists=frozenset(), bpm=140.0)
        self.assertEqual(result.name, "hard_techno")

    def test_default_when_no_playlist_or_bpm_match(self) -> None:
        result = _resolver().resolve(playlists=frozenset(), bpm=118.0)
        self.assertEqual(result.name, "house")
        self.assertEqual(result.reason, "default")

    def test_bpm_priority_absent_personality_is_not_eligible(self) -> None:
        resolver = PersonalityResolver(
            alias_index={},
            bpm_priority=("house",),
            bpm_bands={"house": (120.0, 130.0), "trap": (90.0, 100.0)},
            known_personalities={"house", "trap"},
            default="house",
        )
        result = resolver.resolve(playlists=frozenset(), bpm=95.0)
        self.assertEqual(result.name, "house")
        self.assertEqual(result.reason, "default")

    def test_empty_default_returns_empty_name(self) -> None:
        resolver = PersonalityResolver(
            alias_index={}, bpm_priority=(), bpm_bands={},
            known_personalities=set(), default="",
        )
        result = resolver.resolve(playlists=frozenset(), bpm=0.0)
        self.assertEqual(result.name, "")
        self.assertEqual(result.reason, "default")

    def test_default_not_in_known_personalities_returns_empty(self) -> None:
        resolver = PersonalityResolver(
            alias_index={}, bpm_priority=(), bpm_bands={},
            known_personalities={"house"}, default="techno",
        )
        result = resolver.resolve(playlists=frozenset(), bpm=0.0)
        self.assertEqual(result.name, "")

    def test_bpm_zero_skips_bpm_path(self) -> None:
        result = _resolver().resolve(playlists=frozenset(), bpm=0.0)
        self.assertEqual(result.reason, "default")

    def test_empty_bpm_priority_skips_bpm_even_with_bands(self) -> None:
        resolver = PersonalityResolver(
            alias_index={},
            bpm_priority=(),
            bpm_bands={"house": (120.0, 130.0)},
            known_personalities={"house"},
            default="house",
        )
        result = resolver.resolve(playlists=frozenset(), bpm=125.0)
        self.assertEqual(result.reason, "default")

    def test_alias_canonicalizes_multiple_internal_whitespace(self) -> None:
        resolver = PersonalityResolver(
            alias_index={"bass    house": "bass_house"},
            bpm_priority=(), bpm_bands={},
            known_personalities={"bass_house"},
            default="bass_house",
        )
        result = resolver.resolve(
            playlists=frozenset({"Bass   House  Selects"}), bpm=0.0,
        )
        self.assertEqual(result.name, "bass_house")
        self.assertEqual(result.matched, "bass house")

    def test_alias_canonicalization_is_case_insensitive(self) -> None:
        result = _resolver().resolve(
            playlists=frozenset({"DUBSTEP DESTROYERS"}), bpm=0.0,
        )
        self.assertEqual(result.name, "dubstep")

    def test_get_empty_content_id_returns_known_miss(self) -> None:
        from rb_ss_bridge_v2.personality_resolver import PlaylistCache
        cache = PlaylistCache(Path("/tmp/nonexistent.db"))
        self.assertEqual(cache.get(""), frozenset())
        self.assertIsNone(cache.get("missing"))

    def test_playlist_cache_reads_content_id_from_current_pyrekordbox_rows(self) -> None:
        from rb_ss_bridge_v2.personality_resolver import PlaylistCache

        class Db:
            def get_playlist_contents(self, playlist_id):  # type: ignore[no-untyped-def]
                self.playlist_id = playlist_id
                return (SimpleNamespace(ID="track-1"),)

        cache = PlaylistCache(Path("/tmp/nonexistent.db"))

        self.assertEqual(
            cache._iter_playlist_content_ids(Db(), "playlist-1"),
            (("track-1",), 0),
        )

    def test_playlist_cache_counts_rows_without_recognized_id(self) -> None:
        from rb_ss_bridge_v2.personality_resolver import PlaylistCache

        class Db:
            def get_playlist_contents(self, playlist_id):  # type: ignore[no-untyped-def]
                return (
                    SimpleNamespace(ID="track-1"),
                    SimpleNamespace(Other="x"),
                    SimpleNamespace(),
                )

        cache = PlaylistCache(Path("/tmp/nonexistent.db"))
        ids, skipped = cache._iter_playlist_content_ids(Db(), "playlist-1")

        self.assertEqual(ids, ("track-1",))
        self.assertEqual(skipped, 2)

    def test_playlist_cache_returns_empty_set_for_known_negative_after_refresh(self) -> None:
        from rb_ss_bridge_v2.personality_resolver import PlaylistCache

        class FakeDb:
            def __init__(self, _path: str, *, unlock: bool) -> None:
                self.unlock = unlock

            def get_playlist(self):  # type: ignore[no-untyped-def]
                return (
                    SimpleNamespace(ID="folder-1", Name="PER GENRE", ParentID=""),
                    SimpleNamespace(ID="playlist-1", Name="Dubstep", ParentID="folder-1"),
                )

            def get_playlist_contents(self, playlist_id):  # type: ignore[no-untyped-def]
                self.playlist_id = playlist_id
                return (SimpleNamespace(ID="track-1"),)

            def close(self) -> None:
                pass

        pyrekordbox = ModuleType("pyrekordbox")
        db6 = ModuleType("pyrekordbox.db6")
        db6.Rekordbox6Database = FakeDb  # type: ignore[attr-defined]
        cache = PlaylistCache(Path("/tmp/fake.db"))

        self.assertIsNone(cache.get("missing"))
        with patch.dict(sys.modules, {"pyrekordbox": pyrekordbox, "pyrekordbox.db6": db6}):
            self.assertEqual(cache.refresh(), 1)

        self.assertEqual(cache.get("track-1"), frozenset({"Dubstep"}))
        self.assertEqual(cache.get("missing"), frozenset())


if __name__ == "__main__":
    unittest.main()
