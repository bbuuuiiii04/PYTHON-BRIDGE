"""Freeze-stage engine (spec B3 dev-manifest, B4 methods, B7). Synthetic fixtures
only — injected window_fn/plan_fn stand in for the live v4/F2 reads, so these tests
never touch the library and also prove the engine is deterministic (run-twice)."""
import unittest

from tools.spectral_pilot import candidates as cand
from tools.spectral_pilot import freeze
from tools.spectral_pilot.firewall import ALLOWLIST
from tools.spectral_pilot.selection import track_instance_id

SEED = "spectral-ai-pilot-v1-790c625-2026-07-14"


def win(scale=1.0, coverage=16.0):
    d = {k: float(i + 1) * scale for i, k in enumerate(ALLOWLIST)}
    d["coverage"] = coverage
    return d


def gold(cid, beat, genuine, tier=None, family=None):
    return {"content_id": cid, "marker_beat": beat, "is_genuine_drop": genuine,
            "drop": {"tier": tier, "family": family}}


class ReduceFamilyTests(unittest.TestCase):
    def test_match_differ(self):
        self.assertEqual(freeze.reduce_family("HOUSE", "HOUSE"), "HOUSE")
        self.assertEqual(freeze.reduce_family("HOUSE", "COMET"), "mixed")
        self.assertEqual(freeze.reduce_family("none", "none"), "none")
        self.assertEqual(freeze.reduce_family("none", "WALL"), "mixed")


class DevManifestTests(unittest.TestCase):
    def _gold(self):
        return [
            gold("D1", 128, True, 2, "house"), gold("D1", 256, True, 3, "comet"),  # montage lineage
            gold("D2", 64, False),                                                  # not-genuine
            gold("D3", 100, True, 1, "wall"),                                       # single genuine
            gold("D4", 32, None),                                                   # unlabeled -> excluded
        ]

    def _mk(self):
        sha = {"D1": "sha1", "D2": "sha2", "D3": "sha3"}
        wf = lambda cid, beat: None if beat == 999 else win(scale=1.0 + 0.1 * (beat % 5))
        return freeze.build_dev_manifest(
            pilot_seed=SEED, gold_rows=self._gold(), dev_content_ids={"D1", "D2", "D3", "D4"},
            sha_by_cid=sha, window_fn=wf, anchor_rows=[{"content_id_locator": "A1"}],
            label_hashes={"gold.json": "abc"})

    def test_targets_and_exclusions(self):
        dm = self._mk()
        by_beat = {(r.recording_lineage_id, r.marker_beat): r for r in dm.dev_rows}
        self.assertEqual(by_beat[("D1", 128)].targets, {"genuine": "genuine", "hardness": "T2"})
        self.assertEqual(by_beat[("D2", 64)].targets, {"genuine": "not_genuine"})   # no hardness
        self.assertEqual(by_beat[("D3", 100)].targets, {"genuine": "genuine", "hardness": "T1"})
        self.assertEqual(dm.manifest["per_axis_target_counts"],
                         {"genuine": 4, "hardness": 3, "family": 1})               # D4 excluded
        self.assertEqual(dm.manifest["montage_lineages"], ["D1"])                  # only D1 has >=2 genuine
        # D4 (null) never becomes a row; exclusions record only real read failures
        self.assertNotIn("D4", {r.recording_lineage_id for r in dm.dev_rows})

    def test_montage_family_reduced(self):
        dm = self._mk()
        lineage, desc, fam = dm.dev_montages[0]
        self.assertEqual(lineage, "D1")
        self.assertEqual(fam, "mixed")                                             # HOUSE vs COMET
        self.assertIn("sub_db__med", desc)

    def test_output_hash_deterministic(self):
        self.assertEqual(self._mk().hash, self._mk().hash)


