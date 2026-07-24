"""EVICTFIX: the spectral-cache eviction gate + worker in __main__.py.

The old gate demanded RBSS_SPECTRAL_ENABLE=1, which no launch path sets
(launch_profile.BRIDGE_ENV, ss_bridge_watcher.sh, usb_launcher.py), while the
ANLZ worker writes cache entries under a different condition entirely — the
gated v3 spectral path OR LED identity-v2. So the collector never ran while
the cache grew on every new track. These tests pin the new condition.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# rb_ss_bridge_v2.__main__ calls bridge_log.init() at import time. Redirect it
# into a throwaway dir so importing it here never touches the operator's real
# ~/Library/Logs, then shut it down so test_bridge_log.py still gets a clean,
# un-initialized singleton (same preamble as test_main_mixer_authority_wiring).
with mock.patch.dict(
    os.environ, {"RBSS_RUNTIME_DIR": tempfile.mkdtemp(prefix="rbss_test_runtime_")}
):
    from rb_ss_bridge_v2 import __main__ as main_mod  # noqa: E402
from rb_ss_bridge_v2 import bridge_log  # noqa: E402

bridge_log.shutdown()

_FLAGS_OFF = {"RBSS_SMART_REARM_EXPERIMENT": "0", "RBSS_SPECTRAL_ENABLE": "0"}
_FLAGS_ON = {"RBSS_SMART_REARM_EXPERIMENT": "1", "RBSS_SPECTRAL_ENABLE": "1"}


def _engine(identity_v2_enabled: bool):
    """The shape state_manager reads: led_color_engine._config.v2.enabled."""
    return SimpleNamespace(
        _config=SimpleNamespace(v2=SimpleNamespace(enabled=identity_v2_enabled))
    )


class SpectralEvictionGateTests(unittest.TestCase):
    def _run_gate(self, env, led_color_engine, v3_side_effect=None):
        calls: list[str] = []

        def _v3():
            calls.append("v3")
            if v3_side_effect is not None:
                raise v3_side_effect
            return 0

        def _v4():
            calls.append("v4")
            return 0

        with mock.patch.dict(os.environ, env), mock.patch(
            "rb_ss_bridge_v2.spectral_cache.evict_stale", _v3
        ), mock.patch("rb_ss_bridge_v2.spectral_cache.evict_stale_v4", _v4):
            thread = main_mod._start_spectral_cache_eviction_if_enabled(led_color_engine)
            if thread is not None:
                thread.join(timeout=5)
                self.assertFalse(thread.is_alive(), "eviction thread did not finish")
        return thread, calls

    def test_identity_v2_alone_opens_the_gate(self) -> None:
        # The live shape: RBSS_SPECTRAL_ENABLE is unset everywhere, identity-v2
        # comes from the colour-engine config, and the cache is being written.
        thread, calls = self._run_gate(_FLAGS_OFF, _engine(True))
        self.assertIsNotNone(thread)
        self.assertEqual(calls, ["v3", "v4"])

    def test_spectral_path_alone_opens_the_gate(self) -> None:
        thread, calls = self._run_gate(_FLAGS_ON, None)
        self.assertIsNotNone(thread)
        self.assertEqual(calls, ["v3", "v4"])

    def test_no_writer_no_eviction(self) -> None:
        thread, calls = self._run_gate(_FLAGS_OFF, _engine(False))
        self.assertIsNone(thread)
        self.assertEqual(calls, [])

    def test_smart_rearm_alone_does_not_open_the_gate(self) -> None:
        # The v3 spectral path needs both flags; identity-v2 off means no writes.
        env = {"RBSS_SMART_REARM_EXPERIMENT": "1", "RBSS_SPECTRAL_ENABLE": "0"}
        thread, calls = self._run_gate(env, _engine(False))
        self.assertIsNone(thread)
        self.assertEqual(calls, [])

    def test_missing_colour_engine_is_not_a_writer(self) -> None:
        thread, calls = self._run_gate(_FLAGS_OFF, None)
        self.assertIsNone(thread)
        self.assertEqual(calls, [])

    def test_worker_survives_an_exception_instead_of_killing_the_thread(self) -> None:
        with self.assertLogs("bridge", level="DEBUG") as captured:
            thread, calls = self._run_gate(
                _FLAGS_ON, None, v3_side_effect=UnicodeDecodeError(
                    "utf-8", b"\xb0", 0, 1, "invalid start byte"
                )
            )
        self.assertIsNotNone(thread)
        self.assertEqual(calls, ["v3"])
        self.assertTrue(
            any("spectral-cache-evict-aborted" in line for line in captured.output),
            captured.output,
        )


if __name__ == "__main__":
    unittest.main()
