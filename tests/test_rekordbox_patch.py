"""Tests for rekordbox_patch — the consent-gated Rekordbox get-task-allow patch.

All codesign/pgrep calls are mocked; no real re-signing happens.
"""
from __future__ import annotations

import base64
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
        self.assertNotIn("com.apple.security.cs.disable-library-validation", merged)
        self.assertNotIn("com.apple.security.cs.allow-unsigned-executable-memory", merged)
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


class TargetIdentityAndSignatureTests(unittest.TestCase):
    def test_malformed_info_plist_fails_closed(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / "rekordbox.app"
            (app / "Contents").mkdir(parents=True)
            (app / "Contents" / "Info.plist").write_bytes(b"not a plist")
            self.assertEqual(rp.bundle_id(app), "")

    def test_valid_target_patch_requires_entitlement_and_signature(self) -> None:
        with mock.patch.object(rp, "has_get_task_allow", return_value=True), \
             mock.patch.object(rp, "verify_signature", return_value=(True, "")):
            self.assertTrue(rp.has_valid_target_patch(APP))
        with mock.patch.object(rp, "has_get_task_allow", return_value=True), \
             mock.patch.object(rp, "verify_signature", return_value=(False, "invalid")):
            self.assertFalse(rp.has_valid_target_patch(APP))
        with mock.patch.object(rp, "has_get_task_allow", return_value=False), \
             mock.patch.object(rp, "verify_signature") as verify:
            self.assertFalse(rp.has_valid_target_patch(APP))
        verify.assert_not_called()


class SignPlanPureSeamTests(unittest.TestCase):
    """Root-only plan + privileged-sign-script seams (no nested walk)."""

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

    def test_build_sign_script_has_no_backup_or_restore_step(self) -> None:
        app = Path("/Applications/rekordbox 7/rekordbox.app")
        steps = [
            (str(app),
             ["codesign", "--force", "--sign", "-",
              "--entitlements", "/tmp/e.plist", str(app)]),
        ]
        script = rp.build_sign_script(steps)
        self.assertTrue(script.startswith("#!/bin/sh\n"))
        self.assertIn(f"RBSS_SIGNING:{app}", script)
        self.assertIn(f"RBSS_SIGN_FAIL:{app}", script)
        self.assertIn("RBSS_SIGN_OK", script)
        self.assertIn(shlex.quote(str(app)), script)
        fail_idx = script.index(f"RBSS_SIGN_FAIL:{app}")
        ok_idx = script.index("RBSS_SIGN_OK")
        self.assertLess(fail_idx, ok_idx)
        self.assertIn('exit "$rc"', script)
        # Exactly one codesign invocation in the script body.
        self.assertEqual(script.count("codesign --force --sign -"), 1)

    def test_native_sign_script_creates_entitlements_as_root(self) -> None:
        payload = plistlib.dumps({GET_TASK_ALLOW: True})
        argv = codesign_argv(APP, Path("/tmp/user-writable-entitlements.plist"))
        script = rp.build_sign_script(
            [(str(APP), argv)], entitlements_plist=payload
        )
        self.assertIn("/var/tmp/rbss_rekordbox_entitlements.XXXXXX", script)
        self.assertIn(base64.b64encode(payload).decode("ascii"), script)
        self.assertIn('"$RBSS_ENTITLEMENTS"', script)
        self.assertNotIn("/tmp/user-writable-entitlements.plist", script)
        self.assertIn("umask 077", script)
        self.assertIn("trap 'rm -f", script)

    def test_parse_sign_fail_marker(self) -> None:
        err = (
            f"RBSS_SIGNING:{APP}\n"
            f"RBSS_SIGN_FAIL:{APP}\n"
        )
        self.assertEqual(rp.parse_sign_fail_component(err), str(APP))
        self.assertIsNone(rp.parse_sign_fail_component("RBSS_SIGN_OK"))

    def test_parse_native_admin_exit_marker(self) -> None:
        output = "codesign: replacing existing signature\nRBSS_NATIVE_RC:0\n"
        self.assertEqual(
            rp.parse_native_admin_exit(output),
            (0, "codesign: replacing existing signature"),
        )
        self.assertIsNone(rp.parse_native_admin_exit("codesign: replacing existing signature"))

    def test_codesign_fail_detail_strips_markers_and_secrets(self) -> None:
        err = (
            f"RBSS_SIGN_FAIL:{APP}\n"
            "codesign: internal error in Code Signing subsystem\n"
            "Please enter your password:\n"
        )
        detail = rp._codesign_fail_detail(err)
        self.assertIn("internal error", detail)
        self.assertNotIn("RBSS_", detail)
        self.assertNotIn("password", detail.lower())


class RootOnlyApplyTests(unittest.TestCase):
    """Single root-bundle execution without a full-bundle backup."""

    def test_non_admin_runs_one_root_command_and_reports_no_backup(self) -> None:
        calls: list[list[str]] = []

        def runner(argv):
            calls.append(list(argv))
            return 1, "codesign: boom"

        with mock.patch.object(rp, "bundle_id", return_value=REKORDBOX_BUNDLE_ID), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=False), \
             mock.patch.object(rp, "read_entitlements", return_value={}), \
             mock.patch.object(rp, "plan_codesign_argvs", side_effect=_fake_plan):
            r = apply_patch(APP, dry_run=False, runner=runner)
        self.assertFalse(r.ok)
        self.assertEqual(r.action, "failed")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][-1], str(APP))
        self.assertIn("--entitlements", calls[0])
        self.assertNotIn("--deep", calls[0])
        self.assertIn("no rekordbox backup", r.message.lower())
        self.assertEqual(r.command, calls[0])

    def test_native_admin_sign_fail_names_command_and_reports_no_backup(self) -> None:
        err = (
            f"RBSS_SIGNING:{APP}\n"
            f"RBSS_SIGN_FAIL:{APP}\n"
            "codesign: boom\n"
        )
        with mock.patch.object(rp, "bundle_id", return_value=REKORDBOX_BUNDLE_ID), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=False), \
             mock.patch.object(rp, "read_entitlements", return_value={}), \
             mock.patch.object(rp, "plan_codesign_argvs", side_effect=_fake_plan), \
             mock.patch.object(rp, "run_shell_via_native_authorization", return_value=(1, err)) as shell:
            r = apply_patch(APP, dry_run=False, runner=rp.run_via_native_authorization)
        self.assertFalse(r.ok)
        self.assertEqual(r.action, "failed")
        self.assertIn(str(APP), r.message)
        self.assertIn("Failed command:", r.message)
        self.assertIn("--entitlements", r.message)
        self.assertNotIn("--deep", r.message)
        self.assertIn("no rekordbox backup", r.message.lower())
        self.assertIn("boom", r.message)
        shell.assert_called_once()
        self.assertEqual(r.command[-1], str(APP))

    def test_native_admin_cancel_is_clean_abort(self) -> None:
        with mock.patch.object(rp, "bundle_id", return_value=REKORDBOX_BUNDLE_ID), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=False), \
             mock.patch.object(rp, "read_entitlements", return_value={}), \
             mock.patch.object(rp, "plan_codesign_argvs", side_effect=_fake_plan), \
             mock.patch.object(
                 rp, "run_shell_via_native_authorization",
                 return_value=(1, "User canceled native admin authorization."),
             ):
            r = apply_patch(APP, dry_run=False, runner=rp.run_via_native_authorization)
        self.assertFalse(r.ok)
        self.assertEqual(r.action, "refused")
        self.assertIn("cancel", r.message.lower())


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

    def test_running_state_uncertainty_refuses_before_signing(self) -> None:
        runner = mock.Mock()
        with mock.patch.object(rp, "bundle_id", return_value=REKORDBOX_BUNDLE_ID), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=None):
            result = apply_patch(APP, dry_run=False, runner=runner)
        self.assertFalse(result.ok)
        self.assertEqual(result.action, "refused")
        self.assertIn("could not tell", result.message.lower())
        runner.assert_not_called()

    def test_entitlement_read_failure_refuses_before_signing(self) -> None:
        runner = mock.Mock()
        with mock.patch.object(rp, "bundle_id", return_value=REKORDBOX_BUNDLE_ID), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=False), \
             mock.patch.object(
                 rp, "read_entitlements",
                 side_effect=EntitlementsReadError("malformed output"),
            ):
            r = apply_patch(APP, dry_run=False, runner=runner)
        self.assertFalse(r.ok)
        self.assertEqual(r.action, "refused")
        self.assertIn("none are stripped", r.message.lower())
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
             mock.patch.object(rp, "read_entitlements", return_value={GET_TASK_ALLOW: True}), \
             mock.patch.object(rp, "verify_signature", return_value=(True, "")):
            r = apply_patch(APP, dry_run=False)
        self.assertTrue(r.ok)
        self.assertEqual(r.action, "already_patched")

    def test_get_task_allow_with_invalid_signature_is_repaired(self) -> None:
        runner = mock.Mock(return_value=(0, ""))
        with mock.patch.object(rp, "bundle_id", return_value=REKORDBOX_BUNDLE_ID), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=False), \
             mock.patch.object(rp, "read_entitlements", return_value={GET_TASK_ALLOW: True}), \
             mock.patch.object(
                 rp, "verify_signature", side_effect=[(False, "invalid"), (True, "")]
             ), \
             mock.patch.object(rp, "has_get_task_allow", return_value=True), \
             mock.patch.object(rp, "plan_codesign_argvs", side_effect=_fake_plan):
            result = apply_patch(APP, dry_run=False, runner=runner)
        self.assertTrue(result.ok)
        self.assertEqual(result.action, "patched")
        runner.assert_called_once()

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
    def _apply(self, verify, after_has_gta):
        with mock.patch.object(rp, "bundle_id", return_value=REKORDBOX_BUNDLE_ID), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=False), \
             mock.patch.object(rp, "read_entitlements", return_value={}), \
             mock.patch.object(rp, "has_get_task_allow", return_value=after_has_gta), \
             mock.patch.object(rp, "plan_codesign_argvs", side_effect=_fake_plan), \
             mock.patch.object(rp.subprocess, "run", return_value=verify):
            return apply_patch(APP, dry_run=False, runner=lambda argv: (0, ""))

    def test_success_does_not_make_a_full_backup(self) -> None:
        r = self._apply(_proc(0), after_has_gta=True)
        self.assertTrue(r.ok)
        self.assertEqual(r.action, "patched")
        self.assertIn("does not prove", r.message.lower())
        self.assertIn("no full rekordbox backup", r.message.lower())
        self.assertFalse(hasattr(rp, "_snapshot_app"))

    def test_verify_failure_reports_no_recovery_claim(self) -> None:
        r = self._apply(_proc(1, stderr="invalid signature"), after_has_gta=True)
        self.assertFalse(r.ok)
        self.assertEqual(r.action, "failed")
        self.assertIn("no rekordbox backup", r.message.lower())
        self.assertIn("reinstall or update", r.message.lower())
        self.assertNotIn("launchable", r.message.lower())

    def test_verify_subprocess_error_is_failed_not_crash(self) -> None:
        with mock.patch.object(rp, "bundle_id", return_value=REKORDBOX_BUNDLE_ID), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=False), \
             mock.patch.object(rp, "read_entitlements", return_value={}), \
             mock.patch.object(rp, "plan_codesign_argvs", side_effect=_fake_plan), \
             mock.patch.object(rp.subprocess, "run", side_effect=OSError("boom")):
            r = apply_patch(APP, dry_run=False, runner=lambda argv: (0, ""))
        self.assertFalse(r.ok)
        self.assertIn("no rekordbox backup", r.message.lower())

    def test_codesign_failure_reports_no_recovery_claim(self) -> None:
        with mock.patch.object(rp, "bundle_id", return_value=REKORDBOX_BUNDLE_ID), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=False), \
             mock.patch.object(rp, "read_entitlements", return_value={}), \
             mock.patch.object(rp, "plan_codesign_argvs", side_effect=_fake_plan):
            r = apply_patch(APP, dry_run=False, runner=lambda argv: (1, "codesign: boom"))
        self.assertFalse(r.ok)
        self.assertIn("no rekordbox backup", r.message.lower())

    def test_entitlement_did_not_take_reports_no_recovery_claim(self) -> None:
        r = self._apply(_proc(0), after_has_gta=False)
        self.assertFalse(r.ok)
        self.assertIn("no rekordbox backup", r.message.lower())

    def test_user_cancel_is_clean_abort(self) -> None:
        with mock.patch.object(rp, "bundle_id", return_value=REKORDBOX_BUNDLE_ID), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=False), \
             mock.patch.object(rp, "read_entitlements", return_value={}), \
             mock.patch.object(rp, "plan_codesign_argvs", side_effect=_fake_plan):
            r = apply_patch(APP, dry_run=False,
                            runner=lambda argv: (1, "execution error: User canceled. (-128)"))
        self.assertFalse(r.ok)
        self.assertEqual(r.action, "refused")

    def test_is_user_cancel(self) -> None:
        self.assertTrue(rp.is_user_cancel("User canceled native admin authorization."))
        self.assertTrue(rp.is_user_cancel("boom (-128)"))
        self.assertFalse(rp.is_user_cancel("codesign: not permitted"))

    def test_refuses_when_a_patch_is_already_running(self) -> None:
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
        self.assertEqual(called, [])


