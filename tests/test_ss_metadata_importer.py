import logging
import plistlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.ss_metadata_importer import (
    SS_PROJECT_DIR_ENV,
    build_catalog,
    check_ss_plist,
    discover_project_dir,
    parse_autoloops_bin,
    parse_venues_bin,
)


def _write_utf16_strings(path, strings, *, odd_offset=False):
    payload = "\x00".join(strings).encode("utf-16-le")
    if odd_offset:
        payload = b"\xaa" + payload
    path.write_bytes(payload)


def test_discover_project_dir_respects_env(monkeypatch, tmp_path):
    monkeypatch.setenv(SS_PROJECT_DIR_ENV, str(tmp_path))

    assert discover_project_dir() == tmp_path


def test_parse_autoloops_bin_extracts_bank_pairs(tmp_path):
    path = tmp_path / "SoundSwitchAutoLoops.bin"
    _write_utf16_strings(
        path,
        [
            "BREAKDOWN",
            "GROOVE // MID ENERGY",
            "BUILDUP // RISING",
            "DROP // HIGH ENERGY",
            "RED  // AG1",
            "RAINBOW  // AG",
            "BLACKOUT",
            "LAGGY 1/4 W ",
            "WHITE  // AG1",
            "RAINBOW LAGGY",
            "GREEN  // AG",
            "New Autoloop",
            "CYAN // AG1",
            "PURPLE // AG1",
            "GREEN  // AG1",
            "BLUE // AG1",
        ],
    )

    pairs = parse_autoloops_bin(path)

    assert pairs[:3] == [
        ("BREAKDOWN", "RED  // AG1"),
        ("BREAKDOWN", "RAINBOW  // AG"),
        ("BREAKDOWN", "BLACKOUT"),
    ]
    assert pairs[-1] == ("DROP // HIGH ENERGY", "BLUE // AG1")


def test_parse_venues_bin_uses_odd_offset_and_bank_headers(tmp_path):
    path = tmp_path / "SoundSwitchVenues.bin"
    _write_utf16_strings(
        path,
        [
            "Fixture Parameter",
            "INTRO",
            "STROBE EFFECT",
            "STATIC LASERS",
            "BLACK OUT",
            "FOUNDATION - GROOVE 128 bpm",
            "FKDASPKR (cutout)",
            "TRACK SPECIFIC CUES",
            "RAINBOW STROBE",
        ],
        odd_offset=True,
    )

    pairs = parse_venues_bin(path)

    assert ("INTRO", "STROBE EFFECT") in pairs
    assert ("STATIC LASERS", "BLACK OUT") in pairs
    assert ("FOUNDATION - GROOVE 128 bpm", "FOUNDATION - GROOVE 128 bpm") in pairs
    assert ("FOUNDATION - GROOVE 128 bpm", "FKDASPKR (cutout)") in pairs
    assert all(name != "Fixture Parameter" for _, name in pairs)


def test_build_catalog_dedupes_by_source_file_and_name(tmp_path):
    _write_utf16_strings(
        tmp_path / "SoundSwitchAutoLoops.bin",
        [
            "BREAKDOWN",
            "GROOVE // MID ENERGY",
            "BUILDUP // RISING",
            "DROP // HIGH ENERGY",
            "NEON",
            "NEON",
            "BLACKOUT",
            "BLUE // AG1",
        ],
    )
    _write_utf16_strings(
        tmp_path / "SoundSwitchAutoLoopsEx.bin",
        [
            "BREAKDOWN",
            "GROOVE // MID ENERGY",
            "BUILDUP // RISING",
            "DROP // HIGH ENERGY",
            "NEON",
            "BLUE FANNING",
            "CONVERGING",
            "CYAN STATIC",
        ],
    )
    _write_utf16_strings(
        tmp_path / "SoundSwitchVenues.bin",
        [
            "STATIC LASERS",
            "NEON",
            "BLUE FANNING",
            "BLACK OUT",
        ],
        odd_offset=True,
    )

    catalog = build_catalog(tmp_path)
    neon_sources = sorted(
        record.source_file
        for record in catalog.records
        if record.name == "NEON"
    )

    assert neon_sources == [
        "SoundSwitchAutoLoops.bin",
        "SoundSwitchAutoLoopsEx.bin",
        "SoundSwitchVenues.bin",
    ]
    assert any(record.name == "BLUE FANNING" for record in catalog.records)
    assert any(record.name == "BLACK OUT" for record in catalog.records)


def test_build_catalog_returns_empty_on_parse_failure(tmp_path, caplog):
    caplog.set_level(logging.WARNING, logger="ss_metadata_importer")

    catalog = build_catalog(tmp_path)

    assert catalog.records == ()
    assert "[SS-CATALOG] parse-fail" in caplog.text


def test_check_ss_plist_logs_known_keys(tmp_path, caplog):
    path = tmp_path / "com.soundswitch.SoundSwitch.plist"
    with path.open("wb") as fh:
        plistlib.dump(
            {
                "randomiseAutoLoops": True,
                "autoloopRepeatMode": 2,
                "overrideScriptedTracks": False,
            },
            fh,
        )
    caplog.set_level(logging.INFO, logger="ss_metadata_importer")

    values = check_ss_plist(path)

    assert values == {
        "randomiseAutoLoops": True,
        "autoloopRepeatMode": 2,
        "overrideScriptedTracks": False,
    }
    assert "[SS-PLIST] randomiseAutoLoops=true" in caplog.text
