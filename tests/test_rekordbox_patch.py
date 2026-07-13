"""Tests for rekordbox_patch — the consent-gated Rekordbox get-task-allow patch.

All codesign/pgrep calls are mocked; no real re-signing happens.
"""
from __future__ import annotations

import contextlib
import io
import plistlib
import shlex
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import rekordbox_patch as rp  # noqa: E402
from rb_ss_bridge_v2.rekordbox_patch import (  # noqa: E402
    parse_entitlements_output, build_patched_entitlements, needs_patch,
    codesign_argv, apply_patch, EntitlementsReadError, GET_TASK_ALLOW,
    REKORDBOX_BUNDLE_ID,
)

APP = Path("/Applications/rekordbox 7/rekordbox.app")


def _fake_plan(app, ents_path, **_kwargs):
    """One-step final-only plan — keeps legacy apply tests off the real tree."""
    return [codesign_argv(app, Path(ents_path))]


def _proc(returncode=0, stdout=b"", stderr=""):
    m = mock.Mock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


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


class ReadEntitlementsTests(unittest.TestCase):
    def test_valid_empty_and_nonempty_plists_are_distinct_from_failure(self) -> None:
        with mock.patch.object(
            rp.subprocess, "run", return_value=_proc(0, stdout=plistlib.dumps({}))
        ):
            self.assertEqual(rp.read_entitlements(APP), {})
        expected = {GET_TASK_ALLOW: True, "preserve": "me"}
        with mock.patch.object(
            rp.subprocess, "run", return_value=_proc(0, stdout=plistlib.dumps(expected))
        ):
            self.assertEqual(rp.read_entitlements(APP), expected)

    def test_malformed_or_failed_codesign_raises(self) -> None:
        for proc in (
            _proc(0, stdout=b"not a plist"),
            _proc(1, stderr=b"codesign failed"),
        ):
            with self.subTest(returncode=proc.returncode), mock.patch.object(
                rp.subprocess, "run", return_value=proc
            ):
                with self.assertRaises(EntitlementsReadError):
                    rp.read_entitlements(APP)
        with mock.patch.object(rp.subprocess, "run", side_effect=OSError("missing")):
            with self.assertRaises(EntitlementsReadError):
                rp.read_entitlements(APP)


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
    def test_argv_shape_is_final_main_only_no_deep(self) -> None:
        # Deep one-shot is retired; codesign_argv is the final main-bundle step only.
        argv = codesign_argv(APP, Path("/tmp/e.plist"))
        self.assertEqual(argv, ["codesign", "--force", "--sign", "-",
                                "--entitlements", "/tmp/e.plist", str(APP)])
        self.assertNotIn("--deep", argv)


class SignPlanPureSeamTests(unittest.TestCase):
    """Root-only plan + admin-script marker seams (no nested walk)."""

    def test_plan_is_exactly_one_root_bundle_command(self) -> None:
        ents = Path("/tmp/e.plist")
        argvs = rp.plan_codesign_argvs(APP, ents)
        self.assertEqual(len(argvs), 1)
        self.assertEqual(argvs[0], codesign_argv(APP, ents))
        self.assertNotIn("--deep", argvs[0])
        self.assertNotIn("--preserve-metadata", " ".join(argvs[0]))
        # No walk/probe parameters on the compatibility seam.
        self.assertEqual(
            list(rp.plan_codesign_argvs.__code__.co_varnames[:2]),
            ["app", "entitlements_path"],
        )

    def test_build_sign_restore_script_markers_and_mid_failure_restore(self) -> None:
        app = Path("/Applications/rekordbox 7/rekordbox.app")
        backup = Path("/tmp/backup dir/rekordbox.app")
        steps = [
            (str(app),
             ["codesign", "--force", "--sign", "-",
              "--entitlements", "/tmp/e.plist", str(app)]),
        ]
        script = rp.build_sign_restore_script(steps, app, backup)
        self.assertTrue(script.startswith("#!/bin/sh\n"))
        self.assertIn(f"RBSS_SIGNING:{app}", script)
        self.assertIn(f"RBSS_SIGN_FAIL:{app}", script)
        self.assertIn("RBSS_RESTORE_OK", script)
        self.assertIn("RBSS_RESTORE_FAIL", script)
        self.assertIn("RBSS_SIGN_OK", script)
        self.assertIn(shlex.quote(str(backup)), script)
        self.assertIn(shlex.quote(str(app)), script)
        fail_idx = script.index(f"RBSS_SIGN_FAIL:{app}")
        ok_idx = script.index("RBSS_SIGN_OK")
        self.assertLess(fail_idx, ok_idx)
        self.assertIn('exit "$rc"', script)
        # Exactly one codesign invocation in the script body.
        self.assertEqual(script.count("codesign --force --sign -"), 1)

    def test_parse_sign_fail_and_restore_markers(self) -> None:
        err = (
            f"RBSS_SIGNING:{APP}\n"
            f"RBSS_SIGN_FAIL:{APP}\n"
            "RBSS_RESTORE_OK\n"
        )
        self.assertEqual(rp.parse_sign_fail_component(err), str(APP))
        self.assertEqual(rp.parse_restore_marker(err), "ok")
        self.assertEqual(rp.parse_restore_marker("RBSS_RESTORE_FAIL"), "fail")
        self.assertIsNone(rp.parse_restore_marker("RBSS_SIGN_OK"))
        self.assertIsNone(rp.parse_sign_fail_component("RBSS_SIGN_OK"))

    def test_codesign_fail_detail_strips_markers_and_secrets(self) -> None:
        err = (
            f"RBSS_SIGN_FAIL:{APP}\n"
            "RBSS_RESTORE_OK\n"
            "codesign: internal error in Code Signing subsystem\n"
            "Please enter your password:\n"
        )
        detail = rp._codesign_fail_detail(err)
        self.assertIn("internal error", detail)
        self.assertNotIn("RBSS_", detail)
        self.assertNotIn("password", detail.lower())


