"""Tests for rekordbox_patch — the consent-gated Rekordbox get-task-allow patch.

All codesign/pgrep calls are mocked; no real re-signing happens.
"""
from __future__ import annotations

import plistlib
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import rekordbox_patch as rp  # noqa: E402
from rb_ss_bridge_v2.rekordbox_patch import (  # noqa: E402
    parse_entitlements_output, build_patched_entitlements, needs_patch,
    codesign_argv, apply_patch, GET_TASK_ALLOW, REKORDBOX_BUNDLE_ID,
)

APP = Path("/Applications/rekordbox 7/rekordbox.app")


class ParseEntitlementsTests(unittest.TestCase):
    def test_parses_plist_with_get_task_allow(self) -> None:
        data = plistlib.dumps({GET_TASK_ALLOW: True, "other": "x"})
        self.assertEqual(parse_entitlements_output(data).get(GET_TASK_ALLOW), True)

    def test_tolerates_leading_noise(self) -> None:
        data = b"Executable=/Applications/rekordbox 7/rekordbox.app\n" + plistlib.dumps({GET_TASK_ALLOW: True})
        self.assertEqual(parse_entitlements_output(data).get(GET_TASK_ALLOW), True)

    def test_empty_and_garbage_are_empty_dict(self) -> None:
        self.assertEqual(parse_entitlements_output(b""), {})
        self.assertEqual(parse_entitlements_output(b"code object is not signed at all"), {})


class MergeLogicTests(unittest.TestCase):
    def test_merge_adds_but_preserves(self) -> None:
        current = {"com.apple.security.device.audio-input": True, "custom": 1}
        merged = build_patched_entitlements(current)
        self.assertIs(merged[GET_TASK_ALLOW], True)
        self.assertIs(merged["com.apple.security.cs.disable-library-validation"], True)
        self.assertEqual(merged["custom"], 1)                     # preserved
        self.assertIs(merged["com.apple.security.device.audio-input"], True)  # preserved
        self.assertNotIn(GET_TASK_ALLOW, current)                # input untouched

    def test_needs_patch(self) -> None:
        self.assertTrue(needs_patch({}))
        self.assertTrue(needs_patch({GET_TASK_ALLOW: False}))
        self.assertFalse(needs_patch({GET_TASK_ALLOW: True}))


class CodesignArgvTests(unittest.TestCase):
    def test_argv_shape_and_no_deep(self) -> None:
        argv = codesign_argv(APP, Path("/tmp/e.plist"))
        self.assertEqual(argv, ["codesign", "--force", "--sign", "-",
                                "--entitlements", "/tmp/e.plist", str(APP)])
        self.assertNotIn("--deep", argv)  # nested Pioneer frameworks stay intact


def _proc(returncode=0, stdout=b"", stderr=""):
    m = mock.Mock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


class ApplyPatchGuardTests(unittest.TestCase):
    def test_refuses_non_rekordbox_bundle(self) -> None:
        with mock.patch.object(rp, "bundle_id", return_value="com.evil.app"):
            r = apply_patch(APP, dry_run=False)
        self.assertFalse(r.ok)
        self.assertEqual(r.action, "refused")

    def test_refuses_while_running(self) -> None:
        with mock.patch.object(rp, "bundle_id", return_value=REKORDBOX_BUNDLE_ID), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=True):
            r = apply_patch(APP, dry_run=False)
        self.assertFalse(r.ok)
        self.assertEqual(r.action, "refused")

    def test_already_patched_is_noop(self) -> None:
        with mock.patch.object(rp, "bundle_id", return_value=REKORDBOX_BUNDLE_ID), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=False), \
             mock.patch.object(rp, "read_entitlements", return_value={GET_TASK_ALLOW: True}):
            r = apply_patch(APP, dry_run=False)
        self.assertTrue(r.ok)
        self.assertEqual(r.action, "already_patched")

    def test_dry_run_makes_no_changes(self) -> None:
        with mock.patch.object(rp, "bundle_id", return_value=REKORDBOX_BUNDLE_ID), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=False), \
             mock.patch.object(rp, "read_entitlements", return_value={}), \
             mock.patch.object(rp.subprocess, "run") as run:
            r = apply_patch(APP, dry_run=True)
        self.assertTrue(r.ok)
        self.assertEqual(r.action, "would_patch")
        self.assertIsNotNone(r.command)
        run.assert_not_called()  # NOTHING executed in dry-run


class ApplyPatchRunTests(unittest.TestCase):
    def _apply(self, run_side_effect, after_has_gta):
        with mock.patch.object(rp, "bundle_id", return_value=REKORDBOX_BUNDLE_ID), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=False), \
             mock.patch.object(rp, "read_entitlements", return_value={}), \
             mock.patch.object(rp, "has_get_task_allow", return_value=after_has_gta), \
             mock.patch.object(rp.subprocess, "run", side_effect=run_side_effect):
            return apply_patch(APP, dry_run=False)

    def test_success(self) -> None:
        r = self._apply([_proc(0), _proc(0)], after_has_gta=True)  # codesign ok, verify ok
        self.assertTrue(r.ok)
        self.assertEqual(r.action, "patched")

    def test_codesign_failure_reports_step(self) -> None:
        r = self._apply([_proc(1, stderr="not permitted")], after_has_gta=False)
        self.assertFalse(r.ok)
        self.assertEqual(r.action, "failed")
        self.assertIn("admin", r.message.lower())  # permission hint surfaced

    def test_verify_failure_tells_user_to_reinstall(self) -> None:
        r = self._apply([_proc(0), _proc(1, stderr="invalid signature")], after_has_gta=True)
        self.assertFalse(r.ok)
        self.assertIn("reinstall", r.message.lower())

    def test_entitlement_did_not_take(self) -> None:
        r = self._apply([_proc(0), _proc(0)], after_has_gta=False)  # verify ok but gta absent
        self.assertFalse(r.ok)
        self.assertEqual(r.action, "failed")


if __name__ == "__main__":
    unittest.main()