class AppManagementHintTests(unittest.TestCase):
    def test_frozen_applications_operation_not_permitted(self) -> None:
        hint = rp.app_management_block_hint(
            "codesign: Operation not permitted", APP, frozen=True,
        )
        self.assertIn("App Management", hint)
        self.assertIn("System Settings", hint)
        self.assertIn("RBSS Bridge", hint)
        self.assertIn("admin password alone is not enough", hint)
        self.assertNotIn("Use the RBSS Bridge app build", hint)

    def test_source_applications_operation_not_permitted(self) -> None:
        hint = rp.app_management_block_hint(
            "codesign: Operation not permitted", APP, frozen=False,
        )
        self.assertIn("App Management", hint)
        self.assertIn("RBSS Bridge app build that requests App Management", hint)
        self.assertNotIn("System Settings", hint)
        self.assertNotIn("admin password alone", hint)

    def test_irrelevant_errors_and_non_applications_targets_are_silent(self) -> None:
        self.assertEqual(
            rp.app_management_block_hint("codesign: boom", APP, frozen=True),
            "",
        )
        self.assertEqual(
            rp.app_management_block_hint(
                "Operation not permitted",
                Path("/tmp/rekordbox.app"),
                frozen=True,
            ),
            "",
        )
        self.assertEqual(
            rp.app_management_block_hint(
                "permission denied", APP, frozen=True,
            ),
            "",
        )

    def test_native_admin_operation_not_permitted_appends_source_hint(self) -> None:
        err = (
            f"RBSS_SIGN_FAIL:{APP}\n"
            f"{APP}: Operation not permitted\n"
        )
        with mock.patch.object(rp, "bundle_id", return_value=REKORDBOX_BUNDLE_ID), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=False), \
             mock.patch.object(rp, "read_entitlements", return_value={}), \
             mock.patch.object(rp, "plan_codesign_argvs", side_effect=_fake_plan), \
             mock.patch.object(rp, "run_shell_via_native_authorization", return_value=(1, err)), \
             mock.patch.object(rp.sys, "frozen", False, create=True):
            r = apply_patch(APP, dry_run=False, runner=rp.run_via_native_authorization)
        self.assertFalse(r.ok)
        self.assertEqual(r.action, "failed")
        self.assertIn("App Management", r.message)
        self.assertIn("RBSS Bridge app build that requests App Management", r.message)
        self.assertNotIn("admin password alone is not enough", r.message)

    def test_native_admin_unrelated_sign_fail_omits_app_management_hint(self) -> None:
        err = (
            f"RBSS_SIGN_FAIL:{APP}\n"
            "codesign: boom\n"
        )
        with mock.patch.object(rp, "bundle_id", return_value=REKORDBOX_BUNDLE_ID), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=False), \
             mock.patch.object(rp, "read_entitlements", return_value={}), \
             mock.patch.object(rp, "plan_codesign_argvs", side_effect=_fake_plan), \
             mock.patch.object(rp, "run_shell_via_native_authorization", return_value=(1, err)):
            r = apply_patch(APP, dry_run=False, runner=rp.run_via_native_authorization)
        self.assertFalse(r.ok)
        self.assertIn("boom", r.message)
        self.assertNotIn("App Management", r.message)


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
             mock.patch.object(rp.subprocess, "run", return_value=_proc(0)):  # verify only
            r = apply_patch(APP, dry_run=False, runner=fake_runner)
        self.assertTrue(r.ok)
        self.assertEqual(r.action, "patched")
        self.assertEqual(len(calls), 1)          # runner used for the codesign step
        self.assertIn("codesign", calls[0])

    def test_native_shell_carries_payload_in_argv_not_a_temp_file(self) -> None:
        script = "echo safe; codesign '/Applications/odd name.app'\n"
        argv = rp.native_shell_argv(script)
        self.assertEqual(argv[0:2], ["/bin/sh", "-c"])
        self.assertIn('/bin/sh -c "$1"', argv[2])
        self.assertNotIn(script, argv[2])
        self.assertEqual(argv[-1], script)
        self.assertFalse(any("/tmp/" in arg for arg in argv))
        with self.assertRaises(ValueError):
            rp.native_shell_argv("echo before\0echo after")

    def test_patch_lock_refuses_symlink_without_truncating_target(self) -> None:
        import tempfile

        if not hasattr(rp.os, "O_NOFOLLOW"):
            self.skipTest("platform has no O_NOFOLLOW")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            victim = root / "victim"
            victim.write_text("keep")
            (root / "rbss_rekordbox_patch.lock").symlink_to(victim)
            with mock.patch.object(rp.tempfile, "gettempdir", return_value=tmp):
                with self.assertRaises(OSError):
                    rp.open_patch_lock()
            self.assertEqual(victim.read_text(), "keep")

    def test_native_runner_wraps_one_argv_without_calling_osascript(self) -> None:
        with mock.patch.object(
            rp, "run_shell_via_native_authorization", return_value=(0, "")
        ) as shell:
            rc, detail = rp.run_via_native_authorization(
                ["codesign", "--force", "-", "/Applications/rekordbox 7/rekordbox.app"]
            )
        self.assertEqual((rc, detail), (0, ""))
        script = shell.call_args.args[0]
        self.assertTrue(script.startswith("exec codesign --force - "))
        self.assertIn("rekordbox.app", script)
        self.assertEqual(shell.call_args.kwargs["timeout"], 600)

    def test_native_runner_uses_one_combined_sign_script_without_backup(self) -> None:
        err = f"RBSS_SIGN_FAIL:{APP}\ncodesign: boom\n"
        with mock.patch.object(rp, "bundle_id", return_value=REKORDBOX_BUNDLE_ID), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=False), \
             mock.patch.object(rp, "read_entitlements", return_value={}), \
             mock.patch.object(rp, "plan_codesign_argvs", side_effect=_fake_plan), \
             mock.patch.object(rp, "run_shell_via_native_authorization", return_value=(1, err)) as shell:
            result = apply_patch(APP, dry_run=False, runner=rp.run_via_native_authorization)
        self.assertFalse(result.ok)
        self.assertIn("no rekordbox backup", result.message.lower())
        shell.assert_called_once()
        self.assertIn("RBSS_SIGN_FAIL", shell.call_args.args[0])
        self.assertNotIn("RBSS_RESTORE", shell.call_args.args[0])
        self.assertNotIn("user-writable-entitlements", shell.call_args.args[0])
        self.assertIn("$RBSS_ENTITLEMENTS", shell.call_args.args[0])


