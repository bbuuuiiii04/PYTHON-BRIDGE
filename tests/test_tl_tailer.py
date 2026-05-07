import sys
import tempfile
import unittest
import queue
import os
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import __main__ as bridge_main
from rb_ss_bridge_v2.__main__ import _acquire_single_instance_lock, _seed_initial_decks
from rb_ss_bridge_v2.models import Ev
from rb_ss_bridge_v2.rb_state_reader import DirectMasterStatus, RB_MASTER_DIRECT_SOURCE
from rb_ss_bridge_v2.tl_tailer import ANLZ_DIRECT_ENV, TLLogTailer, read_initial_state


def _engine_state_log(ts: datetime) -> str:
    stamp = ts.strftime("%Y-%m-%d %H:%M:%S")
    return f"""[2026-05-05 02:27:31] [info] [EVENT] Deck B playing
[{stamp}] [info] === ENGINE STATE ===
[{stamp}] [info] Input: connected
[{stamp}] [info] Master: Layer B @ 00:02:32:15 (100.0%)
[{stamp}] [info] Deck A: "Function  (Extended Mix)" @ 3:56 BPM=130.0 pitch=+0.0% [PLAYING] [ON-AIR] -> Layer A
[{stamp}] [info] Deck B: "Blow Your Brain Cell (Extended" @ 2:32 BPM=145.0 pitch=+11.5% [PLAYING] [MASTER] [ON-AIR] -> Layer B
[{stamp}] [info] Deck C: (empty)
[{stamp}] [info] Deck D: (empty)
[{stamp}] [info] Layer A: Deck A, TC=00:03:56:03, 100.0% [ACTIVE]
[{stamp}] [info] Layer B: Deck B, TC=00:02:32:15, 111.5% [ACTIVE]
[{stamp}] [info] Layer C: (unassigned)
[{stamp}] [info] Layer D: (unassigned)
[{stamp}] [info] ====================
"""


