"""AWR-211 R1 — executed no-mocked-seams sidecar phrase proof.

The AWR-209/211 review flagged that the sidecar's phrase handoff
(`local_anlz_path` → `read_anlz_drops` → real PSSI) was never proven with real
files — every sidecar test mocked `_extract_beatgrid_from_anlz` /
`_features_v4_from_payload` or stubbed `_sidecar_lookup` wholesale. This closes
that gap two ways:

  * a hermetic test (CI-runnable, zero mocks) that builds a REAL sidecar with a
    real PQTZ/.DAT + PSSI/.EXT, loads + validates the real index, selects the
    record via the real exact-fingerprint rule, and parses phrase from the real
    sidecar file through the real runtime worker; and
  * a real-MINK test (skipped without the stick) that drives AWR-210's actual
    880-track sidecar through the FULL real chain — `_sidecar_lookup` →
    `_payload_for_sidecar` (real `_device_audio_filepath`, real ANLZ + v4 reads)
    → `_read_runtime_anlz_data` — and asserts real USB loads resolve to phrase.

Fixture builders are reused from the AWR-207 e2e (real ANLZ via pyrekordbox
construct structs).
"""
from __future__ import annotations

import glob
import json
import os
import queue
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import skipUnless
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import filepath_resolver as R  # noqa: E402
from rb_ss_bridge_v2 import state_manager as SM  # noqa: E402
from rb_ss_bridge_v2.models import Ev  # noqa: E402
from rb_ss_bridge_v2.rb_memory import PositionCache  # noqa: E402
from rb_ss_bridge_v2.filepath_resolver import (  # noqa: E402
    _beatgrid_fingerprint,
    _extract_beatgrid_from_anlz,
)
from rb_ss_bridge_v2.tests.test_awr207_usb_phrase_e2e import (  # noqa: E402
    _anlz_file,
    _pqtz_bytes,
    _pssi_bytes,
    _write,
)

_MINK_SIDECAR = Path("/Volumes/MINK/RBSS BRIDGE USB/lighting_sidecar/index.json")


class _CacheIsolated(unittest.TestCase):
    def setUp(self) -> None:
        R._SIDECAR_CACHE = {}
        R._SIDECAR_ONLY_LOGGED = False

    def tearDown(self) -> None:
        R._SIDECAR_CACHE = {}
        R._SIDECAR_ONLY_LOGGED = False


def _hermetic_sidecar(mount: Path) -> tuple[Path, Path, dict, dict]:
    root = mount / "RBSS BRIDGE USB" / "lighting_sidecar"
    anlz_dir = root / "anlz" / "555"
    dat = anlz_dir / "ANLZ0000.DAT"
    ext = anlz_dir / "ANLZ0000.EXT"
    _write(str(dat), _anlz_file(_pqtz_bytes()))
    _write(str(ext), _anlz_file(_pssi_bytes()))

    grid = _extract_beatgrid_from_anlz(str(dat))
    record = {
        "content_id": "555",
        "title": "Hermetic Twin",
        "artist": "Test Artist",
        "duration_s": grid["beatgrid_times_ms"][-1] / 1000.0,
        "bpm": 128.0,
        "beatgrid_fingerprint": _beatgrid_fingerprint(grid["beatgrid_times_ms"]),
        "anlz_relpaths": ["anlz/555/ANLZ0000.DAT", "anlz/555/ANLZ0000.EXT"],
        "v4_relpath": None,
        "soundswitch_id": "{SSID}",
        "laser_tag_beats": [],
        "source_filepath": "/music/hermetic.mp3",
    }
    index = {"schema_version": 1, "track_count": 1, "tracks": [record]}
    (root / "index.json").write_text(json.dumps(index), encoding="utf-8")
    return root, dat, grid, record


