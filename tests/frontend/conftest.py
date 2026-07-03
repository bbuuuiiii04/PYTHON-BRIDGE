# Requires one-time browser install before running locally:
#   python -m playwright install chromium
from __future__ import annotations

import shutil
import sys
import tempfile
import threading
from dataclasses import dataclass
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from rb_ss_bridge_v2.tools.laser_pad_web import LaserPadService, build_handler  # noqa: E402
from rb_ss_bridge_v2.tools.led_pad_web import LedPadService, build_handler as build_led_handler  # noqa: E402

_LED_EXAMPLE_CONFIG = Path(__file__).resolve().parents[2] / "config" / "led_look_director.example.json"


@dataclass(frozen=True)
class LaserPadBrowserServer:
    base_url: str
    config_path: Path
    config_dir: Path
    service: LaserPadService


@pytest.fixture()
def laser_pad_server() -> LaserPadBrowserServer:
    with tempfile.TemporaryDirectory() as td:
        config_path = Path(td) / "laser_director.json"
        service = LaserPadService(config_path)
        service.duplicate_personality({"source": "house", "name": "dubstep"})
        service.apply_draft_patch(
            {"patch": {"personalities": {"dubstep": {"phrase_bank": []}}}}
        )
        initial_commit = service.commit_draft()
        assert initial_commit.get("ok"), initial_commit

        server = ThreadingHTTPServer(("127.0.0.1", 0), build_handler(service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address
            yield LaserPadBrowserServer(
                base_url=f"http://{host}:{port}",
                config_path=config_path,
                config_dir=config_path.parent,
                service=service,
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2.0)


@dataclass(frozen=True)
class LedPadBrowserServer:
    base_url: str
    config_path: Path
    config_dir: Path
    service: LedPadService


@pytest.fixture()
def led_pad_server() -> LedPadBrowserServer:
    with tempfile.TemporaryDirectory() as td:
        config_path = Path(td) / "led_look_director.json"
        shutil.copy2(_LED_EXAMPLE_CONFIG, config_path)
        service = LedPadService(config_path, dry_run=True)

        server = ThreadingHTTPServer(("127.0.0.1", 0), build_led_handler(service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address
            yield LedPadBrowserServer(
                base_url=f"http://{host}:{port}",
                config_path=config_path,
                config_dir=config_path.parent,
                service=service,
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2.0)