class RootOnlyApplyTests(unittest.TestCase):
    """Single root-bundle execution + one-admin failure markers."""

    def test_non_admin_runs_one_root_command_and_restores_once(self) -> None:
        calls: list[list[str]] = []

        def runner(argv):
            calls.append(list(argv))
            return 1, "codesign: boom"

        restore = mock.Mock(return_value=True)
        with mock.patch.object(rp, "bundle_id", return_value=REKORDBOX_BUNDLE_ID), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=False), \
             mock.patch.object(rp, "read_entitlements", return_value={}), \
             mock.patch.object(rp, "plan_codesign_argvs", side_effect=_fake_plan), \
             mock.patch.object(rp, "_snapshot_app", return_value=Path("/tmp/bk/rekordbox.app")), \
             mock.patch.object(rp, "_restore_app", restore), \
             mock.patch.object(rp, "_cleanup_backup"):
            r = apply_patch(APP, dry_run=False, runner=runner)
        self.assertFalse(r.ok)
        self.assertEqual(r.action, "failed")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][-1], str(APP))
        self.assertIn("--entitlements", calls[0])
        self.assertNotIn("--deep", calls[0])
        restore.assert_called_once()
        self.assertEqual(r.command, calls[0])

    def test_admin_sign_fail_names_command_and_skips_second_restore(self) -> None:
        restore = mock.Mock(return_value=True)
        err = (
            f"RBSS_SIGNING:{APP}\n"
            f"RBSS_SIGN_FAIL:{APP}\n"
            "RBSS_RESTORE_OK\n"
            "codesign: boom\n"
        )
        with mock.patch.object(rp, "bundle_id", return_value=REKORDBOX_BUNDLE_ID), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=False), \
             mock.patch.object(rp, "read_entitlements", return_value={}), \
             mock.patch.object(rp, "plan_codesign_argvs", side_effect=_fake_plan), \
             mock.patch.object(rp, "_snapshot_app", return_value=Path("/tmp/bk/rekordbox.app")), \
             mock.patch.object(rp, "_restore_app", restore), \
             mock.patch.object(rp, "_cleanup_backup"), \
             mock.patch.object(rp, "run_shell_via_admin", return_value=(1, err)) as shell:
            r = apply_patch(APP, dry_run=False, runner=rp.run_via_admin)
        self.assertFalse(r.ok)
        self.assertEqual(r.action, "failed")
        self.assertIn(str(APP), r.message)
        self.assertIn("Failed command:", r.message)
        self.assertIn("--entitlements", r.message)
        self.assertNotIn("--deep", r.message)
        self.assertIn("same admin step", r.message.lower())
        self.assertIn("restored", r.message.lower())
        self.assertIn("/tmp/bk", r.message)
        self.assertIn("boom", r.message)
        restore.assert_not_called()
        shell.assert_called_once()
        self.assertEqual(r.command[-1], str(APP))

    def test_admin_cancel_cleans_backup_no_restore(self) -> None:
        restore = mock.Mock(return_value=True)
        cleanup = mock.Mock()
        with mock.patch.object(rp, "bundle_id", return_value=REKORDBOX_BUNDLE_ID), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=False), \
             mock.patch.object(rp, "read_entitlements", return_value={}), \
             mock.patch.object(rp, "plan_codesign_argvs", side_effect=_fake_plan), \
             mock.patch.object(rp, "_snapshot_app", return_value=Path("/tmp/bk/rekordbox.app")), \
             mock.patch.object(rp, "_restore_app", restore), \
             mock.patch.object(rp, "_cleanup_backup", cleanup), \
             mock.patch.object(
                 rp, "run_shell_via_admin",
                 return_value=(1, "User canceled. (-128)"),
             ):
            r = apply_patch(APP, dry_run=False, runner=rp.run_via_admin)
        self.assertFalse(r.ok)
        self.assertEqual(r.action, "refused")
        self.assertIn("cancel", r.message.lower())
        restore.assert_not_called()
        cleanup.assert_called_once()

    def test_admin_restore_fail_keeps_backup_path(self) -> None:
        restore = mock.Mock(return_value=True)
        err = (
            f"RBSS_SIGN_FAIL:{APP}\n"
            "RBSS_RESTORE_FAIL\n"
        )
        with mock.patch.object(rp, "bundle_id", return_value=REKORDBOX_BUNDLE_ID), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=False), \
             mock.patch.object(rp, "read_entitlements", return_value={}), \
             mock.patch.object(rp, "plan_codesign_argvs", side_effect=_fake_plan), \
             mock.patch.object(rp, "_snapshot_app", return_value=Path("/tmp/bk/rekordbox.app")), \
             mock.patch.object(rp, "_restore_app", restore), \
             mock.patch.object(rp, "_cleanup_backup"), \
             mock.patch.object(rp, "run_shell_via_admin", return_value=(1, err)):
            r = apply_patch(APP, dry_run=False, runner=rp.run_via_admin)
        self.assertFalse(r.ok)
        self.assertIn(str(APP), r.message)
        self.assertIn("Automatic restore failed", r.message)
        self.assertIn("backed up at", r.message.lower())
        self.assertIn("/tmp/bk", r.message)
        restore.assert_not_called()

    def test_admin_missing_restore_marker_is_unconfirmed_not_fail(self) -> None:
        restore = mock.Mock(return_value=True)
        err = f"RBSS_SIGN_FAIL:{APP}\n"
        with mock.patch.object(rp, "bundle_id", return_value=REKORDBOX_BUNDLE_ID), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=False), \
             mock.patch.object(rp, "read_entitlements", return_value={}), \
             mock.patch.object(rp, "plan_codesign_argvs", side_effect=_fake_plan), \
             mock.patch.object(rp, "_snapshot_app", return_value=Path("/tmp/bk/rekordbox.app")), \
             mock.patch.object(rp, "_restore_app", restore), \
             mock.patch.object(rp, "_cleanup_backup"), \
             mock.patch.object(rp, "run_shell_via_admin", return_value=(1, err)):
            r = apply_patch(APP, dry_run=False, runner=rp.run_via_admin)
        self.assertFalse(r.ok)
        self.assertIn("could not be confirmed", r.message.lower())
        self.assertNotIn("Automatic restore failed", r.message)
        self.assertIn("/tmp/bk", r.message)
        restore.assert_not_called()


