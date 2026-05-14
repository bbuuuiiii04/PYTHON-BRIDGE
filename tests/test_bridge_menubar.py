from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


class BridgeMenubarTests(unittest.TestCase):
    def test_map_lasers_opens_pad_url(self) -> None:
        scripts_dir = Path(__file__).resolve().parents[1] / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        try:
            bridge_menubar = importlib.import_module("bridge_menubar")
        except ModuleNotFoundError as exc:
            if exc.name in {"objc", "AppKit", "Foundation"}:
                self.skipTest(f"PyObjC unavailable: {exc.name}")
            raise

        handler = bridge_menubar.BridgeMenuBar.mapLasers_
        with patch.object(bridge_menubar, "open_browser_url") as open_browser:
            handler.callable(None, None)

        open_browser.assert_called_once_with(bridge_menubar.LASER_PAD_URL)
        self.assertEqual(bridge_menubar.LASER_PAD_URL, "http://127.0.0.1:8765")
        source = (scripts_dir / "bridge_menubar.py").read_text(encoding="utf-8")
        self.assertIn("Laser Pad…", source)


if __name__ == "__main__":
    unittest.main()
