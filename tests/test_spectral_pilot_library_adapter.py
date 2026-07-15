"""Offline library adapter: metadata listing, pool pick, enrichment (spec B3.1).

Synthetic fixtures only — no live Rekordbox/audio/cache. Fake content objects and
a fake ``LibraryReaders`` drive every path; ``real_readers`` (the live-bridge
import) is never exercised here.
"""
import unittest
from types import SimpleNamespace

from tools.spectral_pilot import library_adapter as la
from tools.spectral_pilot import selection as sel

SEED = "spectral-ai-pilot-v1-790c625-2026-07-14"


def content(i, deleted=0, adp="a.DAT"):
    return SimpleNamespace(ID=i, Title=f"track {i}", ArtistName=f"artist {i}",
                           Length=200.0 + i, BPM=12800 + i, FolderPath=f"/music/{i}.wav",
                           AnalysisDataPath=adp, rb_local_deleted=deleted)


def fake_readers(*, present=True, valid=True, n_beats=600, drops=(64, 128, 256), grid_len=700):
    return la.LibraryReaders(
        audio_sha256=lambda p: "sha-" + p,                 # distinct per path
        beatgrid_times=lambda a: ([0.0] * grid_len if a else None),
        beatgrid_fingerprint=lambda t: f"bg-{len(t)}",
        phrase_drops=lambda a: list(drops),
        v4_status=lambda p, t: (present, valid, n_beats),
        label_store_hash=lambda: "labelhash",
    )


class ListLocatorTests(unittest.TestCase):
    def test_metadata_only_and_skips_deleted(self):
        metas = la.list_locators([content(1), content(2, deleted=1), content(3)])
        self.assertEqual([m.content_id_locator for m in metas], ["1", "3"])
        self.assertEqual(metas[0].bpm, 128.01)          # BPM stored x100
        self.assertEqual(metas[0].duration_s, 201.0)
        self.assertEqual(metas[0].audio_path, "/music/1.wav")

    def test_scripted_flag(self):
        metas = la.list_locators([content(1), content(2)], scripted_ids={"2"})
        self.assertFalse(metas[0].is_scripted)
        self.assertTrue(metas[1].is_scripted)


class SeedPoolIdTests(unittest.TestCase):
    def test_first_60_by_hash_input_order_independent(self):
        metas = la.list_locators([content(i) for i in range(100)])
        a = la.seed_pool_ids(metas, pilot_seed=SEED)
        b = la.seed_pool_ids(list(reversed(metas)), pilot_seed=SEED)
        self.assertEqual(len(a), 60)
        self.assertEqual(a, b)                            # order-independent, deterministic
        # matches selection.seed_pool's ordering on the same ids
        expected = sorted((m.content_id_locator for m in metas),
                          key=lambda c: sel.selection_hash(SEED, c))[:60]
        self.assertEqual(a, expected)

    def test_removes_dev_and_scripted(self):
        metas = la.list_locators([content(i) for i in range(70)], scripted_ids={"5"})
        ids = la.seed_pool_ids(metas, pilot_seed=SEED, dev_content_ids={"6"}, scripted_ids={"5"})
        self.assertNotIn("5", ids)
        self.assertNotIn("6", ids)