class ApplyPatchGuardTests(unittest.TestCase):
    def test_pgrep_guard_only_accepts_zero_and_one_as_known(self) -> None:
        for returncode, expected in ((0, True), (1, False), (2, None)):
            with self.subTest(returncode=returncode), mock.patch.object(
                rp.subprocess, "run", return_value=_proc(returncode)
            ):
                self.assertIs(rp.is_rekordbox_running(), expected)
        with mock.patch.object(rp.subprocess, "run", side_effect=OSError("pgrep missing")):
            self.assertIsNone(rp.is_rekordbox_running())
        with mock.patch.object(rp.subprocess, "run", side_effect=rp.subprocess.TimeoutExpired("pgrep", 10)):
            self.assertIsNone(rp.is_rekordbox_running())

    def test_running_state_uncertainty_refuses_before_snapshot_or_signing(self) -> None:
        runner = mock.Mock()
        with mock.patch.object(rp, "bundle_id", return_value=REKORDBOX_BUNDLE_ID), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=None), \
             mock.patch.object(rp, "_snapshot_app") as snapshot:
            result = apply_patch(APP, dry_run=False, runner=runner)
        self.assertFalse(result.ok)
        self.assertEqual(result.action, "refused")
        self.assertIn("could not tell", result.message.lower())
        snapshot.assert_not_called()
        runner.assert_not_called()

    def test_entitlement_read_failure_refuses_before_signing(self) -> None:
        runner = mock.Mock()
        with mock.patch.object(rp, "bundle_id", return_value=REKORDBOX_BUNDLE_ID), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=False), \
             mock.patch.object(
                 rp, "read_entitlements",
                 side_effect=EntitlementsReadError("malformed output"),
             ), mock.patch.object(rp, "_snapshot_app") as snapshot:
            r = apply_patch(APP, dry_run=False, runner=runner)
        self.assertFalse(r.ok)
        self.assertEqual(r.action, "refused")
        self.assertIn("none are stripped", r.message.lower())
        snapshot.assert_not_called()
        runner.assert_not_called()

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
             mock.patch.object(rp, "plan_codesign_argvs", side_effect=_fake_plan), \
             mock.patch.object(rp.subprocess, "run") as run:
            r = apply_patch(APP, dry_run=True)
        self.assertTrue(r.ok)
        self.assertEqual(r.action, "would_patch")
        self.assertIsNotNone(r.command)
        self.assertIsNotNone(r.commands)
        self.assertEqual(len(r.commands), 1)
        self.assertEqual(r.command, r.commands[0])
        self.assertNotIn("--deep", r.command)
        self.assertIn("Root-bundle", r.message)
        self.assertIn("exactly 1", r.message)
        self.assertNotIn("Inside-out", r.message)
        self.assertIn("no nested re-sign", r.message)
        run.assert_not_called()  # NOTHING executed in dry-run