class TLInitialStateTests(unittest.TestCase):
    def tearDown(self) -> None:
        if bridge_main._LOCK_FD is not None:
            os.close(bridge_main._LOCK_FD)
            bridge_main._LOCK_FD = None

    def test_bridge_single_instance_lock_rejects_second_owner(self) -> None:
        original_path = bridge_main._LOCK_PATH
        with tempfile.TemporaryDirectory() as td:
            bridge_main._LOCK_PATH = str(Path(td) / "bridge.lock")
            try:
                self.assertTrue(_acquire_single_instance_lock())
                self.assertFalse(_acquire_single_instance_lock())
            finally:
                bridge_main._LOCK_PATH = original_path

    def test_read_initial_state_parses_fresh_loaded_decks(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            log_path = Path(td) / "timecodelink.log"
            log_path.write_text(_engine_state_log(datetime.now()), encoding="utf-8")

            init = read_initial_state(log_path)

        self.assertEqual(init["active_deck"], 2)
        self.assertEqual(set(init["decks"].keys()), {1, 2})
        self.assertEqual(init["decks"][2]["title"], "Blow Your Brain Cell (Extended")
        self.assertEqual(init["decks"][2]["bpm"], 145.0)
        self.assertTrue(init["decks"][2]["playing"])
        self.assertEqual(init["decks"][2]["elapsed_ms"], 152500)
        self.assertAlmostEqual(init["decks"][2]["pitch_factor"], 1.115)

    def test_read_initial_state_skips_stale_loaded_decks(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            log_path = Path(td) / "timecodelink.log"
            log_path.write_text(
                _engine_state_log(datetime.now() - timedelta(minutes=5)),
                encoding="utf-8",
            )

            init = read_initial_state(log_path)

        self.assertEqual(init["active_deck"], 2)
        self.assertEqual(init["decks"], {})

    def test_seed_initial_decks_enqueues_events_in_startup_order(self) -> None:
        q: queue.Queue = queue.Queue()

        _seed_initial_decks(q, {
            "decks": {
                2: {
                    "title": "Loaded Before Bridge",
                    "bpm": 145.0,
                    "elapsed_ms": 2271,
                    "pitch_factor": 1.0,
                    "playing": True,
                },
            },
        })

        events = []
        while not q.empty():
            events.append(q.get_nowait())

        self.assertEqual([ev.kind for ev in events], [
            Ev.TRACK_LOADED,
            Ev.BPM_UPDATE,
            Ev.TC_UPDATE,
            Ev.PLAY,
        ])
        self.assertEqual([ev.deck for ev in events], [2, 2, 2, 2])
        self.assertEqual(events[0].payload["title"], "Loaded Before Bridge")
        self.assertEqual(events[0].source, "initial_engine_state")

    def test_tl_anlz_path_bypassed_when_direct_enabled(self) -> None:
        q: queue.Queue = queue.Queue()
        tailer = TLLogTailer(Path("/tmp/no-such-log"), q)

        with unittest.mock.patch.dict(os.environ, {}, clear=True):
            tailer._process_line('AnlzParser: parsed 123 beats from "/tmp/ANLZ0000.DAT"')
            tailer._process_line("Deck 0 ANLZ loaded: 123 beats")
        ev = q.get_nowait()
        self.assertEqual(ev.kind, Ev.ANLZ_PATH)
        self.assertEqual(ev.source, "tl_log")

        q = queue.Queue()
        tailer = TLLogTailer(Path("/tmp/no-such-log"), q)
        with unittest.mock.patch.dict(os.environ, {ANLZ_DIRECT_ENV: "1"}, clear=True):
            tailer._process_line('AnlzParser: parsed 123 beats from "/tmp/ANLZ0000.DAT"')
            tailer._process_line("Deck 0 ANLZ loaded: 123 beats")
        self.assertTrue(q.empty())

    def test_direct_master_startup_seed_uses_stable_direct_deck(self) -> None:
        statuses = [
            DirectMasterStatus(
                attempted=True,
                supported=True,
                available=True,
                readable=True,
                source=RB_MASTER_DIRECT_SOURCE,
                reason="ok",
                rb_version="7.2.11",
                rb_raw=1,
                bridge_deck=2,
                pid=123,
                base=0x1000,
            ),
            DirectMasterStatus(
                attempted=True,
                supported=True,
                available=True,
                readable=True,
                source=RB_MASTER_DIRECT_SOURCE,
                reason="ok",
                rb_version="7.2.11",
                rb_raw=1,
                bridge_deck=2,
                pid=123,
                base=0x1000,
            ),
        ]
        with unittest.mock.patch.dict(os.environ, {bridge_main.MASTER_SEED_DIRECT_ENV: "1"}, clear=True):
            with unittest.mock.patch.object(bridge_main, "read_direct_master_status", side_effect=statuses):
                with unittest.mock.patch.object(bridge_main.time, "sleep"):
                    deck, source = bridge_main._direct_master_startup_seed("7.2.11", 1)
        self.assertEqual(deck, 2)
        self.assertEqual(source, "direct master seed")

    def test_direct_master_startup_seed_falls_back_on_unstable_direct_deck(self) -> None:
        statuses = [
            DirectMasterStatus(
                attempted=True,
                supported=True,
                available=True,
                readable=True,
                source=RB_MASTER_DIRECT_SOURCE,
                reason="ok",
                rb_version="7.2.11",
                rb_raw=1,
                bridge_deck=2,
            ),
            DirectMasterStatus(
                attempted=True,
                supported=True,
                available=True,
                readable=True,
                source=RB_MASTER_DIRECT_SOURCE,
                reason="ok",
                rb_version="7.2.11",
                rb_raw=0,
                bridge_deck=1,
            ),
        ]
        with unittest.mock.patch.dict(os.environ, {bridge_main.MASTER_SEED_DIRECT_ENV: "1"}, clear=True):
            with unittest.mock.patch.object(bridge_main, "read_direct_master_status", side_effect=statuses):
                with unittest.mock.patch.object(bridge_main.time, "sleep"):
                    deck, source = bridge_main._direct_master_startup_seed("7.2.11", 1)
        self.assertEqual(deck, 1)
        self.assertEqual(source, "TL ENGINE STATE")


if __name__ == "__main__":
    unittest.main()
