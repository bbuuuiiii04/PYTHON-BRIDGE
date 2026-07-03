from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.tools.pad_access import access_payload  # noqa: E402


class PadAccessTests(unittest.TestCase):
    def test_loopback_bind_has_no_lan_url(self) -> None:
        payload = access_payload("127.0.0.1", 8766)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["bound_host"], "127.0.0.1")
        self.assertEqual(payload["port"], 8766)
        self.assertTrue(payload["loopback_only"])
        self.assertIsNone(payload["lan_url"])

    def test_bound_to_specific_ip_uses_that_ip_directly(self) -> None:
        payload = access_payload("192.168.1.50", 8766)

        self.assertFalse(payload["loopback_only"])
        self.assertEqual(payload["lan_url"], "http://192.168.1.50:8766/")

    def test_bound_to_all_interfaces_with_detection_failure_has_no_lan_url(self) -> None:
        with patch("rb_ss_bridge_v2.tools.pad_access.detect_lan_ip", return_value=None):
            payload = access_payload("0.0.0.0", 8765)

        self.assertFalse(payload["loopback_only"])
        self.assertIsNone(payload["lan_url"])

    def test_bound_to_all_interfaces_with_detection_success_builds_url(self) -> None:
        with patch("rb_ss_bridge_v2.tools.pad_access.detect_lan_ip", return_value="10.0.0.5"):
            payload = access_payload("0.0.0.0", 8765)

        self.assertFalse(payload["loopback_only"])
        self.assertEqual(payload["lan_url"], "http://10.0.0.5:8765/")

    def test_loopback_hostname_localhost_is_treated_as_loopback(self) -> None:
        payload = access_payload("localhost", 8766)

        self.assertTrue(payload["loopback_only"])
        self.assertIsNone(payload["lan_url"])


if __name__ == "__main__":
    unittest.main()
