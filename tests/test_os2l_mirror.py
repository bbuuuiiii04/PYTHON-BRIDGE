import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.os2l_mirror import OS2LMirror  # noqa: E402
from rb_ss_bridge_v2.osl_output import OS2LConnection  # noqa: E402


class OS2LMirrorTests(unittest.TestCase):
    def test_records_classified_packet_when_enabled(self) -> None:
        mirror = OS2LMirror(ring_size=3)
        mirror.set_enabled(True)

        mirror.record({"evt": "subscribed", "trigger": "deck 2 get_bpm", "value": 128.0}, "queued")

        summary = mirror.get_summary()
        self.assertTrue(summary["enabled"])
        self.assertEqual(summary["ring_size"], 1)
        self.assertEqual(summary["last_packet"]["packet_kind"], "subscribed")
        self.assertEqual(summary["last_packet"]["deck"], 2)
        self.assertEqual(summary["last_packet"]["outcome"], "queued")

    def test_ring_is_bounded(self) -> None:
        mirror = OS2LMirror(ring_size=2)
        mirror.set_enabled(True)

        for deck in (1, 2, 3):
            mirror.record({"evt": "beat", "deck": deck}, "queued")

        summary = mirror.get_summary()
        self.assertEqual(summary["ring_size"], 2)
        self.assertEqual(summary["last_packet"]["deck"], 3)


class OS2LConnectionMirrorTests(unittest.TestCase):
    def test_send_records_queue_outcome(self) -> None:
        conn = OS2LConnection()
        mirror = OS2LMirror()
        mirror.set_enabled(True)
        conn.set_mirror(mirror)

        conn.send({"evt": "beat", "deck": 1, "bpm": 128.0})

        summary = mirror.get_summary()
        self.assertEqual(summary["last_packet"]["outcome"], "queued")
        self.assertEqual(conn.status()["queue_size"], 1)

    def test_sender_records_no_socket_drop(self) -> None:
        conn = OS2LConnection()
        mirror = OS2LMirror()
        mirror.set_enabled(True)
        conn.set_mirror(mirror)

        conn.send({"evt": "beat", "deck": 1, "bpm": 128.0})
        item = conn._send_q.get_nowait()
        self.assertIsNotNone(item)
        msg, obj = item
        self.assertGreater(len(msg), 0)
        self.assertEqual(obj["deck"], 1)
        mirror.record(obj, "no_socket_drop")

        summary = mirror.get_summary()
        self.assertEqual(summary["last_packet"]["outcome"], "no_socket_drop")


if __name__ == "__main__":
    unittest.main()
