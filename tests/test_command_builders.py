from __future__ import annotations

import runpy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = _ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from command_builders import build_laser_wizard_command  # noqa: E402


class CommandBuilderTests(unittest.TestCase):
    def test_wizard_command_uses_repo_parent_for_module_launch(self) -> None:
        script_path = Path("/Users/bbui/rb_ss_bridge_v2/scripts/bridge_menubar.py")
        command = build_laser_wizard_command(script_path)
        self.assertTrue(command.startswith("cd /Users/bbui && python3 -m"))

    def test_wizard_command_contains_module_launch(self) -> None:
        script_path = Path("/Users/bbui/rb_ss_bridge_v2/scripts/bridge_menubar.py")
        command = build_laser_wizard_command(script_path)
        self.assertIn("python3 -m rb_ss_bridge_v2.tools.laser_map_wizard", command)

    def test_wizard_command_contains_script_fallback_launch(self) -> None:
        script_path = Path("/Users/bbui/rb_ss_bridge_v2/scripts/bridge_menubar.py")
        command = build_laser_wizard_command(script_path)
        self.assertIn("python3 scripts/laser_map_wizard.py", command)

    def test_fallback_script_imports_when_repo_parent_missing_from_sys_path(self) -> None:
        script_path = _ROOT / "scripts" / "laser_map_wizard.py"
        original_sys_path = list(sys.path)
        scrubbed = [
            entry
            for entry in original_sys_path
            if entry
            and Path(entry).resolve()
            not in {
                _ROOT.resolve(),
                _ROOT.parent.resolve(),
            }
        ]
        modules_to_clear = [
            name
            for name in list(sys.modules)
            if name == "rb_ss_bridge_v2" or name.startswith("rb_ss_bridge_v2.")
        ]
        saved_modules = {
            name: sys.modules.pop(name)
            for name in modules_to_clear
            if name in sys.modules
        }
        try:
            with patch.object(sys, "path", scrubbed):
                loaded = runpy.run_path(str(script_path))
        finally:
            sys.modules.update(saved_modules)
        self.assertIn("main", loaded)
        self.assertEqual(loaded["REPO_PARENT"], _ROOT.parent)


if __name__ == "__main__":
    unittest.main()
