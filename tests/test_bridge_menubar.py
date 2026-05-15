from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


class BridgeMenubarTests(unittest.TestCase):
    def _import_module(self):
        scripts_dir = Path(__file__).resolve().parents[1] / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        try:
            return importlib.import_module("bridge_menubar")
        except ModuleNotFoundError as exc:
            if exc.name in {"objc", "AppKit", "Foundation"}:
                self.skipTest(f"PyObjC unavailable: {exc.name}")
            raise

    def test_map_lasers_opens_pad_url(self) -> None:
        scripts_dir = Path(__file__).resolve().parents[1] / "scripts"
        bridge_menubar = self._import_module()

        handler = bridge_menubar.BridgeMenuBar.mapLasers_
        with patch.object(bridge_menubar, "open_browser_url") as open_browser:
            handler.callable(None, None)

        open_browser.assert_called_once_with(bridge_menubar.LASER_PAD_URL)
        self.assertEqual(bridge_menubar.LASER_PAD_URL, "http://127.0.0.1:8765")
        source = (scripts_dir / "bridge_menubar.py").read_text(encoding="utf-8")
        self.assertIn("Laser Pad…", source)

    def test_toggle_record_session_appends_runtime_command(self) -> None:
        bridge_menubar = self._import_module()

        handler = bridge_menubar.BridgeMenuBar.toggleRecordSession_
        with (
            patch.object(bridge_menubar, "read_status", return_value={}),
            patch.object(bridge_menubar, "default_recording_path", return_value="/tmp/session.jsonl"),
            patch.object(bridge_menubar, "append_command") as append_command,
        ):
            handler.callable(None, None)

        append_command.assert_called_once_with(
            {
                "cmd": "toggle_record_session",
                "path": "/tmp/session.jsonl",
                "dedup": False,
            }
        )


if __name__ == "__main__":
    unittest.main()