class ApplyPatchRunTests(unittest.TestCase):
    def _apply(self, run_side_effect, after_has_gta):
        with mock.patch.object(rp, "bundle_id", return_value=REKORDBOX_BUNDLE_ID), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=False), \
             mock.patch.object(rp, "read_entitlements", return_value={}), \
             mock.patch.object(rp, "has_get_task_allow", return_value=after_has_gta), \
             mock.patch.object(rp, "plan_codesign_argvs", side_effect=_fake_plan), \
             mock.patch.object(rp, "_snapshot_app", return_value=Path("/tmp/rbss_bk/rekordbox.app")), \
             mock.patch.object(rp, "_restore_app", return_value=True), \
             mock.patch.object(rp, "_cleanup_backup"), \
             mock.patch.object(rp.subprocess, "run", side_effect=run_side_effect):
            return apply_patch(APP, dry_run=False)

    def test_success(self) -> None:
        r = self._apply([_proc(0), _proc(0)], after_has_gta=True)  # codesign ok, verify ok
        self.assertTrue(r.ok)
        self.assertEqual(r.action, "patched")
        self.assertIn("does not prove", r.message.lower())
        self.assertNotIn("will read", r.message.lower())
        self.assertIn("original app is kept", r.message.lower())

    def test_success_retains_backup_until_explicit_purge(self) -> None:
        cleanup = mock.Mock()
        with mock.patch.object(rp, "bundle_id", return_value=REKORDBOX_BUNDLE_ID), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=False), \
             mock.patch.object(rp, "read_entitlements", return_value={}), \
             mock.patch.object(rp, "has_get_task_allow", return_value=True), \
             mock.patch.object(rp, "plan_codesign_argvs", side_effect=_fake_plan), \
             mock.patch.object(
                 rp, "_snapshot_app",
                 return_value=Path("/tmp/backups/backup_1/rekordbox.app"),
             ), mock.patch.object(rp, "_cleanup_backup", cleanup), \
             mock.patch.object(rp.subprocess, "run", return_value=_proc(0)):
            r = apply_patch(APP, dry_run=False, runner=lambda argv: (0, ""))
        self.assertTrue(r.ok)
        cleanup.assert_not_called()
        self.assertIn("/tmp/backups/backup_1", r.message)
        self.assertIn("does not remove", r.message)

    def test_backup_root_is_outside_bridge_app_support(self) -> None:
        self.assertEqual(rp.BACKUP_ROOT.name, "RBSS Rekordbox Backups")
        self.assertNotIn("RBSS Bridge", rp.BACKUP_ROOT.parts)

    def test_codesign_failure_restores_and_stays_launchable(self) -> None:
        r = self._apply([_proc(1, stderr="not permitted")], after_has_gta=False)
        self.assertFalse(r.ok)
        self.assertEqual(r.action, "failed")
        self.assertIn("admin", r.message.lower())         # permission hint surfaced
        self.assertIn("launchable", r.message.lower())    # restored, NOT told to reinstall
        self.assertNotIn("reinstall", r.message.lower())

    def test_verify_failure_restores_and_stays_launchable(self) -> None:
        r = self._apply([_proc(0), _proc(1, stderr="invalid signature")], after_has_gta=True)
        self.assertFalse(r.ok)
        self.assertIn("launchable", r.message.lower())
        self.assertNotIn("reinstall", r.message.lower())

    def test_verify_subprocess_error_is_failed_not_crash(self) -> None:
        # codesign ok (via runner), but the verify subprocess.run RAISES -> caught,
        # backup restored, never left claiming "patched".
        with mock.patch.object(rp, "bundle_id", return_value=REKORDBOX_BUNDLE_ID), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=False), \
             mock.patch.object(rp, "read_entitlements", return_value={}), \
             mock.patch.object(rp, "plan_codesign_argvs", side_effect=_fake_plan), \
             mock.patch.object(rp, "_snapshot_app", return_value=Path("/tmp/rbss_bk/rekordbox.app")), \
             mock.patch.object(rp, "_restore_app", return_value=True), \
             mock.patch.object(rp, "_cleanup_backup"), \
             mock.patch.object(rp.subprocess, "run", side_effect=OSError("boom")):
            r = apply_patch(APP, dry_run=False, runner=lambda argv: (0, ""))
        self.assertFalse(r.ok)
        self.assertEqual(r.action, "failed")
        self.assertIn("launchable", r.message.lower())

    def test_refuses_when_no_disk_for_backup(self) -> None:
        # No safe backup -> refuse; NEVER re-sign (would risk an unrecoverable brick).
        with mock.patch.object(rp, "bundle_id", return_value=REKORDBOX_BUNDLE_ID), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=False), \
             mock.patch.object(rp, "read_entitlements", return_value={}), \
             mock.patch.object(rp, "_snapshot_app", return_value=None), \
             mock.patch.object(rp, "plan_codesign_argvs", side_effect=AssertionError("planned with no backup")), \
             mock.patch.object(rp.subprocess, "run", side_effect=AssertionError("re-signed with no backup")):
            r = apply_patch(APP, dry_run=False, runner=lambda argv: (0, ""))
        self.assertFalse(r.ok)
        self.assertEqual(r.action, "refused")
        self.assertIn("disk", r.message.lower())

    def test_restores_on_codesign_failure(self) -> None:
        with mock.patch.object(rp, "bundle_id", return_value=REKORDBOX_BUNDLE_ID), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=False), \
             mock.patch.object(rp, "read_entitlements", return_value={}), \
             mock.patch.object(rp, "plan_codesign_argvs", side_effect=_fake_plan), \
             mock.patch.object(rp, "_snapshot_app", return_value=Path("/tmp/bk/rekordbox.app")), \
             mock.patch.object(rp, "_restore_app", return_value=True) as restore, \
             mock.patch.object(rp, "_cleanup_backup"):
            r = apply_patch(APP, dry_run=False, runner=lambda argv: (1, "codesign: boom"))
        self.assertFalse(r.ok)
        self.assertEqual(r.action, "failed")
        restore.assert_called_once()                      # the backup WAS restored
        self.assertNotIn("reinstall", r.message.lower())

    def test_restore_failure_keeps_backup_and_says_where(self) -> None:
        with mock.patch.object(rp, "bundle_id", return_value=REKORDBOX_BUNDLE_ID), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=False), \
             mock.patch.object(rp, "read_entitlements", return_value={}), \
             mock.patch.object(rp, "plan_codesign_argvs", side_effect=_fake_plan), \
             mock.patch.object(rp, "_snapshot_app", return_value=Path("/tmp/bk/rekordbox.app")), \
             mock.patch.object(rp, "_restore_app", return_value=False):
            r = apply_patch(APP, dry_run=False, runner=lambda argv: (1, "boom"))
        self.assertFalse(r.ok)
        self.assertIn("backed up at", r.message.lower())      # tells operator WHERE
        self.assertIn("no reinstall needed", r.message.lower())  # explicit: not a reinstall

    def test_enough_disk_for_backup_boundary(self) -> None:
        gb = 1024 ** 3
        self.assertTrue(rp.enough_disk_for_backup(2 * gb, 3 * gb))    # ~1GB spare over margin
        self.assertFalse(rp.enough_disk_for_backup(2 * gb, 2 * gb))   # no room for the margin
        self.assertFalse(rp.enough_disk_for_backup(2 * gb, 1 * gb))   # not even the copy

    def test_user_cancel_is_clean_abort_no_restore(self) -> None:
        # Operator dismisses the admin prompt -> nonzero + "User canceled" -> refused,
        # NO restore attempted (codesign never ran; Rekordbox untouched; no 2nd prompt).
        restore_calls = []
        with mock.patch.object(rp, "bundle_id", return_value=REKORDBOX_BUNDLE_ID), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=False), \
             mock.patch.object(rp, "read_entitlements", return_value={}), \
             mock.patch.object(rp, "plan_codesign_argvs", side_effect=_fake_plan), \
             mock.patch.object(rp, "_snapshot_app", return_value=Path("/tmp/bk/rekordbox.app")), \
             mock.patch.object(rp, "_restore_app", side_effect=lambda *a: restore_calls.append(a) or True), \
             mock.patch.object(rp, "_cleanup_backup"):
            r = apply_patch(APP, dry_run=False,
                            runner=lambda argv: (1, "0:101: execution error: User canceled. (-128)"))
        self.assertFalse(r.ok)
        self.assertEqual(r.action, "refused")
        self.assertIn("cancel", r.message.lower())
        self.assertEqual(restore_calls, [])  # never restored -> no spurious 2nd admin prompt

    def test_is_user_cancel(self) -> None:
        self.assertTrue(rp.is_user_cancel("execution error: User canceled. (-128)"))
        self.assertTrue(rp.is_user_cancel("boom (-128)"))
        self.assertFalse(rp.is_user_cancel("codesign: not permitted"))
        self.assertFalse(rp.is_user_cancel(""))

    def test_entitlement_did_not_take(self) -> None:
        r = self._apply([_proc(0), _proc(0)], after_has_gta=False)  # verify ok but gta absent
        self.assertFalse(r.ok)
        self.assertEqual(r.action, "failed")

    def test_post_sign_entitlement_read_failure_restores(self) -> None:
        restore = mock.Mock(return_value=True)
        with mock.patch.object(rp, "bundle_id", return_value=REKORDBOX_BUNDLE_ID), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=False), \
             mock.patch.object(rp, "read_entitlements", return_value={}), \
             mock.patch.object(rp, "plan_codesign_argvs", side_effect=_fake_plan), \
             mock.patch.object(
                 rp, "has_get_task_allow",
                 side_effect=EntitlementsReadError("malformed output"),
             ), mock.patch.object(
                 rp, "_snapshot_app", return_value=Path("/tmp/bk/rekordbox.app"),
             ), mock.patch.object(rp, "_restore_app", restore), \
             mock.patch.object(rp, "_cleanup_backup"), \
             mock.patch.object(rp.subprocess, "run", return_value=_proc(0)):
            r = apply_patch(APP, dry_run=False, runner=lambda argv: (0, ""))
        self.assertFalse(r.ok)
        self.assertEqual(r.action, "failed")
        restore.assert_called_once()

    def test_refuses_when_a_patch_is_already_running(self) -> None:
        # A concurrent patch (double-click) holds the lock; the second refuses
        # instead of running a second interleaving codesign --force.
        import fcntl
        import tempfile as _tf
        lock_path = Path(_tf.gettempdir()) / "rbss_rekordbox_patch.lock"
        holder = open(lock_path, "w")
        fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
        called = []
        try:
            with mock.patch.object(rp, "bundle_id", return_value=REKORDBOX_BUNDLE_ID), \
                 mock.patch.object(rp, "is_rekordbox_running", return_value=False), \
                 mock.patch.object(rp, "read_entitlements", return_value={}):
                r = apply_patch(APP, dry_run=False, runner=lambda argv: (called.append(argv), (0, ""))[1])
        finally:
            fcntl.flock(holder, fcntl.LOCK_UN)
            holder.close()
        self.assertFalse(r.ok)
        self.assertEqual(r.action, "refused")
        self.assertEqual(called, [])  # never ran codesign while another holds the lock


