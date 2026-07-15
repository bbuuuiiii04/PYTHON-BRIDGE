"""Pure VenueReport tests — every probe is faked; no network/MIDI/serial."""
from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import venue_check as vc  # noqa: E402


def _row(name: str, status: str, hint: str) -> vc.CheckResult:
    return vc.CheckResult(name=name, status=status, hint=hint)


def _probes(**overrides) -> vc.VenueProbes:
    defaults = {
        "check_bundle_deps": lambda: _row("Bundle deps", vc.STATUS_OK, "ok"),
        "check_rekordbox_version": lambda: _row(
            "Rekordbox version", vc.STATUS_OK, "ok"
        ),
        "check_rekordbox_patch": lambda: _row(
            "Rekordbox patch", vc.STATUS_OK, "ok"
        ),
        "check_govee_lan": lambda: _row(
            "Govee / Local Network", vc.STATUS_OK, "ok"
        ),
        "check_iac_bus": lambda: _row("IAC Bus 1 (lasers)", vc.STATUS_OK, "ok"),
        "check_enttec": lambda: _row("Enttec DMX", vc.STATUS_INFO, "info"),
    }
    defaults.update(overrides)
    return vc.VenueProbes(**defaults)


class VenueCheckReportTests(unittest.TestCase):
    def test_all_ok_report_order_and_no_patch_button(self) -> None:
        report = vc.run_venue_check(_probes())
        self.assertEqual(
            [r.name for r in report.results],
            [
                "Bundle deps",
                "Rekordbox version",
                "Rekordbox patch",
                "Govee / Local Network",
                "IAC Bus 1 (lasers)",
                "Enttec DMX",
            ],
        )
        self.assertFalse(report.needs_patch)
        body = vc.format_venue_alert_body(report)
        self.assertIn("✓ Bundle deps:", body)
        self.assertIn("• Enttec DMX:", body)

    def test_warn_fail_symbols_and_hints(self) -> None:
        report = vc.run_venue_check(
            _probes(
                check_govee_lan=lambda: _row(
                    "Govee / Local Network",
                    vc.STATUS_WARN,
                    vc._GOVEE_EMPTY_HINT,
                ),
                check_rekordbox_version=lambda: _row(
                    "Rekordbox version",
                    vc.STATUS_FAIL,
                    "Rekordbox 9.9.9 is not supported; use 7.2.11.",
                ),
                check_iac_bus=lambda: _row(
                    "IAC Bus 1 (lasers)", vc.STATUS_WARN, vc._IAC_HINT
                ),
            )
        )
        body = vc.format_venue_alert_body(report)
        self.assertIn("⚠ Govee / Local Network:", body)
        self.assertIn(vc._GOVEE_EMPTY_HINT, body)
        self.assertIn("✗ Rekordbox version:", body)
        self.assertIn("⚠ IAC Bus 1 (lasers):", body)
        self.assertIn("Audio MIDI Setup", body)
        self.assertIn("Lasers only", body)
        self.assertFalse(report.needs_patch)

    def test_unpatched_sets_needs_patch(self) -> None:
        report = vc.run_venue_check(
            _probes(
                check_rekordbox_patch=lambda: _row(
                    "Rekordbox patch",
                    vc.STATUS_FAIL,
                    "Use Patch Rekordbox…",
                )
            )
        )
        self.assertTrue(report.needs_patch)
        self.assertIn("✗ Rekordbox patch:", vc.format_venue_alert_body(report))

    def test_probe_bundle_deps_skips_when_not_frozen(self) -> None:
        row = vc.probe_bundle_deps(frozen=False)
        self.assertEqual(row.status, vc.STATUS_OK)
        self.assertIn("source run", row.hint.lower())

    def test_probe_bundle_deps_fail_lists_missing(self) -> None:
        def boom(_name):
            raise ImportError("nope")

        with mock.patch.object(importlib, "import_module", side_effect=boom):
            row = vc.probe_bundle_deps(frozen=True)
        self.assertEqual(row.status, vc.STATUS_FAIL)
        self.assertIn("missing", row.hint.lower())

    def test_probe_rekordbox_version_supported_and_unsupported(self) -> None:
        with mock.patch(
            "rb_ss_bridge_v2.live_bpm.read_rekordbox_version", return_value=""
        ), mock.patch(
            "rb_ss_bridge_v2.rb_offsets.all_offsets",
            return_value={"7.2.11": object()},
        ):
            row = vc.probe_rekordbox_version()
        self.assertEqual(row.status, vc.STATUS_FAIL)
        self.assertIn("7.2.11", row.hint)

        with mock.patch(
            "rb_ss_bridge_v2.live_bpm.read_rekordbox_version",
            return_value="9.9.9",
        ), mock.patch(
            "rb_ss_bridge_v2.rb_offsets.load_offsets_for_version",
            return_value=None,
        ), mock.patch(
            "rb_ss_bridge_v2.rb_offsets.all_offsets",
            return_value={"7.2.11": object()},
        ):
            row = vc.probe_rekordbox_version()
        self.assertEqual(row.status, vc.STATUS_FAIL)
        self.assertIn("9.9.9", row.hint)

        with mock.patch(
            "rb_ss_bridge_v2.live_bpm.read_rekordbox_version",
            return_value="7.2.11",
        ), mock.patch(
            "rb_ss_bridge_v2.rb_offsets.load_offsets_for_version",
            return_value=object(),
        ):
            row = vc.probe_rekordbox_version()
        self.assertEqual(row.status, vc.STATUS_OK)
        self.assertIn("7.2.11", row.hint)

    def test_probe_rekordbox_patch_verdict_tokens(self) -> None:
        self.assertEqual(
            vc.probe_rekordbox_patch(
                verdict_fn=lambda: ("enabled", "/Applications/rekordbox.app")
            ).status,
            vc.STATUS_OK,
        )
        fail = vc.probe_rekordbox_patch(
            verdict_fn=lambda: ("not_enabled", "/Applications/rekordbox.app")
        )
        self.assertEqual(fail.status, vc.STATUS_FAIL)
        self.assertTrue(vc.VenueReport(results=(fail,)).needs_patch)
        warn = vc.probe_rekordbox_patch(
            verdict_fn=lambda: ("unknown", "boom")
        )
        self.assertEqual(warn.status, vc.STATUS_WARN)

    def test_probe_govee_lan_empty_warns_with_exact_hint(self) -> None:
        row = vc.probe_govee_lan(discover_fn=lambda _t: [])
        self.assertEqual(row.status, vc.STATUS_WARN)
        self.assertEqual(row.hint, vc._GOVEE_EMPTY_HINT)
        ok = vc.probe_govee_lan(discover_fn=lambda _t: [{"ip": "1.2.3.4"}])
        self.assertEqual(ok.status, vc.STATUS_OK)

    def test_probe_iac_bus_missing_mido_or_port_warns(self) -> None:
        row = vc.probe_iac_bus(output_names_fn=lambda: ["Other Port"])
        self.assertEqual(row.status, vc.STATUS_WARN)
        self.assertEqual(row.hint, vc._IAC_HINT)
        ok = vc.probe_iac_bus(
            output_names_fn=lambda: ["IAC Driver Bus 1"]
        )
        self.assertEqual(ok.status, vc.STATUS_OK)

    def test_probe_enttec_is_informational(self) -> None:
        present = vc.probe_enttec(find_port_fn=lambda: "/dev/cu.usbserial-ENT")
        self.assertEqual(present.status, vc.STATUS_INFO)
        self.assertIn("informational", present.hint.lower())
        absent = vc.probe_enttec(find_port_fn=lambda: None)
        self.assertEqual(absent.status, vc.STATUS_INFO)
        self.assertIn("informational", absent.hint.lower())

    def test_first_run_marker_helpers(self) -> None:
        self.assertTrue(
            vc.should_auto_venue_check(
                frozen=True, installed=True, marker_exists=False
            )
        )
        self.assertFalse(
            vc.should_auto_venue_check(
                frozen=True, installed=True, marker_exists=True
            )
        )
        self.assertFalse(
            vc.should_auto_venue_check(
                frozen=False, installed=True, marker_exists=False
            )
        )
        self.assertFalse(
            vc.should_auto_venue_check(
                frozen=True, installed=False, marker_exists=False
            )
        )
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "venue_check_seen"
            self.assertEqual(vc.venue_check_seen_path(Path(tmp)), marker)
            vc.write_venue_check_seen(marker)
            self.assertTrue(marker.exists())
            self.assertEqual(marker.read_text(encoding="utf-8").strip(), "seen")


if __name__ == "__main__":
    unittest.main()