class InteractiveGuiTests(unittest.TestCase):
    def test_confirm_button_names_target_patch_not_live_reads(self) -> None:
        with mock.patch.object(
            rp, "_native_alert", return_value="Apply Patch"
        ) as native_alert:
            self.assertTrue(rp._gui_confirm("confirm"))
        native_alert.assert_called_once_with("confirm", ("Cancel", "Apply Patch"))

    def test_confirm_fails_closed_when_native_alert_cannot_open(self) -> None:
        with mock.patch.object(rp, "_native_alert", side_effect=RuntimeError("no GUI")):
            self.assertFalse(rp._gui_confirm("confirm"))

    def test_notify_does_not_turn_a_result_dialog_failure_into_a_patch_error(self) -> None:
        with mock.patch.object(rp, "_native_alert", side_effect=RuntimeError("no GUI")):
            rp._gui_notify("result")

    def test_not_found(self) -> None:
        with mock.patch.object(rp, "find_rekordbox", return_value=None), \
             mock.patch.object(rp, "_gui_notify") as notify:
            self.assertEqual(rp.run_interactive_gui(), 2)
        self.assertIn("not found", notify.call_args[0][0].lower())

    def test_unreadable_entitlements_refuses_without_prompt(self) -> None:
        with mock.patch.object(rp, "find_rekordbox", return_value=APP), \
             mock.patch.object(
                 rp, "has_valid_target_patch",
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
             mock.patch.object(rp, "has_valid_target_patch", return_value=True), \
             mock.patch.object(rp, "_gui_notify") as notify:
            self.assertEqual(rp.run_interactive_gui(), 0)
        self.assertIn("already", notify.call_args[0][0].lower())
        self.assertIn("does not prove", notify.call_args[0][0].lower())

    def test_running_refused(self) -> None:
        with mock.patch.object(rp, "find_rekordbox", return_value=APP), \
             mock.patch.object(rp, "has_valid_target_patch", return_value=False), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=True), \
             mock.patch.object(rp, "_gui_notify") as notify:
            self.assertEqual(rp.run_interactive_gui(), 1)
        self.assertIn("quit", notify.call_args[0][0].lower())

    def test_running_uncertainty_refuses_without_prompt_or_apply(self) -> None:
        with mock.patch.object(rp, "find_rekordbox", return_value=APP), \
             mock.patch.object(rp, "has_valid_target_patch", return_value=False), \
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
             mock.patch.object(rp, "has_valid_target_patch", return_value=False), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=False), \
             mock.patch.object(rp, "_gui_confirm", return_value=False) as confirm, \
             mock.patch.object(rp, "apply_patch") as ap, \
             mock.patch.object(rp, "_gui_notify"), \
             contextlib.redirect_stderr(io.StringIO()) as stderr:
            self.assertEqual(rp.run_interactive_gui(), 1)
        ap.assert_not_called()  # no consent -> no modification
        self.assertIn("User canceled", stderr.getvalue())
        confirm_text = confirm.call_args[0][0].lower()
        self.assertIn("live-unvalidated", confirm_text)
        self.assertIn("not a confirmed caller-authorization", confirm_text)

    def test_confirmed_applies_via_native_admin(self) -> None:
        with mock.patch.object(rp, "find_rekordbox", return_value=APP), \
             mock.patch.object(rp, "has_valid_target_patch", return_value=False), \
             mock.patch.object(rp, "is_rekordbox_running", return_value=False), \
             mock.patch.object(rp, "_gui_confirm", return_value=True), \
             mock.patch.object(rp, "apply_patch",
                               return_value=rp.PatchResult(True, "patched", "done")) as ap, \
             mock.patch.object(rp, "_gui_notify"):
            self.assertEqual(rp.run_interactive_gui(), 0)
        ap.assert_called_once()
        self.assertFalse(ap.call_args.kwargs["dry_run"])          # real apply, not dry-run
        self.assertIs(ap.call_args.kwargs["runner"], rp.run_via_native_authorization)


class CliConsentTests(unittest.TestCase):
    def test_check_reports_process_uncertainty(self) -> None:
        with mock.patch.object(rp, "find_rekordbox", return_value=APP), \
             mock.patch.object(rp, "has_get_task_allow", return_value=True), \
             mock.patch.object(rp, "verify_signature", return_value=(True, "")), \
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

    def test_apply_admin_uses_native_authorization(self) -> None:
        with mock.patch.object(rp, "find_rekordbox", return_value=APP), \
             mock.patch("builtins.input", return_value="YES"), \
             mock.patch.object(
                 rp, "apply_patch", return_value=rp.PatchResult(True, "patched", "ok")
             ) as ap, contextlib.redirect_stdout(io.StringIO()):
            rc = rp.main(["--apply", "--admin"])
        self.assertEqual(rc, 0)
        self.assertIs(ap.call_args.kwargs["runner"], rp.run_via_native_authorization)


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
