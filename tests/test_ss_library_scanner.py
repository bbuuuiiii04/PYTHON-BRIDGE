import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.filepath_resolver import (
    _SS_SCRIPTED_ID_CACHE,
    _SS_PRELOAD_CACHE,
    has_soundswitch_scripted_id,
    _read_soundswitch_id,
    seed_soundswitch_id_cache,
    seed_soundswitch_scripted_id_cache,
)
from rb_ss_bridge_v2.ss_library_scanner import (
    _scan_worker,
    parse_project_scripted_ids,
    parse_trackmap_filepaths,
)


def test_parse_trackmap_filepaths_extracts_unique_utf16_audio_paths(tmp_path):
    path = tmp_path / "SoundSwitchTrackMap.bin"
    text = (
        "noise "
        "/Users/bbui/Music/A.mp3\0"
        "/Users/bbui/Music/A.mp3\0"
        "/Users/bbui/Music/folder/B Track.wav\0"
        "/Users/bbui/Music/ignore.txt\0"
    )
    path.write_bytes(text.encode("utf-16-le"))

    assert sorted(parse_trackmap_filepaths(str(path))) == [
        "/Users/bbui/Music/A.mp3",
        "/Users/bbui/Music/folder/B Track.wav",
    ]


def test_read_soundswitch_id_uses_preload_cache():
    _SS_PRELOAD_CACHE.clear()
    seed_soundswitch_id_cache({"/tmp/scripted.mp3": "ssid-123"})

    try:
        assert _read_soundswitch_id("/tmp/scripted.mp3") == "ssid-123"
    finally:
        _SS_PRELOAD_CACHE.clear()


def test_seed_soundswitch_scripted_id_cache_normalizes_ids():
    _SS_SCRIPTED_ID_CACHE.clear()
    seed_soundswitch_scripted_id_cache(["first", "{SECOND}"])

    try:
        assert has_soundswitch_scripted_id("{FIRST}")
        assert has_soundswitch_scripted_id("second")
        assert not has_soundswitch_scripted_id("{THIRD}")
    finally:
        _SS_SCRIPTED_ID_CACHE.clear()


def test_read_soundswitch_id_uses_generic_mutagen_tag(monkeypatch):
    class FakeAudio:
        tags = {"soundswitch_id": ["ssid-flac"]}

    monkeypatch.setattr(
        "mutagen.File",
        lambda filepath: FakeAudio(),
    )

    assert _read_soundswitch_id("/tmp/scripted.flac") == "ssid-flac"


def test_parse_project_scripted_ids_reads_uuid_ssfiles_only(tmp_path):
    (tmp_path / "{528E8B22-BD17-41B9-A111-275D3E8B3031}.ssfile").touch()
    (tmp_path / "SSAutoLoop1.ssfile").touch()
    (tmp_path / "not-a-show.ssfile").touch()

    assert parse_project_scripted_ids(str(tmp_path)) == [
        "{528E8B22-BD17-41B9-A111-275D3E8B3031}",
    ]


def test_scan_worker_reports_all_tagged_files(tmp_path, monkeypatch):
    monkeypatch.setenv("RBSS_SS_SCAN_ROOTS", "0")
    first = tmp_path / "first.wav"
    second = tmp_path / "second.wav"
    first.touch()
    second.touch()
    trackmap = tmp_path / "SoundSwitchTrackMap.bin"
    trackmap.write_bytes(
        f"{first}\0{second}\0".encode("utf-16-le")
    )
    ids = {
        str(first): "{FIRST}",
        str(second): "{SECOND}",
    }
    captured = {}

    monkeypatch.setattr("rb_ss_bridge_v2.filepath_resolver._read_soundswitch_id", ids.get)

    _scan_worker(str(trackmap), captured.update)

    assert captured == {
        str(first): "{FIRST}",
        str(second): "{SECOND}",
    }


def test_scan_worker_seeds_scripted_id_cache_from_project(tmp_path, monkeypatch):
    monkeypatch.setenv("RBSS_SS_SCAN_ROOTS", "0")
    first = tmp_path / "first.wav"
    ssid = "{528E8B22-BD17-41B9-A111-275D3E8B3031}"
    first.touch()
    (tmp_path / f"{ssid}.ssfile").touch()
    trackmap = tmp_path / "SoundSwitchTrackMap.bin"
    trackmap.write_bytes(f"{first}\0".encode("utf-16-le"))
    captured = {}
    scripted_ids = []

    monkeypatch.setattr(
        "rb_ss_bridge_v2.filepath_resolver._read_soundswitch_id",
        lambda filepath: ssid,
    )

    _scan_worker(str(trackmap), captured.update, scripted_ids.extend)

    assert captured == {str(first): ssid}
    assert scripted_ids == [ssid]


def test_scan_worker_excludes_env_false_scripted_ids(tmp_path, monkeypatch):
    monkeypatch.setenv("RBSS_SS_SCAN_ROOTS", "0")
    denied = "{528E8B22-BD17-41B9-A111-275D3E8B3031}"
    audio = tmp_path / "false.wav"
    audio.touch()
    (tmp_path / f"{denied}.ssfile").touch()
    trackmap = tmp_path / "SoundSwitchTrackMap.bin"
    trackmap.write_bytes(f"{audio}\0".encode("utf-16-le"))
    captured = {}
    scripted_ids = []

    monkeypatch.setenv("RBSS_SS_SCRIPTED_DENYLIST", denied)
    monkeypatch.setattr(
        "rb_ss_bridge_v2.filepath_resolver._read_soundswitch_id",
        lambda filepath: denied,
    )

    _scan_worker(str(trackmap), captured.update, scripted_ids.extend)

    assert captured == {str(audio): denied}
    assert scripted_ids == []


def test_scan_worker_adds_scripted_files_missing_from_trackmap(tmp_path, monkeypatch):
    ssid = "{528E8B22-BD17-41B9-A111-275D3E8B3031}"
    in_trackmap = tmp_path / "known.wav"
    extra_root = tmp_path / "library"
    extra = extra_root / "missing.mp3"
    in_trackmap.touch()
    extra_root.mkdir()
    extra.touch()
    (tmp_path / f"{ssid}.ssfile").touch()
    trackmap = tmp_path / "SoundSwitchTrackMap.bin"
    trackmap.write_bytes(f"{in_trackmap}\0".encode("utf-16-le"))
    captured = {}

    monkeypatch.setenv("RBSS_SS_SCAN_ROOTS", str(extra_root))
    monkeypatch.setattr(
        "rb_ss_bridge_v2.filepath_resolver._read_soundswitch_id",
        lambda filepath: ssid,
    )

    _scan_worker(str(trackmap), captured.update)

    assert captured == {
        str(in_trackmap): ssid,
        str(extra): ssid,
    }
