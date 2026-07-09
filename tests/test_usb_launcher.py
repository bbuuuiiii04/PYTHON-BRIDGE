"""Pure arg-dispatch coverage for the USB bundle entrypoint (usb_launcher.py).

No build, no AppKit, no bridge run -- every mode target is monkeypatched, so
these prove the dispatch table and the --run-bridge env application only.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import usb_launcher  # noqa: E402
from rb_ss_bridge_v2 import launch_profile  # noqa: E402


class DispatchTests(unittest.TestCase):
    def test_no_args_runs_menubar(self) -> None:
        with mock.patch.object(usb_launcher, "_run_menubar", return_value=0) as menubar:
            self.assertEqual(usb_launcher.main([]), 0)
        menubar.assert_called_once_with()

    def test_run_bridge_dispatch(self) -> None:
        with mock.patch.object(usb_launcher, "_run_bridge", return_value=0) as run:
            self.assertEqual(usb_launcher.main(["--run-bridge"]), 0)
        run.assert_called_once_with()

    def test_run_streamdeck_dispatch(self) -> None:
        with mock.patch.object(usb_launcher, "_run_streamdeck", return_value=0) as run:
            self.assertEqual(usb_launcher.main(["--run-streamdeck"]), 0)
        run.assert_called_once_with()

    def test_run_frame_engine_passes_fd(self) -> None:
        with mock.patch.object(usb_launcher, "_run_frame_engine", return_value=0) as run:
            self.assertEqual(usb_launcher.main(["--run-frame-engine", "--fd", "7"]), 0)
        run.assert_called_once_with(["--fd", "7"])

    def test_unknown_mode_fails_closed_nonzero(self) -> None:
        with mock.patch.object(usb_launcher, "_run_menubar", side_effect=AssertionError):
            rc = usb_launcher.main(["--bogus"])
        self.assertEqual(rc, 2)

    def test_replay_session_dispatch_passes_path(self) -> None:
        with mock.patch.object(usb_launcher, "_run_replay_session", return_value=0) as run:
            self.assertEqual(usb_launcher.main(["--replay-session", "/tmp/s.jsonl"]), 0)
        run.assert_called_once_with("/tmp/s.jsonl")

    def test_replay_session_without_path_fails_closed(self) -> None:
        self.assertEqual(usb_launcher.main(["--replay-session"]), 2)


class ReplaySessionGuardTests(unittest.TestCase):
    def test_preflight_refusal_blocks_bridge_and_returns_nonzero(self) -> None:
        # Rekordbox running (or any refusal) must stop before the bridge starts.
        with mock.patch("rb_ss_bridge_v2.replay_event_source.replay_preflight",
                        return_value="Rekordbox is running"), \
             mock.patch.object(usb_launcher, "_run_bridge", side_effect=AssertionError("bridge started")):
            rc = usb_launcher._run_replay_session("/tmp/s.jsonl")
        self.assertEqual(rc, 1)

    def test_preflight_pass_sets_env_and_runs_bridge(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False), \
             mock.patch("rb_ss_bridge_v2.replay_event_source.replay_preflight", return_value=None), \
             mock.patch.object(usb_launcher, "_run_bridge", return_value=0) as run:
            os.environ.pop("RBSS_REPLAY_SESSION", None)
            rc = usb_launcher._run_replay_session("/tmp/s.jsonl")
            self.assertEqual(os.environ.get("RBSS_REPLAY_SESSION"), "/tmp/s.jsonl")
        self.assertEqual(rc, 0)
        run.assert_called_once_with()


class FrameEngineIsolationTests(unittest.TestCase):
    def test_frame_engine_dispatch_never_loads_menubar(self) -> None:
        # The headless child must reach the frame engine without loading the
        # Cocoa menubar path (menubar patched to explode if touched).
        with mock.patch("rb_ss_bridge_v2.govee_frame_engine.main") as frame_main, \
             mock.patch.object(
                 usb_launcher, "_run_menubar", side_effect=AssertionError("menubar loaded")
             ):
            usb_launcher.main(["--run-frame-engine", "--fd", "3"])
        frame_main.assert_called_once_with(["--fd", "3"])


class RunBridgeEnvTests(unittest.TestCase):
    def test_run_bridge_applies_launch_profile_and_calls_main(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False), \
             mock.patch("rb_ss_bridge_v2.__main__.main") as bridge_main:
            # scrub inherited flags so we prove _run_bridge sets them
            for key in list(launch_profile.BRIDGE_ENV):
                os.environ.pop(key, None)
            os.environ.pop("RBSS_LASER_CONFIG", None)

            usb_launcher._run_bridge()

            for key, value in launch_profile.BRIDGE_ENV.items():
                self.assertEqual(os.environ.get(key), value, key)
            self.assertTrue(os.environ.get("RBSS_LASER_CONFIG"))
        bridge_main.assert_called_once_with()

    def test_run_bridge_honors_operator_laser_config_override(self) -> None:
        with mock.patch.dict(os.environ, {"RBSS_LASER_CONFIG": "/custom/laser.json"}, clear=False), \
             mock.patch("rb_ss_bridge_v2.__main__.main"):
            usb_launcher._run_bridge()
            self.assertEqual(os.environ["RBSS_LASER_CONFIG"], "/custom/laser.json")


class GoveeEnvSourcingTests(unittest.TestCase):
    def test_parse_tolerates_export_comments_blanks_quotes(self) -> None:
        text = (
            "# a comment\n"
            "\n"
            "export GOVEE_API_KEY=abc123\n"
            'GOVEE_DEVICE="AA:BB:CC"\n'
            "  SPACED = 7 \n"
            "notanassignment\n"
        )
        parsed = usb_launcher._parse_env_file(text)
        self.assertEqual(parsed["GOVEE_API_KEY"], "abc123")
        self.assertEqual(parsed["GOVEE_DEVICE"], "AA:BB:CC")
        self.assertEqual(parsed["SPACED"], "7")
        self.assertNotIn("notanassignment", parsed)

    def test_load_sets_keys_from_file(self) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as fh:
            fh.write("GOVEE_API_KEY=fromfile\n")
            path = fh.name
        env: dict[str, str] = {}
        usb_launcher._load_govee_env(env=env, path=path)
        self.assertEqual(env["GOVEE_API_KEY"], "fromfile")

    def test_existing_env_key_wins(self) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as fh:
            fh.write("GOVEE_API_KEY=fromfile\n")
            path = fh.name
        env = {"GOVEE_API_KEY": "already_set"}
        usb_launcher._load_govee_env(env=env, path=path)
        self.assertEqual(env["GOVEE_API_KEY"], "already_set")

    def test_missing_file_is_noop(self) -> None:
        env: dict[str, str] = {}
        usb_launcher._load_govee_env(env=env, path="/no/such/govee.env")
        self.assertEqual(env, {})

    def test_run_bridge_sources_govee_env(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False), \
             mock.patch.object(usb_launcher, "_load_govee_env") as loader, \
             mock.patch("rb_ss_bridge_v2.__main__.main"):
            usb_launcher._run_bridge()
        loader.assert_called_once()


if __name__ == "__main__":
    unittest.main()