class ScalerContractTests(unittest.TestCase):
    def _dm(self):
        rows = [gold(f"L{i}", 128, True, 1 + i % 3, ["house", "comet", "wall"][i % 3]) for i in range(6)]
        rows += [gold(f"L{i}", 256, True, 1 + (i + 1) % 3, ["comet", "wall", "house"][i % 3]) for i in range(6)]
        sha = {f"L{i}": f"sha{i}" for i in range(6)}
        wf = lambda cid, beat: win(scale=1.0 + 0.3 * (int(cid[1:]) + beat % 7))
        return freeze.build_dev_manifest(
            pilot_seed=SEED, gold_rows=rows, dev_content_ids={f"L{i}" for i in range(6)},
            sha_by_cid=sha, window_fn=wf, anchor_rows=[], label_hashes={})

    def test_fit_both_scalers(self):
        sc = freeze.fit_scalers(self._dm())
        self.assertTrue(sc.marker.retained)                       # some non-zero-MAD fields
        self.assertTrue(sc.family.retained)
        self.assertEqual(sc.marker.allowlist, ALLOWLIST)

    def test_contracts_only_candidate_c_scaler_bound(self):
        sc = freeze.fit_scalers(self._dm())
        cons = {c.method_version: c for c in freeze.candidate_contracts(
            pilot_seed=SEED, scalers=sc, dev_manifest_hash="dmh", code_hash="ch")}
        self.assertEqual(cons[cand.CANDIDATE_C].scaler_population_hash, sc.marker.scaler_population_hash)
        self.assertEqual(cons[cand.BASELINE_A].scaler_population_hash, "")
        self.assertEqual(len(cons), 5)                            # 3 predictions + 2 diagnostics