class EnrichTests(unittest.TestCase):
    def test_enrich_produces_valid_locator_row(self):
        meta = la.list_locators([content(1)])[0]
        row = la.enrich(meta, fake_readers())
        self.assertIsInstance(row, sel.LocatorRow)
        self.assertEqual(row.audio_sha256, "sha-/music/1.wav")
        self.assertEqual(row.audio_duplicate_group, row.audio_sha256)   # exact-audio group
        self.assertEqual(row.recording_lineage_id, "1")                 # each its own lineage
        self.assertEqual(row.candidate_markers, (64, 128, 256))
        self.assertEqual(row.n_beats, 600)                              # from valid v4
        self.assertTrue(row.v4_present and row.v4_valid)
        self.assertEqual(len(row.eligible_markers()), 3)                # all +16 <= 600

    def test_missing_and_invalid_v4_flags(self):
        meta = la.list_locators([content(1)])[0]
        miss = la.enrich(meta, fake_readers(present=False, valid=False, n_beats=None))
        self.assertFalse(miss.v4_present)
        self.assertEqual(miss.n_beats, 700)                             # falls back to grid length
        inval = la.enrich(meta, fake_readers(present=True, valid=False, n_beats=None))
        self.assertTrue(inval.v4_present)
        self.assertFalse(inval.v4_valid)

    def test_marker_override_and_anchor_beats(self):
        meta = la.list_locators([content(1)])[0]
        row = la.enrich(meta, fake_readers(), marker_beats=[10, 400], anchor_marker_beat=400)
        self.assertEqual(row.candidate_markers, (10, 400))              # override wins over phrase drops
        self.assertEqual(row.anchor_marker_beat, 400)
        mix = la.enrich(meta, fake_readers(), anchor_montage_beats=(192, 288))
        self.assertEqual(mix.anchor_montage_beats, (192, 288))


class EndToEndSelectionTests(unittest.TestCase):
    """metas -> pool ids -> enrich -> build_selection yields an OK manifest (D-style)."""

    def test_enriched_pool_builds_manifest(self):
        metas = la.list_locators([content(i) for i in range(20)])
        pool_ids = set(la.seed_pool_ids(metas, pilot_seed=SEED))
        by_id = {m.content_id_locator: m for m in metas}
        rows = [la.enrich(by_id[cid], fake_readers()) for cid in pool_ids]
        ls = {r.content_id_locator: "confirmed" for r in rows}
        res = sel.build_selection(
            rows, pilot_seed=SEED, created_from_head="head", dev_content_ids=set(),
            dev_lineages=set(), scripted_ids=set(), unresolved_ids=set(), lineage_states=ls)
        self.assertEqual(res.status, "OK")
        self.assertEqual(len(res.selected_rows), 18)


class AnchorPinningTests(unittest.TestCase):
    def test_pick_highest_tier_tiebreak_earliest(self):
        self.assertEqual(la.pick_highest_tier_beat([(64, 1), (128, 3), (256, 3)]), 128)  # T3 tie -> earliest
        self.assertEqual(la.pick_highest_tier_beat([(400, 2), (64, 3)]), 64)             # highest tier wins
        self.assertIsNone(la.pick_highest_tier_beat([]))

    def _meta_getter(self):
        metas = {cid: la.LocatorMeta(content_id_locator=cid, artist="a", title=role, duration_s=200.0,
                                     bpm=128.0, audio_path=f"/{cid}.wav", analysis_data_path=f"{cid}.DAT")
                 for role, cid, kind, gold in la.ANCHOR_SPECS}
        return lambda cid: metas.get(cid)

    def test_build_seven_anchor_rows(self):
        readers = fake_readers(drops=(64, 128, 256))
        tier_fn = lambda meta, covered: [(b, 3 if b == 128 else 2) for b in covered]  # 128 is hardest
        rows, pins = la.build_anchor_rows(self._meta_getter(), readers, tier_fn)
        self.assertEqual(len(rows), 7)
        by_role = dict(zip(la.ANCHOR_ROLES, rows))
        self.assertEqual(by_role["WALL"].anchor_marker_beat, 128)              # gold beat
        self.assertEqual(by_role["mixed"].anchor_montage_beats, (192, 288))    # montage windows
        self.assertIsNone(by_role["mixed"].anchor_marker_beat)
        self.assertEqual(by_role["T2"].anchor_marker_beat, 128)               # pinned highest tier
        self.assertEqual(pins, {"T2": 128, "T3": 128})

    def test_invalid_v4_anchor_fails_closed(self):
        readers = fake_readers(valid=False)
        with self.assertRaises(la.AnchorError):
            la.build_anchor_rows(self._meta_getter(), readers, lambda m, c: [], )

    def test_pinned_anchor_no_markers_fails_closed(self):
        readers = fake_readers(drops=())                                       # no phrase drops
        with self.assertRaises(la.AnchorError):
            la.build_anchor_rows(self._meta_getter(), readers, lambda m, c: [(c[0], 3)])


if __name__ == "__main__":
    unittest.main()
