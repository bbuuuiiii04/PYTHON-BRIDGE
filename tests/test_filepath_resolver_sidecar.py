from __future__ import annotations

import json
import sys
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import filepath_resolver as resolver  # noqa: E402
from rb_ss_bridge_v2 import state_manager  # noqa: E402


def _record() -> dict:
    return {
        "content_id": "42",
        "title": "Twin Track",
        "artist": "Twin Artist",
        "duration_s": 200.0,
        "bpm": 128.0,
        "beatgrid_fingerprint": "0123456789abcdef",
        "anlz_relpaths": ["anlz/42/ANLZ0000.DAT", "anlz/42/ANLZ0000.EXT"],
        "v4_relpath": "v4/42.json",
        "soundswitch_id": "{SSID}",
        "laser_tag_beats": [4.0, 68.0],
        "source_filepath": "/home/music/twin.wav",
    }


def _write_index(mount: Path, *, schema: int = 1, record: dict | None = None) -> Path:
    path = mount / "RBSS BRIDGE USB" / "lighting_sidecar" / "index.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": schema,
        "track_count": 1,
        "tracks": [record if record is not None else _record()],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class SidecarReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        resolver._SIDECAR_CACHE = {}
        resolver._SIDECAR_ONLY_LOGGED = False

    def tearDown(self) -> None:
        resolver._SIDECAR_CACHE = {}
        resolver._SIDECAR_ONLY_LOGGED = False

    def test_schema_one_loads_and_unknown_schema_fails_closed(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            valid = _write_index(root / "valid")
            loaded = resolver._load_sidecar_index(valid)
            self.assertEqual(loaded[0], valid.parent)
            self.assertEqual(loaded[1][0]["content_id"], "42")

            unsupported = _write_index(root / "unsupported", schema=2)
            with self.assertLogs("filepath_resolver", level="INFO") as logs:
                self.assertIsNone(resolver._load_sidecar_index(unsupported))
            self.assertTrue(any("sidecar-schema-unsupported" in line for line in logs.output))

    def test_discovers_his_sidecar_beside_guest_stick_and_drops_it_when_unplugged(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            guest = root / "A-GUEST"
            guest.mkdir()
            his = root / "MINK"
            index = _write_index(his)

            loaded = resolver._discover_sidecar_index([guest, his])
            self.assertEqual(loaded[0], his / "RBSS BRIDGE USB" / "lighting_sidecar")

            index.unlink()
            self.assertIsNone(resolver._discover_sidecar_index([guest, his]))

    def test_rebuild_reloads_changed_index_and_new_mount_is_discovered(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "FIRST"
            _write_index(first)
            loaded = resolver._discover_sidecar_indexes([first])
            self.assertEqual(loaded[0][1][0]["title"], "Twin Track")

            rebuilt = _record()
            rebuilt["title"] = "Twin Track Rebuilt With Fresh Phrase Memory"
            _write_index(first, record=rebuilt)
            loaded = resolver._discover_sidecar_indexes([first])
            self.assertEqual(loaded[0][1][0]["title"], rebuilt["title"])

            second = root / "SECOND"
            _write_index(second)
            loaded = resolver._discover_sidecar_indexes([second, first])
            self.assertEqual(
                [entry[0] for entry in loaded],
                [
                    first / "RBSS BRIDGE USB" / "lighting_sidecar",
                    second / "RBSS BRIDGE USB" / "lighting_sidecar",
                ],
            )

    def test_replug_at_a_new_mount_and_installed_candidate_are_discovered(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root / "OLD"
            old_index = _write_index(old)
            self.assertIsNotNone(resolver._discover_sidecar_index([old]))
            old_index.unlink()

            new = root / "NEW"
            _write_index(new)
            loaded = resolver._discover_sidecar_indexes([old, new])
            self.assertEqual(
                [entry[0] for entry in loaded],
                [new / "RBSS BRIDGE USB" / "lighting_sidecar"],
            )

            source = _write_index(root / "SOURCE")
            installed = root / "Application Support" / "RBSS Bridge" / "lighting_sidecar" / "index.json"
            installed.parent.mkdir(parents=True)
            installed.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            with patch.object(resolver, "_INSTALLED_SIDECAR_INDEX", installed):
                loaded = resolver._discover_sidecar_indexes([])
            self.assertEqual([entry[0] for entry in loaded], [installed.parent])

    def test_missing_and_path_escape_are_silent_misses(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertIsNone(resolver._discover_sidecar_index([root / "missing"]))
            path = _write_index(root / "bad")
            payload = json.loads(path.read_text())
            payload["tracks"][0]["anlz_relpaths"] = ["../../outside.DAT"]
            path.write_text(json.dumps(payload))
            self.assertIsNone(resolver._load_sidecar_index(path))


class DeviceAudioFilepathTests(unittest.TestCase):
    def _device_path(self, anlz_path: str, parsed_path: str) -> str:
        anlz = types.ModuleType("pyrekordbox.anlz")
        anlz.AnlzFile = type(
            "AnlzFile", (), {"parse_file": staticmethod(lambda _path: {"path": parsed_path})}
        )
        package = types.ModuleType("pyrekordbox")
        package.__path__ = []
        with patch.dict(sys.modules, {"pyrekordbox": package, "pyrekordbox.anlz": anlz}):
            return resolver._device_audio_filepath(anlz_path)

    def test_device_audio_path_stays_inside_anlz_usb_mount(self) -> None:
        with TemporaryDirectory() as tmp:
            volumes = Path(tmp)
            mount = volumes / "TEST_STICK"
            (mount / "PIONEER" / "ANLZ").mkdir(parents=True)
            with patch.object(resolver, "_VOLUMES_ROOT", volumes):
                path = self._device_path(
                    str(mount / "PIONEER" / "ANLZ" / "ANLZ0000.DAT").replace("/", "\\"),
                    "MUSIC\\Folder\\song.wav",
                )
            self.assertEqual(path, str((mount / "MUSIC" / "Folder" / "song.wav").resolve()))

    def test_device_audio_path_rejects_escapes_and_outside_symlink(self) -> None:
        with TemporaryDirectory() as tmp:
            volumes = Path(tmp)
            mount = volumes / "TEST_STICK"
            (mount / "PIONEER" / "ANLZ").mkdir(parents=True)
            outside = volumes / "outside"
            outside.mkdir()
            (mount / "MUSIC").mkdir()
            (mount / "MUSIC" / "escape").symlink_to(outside, target_is_directory=True)
            anlz_path = str(mount / "PIONEER" / "ANLZ" / "ANLZ0000.DAT")
            with patch.object(resolver, "_VOLUMES_ROOT", volumes):
                for parsed_path in ("../outside.wav", "/tmp/outside.wav", "C:/outside.wav", "MUSIC/escape/song.wav"):
                    with self.subTest(parsed_path=parsed_path):
                        self.assertEqual(self._device_path(anlz_path, parsed_path), "")


class SidecarResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        resolver._SIDECAR_CACHE = {}
        resolver._SIDECAR_ONLY_LOGGED = False

    def tearDown(self) -> None:
        resolver._SIDECAR_CACHE = {}
        resolver._SIDECAR_ONLY_LOGGED = False

    def test_multiple_roots_try_deterministically_and_deduplicate_identical_records(self) -> None:
        times = [i * 500.0 for i in range(401)]
        grid = {
            "beatgrid_times_ms": times,
            "beatgrid_bpms": [128.0] * len(times),
        }
        match = _record()
        match["beatgrid_fingerprint"] = resolver._beatgrid_fingerprint(times)
        miss = {**match, "content_id": "99", "bpm": 100.0}
        roots = (
            (Path("/a-sidecar"), (miss,)),
            (Path("/b-sidecar"), (match,)),
        )

        with patch.object(resolver, "_mounted_sidecar_indexes", return_value=roots), \
             patch.object(resolver, "_read_device_pdb_track", return_value=None), \
             patch.object(
                 resolver,
                 "_payload_for_sidecar",
                 side_effect=lambda root, _record, _path: {"root": str(root)},
             ):
            self.assertEqual(
                resolver._sidecar_lookup("/Volumes/GUEST/PIONEER/x", grid),
                {"root": "/b-sidecar"},
            )

        installed = Path("/z-installed/lighting_sidecar")
        identical = (
            (Path("/a-mounted/lighting_sidecar"), (match,)),
            (installed, (match,)),
        )
        with patch.object(resolver, "_mounted_sidecar_indexes", return_value=identical), \
             patch.object(resolver, "_INSTALLED_SIDECAR_INDEX", installed / "index.json"), \
             patch.object(resolver, "_read_device_pdb_track", return_value=None), \
             patch.object(
                 resolver,
                 "_payload_for_sidecar",
                 side_effect=lambda root, _record, _path: {"root": str(root)},
             ), \
             self.assertLogs("filepath_resolver", level="INFO") as logs:
            self.assertEqual(
                resolver._sidecar_lookup("/Volumes/GUEST/PIONEER/x", grid),
                {"root": str(installed)},
            )
        self.assertTrue(any("sidecar-root-deduplicated" in line for line in logs.output))

        old_generation = {**match, "source_sig": {"mtime_ns": 1, "size": 10}}
        new_generation = {**match, "source_sig": {"mtime_ns": 2, "size": 10}}
        conflicting = (
            (Path("/a-sidecar"), (old_generation,)),
            (Path("/b-sidecar"), (new_generation,)),
        )
        with patch.object(resolver, "_mounted_sidecar_indexes", return_value=conflicting), \
             patch.object(resolver, "_read_device_pdb_track", return_value=None), \
             patch.object(resolver, "_payload_for_sidecar", return_value={"ok": True}), \
             self.assertLogs("filepath_resolver", level="INFO") as logs:
            self.assertIsNone(resolver._sidecar_lookup("/Volumes/GUEST/PIONEER/x", grid))
        self.assertTrue(any("sidecar-root-ambiguous" in line for line in logs.output))

    def test_cross_analysis_collision_needs_tags(self) -> None:
        base = [i * 500.0 for i in range(401)]
        foreign = [value + 11.0 for value in base]
        true_record = _record()
        true_record["beatgrid_fingerprint"] = resolver._beatgrid_fingerprint(base)
        wrong_record = {**_record(), "content_id": "99", "title": "Rude Boy (Cazes Edit)"}
        wrong_record["beatgrid_fingerprint"] = resolver._beatgrid_fingerprint(
            [value + 15.0 for value in base]
        )
        grid = {
            "beatgrid_times_ms": foreign,
            "beatgrid_bpms": [128.0] * len(foreign),
        }

        selected, reason, _ids = resolver._select_sidecar_record(
            [true_record, wrong_record], grid, None,
        )
        self.assertIsNone(selected)
        self.assertEqual(reason, "usb-crossanalysis-unconfirmed")

        device_track = {
            "title": "Twin Track", "artist": "Twin Artist", "duration_s": 200,
        }
        selected, reason, _ids = resolver._select_sidecar_record(
            [true_record, wrong_record], grid, device_track,
        )
        self.assertIs(selected, true_record)
        self.assertEqual(reason, "sidecar-pdb-match")

        duplicate = {**true_record, "content_id": "43"}
        selected, reason, ids = resolver._select_sidecar_record(
            [true_record, duplicate], grid, device_track,
        )
        self.assertIsNone(selected)
        self.assertEqual(reason, "usb-pdb-ambiguous")
        self.assertEqual(ids, ["42", "43"])

    def test_sidecar_payload_carries_local_anlz_v4_ssid_and_tags(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            dat = root / "anlz/42/ANLZ0000.DAT"
            dat.parent.mkdir(parents=True)
            dat.write_bytes(b"ANLZ")
            v4 = root / "v4/42.json"
            v4.parent.mkdir()
            v4.write_text("{}")
            record = _record()
            record["anlz_relpaths"] = ["anlz/42/ANLZ0000.DAT"]
            sentinel_v4 = object()
            grid = {
                "beatgrid_times_ms": [0.0, 500.0, 1000.0],
                "beatgrid_bpms": [128.0, 128.0, 128.0],
                "beatgrid_source": "sidecar-test",
            }
            with patch.object(resolver, "_device_audio_filepath", return_value="/Volumes/GUEST/song.wav"), \
                 patch.object(resolver, "_extract_beatgrid_from_anlz", return_value=grid), \
                 patch.object(resolver, "_features_v4_from_payload", return_value=sentinel_v4):
                payload = resolver._payload_for_sidecar(root, record, "/Volumes/GUEST/PIONEER/x")

            content = SimpleNamespace(
                ID="42", FolderPath="/home/music/twin.wav", BPM=12800, Length=200,
            )
            with patch.object(resolver, "_read_soundswitch_id", return_value="{SSID}"), \
                 patch.object(resolver, "_fetch_laser_tag_beats", return_value=[4.0, 68.0]), \
                 patch.object(resolver, "_hotcue_marker", return_value="LASER"):
                local_payload = resolver._payload_for_content(Mock(), content, grid)

        self.assertEqual(payload["filepath"], "/Volumes/GUEST/song.wav")
        self.assertEqual(payload["local_anlz_path"], str(dat.resolve()))
        self.assertIs(payload["sidecar_v4"], sentinel_v4)
        self.assertEqual(payload["soundswitch_id"], "{SSID}")
        self.assertEqual(payload["laser_tag_beats"], [4.0, 68.0])
        for key in (
            "bpm", "content_id", "first_beat_ms", "beatgrid_times_ms",
            "beatgrid_bpms", "beatgrid_source", "soundswitch_id", "total_ms",
            "laser_tag_beats",
        ):
            self.assertEqual(payload[key], local_payload[key], key)

    def test_local_uuid_hit_never_consults_sidecar(self) -> None:
        local_id = "938c2a63-a637-4000-8000-000000000001"
        path = f"/share/PIONEER/USBANLZ/967/{local_id}/ANLZ0000.DAT"
        content = SimpleNamespace(
            ID="7", AnalysisDataPath=path, FolderPath="/music/local.wav",
            BPM=12800, Length=200,
        )
        db = Mock()
        db.get_content.return_value = [content]
        db.get_cue.return_value = []
        with patch("pyrekordbox.db6.Rekordbox6Database", return_value=db), \
             patch.object(resolver, "_extract_beatgrid_from_anlz", return_value={
                 "beatgrid_times_ms": [0.0, 500.0],
                 "beatgrid_bpms": [128.0, 128.0],
                 "beatgrid_source": "test",
             }), \
             patch.object(resolver, "_read_soundswitch_id", return_value=""), \
             patch.object(resolver, "_hotcue_marker", return_value="LASER"), \
             patch.object(resolver, "_sidecar_lookup") as sidecar_lookup:
            result = resolver._db_lookup_by_anlz(path)

        self.assertEqual(result["content_id"], "7")
        sidecar_lookup.assert_not_called()

    def test_local_miss_chains_to_sidecar(self) -> None:
        db = Mock()
        db.get_content.return_value = []
        expected = {"content_id": "42"}
        with patch("pyrekordbox.db6.Rekordbox6Database", return_value=db), \
             patch.object(resolver, "_extract_beatgrid_from_anlz", return_value={
                 "beatgrid_times_ms": [0.0, 500.0],
                 "beatgrid_bpms": [12000.0, 12000.0],
                 "beatgrid_source": "test",
             }), \
             patch.object(resolver, "_read_device_pdb_track", return_value=None), \
             patch.object(resolver, "_sidecar_lookup", return_value=expected) as sidecar_lookup:
            result = resolver._db_lookup_by_anlz(
                "/Volumes/GUEST/PIONEER/USBANLZ/P001/00000001/ANLZ0000.DAT"
            )

        self.assertIs(result, expected)
        sidecar_lookup.assert_called_once()

    def test_no_db_enters_sidecar_only_mode_and_logs_once(self) -> None:
        expected = {"content_id": "42"}
        path = "/Volumes/GUEST/PIONEER/USBANLZ/P001/00000001/ANLZ0000.DAT"
        with patch("pyrekordbox.db6.Rekordbox6Database", side_effect=FileNotFoundError), \
             patch.object(resolver, "_extract_beatgrid_from_anlz", return_value={
                 "beatgrid_times_ms": [0.0, 500.0],
                 "beatgrid_bpms": [120.0, 120.0],
                 "beatgrid_source": "test",
             }), \
             patch.object(resolver, "_sidecar_lookup", return_value=expected), \
             self.assertLogs("filepath_resolver", level="INFO") as logs:
            first = resolver._db_lookup_by_anlz(path)
            second = resolver._db_lookup_by_anlz(path)

        self.assertIs(first, expected)
        self.assertIs(second, expected)
        self.assertEqual(
            sum("no local library — sidecar-only mode" in line for line in logs.output),
            1,
        )

    def test_runtime_prefers_payload_v4_over_local_cache(self) -> None:
        sentinel_v4 = object()
        data = SimpleNamespace(
            waveform_context=SimpleNamespace(beatgrid_times_ms=(0.0, 500.0)),
            drop_beat_indices=[], breakdown_beat_indices=[], buildup_beat_indices=[],
            led_identity=None, f2_plan=None, energy_shadow=None,
        )
        with patch.object(state_manager, "read_anlz_drops", return_value=data), \
             patch.object(state_manager.spectral_cache, "get_cached_v4") as cache_read, \
             self.assertLogs("state_manager", level="INFO") as logs:
            result = state_manager._read_runtime_anlz_data(
                "/sidecar/ANLZ0000.DAT",
                audio_filepath="/Volumes/GUEST/song.wav",
                spectral_enabled=True,
                sidecar_v4=sentinel_v4,
            )

        self.assertIs(result, data)
        cache_read.assert_not_called()
        self.assertTrue(any("source=sidecar-v4" in line for line in logs.output))


if __name__ == "__main__":
    unittest.main()