class RunnerSeamTests(unittest.TestCase):
    def test_apply_patch_uses_custom_runner_for_codesign(self) -> None:
        calls = []

        def fake_runner(argv):
            calls.append(argv)
            return (0, "")

        with mock.patch.object(rp, "bundle_id", return_value=REKORDBOX_BUNDLE_ID), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=False), \
             mock.patch.object(rp, "read_entitlements", return_value={}), \
             mock.patch.object(rp, "has_get_task_allow", return_value=True), \
             mock.patch.object(rp, "plan_codesign_argvs", side_effect=_fake_plan), \
             mock.patch.object(rp, "_snapshot_app", return_value=Path("/tmp/rbss_bk/rekordbox.app")), \
             mock.patch.object(rp, "_restore_app", return_value=True), \
             mock.patch.object(rp, "_cleanup_backup"), \
             mock.patch.object(rp.subprocess, "run", return_value=_proc(0)):  # verify only
            r = apply_patch(APP, dry_run=False, runner=fake_runner)
        self.assertTrue(r.ok)
        self.assertEqual(r.action, "patched")
        self.assertEqual(len(calls), 1)          # runner used for the codesign step
        self.assertIn("codesign", calls[0])

    def test_run_via_admin_builds_safe_osascript(self) -> None:
        with mock.patch.object(rp.subprocess, "run", return_value=_proc(0)) as run:
            rc, _ = rp.run_via_admin(["codesign", "--force", "-",
                                      "/Applications/rekordbox 7/rekordbox.app"])
        self.assertEqual(rc, 0)
        argv = run.call_args[0][0]
        self.assertEqual(argv[0], "osascript")
        script_arg = argv[-1]
        self.assertIn("do shell script", script_arg)
        self.assertIn("administrator privileges", script_arg)
        # osascript only references a /bin/sh <tempfile>, never the raw codesign args
        self.assertIn("/bin/sh", script_arg)
        self.assertNotIn("rekordbox.app", script_arg)


