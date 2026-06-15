"""Tests for Govee LAN discovery IP resolution (pure selection + injected scan)."""
import unittest

from rb_ss_bridge_v2.govee_lan_discovery import resolve_realtime_ip, select_device_ip

_CFG = "192.168.0.219"


class SelectDeviceIpTest(unittest.TestCase):
    def test_empty_falls_back_to_config(self):
        self.assertEqual(select_device_ip([], _CFG), (_CFG, "config"))

    def test_device_ref_exact_match_wins(self):
        devices = [
            {"ip": "192.168.0.50", "device": "AA:BB", "sku": "H612D"},
            {"ip": "192.168.0.216", "device": "C1:0A", "sku": "H612D"},
        ]
        self.assertEqual(
            select_device_ip(devices, _CFG, device_ref="c1:0a", expected_sku="H612D"),
            ("192.168.0.216", "device_ref"),
        )

    def test_sku_match_when_no_device_ref(self):
        devices = [{"ip": "192.168.0.216", "device": "X", "sku": "H612D"}]
        self.assertEqual(
            select_device_ip(devices, _CFG, expected_sku="h612d"),
            ("192.168.0.216", "sku"),
        )

    def test_multiple_same_sku_no_ref_is_ambiguous(self):
        devices = [
            {"ip": "192.168.0.10", "device": "X", "sku": "H612D"},
            {"ip": "192.168.0.11", "device": "Y", "sku": "H612D"},
        ]
        self.assertEqual(
            select_device_ip(devices, _CFG, expected_sku="H612D"),
            (_CFG, "ambiguous"),
        )

    def test_sole_device_used_when_no_match_criteria(self):
        devices = [{"ip": "192.168.0.216", "device": "X", "sku": "H612D"}]
        self.assertEqual(select_device_ip(devices, _CFG), ("192.168.0.216", "sole_device"))

    def test_ref_overrides_wrong_sku_ambiguity(self):
        devices = [
            {"ip": "192.168.0.10", "device": "WRONG", "sku": "H612D"},
            {"ip": "192.168.0.216", "device": "RIGHT", "sku": "H612D"},
        ]
        self.assertEqual(
            select_device_ip(devices, _CFG, device_ref="right", expected_sku="H612D"),
            ("192.168.0.216", "device_ref"),
        )


class ResolveRealtimeIpTest(unittest.TestCase):
    def test_uses_injected_discovery(self):
        scan = lambda _t: [{"ip": "192.168.0.216", "device": "C1", "sku": "H612D"}]
        ip, source = resolve_realtime_ip(
            _CFG, device_ref="C1", expected_sku="H612D", discover=scan
        )
        self.assertEqual((ip, source), ("192.168.0.216", "device_ref"))

    def test_discovery_failure_falls_back_to_config(self):
        ip, source = resolve_realtime_ip(_CFG, discover=lambda _t: [])
        self.assertEqual((ip, source), (_CFG, "config"))


if __name__ == "__main__":
    unittest.main()
