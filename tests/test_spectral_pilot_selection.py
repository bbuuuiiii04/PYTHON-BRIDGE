"""Deterministic selection: manifest, lineage disjointness, repeats (tests D2, D3, D8)."""
import unittest

from tools.spectral_pilot import selection as sel
from tools.spectral_pilot.selection import LocatorRow

SEED = "spectral-ai-pilot-v1-790c625-2026-07-14"
HEAD = "deadbeef"


def make_row(i, **kw):
    d = dict(
        content_id_locator=f"loc-{i}", audio_sha256=f"{i:064x}", recording_lineage_id=f"lin-{i}",
        audio_duplicate_group=f"dup-{i}", artist=f"artist {i}", title=f"track {i}",
        duration_s=200.0 + i, bpm=128.0 + i * 0.7, beatgrid_fingerprint=f"bg-{i}",
        marker_set_fingerprint=f"ms-{i}", label_store_hash="lh", n_beats=512,
        candidate_markers=(64, 128, 256),
    )
    d.update(kw)
    return LocatorRow(**d)


def eligible_corpus(n=30):
    rows = [make_row(i) for i in range(n)]
    lineage_states = {r.content_id_locator: "confirmed" for r in rows}
    return rows, lineage_states


def run(rows, lineage_states, **kw):
    return sel.build_selection(
        rows, pilot_seed=SEED, created_from_head=HEAD, dev_content_ids=set(),
        dev_lineages=set(), scripted_ids=set(), unresolved_ids=set(),
        lineage_states=lineage_states, **kw,
    )


class DeterministicManifestTests(unittest.TestCase):
    def test_two_builds_byte_identical(self):
        rows, ls = eligible_corpus()
        a = run(rows, ls)
        b = run(list(reversed(rows)), ls)  # input order must not matter
        self.assertEqual(a.status, "OK")
        self.assertEqual(a.manifest_id, b.manifest_id)
        self.assertEqual([r.to_dict() for r in a.selected_rows], [r.to_dict() for r in b.selected_rows])

    def test_manifest_id_reproduces_and_ids_unique(self):
        rows, ls = eligible_corpus()
        r = run(rows, ls)
        self.assertEqual(len(r.selected_rows), 18)  # 18 pilot lineages, no anchors here
        tids = [s.track_instance_id for s in r.selected_rows]
        self.assertEqual(len(set(tids)), len(tids))
        card_ids = [c.card_id for c in r.cards]
        self.assertEqual(len(set(card_ids)), len(card_ids))
        self.assertEqual(r.manifest_id, sel._manifest_id(r.selected_rows))

    def test_two_markers_per_lineage_and_36_marker_cards(self):
        rows, ls = eligible_corpus()
        r = run(rows, ls)
        markers = [c for c in r.cards if c.card_type == "marker_state"]
        self.assertEqual(len(markers), 36)
        for s in r.selected_rows:
            self.assertEqual(len(s.family_montage_marker_ids), 2)

    def test_hardness_anchors_12_each(self):
        rows, ls = eligible_corpus()
        r = run(rows, ls)
        markers = [c for c in r.cards if c.card_type == "marker_state"]
        counts = {"T1": 0, "T2": 0, "T3": 0}
        for c in markers:
            counts[c.anchor_role] += 1
        self.assertEqual(counts, {"T1": 12, "T2": 12, "T3": 12})

    def test_insufficient_lineages_is_inconclusive(self):
        rows, ls = eligible_corpus(n=10)
        r = run(rows, ls)
        self.assertEqual(r.status, "INCONCLUSIVE")
        self.assertLess(r.eligible_lineage_count, 18)