def _drain_anlz_data(eq: queue.Queue, timeout: float = 5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            event = eq.get(timeout=0.2)
        except queue.Empty:
            continue
        if event.kind == Ev.ANLZ_DATA:
            return event
    return None


class SidecarPhraseHermeticTests(_CacheIsolated):
    def test_real_sidecar_files_yield_phrase_through_the_real_chain(self) -> None:
        with TemporaryDirectory(prefix="awr211_e2e_") as tmp:
            mount = Path(tmp)
            _root, dat, grid, _record = _hermetic_sidecar(mount)

            # REAL discovery + schema/confinement validation of the real index.
            loaded = R._discover_sidecar_index([mount])
            self.assertIsNotNone(loaded)
            side_root, records = loaded

            # REAL exact-fingerprint (mirror-class) selection, no tags needed.
            selected, reason, _ids = R._select_sidecar_record(records, grid, None)
            self.assertIsNotNone(selected)
            self.assertEqual(reason, "sidecar-mirror-match")

            # REAL confined sidecar .DAT path → REAL runtime worker → REAL phrase.
            dat_path = R._sidecar_path(side_root, selected["anlz_relpaths"][0])
            self.assertIsNotNone(dat_path)
            data = SM._read_runtime_anlz_data(str(dat_path), spectral_enabled=False)
            self.assertEqual(list(data.drop_beat_indices), [64])
            self.assertEqual(list(data.breakdown_beat_indices), [32])

    def test_smart_phrase_reaches_runtime_with_spectral_and_v2_off(self) -> None:
        with TemporaryDirectory(prefix="awr211_runtime_") as tmp:
            mount = Path(tmp)
            _root, _dat, grid, _record = _hermetic_sidecar(mount)
            side_root, records = R._discover_sidecar_index([mount])
            selected, reason, _ids = R._select_sidecar_record(records, grid, None)
            self.assertEqual(reason, "sidecar-mirror-match")
            with patch.object(
                R, "_device_audio_filepath", return_value=str(mount / "music" / "track.mp3")
            ):
                payload = R._payload_for_sidecar(
                    side_root,
                    selected,
                    "/Volumes/GUEST/PIONEER/USBANLZ/P001/00000001/ANLZ0000.DAT",
                )
            self.assertIsNotNone(payload)

            with patch.dict(
                os.environ,
                {"RBSS_SMART_REARM_EXPERIMENT": "1", "RBSS_SPECTRAL_ENABLE": "0"},
                clear=False,
            ):
                sm = SM.StateManager(queue.Queue(), PositionCache(), Mock())
            self.assertTrue(sm._smart_rearm_experiment)
            self.assertFalse(sm._spectral_enable)
            self.assertFalse(sm._v2_identity_enabled)

            gen = sm._deck[1].load_gen
            payload["load_gen"] = gen
            sm._loaded_anlz_path[1] = (
                "/Volumes/GUEST/PIONEER/USBANLZ/P001/00000001/ANLZ0000.DAT",
                gen,
            )
            sm._on_filepath_resolved(1, payload)
            event = _drain_anlz_data(sm._eq)
            self.assertIsNotNone(event, "resolved sidecar ANLZ worker emitted no phrase data")
            sm._handle_event(event)
            self.assertEqual(sm._deck[1].meta.anlz_drops, [64])
            self.assertEqual(sm._deck[1].meta.anlz_breakdowns, [32])

    def test_unknown_schema_and_path_escape_still_fail_closed(self) -> None:
        with TemporaryDirectory(prefix="awr211_bad_") as tmp:
            root = Path(tmp) / "RBSS BRIDGE USB" / "lighting_sidecar"
            root.mkdir(parents=True)
            bad = {
                "schema_version": 99, "track_count": 1,
                "tracks": [{"content_id": "1", "anlz_relpaths": ["../../etc/x.DAT"]}],
            }
            (root / "index.json").write_text(json.dumps(bad), encoding="utf-8")
            self.assertIsNone(R._discover_sidecar_index([Path(tmp)]))


class SidecarPhraseRealMinkTests(_CacheIsolated):
    @skipUnless(_MINK_SIDECAR.exists(), "real MINK sidecar not mounted")
    def test_real_mink_sidecar_resolves_usb_loads_to_phrase(self) -> None:
        # Zero-mock proof against AWR-210's real 880-track sidecar. Calling
        # _sidecar_lookup directly is the foreign-laptop / no-DB path (the sidecar
        # source in isolation), exactly what R1 targets.
        R._SIDECAR_CACHE = {}
        self.assertIsNotNone(R._mounted_sidecar_index(), "MINK sidecar not discovered")

        resolved: list[tuple[str, dict, list]] = []
        for usb_dat in sorted(glob.glob("/Volumes/MINK/PIONEER/USBANLZ/*/*/ANLZ0000.DAT"))[:30]:
            grid = _extract_beatgrid_from_anlz(usb_dat)
            if len(grid.get("beatgrid_times_ms", ())) < 2:
                continue
            payload = R._sidecar_lookup(usb_dat, grid)
            if payload is None:
                continue
            data = SM._read_runtime_anlz_data(payload["local_anlz_path"], spectral_enabled=False)
            if data.drop_beat_indices:
                resolved.append((usb_dat, payload, list(data.drop_beat_indices)))
            if len(resolved) >= 3:
                break

        self.assertGreaterEqual(
            len(resolved), 1,
            "no real MINK USB load resolved to phrase through the sidecar chain",
        )
        # Provenance: phrase came from a file INSIDE the sidecar, and v4 rode along.
        _usb, payload, _drops = resolved[0]
        self.assertIn("lighting_sidecar", payload["local_anlz_path"])
        self.assertTrue(payload["local_anlz_path"].endswith(".DAT"))
        self.assertIsNotNone(payload.get("sidecar_v4"))


if __name__ == "__main__":
    unittest.main()
