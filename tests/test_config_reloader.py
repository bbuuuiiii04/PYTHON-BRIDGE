from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.tools.config_reloader import ConfigReloader, HOT_RELOAD_DISABLE_ENV


class ConfigReloaderTests(unittest.TestCase):
    def test_config_reloader_detects_mtime_change(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "laser_director.json"
            path.write_text(json.dumps({"enabled": False}), encoding="utf-8")
            hit = threading.Event()
            calls = []

            def _on_reload(result) -> None:
                calls.append(result)
                hit.set()

            reloader = ConfigReloader(
                config_path=path,
                poll_interval=0.05,
                on_reload=_on_reload,
            )
            reloader.start()
            try:
                time.sleep(0.1)
                path.write_text(json.dumps({"enabled": True}), encoding="utf-8")
                self.assertTrue(hit.wait(1.0), "reloader did not detect mtime change")
            finally:
                reloader.stop()

        self.assertGreaterEqual(len(calls), 1)

    def test_config_reloader_respects_disable_env(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "laser_director.json"
            path.write_text(json.dumps({"enabled": False}), encoding="utf-8")
            hit = threading.Event()

            def _on_reload(_result) -> None:
                hit.set()

            reloader = ConfigReloader(
                config_path=path,
                poll_interval=0.05,
                on_reload=_on_reload,
            )
            os.environ[HOT_RELOAD_DISABLE_ENV] = "1"
            try:
                reloader.start()
                path.write_text(json.dumps({"enabled": True}), encoding="utf-8")
                self.assertFalse(hit.wait(0.2))
            finally:
                os.environ.pop(HOT_RELOAD_DISABLE_ENV, None)
                reloader.stop()


if __name__ == "__main__":
    unittest.main()
