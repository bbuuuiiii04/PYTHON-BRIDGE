"""Session runner: recovery, active time, one-per-day, tamper (tests D10, D11)."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tools.spectral_pilot import session as S
from tools.spectral_pilot.session import Gate1Error, SessionRunner, WorkloadError

SEED = "seed"


class Clock:
    """Deterministic UTC clock, +5s per call."""
    def __init__(self, start=0):
        self.t = start

    def __call__(self):
        self.t += 5
        return datetime.fromtimestamp(self.t, tz=timezone.utc).isoformat()


def manifest():
    return [
        {"card_id": "c0", "card_type": "marker_state"},
        {"card_id": "c1", "card_type": "marker_state"},
        {"card_id": "c2", "card_type": "family_montage"},
        {"card_id": "c3", "card_type": "anchor_confirm"},
    ]


def runner(ws, clock, date="D1"):
    return SessionRunner(ws, manifest(), pilot_seed=SEED, clock=clock, local_date=lambda: date)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self._tmp.name)
        self.clock = Clock()

    def tearDown(self):
        self._tmp.cleanup()

    def test_resume_at_first_unanswered_zero_extra_decisions(self):
        r = runner(self.ws, self.clock)
        r.start_session("P1")
        r.play("c0"); r.commit("c0", "state", "not_genuine", "not_genuine", recognized=False, response_seconds=1.0)
        r.play("c1"); r.commit("c1", "state", "genuine", "genuine", recognized=False, response_seconds=1.0)
        self.assertEqual(r.decisions_total(), 2)

        r2 = runner(self.ws, self.clock)     # simulate restart
        state = r2.resume()
        self.assertEqual(state.first_unanswered_index, 1)   # c1 still needs hardness
        self.assertEqual(state.decisions_total, 2)          # no extra decisions on resume

    def test_re_exposed_card_played_without_commit(self):
        r = runner(self.ws, self.clock)
        r.start_session("P1")
        # close c0 and c1
        r.play("c0"); r.commit("c0", "state", "not_genuine", "not_genuine", recognized=False, response_seconds=1.0)
        r.play("c1"); r.commit("c1", "state", "not_genuine", "not_genuine", recognized=False, response_seconds=1.0)
        r.play("c2")                          # family card played, never committed -> crash
        r2 = runner(self.ws, self.clock)
        state = r2.resume()
        self.assertEqual(state.re_exposed_card_ids, ["c2"])
        self.assertEqual(state.first_unanswered_index, 2)

    def test_active_time_segments_sum(self):
        r = runner(self.ws, self.clock)
        r.start_session("P1")
        r.play("c0"); r.commit("c0", "state", "not_genuine", "not_genuine", recognized=False, response_seconds=1.0)
        # segment 1 span: play@5 .. commit@10 = 5s
        r2 = runner(self.ws, self.clock)      # restart -> new segment
        r2.start_session("P1", resume=True)
        r2.play("c1"); r2.commit("c1", "state", "not_genuine", "not_genuine", recognized=False, response_seconds=1.0)
        # segment 2 span: play@15 .. commit@20 = 5s
        self.assertEqual(r2.active_seconds(), 10.0)

    def test_tampered_chain_hard_fails(self):
        r = runner(self.ws, self.clock)
        r.start_session("P1")
        r.play("c0"); r.commit("c0", "state", "not_genuine", "not_genuine", recognized=False, response_seconds=1.0)
        r.play("c1"); r.commit("c1", "state", "genuine", "genuine", recognized=False, response_seconds=1.0)
        # corrupt the first response row's payload
        p = self.ws / "responses.jsonl"
        rows = [json.loads(x) for x in p.read_text().splitlines()]
        rows[0]["recognized"] = True
        p.write_text("".join(json.dumps(x, sort_keys=True) + "\n" for x in rows))
        with self.assertRaises(Gate1Error):
            runner(self.ws, self.clock)

    def test_torn_tail_dropped_and_flagged(self):
        r = runner(self.ws, self.clock)
        r.start_session("P1")
        r.play("c0"); r.commit("c0", "state", "not_genuine", "not_genuine", recognized=False, response_seconds=1.0)
        with (self.ws / "responses.jsonl").open("a") as fh:
            fh.write('{"partial": ')          # torn trailing record, no newline
        r2 = runner(self.ws, self.clock)
        state = r2.resume()
        self.assertTrue(state.torn_tail)
        self.assertEqual(state.decisions_total, 1)   # good row survived

    def test_order_drift_hard_fails_on_reload(self):
        r = runner(self.ws, self.clock)
        r.start_session("P1")
        r.play("c2"); r.commit("c2", "family", "WALL", "WALL", recognized=False, response_seconds=1.0)
        r.play("c0"); r.commit("c0", "state", "not_genuine", "not_genuine", recognized=False, response_seconds=1.0)
        with self.assertRaises(Gate1Error):
            runner(self.ws, self.clock)      # c0 answered after c2 -> out of frozen order

    def test_immutable_no_recommit(self):
        r = runner(self.ws, self.clock)
        r.start_session("P1")
        r.commit("c0", "state", "genuine", "genuine", recognized=False, response_seconds=1.0)
        with self.assertRaises(ValueError):
            r.commit("c0", "state", "not_genuine", "not_genuine", recognized=False, response_seconds=1.0)

    def test_invalid_question_for_card_type(self):
        r = runner(self.ws, self.clock)
        r.start_session("P1")
        with self.assertRaises(ValueError):
            r.commit("c0", "family", "WALL", "WALL", recognized=False, response_seconds=1.0)

    def test_decision_ceiling_refused(self):
        r = runner(self.ws, self.clock)
        r.start_session("P1")
        r.responses = [{"segment_index": 1}] * S.MAX_DECISIONS   # simulate a full ledger
        with self.assertRaises(WorkloadError):
            r.commit("c0", "state", "genuine", "genuine", recognized=False, response_seconds=1.0)


class WorkloadAndTailTests(unittest.TestCase):
    """65-min ceiling, hardness-before-genuine, valid-unterminated tail (D10)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_65_min_ceiling_refuses_commit(self):
        r = runner(self.ws, Clock())
        r.start_session("P1")
        # two durable playbacks 3900s apart in segment 1 => active_seconds >= 65 min
        t0 = datetime.fromtimestamp(0, tz=timezone.utc).isoformat()
        t1 = datetime.fromtimestamp(65 * 60, tz=timezone.utc).isoformat()
        r.playbacks = [{"segment_index": 1, "utc": t0}, {"segment_index": 1, "utc": t1}]
        with self.assertRaises(WorkloadError):
            r.commit("c0", "state", "genuine", "genuine", recognized=False, response_seconds=1.0)

    def test_hardness_before_genuine_rejected(self):
        r = runner(self.ws, Clock())
        r.start_session("P1")
        r.commit("c0", "state", "not_genuine", "not_genuine", recognized=False, response_seconds=1.0)
        with self.assertRaises(ValueError):
            r.commit("c0", "hardness", "harder", "harder", recognized=False, response_seconds=1.0)

    def test_hardness_after_genuine_allowed(self):
        r = runner(self.ws, Clock())
        r.start_session("P1")
        r.commit("c0", "state", "genuine", "genuine", recognized=False, response_seconds=1.0)
        r.commit("c0", "hardness", "harder", "harder", recognized=False, response_seconds=1.0)
        self.assertEqual(r.decisions_total(), 2)

    def test_valid_unterminated_tail_dropped(self):
        r = runner(self.ws, Clock())
        r.start_session("P1")
        r.commit("c0", "state", "not_genuine", "not_genuine", recognized=False, response_seconds=1.0)
        # append a VALID JSON object with NO trailing newline: a torn write, dropped
        with (self.ws / "responses.jsonl").open("a") as fh:
            fh.write('{"x":1}')
        state = runner(self.ws, Clock()).resume()
        self.assertTrue(state.torn_tail)
        self.assertEqual(state.decisions_total, 1)          # only the durable row survived


