import unittest
import sys
from pathlib import Path


class CommandBuilderTests(unittest.TestCase):
    def test_terminal_command_builders_are_retired(self) -> None:
        scripts_dir = Path(__file__).resolve().parents[1] / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        import command_builders

        public = [name for name in dir(command_builders) if not name.startswith("_")]
        public_callables = [
            name for name in public if callable(getattr(command_builders, name))
        ]
        self.assertEqual(public_callables, [])
        self.assertFalse(any(name.startswith("build_laser_") for name in dir(command_builders)))


if __name__ == "__main__":
    unittest.main()
