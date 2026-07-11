from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import filepath_resolver as resolver  # noqa: E402


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


def _write_index(mount: Path, *, schema: int = 1) -> Path:
    path = mount / "RBSS BRIDGE USB" / "lighting_sidecar" / "index.json"
    path.parent.mkdir(parents=True)
    payload = {"schema_version": schema, "track_count": 1, "tracks": [_record()]}
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class SidecarReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        resolver._SIDECAR_CACHE = None

    def tearDown(self) -> None:
        resolver._SIDECAR_CACHE = None

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

    def test_discovers_his_sidecar_beside_guest_stick_and_caches_it(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            guest = root / "A-GUEST"
            guest.mkdir()
            his = root / "MINK"
            _write_index(his)

            loaded = resolver._discover_sidecar_index([guest, his])
            self.assertEqual(loaded[0], his / "RBSS BRIDGE USB" / "lighting_sidecar")

            # Found roots are session-cached; disappearance does not redirect
            # a running resolver to a different stick mid-session.
            self.assertIs(resolver._discover_sidecar_index([]), loaded)

    def test_missing_and_path_escape_are_silent_misses(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertIsNone(resolver._discover_sidecar_index([root / "missing"]))
            path = _write_index(root / "bad")
            payload = json.loads(path.read_text())
            payload["tracks"][0]["anlz_relpaths"] = ["../../outside.DAT"]
            path.write_text(json.dumps(payload))
            self.assertIsNone(resolver._load_sidecar_index(path))


if __name__ == "__main__":
    unittest.main()