class LineageDisjointnessTests(unittest.TestCase):
    def test_equal_audio_sha_emits_pair(self):
        a = make_row(1)
        b = make_row(2, audio_sha256=a.audio_sha256)
        pairs = sel.find_suspicious_pairs([a, b], pilot_seed=SEED)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(set(pairs[0]), {"loc-1", "loc-2"})

    def test_remix_title_emits_pair(self):
        a = make_row(1, artist="Ray Volpe", title="Laserbeam")
        b = make_row(2, artist="Ray Volpe", title="Laserbeam (Extended Mix)", audio_sha256="f" * 64)
        pairs = sel.find_suspicious_pairs([a, b], pilot_seed=SEED)
        self.assertEqual(len(pairs), 1)

    def test_near_duration_bpm_same_artist_emits_pair(self):
        a = make_row(1, artist="Dombresky", title="Utopia", duration_s=200.0, bpm=126.0, audio_sha256="a" * 64)
        b = make_row(2, artist="Dombresky", title="Utopia VIP", duration_s=202.5, bpm=126.05, audio_sha256="b" * 64)
        pairs = sel.find_suspicious_pairs([a, b], pilot_seed=SEED)
        self.assertEqual(len(pairs), 1)

    def test_unrelated_rows_emit_no_pair(self):
        a = make_row(1, artist="A", title="One", duration_s=100.0, bpm=120.0, audio_sha256="1" * 64)
        b = make_row(2, artist="B", title="Two", duration_s=300.0, bpm=175.0, audio_sha256="2" * 64)
        self.assertEqual(sel.find_suspicious_pairs([a, b], pilot_seed=SEED), [])

    def test_unresolved_row_excluded(self):
        row = make_row(5)
        self.assertEqual(
            sel.classify_exclusion(row, dev_content_ids=set(), dev_lineages=set(),
                                   unresolved_ids={"loc-5"}, lineage_states={"loc-5": "confirmed"}),
            "unresolved_duplicate",
        )

    def test_unconfirmed_lineage_excluded(self):
        row = make_row(5)
        self.assertEqual(
            sel.classify_exclusion(row, dev_content_ids=set(), dev_lineages=set(),
                                   unresolved_ids=set(), lineage_states={}),
            "unresolved_lineage",
        )

    def test_post_selection_related_group_across_splits_hard_fails(self):
        rows, ls = eligible_corpus()
        r = run(rows, ls)
        # forge a related group spanning a pilot lineage and an anchor-role lineage
        pilot_lin = r.selected_rows[0].recording_lineage_id
        forged = sel.SelectedRow(**{**r.selected_rows[1].to_dict(), "split_role": "anchor"})
        rows2 = [forged] + r.selected_rows[2:]
        with self.assertRaises(sel.ManifestError):
            sel.validate_manifest([r.selected_rows[0]] + rows2,
                                  related_groups=[{pilot_lin, forged.recording_lineage_id}])


class RepeatPlacementTests(unittest.TestCase):
    def setUp(self):
        rows, ls = eligible_corpus()
        self.result = run(rows, ls)

    def test_repeat_counts_per_session(self):
        for sess, marker_q, fam_q in (("P1", 2, 1), ("P2", 2, 1), ("P3", 2, 2)):
            mk = [c for c in self.result.cards if c.session_index == sess and c.card_type == "marker_repeat"]
            fam = [c for c in self.result.cards if c.session_index == sess and c.card_type == "family_repeat"]
            self.assertEqual(len(mk), marker_q, sess)
            self.assertEqual(len(fam), fam_q, sess)

    def test_total_repeats(self):
        mk = [c for c in self.result.cards if c.card_type == "marker_repeat"]
        fam = [c for c in self.result.cards if c.card_type == "family_repeat"]
        self.assertEqual(len(mk), 6)
        self.assertEqual(len(fam), 4)

    def test_repeats_non_adjacent_to_source(self):
        pos = {c.card_id: c.order_index for c in self.result.cards}
        for c in self.result.cards:
            if c.repeat_of_card_id is not None:
                self.assertGreaterEqual(abs(pos[c.card_id] - pos[c.repeat_of_card_id]), 2, c.card_id)

    def test_order_index_contiguous(self):
        idxs = sorted(c.order_index for c in self.result.cards)
        self.assertEqual(idxs, list(range(len(idxs))))

    def test_repeats_add_no_lineages(self):
        # sample size (distinct lineages) unchanged by repeats
        lineages = {c.recording_lineage_id for c in self.result.cards
                    if c.card_type in ("marker_state", "family_montage")}
        self.assertEqual(len(lineages), 18)