class OneSessionPerDayTests(unittest.TestCase):
    def test_new_session_refused_same_local_date(self):
        with tempfile.TemporaryDirectory() as d:
            ws, clock = Path(d), Clock()
            r = runner(ws, clock, date="D1")
            r.start_session("P1")
            r.commit("c0", "state", "genuine", "genuine", recognized=False, response_seconds=1.0)
            with self.assertRaises(WorkloadError):
                r.start_session("P2")            # same local date D1

    def test_resume_bypasses_one_per_day(self):
        with tempfile.TemporaryDirectory() as d:
            ws, clock = Path(d), Clock()
            r = runner(ws, clock, date="D1")
            r.start_session("P1")
            r.commit("c0", "state", "genuine", "genuine", recognized=False, response_seconds=1.0)
            r.start_session("P1", resume=True)   # allowed
            self.assertTrue(True)


class FenceAndFreezeTests(unittest.TestCase):
    def test_write_outside_workspace_refused(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                S._safe_path(Path(d), "../escape.jsonl")

    def test_prediction_freeze_gate(self):
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            with self.assertRaises(Gate1Error):
                S.verify_predictions_frozen(ws, ["m1"])
            (ws / "prediction_hashes.json").write_text(json.dumps({"method_hashes": {"m1": "h"}}))
            S.verify_predictions_frozen(ws, ["m1"])
            with self.assertRaises(Gate1Error):
                S.verify_predictions_frozen(ws, ["m1", "m2"])


if __name__ == "__main__":
    unittest.main()