class RunAllMethodsTests(unittest.TestCase):
    def _setup(self):
        # a rich dev population so retrieval has >=3 lineages
        grows = []
        for i in range(6):
            grows.append(gold(f"L{i}", 128, True, 1 + i % 3, ["house", "comet", "wall"][i % 3]))
            grows.append(gold(f"L{i}", 256, True, 1 + (i + 1) % 3, ["comet", "wall", "house"][i % 3]))
        sha = {f"L{i}": f"sha{i}" for i in range(6)}
        wf = lambda cid, beat: win(scale=1.0 + 0.05 * ((int(cid[1:]) if cid[1:].isdigit() else 9) + beat % 11))
        dm = freeze.build_dev_manifest(pilot_seed=SEED, gold_rows=grows,
                                       dev_content_ids={f"L{i}" for i in range(6)}, sha_by_cid=sha,
                                       window_fn=wf, anchor_rows=[], label_hashes={})
        sc = freeze.fit_scalers(dm)
        mtid = track_instance_id(SEED, "Q1")
        ftid = track_instance_id(SEED, "Q2")
        cards = [
            {"card_type": "marker_state", "card_id": "m1", "track_instance_id": mtid,
             "marker_beat": 200, "anchor_role": "T2"},
            {"card_type": "family_montage", "card_id": "f1", "track_instance_id": ftid,
             "marker_beat": None, "clip_spec": {"windows": [{"start_beat": 96, "end_beat": 112},
                                                            {"start_beat": 300, "end_beat": 316}]}},
        ]
        resolve = {mtid: ("Q1", "Q1", "qsha1"), ftid: ("Q2", "Q2", "qsha2")}.__getitem__
        return dm, sc, cards, resolve, wf

    def _plan(self, cid, beat):
        return ("HOUSE", 3)

    def test_every_method_and_axis(self):
        dm, sc, cards, resolve, wf = self._setup()
        rows = freeze.run_all_methods(pilot_seed=SEED, cards=cards, resolve=resolve, window_fn=wf,
                                      plan_fn=self._plan, dev=dm, scalers=sc, manifest_hash="mh")
        # baseline A: genuine(abstain)+hardness on the marker, family on the montage = 3
        self.assertEqual(len(rows[cand.BASELINE_A]), 3)
        self.assertEqual(len(rows[cand.BASELINE_B]), 1)                # genuine only, marker
        # candidate C: marker genuine+hardness at 0,-2,-1,+1,+2 = 10, plus montage family = 11
        self.assertEqual(len(rows[cand.CANDIDATE_C]), 11)
        axes_a = sorted(r["axis"] for r in rows[cand.BASELINE_A])
        self.assertEqual(axes_a, ["family", "genuine", "hardness"])
        # every prediction row carries real hashes
        for r in rows[cand.CANDIDATE_C]:
            self.assertEqual(r["manifest_hash"], "mh")
            self.assertTrue(r["input_hash"])

    def test_missing_v4_named_abstention(self):
        dm, sc, cards, resolve, _ = self._setup()
        wf = lambda cid, beat: None                                  # every window missing
        rows = freeze.run_all_methods(pilot_seed=SEED, cards=cards, resolve=resolve, window_fn=wf,
                                      plan_fn=self._plan, dev=dm, scalers=sc, manifest_hash="mh")
        cabs = [r for r in rows[cand.CANDIDATE_C] if r["abstained"]]
        self.assertEqual(len(cabs), 11)                             # all C rows abstain
        self.assertIn("missing_or_invalid_v4", cabs[0]["reason_codes"])

    def test_determinism_run_twice(self):
        dm, sc, cards, resolve, wf = self._setup()
        kw = dict(pilot_seed=SEED, cards=cards, resolve=resolve, window_fn=wf,
                  plan_fn=self._plan, dev=dm, scalers=sc, manifest_hash="mh")
        self.assertEqual(freeze.run_all_methods(**kw), freeze.run_all_methods(**kw))

    def test_stability_shifts_pin_four_deltas(self):
        # spec B8: each central marker recomputed at deltas -2,-1,+1,+2 -> 5 rows per gated axis.
        self.assertEqual(freeze.STABILITY_SHIFTS, (-2, -1, 1, 2))
        dm, sc, cards, resolve, _ = self._setup()
        # marker card m1 sits at beat 200; kill only the -2 shift window (beat 198) to force an
        # out-of-range-style miss, and prove it is EXCLUDED BY REASON, not silently dropped.
        wf = lambda cid, beat: None if beat == 198 else win(scale=1.0 + 0.05 * (beat % 11))
        rows = freeze.run_all_methods(pilot_seed=SEED, cards=cards, resolve=resolve, window_fn=wf,
                                      plan_fn=self._plan, dev=dm, scalers=sc, manifest_hash="mh")
        expected = {"m1", "m1@-2", "m1@-1", "m1@+1", "m1@+2"}
        for axis in ("genuine", "hardness"):
            got = {r["target_id"] for r in rows[cand.CANDIDATE_C] if r["axis"] == axis}
            self.assertEqual(got, expected, axis)                  # central + 4 shifts, none dropped
            miss = [r for r in rows[cand.CANDIDATE_C]
                    if r["axis"] == axis and r["target_id"] == "m1@-2"]
            self.assertEqual(len(miss), 1)
            self.assertTrue(miss[0]["abstained"])                  # out-of-range window kept as a row...
            self.assertIn("missing_or_invalid_v4", miss[0]["reason_codes"])  # ...with a named reason

    def test_diagnostics_when_wired(self):
        dm, sc, cards, resolve, wf = self._setup()
        rows = freeze.run_all_methods(pilot_seed=SEED, cards=cards, resolve=resolve, window_fn=wf,
                                      plan_fn=self._plan, dev=dm, scalers=sc, manifest_hash="mh",
                                      baseline_fn=lambda method, cid, beat: {"H": 0.5})
        self.assertEqual(len(rows[cand.DIAG_HARDNESS]), 1)          # one per marker card
        self.assertEqual(rows[cand.DIAG_HARDNESS][0]["descriptor"], {"H": 0.5})


if __name__ == "__main__":
    unittest.main()