class InteractiveGuiTests(unittest.TestCase):
    def test_confirm_button_names_target_patch_not_live_reads(self) -> None:
        with mock.patch.object(
            rp, "_osascript", return_value=_proc(0, stdout="button returned:Apply Patch")
        ) as osascript:
            self.assertTrue(rp._gui_confirm("confirm"))
        script = osascript.call_args[0][0]
        self.assertIn("Apply Patch", script)
        self.assertNotIn("Enable Reads", script)

    def test_not_found(self) -> None:
        with mock.patch.object(rp, "find_rekordbox", return_value=None), \
             mock.patch.object(rp, "_gui_notify") as notify:
            self.assertEqual(rp.run_interactive_gui(), 2)
        self.assertIn("not found", notify.call_args[0][0].lower())

    def test_unreadable_entitlements_refuses_without_prompt(self) -> None:
        with mock.patch.object(rp, "find_rekordbox", return_value=APP), \
             mock.patch.object(
                 rp, "has_get_task_allow",
                 side_effect=EntitlementsReadError("codesign failed"),
             ), mock.patch.object(rp, "_gui_notify") as notify, \
             mock.patch.object(rp, "_gui_confirm") as confirm, \
             mock.patch.object(rp, "apply_patch") as apply:
            self.assertEqual(rp.run_interactive_gui(), 1)
        self.assertIn("not modified", notify.call_args[0][0].lower())
        confirm.assert_not_called()
        apply.assert_not_called()

    def test_already_patched(self) -> None:
        with mock.patch.object(rp, "find_rekordbox", return_value=APP), \
             mock.patch.object(rp, "has_get_task_allow", return_value=True), \
             mock.patch.object(rp, "_gui_notify") as notify:
            self.assertEqual(rp.run_interactive_gui(), 0)
        self.assertIn("already", notify.call_args[0][0].lower())
        self.assertIn("does not prove", notify.call_args[0][0].lower())

    def test_running_refused(self) -> None:
        with mock.patch.object(rp, "find_rekordbox", return_value=APP), \
             mock.patch.object(rp, "has_get_task_allow", return_value=False), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=True), \
             mock.patch.object(rp, "_gui_notify") as notify:
            self.assertEqual(rp.run_interactive_gui(), 1)
        self.assertIn("quit", notify.call_args[0][0].lower())

    def test_running_uncertainty_refuses_without_prompt_or_apply(self) -> None:
        with mock.patch.object(rp, "find_rekordbox", return_value=APP), \
             mock.patch.object(rp, "has_get_task_allow", return_value=False), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=None), \
             mock.patch.object(rp, "_gui_notify") as notify, \
             mock.patch.object(rp, "_gui_confirm") as confirm, \
             mock.patch.object(rp, "apply_patch") as apply:
            self.assertEqual(rp.run_interactive_gui(), 1)
        self.assertIn("could not tell", notify.call_args[0][0].lower())
        confirm.assert_not_called()
        apply.assert_not_called()

    def test_cancelled_never_patches(self) -> None:
        with mock.patch.object(rp, "find_rekordbox", return_value=APP), \
             mock.patch.object(rp, "has_get_task_allow", return_value=False), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=False), \
             mock.patch.object(rp, "_gui_confirm", return_value=False) as confirm, \
             mock.patch.object(rp, "apply_patch") as ap, \
             mock.patch.object(rp, "_gui_notify"):
            self.assertEqual(rp.run_interactive_gui(), 1)
        ap.assert_not_called()  # no consent -> no modification
        confirm_text = confirm.call_args[0][0].lower()
        self.assertIn("live-unvalidated", confirm_text)
        self.assertIn("not a confirmed caller-authorization", confirm_text)

    def test_confirmed_applies_via_admin(self) -> None:
        with mock.patch.object(rp, "find_rekordbox", return_value=APP), \
             mock.patch.object(rp, "has_get_task_allow", return_value=False), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=False), \
             mock.patch.object(rp, "_gui_confirm", return_value=True), \
             mock.patch.object(rp, "apply_patch",
                               return_value=rp.PatchResult(True, "patched", "done")) as ap, \
             mock.patch.object(rp, "_gui_notify"):
            self.assertEqual(rp.run_interactive_gui(), 0)
        ap.assert_called_once()
        self.assertFalse(ap.call_args.kwargs["dry_run"])          # real apply, not dry-run
        self.assertIs(ap.call_args.kwargs["runner"], rp.run_via_admin)  # admin-escalated


