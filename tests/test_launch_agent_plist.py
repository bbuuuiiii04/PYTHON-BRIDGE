"""Cover the LaunchAgent plist generator (launch_agent_plist.py) + the AWR-151
ProcessType=Interactive guard via tools/check_launch_agents.py."""
from __future__ import annotations

import plistlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.launch_agent_plist import (  # noqa: E402
    DEFAULT_LABEL,
    render_launch_agent,
    write_launch_agent,
)
from rb_ss_bridge_v2.tools.check_launch_agents import check  # noqa: E402

# A binary path whose name carries the marker check_launch_agents keys on, but
# which does not exist (so its interpreter version-probe fails gracefully and is
# skipped rather than actually executing anything).
FAKE_APP = "/nonexistent/RBSS Bridge.app/Contents/MacOS/rb_ss_bridge_v2"


class RenderTests(unittest.TestCase):
    def test_render_sets_interactive_and_args(self) -> None:
        data = plistlib.loads(render_launch_agent([FAKE_APP, "--run-bridge"]))
        self.assertEqual(data["ProcessType"], "Interactive")
        self.assertEqual(data["ProgramArguments"], [FAKE_APP, "--run-bridge"])
        self.assertEqual(data["Label"], DEFAULT_LABEL)

    def test_empty_args_rejected(self) -> None:
        with self.assertRaises(ValueError):
            render_launch_agent([])


class CheckLaunchAgentsTests(unittest.TestCase):
    def test_generated_plist_passes_the_advisory_checker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            write_launch_agent(Path(tmp) / "com.bbui.rb-ss-bridge-v2-launcher.plist",
                               [FAKE_APP, "--run-bridge"])
            self.assertEqual(check(Path(tmp)), [])

    def test_missing_processtype_is_flagged(self) -> None:
        # Prove the checker actually guards: a plist WITHOUT Process=Interactive
        # (but still marked as a bridge plist) must produce a finding.
        with tempfile.TemporaryDirectory() as tmp:
            bad = {
                "Label": "com.bbui.bad",
                "ProgramArguments": [FAKE_APP, "--run-bridge"],
                # no ProcessType
            }
            (Path(tmp) / "bad.plist").write_bytes(plistlib.dumps(bad))
            findings = check(Path(tmp))
            self.assertTrue(findings)
            self.assertTrue(any("ProcessType" in f for f in findings))


if __name__ == "__main__":
    unittest.main()
