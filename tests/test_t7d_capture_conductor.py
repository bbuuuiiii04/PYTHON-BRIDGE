"""Tests for the T7d capture conductor's pure, safety-critical logic.

The conductor is an observer + operator-instruction tool. It NEVER connects
fixtures, opens DMX, or enables the pack backend. These tests cover the parts
that decide whether a capture is trustworthy:

  * the seven-scenario registry and its required log markers,
  * fail-closed gate classification (ACCEPTED / INCOMPLETE / FAIL),
  * sanitization of summaries (no paths, IPs, ports, UUIDs, device IDs),
  * manifest construction and round-trip.

Side-effecting parts (say/osascript ping, sudo tcpdump, active polling) are
thin wrappers and are exercised only against the live system, never here.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

_MOD = Path(__file__).resolve().parents[1] / "tools" / "t7d_capture_conductor.py"
_spec = importlib.util.spec_from_file_location("t7d_capture_conductor", _MOD)
cc = importlib.util.module_from_spec(_spec)
sys.modules["t7d_capture_conductor"] = cc
_spec.loader.exec_module(cc)


def _green_obs(**over):
    obs = {
        "bridge_process_count": 1,
        "pack_output_disabled": True,
        "project_hash_matched": True,
        "required_markers_present": True,
        "pcap_universe0_frames": 5000,
        "recorder_drops": 0,
        "timed_out": False,
    }
    obs.update(over)
    return obs


class ScenarioRegistryTests(unittest.TestCase):
    def test_all_seven_scenarios_present(self):
        self.assertEqual(
            set(cc.SCENARIOS),
            {
                "arm",
                "refire",
                "master-switch",
                "drop-hold",
                "buildup",
                "phrase-anchor",
                "correction",
            },
        )

    def test_each_scenario_declares_required_markers(self):
        for name, spec in cc.SCENARIOS.items():
            self.assertTrue(spec.get("required_markers"), name)


class ClassifyGateTests(unittest.TestCase):
    def test_all_green_is_accepted(self):
        self.assertEqual(cc.classify_gate(_green_obs()), "ACCEPTED")

    def test_pack_output_enabled_is_fail(self):
        self.assertEqual(cc.classify_gate(_green_obs(pack_output_disabled=False)), "FAIL")

    def test_multiple_bridge_processes_is_fail(self):
        self.assertEqual(cc.classify_gate(_green_obs(bridge_process_count=2)), "FAIL")

    def test_zero_bridge_processes_is_fail(self):
        self.assertEqual(cc.classify_gate(_green_obs(bridge_process_count=0)), "FAIL")

    def test_project_hash_changed_is_fail(self):
        self.assertEqual(cc.classify_gate(_green_obs(project_hash_matched=False)), "FAIL")

    def test_missing_markers_is_incomplete(self):
        self.assertEqual(
            cc.classify_gate(_green_obs(required_markers_present=False)), "INCOMPLETE"
        )

    def test_recorder_drops_is_incomplete(self):
        self.assertEqual(cc.classify_gate(_green_obs(recorder_drops=3)), "INCOMPLETE")

    def test_timeout_is_incomplete_not_reinterpreted(self):
        self.assertEqual(cc.classify_gate(_green_obs(timed_out=True)), "INCOMPLETE")

    def test_too_few_universe0_frames_is_incomplete(self):
        self.assertEqual(
            cc.classify_gate(_green_obs(pcap_universe0_frames=3)), "INCOMPLETE"
        )

    def test_safety_fail_takes_precedence_over_incomplete(self):
        # Both a safety breach and missing evidence -> FAIL (never softened).
        self.assertEqual(
            cc.classify_gate(
                _green_obs(pack_output_disabled=False, required_markers_present=False)
            ),
            "FAIL",
        )


class SanitizeTests(unittest.TestCase):
    def test_strips_paths_ips_ports_uuids(self):
        raw = {
            "path": "/Users/bbui/Music/SoundSwitch/default.ssproj",
            "ip": "192.168.1.216",
            "endpoint": "127.0.0.1:6454",
            "uuid": "8b1f2c3d-4e5a-6789-abcd-ef0123456789",
            "applog": "AppLog20260622.txt",
            "frames": 5000,
        }
        out = cc.sanitize_summary(raw)
        blob = json.dumps(out)
        self.assertNotIn("/Users/bbui", blob)
        self.assertNotIn("192.168.1.216", blob)
        self.assertNotIn("6454", blob)
        self.assertNotIn("8b1f2c3d", blob)
        self.assertNotIn("AppLog20260622", blob)
        self.assertEqual(out["frames"], 5000)  # non-sensitive scalars preserved


class MarkersTests(unittest.TestCase):
    def test_markers_present_requires_all(self):
        log = "12:00:00 [SM] midi-refire ...\n12:00:01 [LX] fired role=autoloop\n"
        self.assertTrue(cc.markers_present(log, ["[SM] midi-refire", "[LX] fired"]))
        self.assertFalse(cc.markers_present(log, ["[SM] midi-refire", "phrase-anchor"]))


class ManifestTests(unittest.TestCase):
    def test_build_manifest_has_core_fields(self):
        man = cc.build_manifest("arm", "t7d_arm_20260622_120000", created_epoch=1.0)
        self.assertEqual(man["scenario"], "arm")
        self.assertEqual(man["run_id"], "t7d_arm_20260622_120000")
        self.assertIn("required_markers", man)
        self.assertIn("HARDWARE-UNVALIDATED", man["hardware_status"])
        self.assertFalse(man["pack_output_enabled"])  # explicit safety assertion

    def test_unknown_scenario_raises(self):
        with self.assertRaises(ValueError):
            cc.build_manifest("nope", "rid", created_epoch=1.0)

    def test_manifest_round_trips_on_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            man = cc.build_manifest("refire", "rid2", created_epoch=2.0)
            p = Path(tmp) / "manifest.json"
            cc.write_manifest(p, man)
            self.assertEqual(json.loads(p.read_text())["scenario"], "refire")


class CoreProcessLineTests(unittest.TestCase):
    """The core-process counter must see exactly one core under the operator's
    real menubar launch (python core + its `| tee /tmp/bridge.log` wrapper)."""

    CORE = (
        "82615 /opt/homebrew/Cellar/python@3.14/3.14.3_1/Frameworks/Python.framework/"
        "Versions/3.14/Resources/Python.app/Contents/MacOS/Python -u -m rb_ss_bridge_v2"
    )
    TEE_WRAPPER = (
        '82612 bash -lc printf "x"; cd /Users/bbui; env RBSS_SMART_DROP=1 '
        "/opt/homebrew/bin/python3 -u -m rb_ss_bridge_v2 2>&1 | tee /tmp/bridge.log MON"
    )
    MENUBAR = (
        "22309 /opt/homebrew/.../Python /Users/bbui/rb_ss_bridge_v2/scripts/bridge_menubar.py"
    )
    LASER_PAD = (
        "24202 /Library/.../Python -m rb_ss_bridge_v2.scripts.laser_pad --host 127.0.0.1"
    )

    def test_real_python_core_counts(self):
        self.assertTrue(cc.is_core_bridge_line(self.CORE))

    def test_tee_shell_wrapper_excluded(self):
        self.assertFalse(cc.is_core_bridge_line(self.TEE_WRAPPER))

    def test_menubar_excluded(self):
        self.assertFalse(cc.is_core_bridge_line(self.MENUBAR))

    def test_laser_pad_submodule_excluded(self):
        self.assertFalse(cc.is_core_bridge_line(self.LASER_PAD))

    def test_blank_line_excluded(self):
        self.assertFalse(cc.is_core_bridge_line("   "))

    def test_single_core_under_full_menubar_launch(self):
        lines = [self.MENUBAR, self.LASER_PAD, self.TEE_WRAPPER, self.CORE]
        self.assertEqual(sum(1 for ln in lines if cc.is_core_bridge_line(ln)), 1)

    def test_two_genuine_cores_still_report_two(self):
        # The safety case: a second real python core must NOT be hidden.
        second = self.CORE.replace("82615", "99999")
        lines = [self.TEE_WRAPPER, self.CORE, second]
        self.assertEqual(sum(1 for ln in lines if cc.is_core_bridge_line(ln)), 2)


class CountFramesTests(unittest.TestCase):
    def test_missing_pcap_counts_zero(self):
        self.assertEqual(cc.count_universe0_frames(Path("/tmp/does-not-exist.pcap")), 0)


if __name__ == "__main__":
    unittest.main()