class MultiRowLineageRepresentativeTests(unittest.TestCase):
    """A lineage with >1 eligible row picks a hash-stable representative (D5, B3.4)."""

    def _corpus(self):
        rows = [make_row(i) for i in range(18)]
        # a SECOND eligible row in lineage lin-0, distinct dup group + content id
        rows.append(make_row(0, content_id_locator="loc-0b", audio_duplicate_group="dup-0b",
                             audio_sha256="f" * 64))
        ls = {r.content_id_locator: "confirmed" for r in rows}
        return rows, ls

    def test_permuted_input_identical_manifest_id(self):
        rows, ls = self._corpus()
        a = run(rows, ls)
        b = run(list(reversed(rows)), ls)
        self.assertEqual(a.status, "OK")
        self.assertEqual(a.manifest_id, b.manifest_id)

    def test_representative_is_lowest_content_id_hash(self):
        rows, ls = self._corpus()
        r = run(rows, ls)
        rep = [s.content_id_locator for s in r.selected_rows if s.recording_lineage_id == "lin-0"][0]
        expected = min(["loc-0", "loc-0b"], key=lambda c: sel.selection_hash(SEED, c))
        self.assertEqual(rep, expected)

    def test_curator_confirmation_stamped(self):
        rows, ls = self._corpus()
        r = sel.build_selection(rows, pilot_seed=SEED, created_from_head=HEAD, dev_content_ids=set(),
                                dev_lineages=set(), scripted_ids=set(), unresolved_ids=set(),
                                lineage_states=ls, adjudications={"loc-1": "confirmed_unrelated"})
        stamped = [s.curator_confirmation for s in r.selected_rows if s.content_id_locator == "loc-1"]
        self.assertEqual(stamped, ["confirmed_unrelated"])
        others = {s.curator_confirmation for s in r.selected_rows if s.content_id_locator != "loc-1"}
        self.assertEqual(others, {"not_applicable"})


class CardManifestRowTests(unittest.TestCase):
    """card_manifest_rows: clip_spec + card_hash, anchor beats, montage windows (B7)."""

    def test_marker_and_montage_clip_specs(self):
        rows, ls = eligible_corpus()
        r = run(rows, ls)
        mrows = sel.card_manifest_rows(SEED, r.cards)
        by_type = {}
        for m in mrows:
            by_type.setdefault(m.card_type, []).append(m)
        marker = by_type["marker_state"][0]
        self.assertEqual(sorted(marker.clip_spec), ["audio_sha256", "end_beat", "start_beat"])
        self.assertEqual(marker.clip_spec["end_beat"] - marker.clip_spec["start_beat"], 16)
        montage = by_type["family_montage"][0]
        self.assertEqual(len(montage.clip_spec["windows"]), 2)
        self.assertIsNotNone(montage.display_left_id)
        self.assertIsNotNone(montage.display_right_id)
        self.assertEqual(len({m.card_hash for m in mrows}), len(mrows))

    def test_anchor_cards_carry_marker_beat_and_clip(self):
        rows, ls = eligible_corpus()
        # seven anchors in ANCHOR_ROLES order; the 4th ("mixed") is montage-style.
        anchors = [make_row(100 + i, anchor_marker_beat=128) for i in range(7)]
        anchors[3] = make_row(103, anchor_marker_beat=None, anchor_montage_beats=(192, 288))
        for a in anchors:
            ls[a.content_id_locator] = "confirmed"
        r = run(rows, ls, anchor_rows=anchors)
        mrows = sel.card_manifest_rows(SEED, r.cards)
        anchor_cards = [m for m in mrows if m.card_type == "anchor_confirm"]
        self.assertEqual(len(anchor_cards), 7)
        for m in anchor_cards:
            if m.anchor_role == "mixed":
                self.assertIsNone(m.marker_beat)
                self.assertEqual([w["start_beat"] for w in m.clip_spec["windows"]], [192, 288])
                self.assertTrue(all(w["end_beat"] - w["start_beat"] == 16 for w in m.clip_spec["windows"]))
            else:
                self.assertEqual(m.marker_beat, 128)
                self.assertEqual(m.clip_spec["end_beat"] - m.clip_spec["start_beat"], 16)

    def test_mixed_anchor_requires_two_montage_beats(self):
        rows, ls = eligible_corpus()
        # a 'mixed' anchor without montage beats is a fail-closed ManifestError (B7)
        anchors = [make_row(100 + i, anchor_marker_beat=128) for i in range(7)]  # anchors[3] == mixed, single beat
        for a in anchors:
            ls[a.content_id_locator] = "confirmed"
        with self.assertRaises(sel.ManifestError):
            run(rows, ls, anchor_rows=anchors)


if __name__ == "__main__":
    unittest.main()