class CliConsentTests(unittest.TestCase):
    def test_check_reports_process_uncertainty(self) -> None:
        with mock.patch.object(rp, "find_rekordbox", return_value=APP), \
             mock.patch.object(rp, "has_get_task_allow", return_value=True), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=None), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            rc = rp.main(["--check"])
        self.assertEqual(rc, 4)
        self.assertIn("unknown", output.getvalue())

    def test_apply_aborts_without_typed_yes(self) -> None:
        with mock.patch.object(rp, "find_rekordbox", return_value=APP), \
             mock.patch("builtins.input", return_value="no"), \
             mock.patch.object(rp, "apply_patch") as ap, \
             contextlib.redirect_stdout(io.StringIO()):
            rc = rp.main(["--apply"])
        self.assertEqual(rc, 1)
        ap.assert_not_called()          # no typed YES -> no re-sign

    def test_apply_proceeds_only_on_typed_yes(self) -> None:
        with mock.patch.object(rp, "find_rekordbox", return_value=APP), \
             mock.patch("builtins.input", return_value="YES"), \
             mock.patch.object(rp, "apply_patch",
                               return_value=rp.PatchResult(True, "patched", "ok")) as ap, \
             contextlib.redirect_stdout(io.StringIO()):
            rc = rp.main(["--apply"])
        self.assertEqual(rc, 0)
        ap.assert_called_once()
        self.assertFalse(ap.call_args.kwargs["dry_run"])


