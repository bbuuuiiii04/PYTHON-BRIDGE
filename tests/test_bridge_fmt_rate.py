from __future__ import annotations

import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.bridge_fmt import log_changed, log_throttled  # noqa: E402


class LogChangedTest(unittest.TestCase):
    def test_first_true_then_false_until_change(self) -> None:
        k = "t_changed_1"
        self.assertTrue(log_changed(k, "a"))
        self.assertFalse(log_changed(k, "a"))
        self.assertTrue(log_changed(k, "b"))
        self.assertFalse(log_changed(k, "b"))

    def test_independent_keys(self) -> None:
        self.assertTrue(log_changed("t_changed_2", 1))
        self.assertTrue(log_changed("t_changed_3", 1))
        self.assertFalse(log_changed("t_changed_2", 1))


class LogThrottledTest(unittest.TestCase):
    def test_one_per_interval_injected_clock(self) -> None:
        k = "t_throttle_1"
        self.assertTrue(log_throttled(k, 1.0, now=100.0))
        self.assertFalse(log_throttled(k, 1.0, now=100.5))
        self.assertTrue(log_throttled(k, 1.0, now=101.0))
        self.assertFalse(log_throttled(k, 1.0, now=101.2))

    def test_independent_keys(self) -> None:
        self.assertTrue(log_throttled("t_throttle_2", 5.0, now=0.0))
        self.assertTrue(log_throttled("t_throttle_3", 5.0, now=0.0))
        self.assertFalse(log_throttled("t_throttle_2", 5.0, now=1.0))

    def test_threaded_independent_keys(self) -> None:
        results: list[bool] = []
        lock = threading.Lock()

        def _worker(index: int) -> None:
            ok = log_throttled(f"t_threaded_throttle_{index}", 1.0, now=10.0)
            with lock:
                results.append(ok)

        threads = [threading.Thread(target=_worker, args=(i,)) for i in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(results, [True] * 8)

    def test_threaded_same_key_only_one_emit(self) -> None:
        results: list[bool] = []
        lock = threading.Lock()

        def _worker() -> None:
            ok = log_throttled("t_threaded_same_key", 1.0, now=20.0)
            with lock:
                results.append(ok)

        threads = [threading.Thread(target=_worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(results.count(True), 1)
        self.assertEqual(results.count(False), 7)


if __name__ == "__main__":
    unittest.main()
