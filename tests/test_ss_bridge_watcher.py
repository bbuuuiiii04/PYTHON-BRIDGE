from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
import textwrap
import unittest
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WATCHER = REPO_ROOT / "scripts" / "ss_bridge_watcher.sh"


@dataclass(frozen=True)
class WatcherRun:
    returncode: int
    stdout: str
    stderr: str
    streamdeck_log: str
    watcher_log: str
    pkill_calls: str
    python_calls: str


class SSBridgeWatcherTests(unittest.TestCase):
    def _write_executable(self, path: Path, body: str) -> None:
        path.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
        path.chmod(0o755)

    def _run_watcher_functions(self, body: str) -> WatcherRun:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            pgrep_state = root / "pgrep_state"
            streamdeck_log = root / "streamdeck.log"
            watcher_log = root / "bridge.log"
            pkill_calls = root / "pkill.calls"
            python_calls = root / "python.calls"
            pgrep_state.write_text("stopped", encoding="utf-8")

            self._write_executable(
                bin_dir / "pgrep",
                """
                #!/bin/sh
                if [ -n "${PGREP_PIDS:-}" ]; then
                    printf '%s\\n' $PGREP_PIDS
                    exit 0
                fi
                if [ "$(cat "$PGREP_STATE_FILE" 2>/dev/null)" = "running" ]; then
                    exit 0
                fi
                exit 1
                """,
            )
            self._write_executable(
                bin_dir / "ps",
                """
                #!/bin/sh
                printf '%s\\n' "${PS_TTY:-??}"
                """,
            )
            self._write_executable(
                bin_dir / "pkill",
                """
                #!/bin/sh
                printf '%s\\n' "$*" >> "$PKILL_CALLS"
                """,
            )
            self._write_executable(
                bin_dir / "osascript",
                """
                #!/bin/sh
                exit 0
                """,
            )
            self._write_executable(
                bin_dir / "date",
                """
                #!/bin/sh
                if [ "${1:-}" = "+%s" ]; then
                    echo 123
                else
                    echo 2026-07-04T12:00:00
                fi
                """,
            )
            self._write_executable(
                bin_dir / "python3",
                """
                #!/bin/sh
                printf '%s\\n' "$*" >> "$PYTHON_CALLS"
                """,
            )

            env = os.environ.copy()
            env.update(
                {
                    "PATH": f"{bin_dir}{os.pathsep}{env.get('PATH', '')}",
                    "WATCHER_NO_LOOP": "1",
                    "STREAMDECK_LOG": str(streamdeck_log),
                    "LOG_FILE": str(watcher_log),
                    "PYTHON": str(bin_dir / "python3"),
                    "PGREP_STATE_FILE": str(pgrep_state),
                    "PKILL_CALLS": str(pkill_calls),
                    "PYTHON_CALLS": str(python_calls),
                }
            )
            script = "\n".join(
                [
                    "set -euo pipefail",
                    f"source {shlex.quote(str(WATCHER))}",
                    "trap - EXIT INT TERM",
                    body,
                ]
            )
            result = subprocess.run(
                ["bash", "-c", script],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            return WatcherRun(
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                streamdeck_log=streamdeck_log.read_text(encoding="utf-8")
                if streamdeck_log.exists()
                else "",
                watcher_log=watcher_log.read_text(encoding="utf-8")
                if watcher_log.exists()
                else "",
                pkill_calls=pkill_calls.read_text(encoding="utf-8")
                if pkill_calls.exists()
                else "",
                python_calls=python_calls.read_text(encoding="utf-8")
                if python_calls.exists()
                else "",
            )

    def test_stop_streamdeck_writes_reason_to_deck_log(self) -> None:
        run = self._run_watcher_functions(
            """
            printf running > "$PGREP_STATE_FILE"
            stop_streamdeck some_reason
            """
        )

        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn(
            "2026-07-04T12:00:00 [watcher] stopping streamdeck reason=some_reason",
            run.streamdeck_log,
        )
        self.assertIn("stopped streamdeck reason=some_reason", run.watcher_log)
        self.assertIn("streamdeck_midi", run.pkill_calls)

    def test_start_streamdeck_noops_when_running_and_spawns_when_missing(self) -> None:
        run = self._run_watcher_functions(
            """
            printf running > "$PGREP_STATE_FILE"
            start_streamdeck
            printf stopped > "$PGREP_STATE_FILE"
            start_streamdeck
            wait
            """
        )

        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.python_calls.count("streamdeck_midi.py"), 1)
        self.assertIn("started streamdeck pid=", run.watcher_log)

    # monitor_open must only count a viewer that still owns a terminal: a
    # headless orphan bridge_view.py (tty "??", ppid 1) left behind by a
    # close race suppressed open_monitor forever -- the 2026-07-05 "menubar
    # start but no viewer window" regression.
    def test_monitor_open_ignores_headless_viewer(self) -> None:
        run = self._run_watcher_functions(
            """
            export PGREP_PIDS="4242"
            export PS_TTY="??"
            if monitor_open; then echo MONITOR=open; else echo MONITOR=closed; fi
            """
        )

        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("MONITOR=closed", run.stdout)

    def test_monitor_open_counts_viewer_with_tty(self) -> None:
        run = self._run_watcher_functions(
            """
            export PGREP_PIDS="4242"
            export PS_TTY="ttys012"
            if monitor_open; then echo MONITOR=open; else echo MONITOR=closed; fi
            """
        )

        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("MONITOR=open", run.stdout)

    def test_monitor_open_no_processes_reports_closed(self) -> None:
        run = self._run_watcher_functions(
            """
            if monitor_open; then echo MONITOR=open; else echo MONITOR=closed; fi
            """
        )

        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("MONITOR=closed", run.stdout)

    # close_monitor must kill the python viewer by its full path, not just the
    # RBSS_BRIDGE_MONITOR marker: the marker lives on the wrapper bash's argv
    # only, so a marker-only pkill orphans the viewer.
    def test_close_monitor_kills_viewer_by_full_path(self) -> None:
        run = self._run_watcher_functions(
            """
            close_monitor
            """
        )

        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("RBSS_BRIDGE_MONITOR", run.pkill_calls)
        self.assertIn("bridge_view", run.pkill_calls)