class SanitizedSystemEnvTests(unittest.TestCase):
    """DEFECT-3: system-tool subprocesses must not inherit PyInstaller's bundle
    DYLD_* pollution; restore each var from its *_ORIG (or drop it)."""

    def test_restores_orig_and_strips_bookkeeping(self) -> None:
        env = {
            "PATH": "/usr/bin",
            "DYLD_LIBRARY_PATH": "/bundle/Frameworks",   # bundle value
            "DYLD_LIBRARY_PATH_ORIG": "/orig/lib",        # pre-launch value
            "DYLD_FRAMEWORK_PATH": "/bundle/fw",          # no _ORIG -> drop entirely
        }
        out = rp.sanitized_system_env(env)
        self.assertEqual(out["DYLD_LIBRARY_PATH"], "/orig/lib")  # restored
        self.assertNotIn("DYLD_LIBRARY_PATH_ORIG", out)          # bookkeeping gone
        self.assertNotIn("DYLD_FRAMEWORK_PATH", out)             # no orig -> removed
        self.assertEqual(out["PATH"], "/usr/bin")                # untouched
        self.assertIn("DYLD_FRAMEWORK_PATH", env)                # input not mutated

    def test_clean_env_passthrough(self) -> None:
        env = {"PATH": "/usr/bin", "HOME": "/Users/x"}
        self.assertEqual(rp.sanitized_system_env(env), env)


if __name__ == "__main__":
    unittest.main()
