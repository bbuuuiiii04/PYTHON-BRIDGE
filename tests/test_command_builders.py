from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = _ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from command_builders import build_laser_wizard_command  # noqa: E402


class CommandBuilderTests(unittest.TestCase):
    def test_wizard_command_uses_repo_parent_for_module_launch(self) -> None:
        script_path = Path("/Users/bbui/rb_ss_bridge_v2/scripts/bridge_menubar.py")
        command = build_laser_wizard_command(script_path)
        self.assertIn("cd /Users/bbui", command)
        self.assertNotIn("cd /Users/bbui/rb_ss_bridge_v2 &&", command)

    def test_wizard_command_contains_module_launch(self) -> None:
        script_path = Path("/Users/bbui/rb_ss_bridge_v2/scripts/bridge_menubar.py")
        command = build_laser_wizard_command(script_path)
        self.assertIn("python3 -m rb_ss_bridge_v2.tools.laser_map_wizard", command)


if __name__ == "__main__":
    unittest.main()
