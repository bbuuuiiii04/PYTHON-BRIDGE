"""Deterministic selection for the Phase-0 spectral pilot (spec B3, items 1-8).

Everything here is a pure function of its inputs + ``pilot_seed``: two builds over
the same synthetic locator fixtures are byte-identical (test D2). No audio decode,
no cache enumeration, no runtime import. The insufficient-data rule holds
throughout: a floor miss yields ``INCONCLUSIVE`` and the pool/budget is never
expanded after any prediction or answer exists.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

from .canonical import selection_hash, sha256_hex
from .schemas import SCHEMA_VERSION, SelectedRow

# --- frozen protocol constants (spec B3) -------------------------------------
POOL_SIZE = 60
N_LINEAGES = 18
MARKERS_PER_LINEAGE = 2
WINDOW = 16                 # full 16-beat coverage (drop_window_vector width)
DUP_WITHIN_S = 3.0
BPM_WITHIN = 0.10
HARDNESS_TIERS = ("T1", "T2", "T3")
ID_TRUNC = 16              # [:16] first 16 lower-case hex chars

# version-token lexicon, frozen (spec B3 item 2)
VERSION_TOKENS = frozenset(
    "remix edit bootleg extended radio instrumental vip dub mix version rework".split()
)

# The seven anchors, operator-decided 2026-07-15 (spec B3.7). Data, not logic:
# each anchor's exact lineage is pinned to a development lineage id at Phase-1;
# here we carry the role table so the manifest builder can slot them.
ANCHOR_ROLES = ("WALL", "COMET", "HOUSE", "mixed", "T1", "T2", "T3")

_BRACKET = re.compile(r"[\(\[\{][^\(\)\[\]\{\}]*[\)\]\}]")


# --- text normalization (spec B3 item 2) -------------------------------------
def _strip_punct(s: str) -> str:
    """Replace every Unicode general-category P* char with a space."""
    return "".join(" " if unicodedata.category(ch).startswith("P") else ch for ch in s)


def normalize_text(s: str) -> str:
    """NFKC, casefold, punctuation->space, collapse whitespace (spec B3 item 2)."""
    s = unicodedata.normalize("NFKC", s).casefold()
    return " ".join(_strip_punct(s).split())


def base_title(title: str) -> str:
    """Normalized title with bracketed groups and trailing version tokens removed."""
    t = unicodedata.normalize("NFKC", title).casefold()
    t = _BRACKET.sub(" ", t)
    words = _strip_punct(t).split()
    while words and words[-1] in VERSION_TOKENS:
        words.pop()
    return " ".join(words)


# --- ID helpers (spec B3 §210, card identity) --------------------------------
def track_instance_id(pilot_seed: str, content_id_locator: str) -> str:
    return selection_hash(pilot_seed, content_id_locator)[:ID_TRUNC]


def marker_card_id(pilot_seed: str, audio_sha256: str, marker_beat: int) -> str:
    return selection_hash(pilot_seed, audio_sha256, marker_beat, "marker-card")[:ID_TRUNC]


def family_card_id(pilot_seed: str, recording_lineage_id: str) -> str:
    return selection_hash(pilot_seed, recording_lineage_id, "family-card")[:ID_TRUNC]


def anchor_card_id(pilot_seed: str, anchor_role: str) -> str:
    return selection_hash(pilot_seed, "anchor-card", anchor_role)[:ID_TRUNC]


def repeat_instance_id(source_card_id: str) -> str:
    return selection_hash(source_card_id, "repeat-instance")[:ID_TRUNC]


def pair_side_left_is_marker(pilot_seed: str, card_id: str) -> bool:
    """Which clip plays first in a hardness pair (spec B3.5): low bit of the hash."""
    return int(selection_hash(pilot_seed, card_id, "pair-side"), 16) & 1 == 0


# --- input fixture type -------------------------------------------------------
@dataclass(frozen=True)
class LocatorRow:
    """A read-only PDB locator row (synthetic in tests; a PDB read at Phase-1)."""
    content_id_locator: str
    audio_sha256: str
    recording_lineage_id: str
    audio_duplicate_group: str
    artist: str
    title: str
    duration_s: float
    bpm: float
    beatgrid_fingerprint: str
    marker_set_fingerprint: str
    label_store_hash: str
    n_beats: int
    candidate_markers: tuple           # candidate drop-marker beats (ints)
    v4_present: bool = True
    v4_valid: bool = True
    is_scripted: bool = False

    def eligible_markers(self) -> tuple:
        """Candidate markers with full 16-beat coverage (marker+16 <= n_beats)."""
        return tuple(sorted(b for b in self.candidate_markers if 0 <= b and b + WINDOW <= self.n_beats))


# --- item 1: seed pool --------------------------------------------------------
def seed_pool(locator_rows, *, pilot_seed, dev_content_ids, scripted_ids):
    """The 60-row seed pool (spec B3 item 1)."""
    dev = set(dev_content_ids)
    scr = set(scripted_ids)
    survivors = [
        r for r in locator_rows
        if r.content_id_locator not in dev and r.content_id_locator not in scr and not r.is_scripted
    ]
    survivors.sort(key=lambda r: selection_hash(pilot_seed, r.content_id_locator))
    return survivors[:POOL_SIZE]


# --- item 2: suspicious pairs -------------------------------------------------
def _rows_pair(a: LocatorRow, b: LocatorRow) -> bool:
    if a.audio_sha256 == b.audio_sha256:
        return True
    na, nb = normalize_text(a.artist), normalize_text(b.artist)
    ba, bb = base_title(a.title), base_title(b.title)
    if na == nb and ba == bb:
        return True
    if ba == bb and abs(a.duration_s - b.duration_s) <= DUP_WITHIN_S:
        return True
    if na == nb and abs(a.duration_s - b.duration_s) <= DUP_WITHIN_S and abs(a.bpm - b.bpm) <= BPM_WITHIN:
        return True
    return False


def find_suspicious_pairs(rows, *, pilot_seed):
    """Emit candidate related pairs over rows (pool ∪ development ∪ anchors).

    Returns a sorted list of (id_a, id_b) tuples; within each pair the two IDs are
    ordered by their selection hash, and the list is sorted canonically.
    """
    # ponytail: O(n^2) over ~60-90 rows — trivial; index by content_id for output.
    pairs = set()
    rows = list(rows)
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            if _rows_pair(rows[i], rows[j]):
                a, b = rows[i].content_id_locator, rows[j].content_id_locator
                ha, hb = selection_hash(pilot_seed, a), selection_hash(pilot_seed, b)
                pairs.add((a, b) if ha <= hb else (b, a))
    return sorted(pairs)


# --- item 3: eligibility ------------------------------------------------------
def classify_exclusion(row, *, dev_content_ids, dev_lineages, unresolved_ids, lineage_states):
    """Per-row exclusion_reason (spec B3 item 3 domain). 'none' means eligible.

    Priority mirrors the enum; cross_partition/pool_cap are assigned later by the
    manifest builder, never here.
    """
    if row.is_scripted:
        return "scripted"
    if row.content_id_locator in dev_content_ids or row.recording_lineage_id in dev_lineages:
        return "development_overlap"
    if not row.v4_present:
        return "missing_v4"
    if not row.v4_valid:
        return "invalid_v4"
    if len(row.eligible_markers()) < 2:
        return "insufficient_markers"
    if row.content_id_locator in unresolved_ids:
        return "unresolved_duplicate"
    if lineage_states.get(row.content_id_locator) != "confirmed":
        return "unresolved_lineage"
    return "none"


# --- items 4-8: full selection ------------------------------------------------
@dataclass
class CardPlan:
    card_id: str
    card_type: str
    session_index: str
    order_index: int
    track_instance_id: str
    marker_beat: Optional[int]
    audio_sha256: Optional[str]
    recording_lineage_id: Optional[str]
    anchor_role: Optional[str]
    display_left_id: Optional[str]
    display_right_id: Optional[str]
    repeat_of_card_id: Optional[str]
    clip_start_beat: Optional[int]
    clip_end_beat: Optional[int]


@dataclass
class SelectionResult:
    status: str                        # "OK" | "INCONCLUSIVE"
    reason: str
    selected_rows: list = field(default_factory=list)     # SelectedRow (pilot + anchor)
    cards: list = field(default_factory=list)             # CardPlan, frozen order
    manifest_id: Optional[str] = None
    eligible_lineage_count: int = 0


def _selected_row(row, pilot_seed, created_from_head, split_role, montage_ids):
    return SelectedRow(
        schema_version=SCHEMA_VERSION, pilot_seed=pilot_seed, created_from_head=created_from_head,
        track_instance_id=track_instance_id(pilot_seed, row.content_id_locator),
        content_id_locator=row.content_id_locator, audio_sha256=row.audio_sha256,
        audio_duplicate_group=row.audio_duplicate_group, recording_lineage_id=row.recording_lineage_id,
        split_role=split_role, beatgrid_fingerprint=row.beatgrid_fingerprint,
        marker_set_fingerprint=row.marker_set_fingerprint, label_store_hash=row.label_store_hash,
        exclusion_reason="none", lineage_review_state="confirmed",
        curator_confirmation="not_applicable", family_montage_marker_ids=list(montage_ids),
    )


def build_selection(
    locator_rows, *, pilot_seed, created_from_head, dev_content_ids, dev_lineages,
    scripted_ids, unresolved_ids, lineage_states, anchor_rows=(),
):
    """Run items 1-8. Returns a SelectionResult; INCONCLUSIVE when a floor is missed.

    ``anchor_rows`` are the seven B3.7 anchor LocatorRows in ANCHOR_ROLES order,
    pinned at Phase-1; empty in most unit fixtures (anchor cards then absent).
    """
    pool = seed_pool(locator_rows, pilot_seed=pilot_seed, dev_content_ids=dev_content_ids,
                     scripted_ids=scripted_ids)
    eligible = [
        r for r in pool
        if classify_exclusion(r, dev_content_ids=dev_content_ids, dev_lineages=dev_lineages,
                              unresolved_ids=unresolved_ids, lineage_states=lineage_states) == "none"
    ]

    # item 4: 18 lineages, distinct recording_lineage_id AND audio_duplicate_group
    eligible.sort(key=lambda r: selection_hash(pilot_seed, r.recording_lineage_id))
    chosen, seen_lin, seen_dup = [], set(), set()
    for r in eligible:
        if r.recording_lineage_id in seen_lin or r.audio_duplicate_group in seen_dup:
            continue
        chosen.append(r)
        seen_lin.add(r.recording_lineage_id)
        seen_dup.add(r.audio_duplicate_group)
        if len(chosen) == N_LINEAGES:
            break
    if len(chosen) < N_LINEAGES:
        return SelectionResult(status="INCONCLUSIVE",
                               reason=f"only {len(chosen)} eligible lineages (<{N_LINEAGES})",
                               eligible_lineage_count=len(chosen))

    # item 4: per lineage, first two eligible markers (also the family montage)
    marker_rows = []       # (row, marker_beat, marker_card_id)
    montage_by_lineage = {}
    for r in chosen:
        ms = sorted(r.eligible_markers(),
                    key=lambda b, r=r: selection_hash(r.audio_sha256, b))[:MARKERS_PER_LINEAGE]
        ids = []
        for b in ms:
            cid = marker_card_id(pilot_seed, r.audio_sha256, b)
            marker_rows.append((r, b, cid))
            ids.append(cid)
        montage_by_lineage[r.recording_lineage_id] = ids

    # item 5: hardness anchors T1/T2/T3 round-robin over the 36 marker rows
    marker_rows.sort(key=lambda t: selection_hash(pilot_seed, t[0].audio_sha256, t[1], "hardness-anchor"))
    hardness_by_card = {}
    for idx, (_, _, cid) in enumerate(marker_rows):
        hardness_by_card[cid] = HARDNESS_TIERS[idx % 3]

    # build selected rows (pilot) + anchors
    selected_rows = [
        _selected_row(r, pilot_seed, created_from_head, "pilot", montage_by_lineage[r.recording_lineage_id])
        for r in chosen
    ]
    for role, arow in zip(ANCHOR_ROLES, anchor_rows):
        selected_rows.append(_selected_row(arow, pilot_seed, created_from_head, "anchor", []))

    # sessions: 6 lineages each -> P1,P2,P3 (chosen already in frozen lineage order)
    sessions = {"P1": chosen[0:6], "P2": chosen[6:12], "P3": chosen[12:18]}
    cards = _build_cards(pilot_seed, sessions, marker_rows, hardness_by_card, montage_by_lineage,
                         anchor_rows)

    manifest_id = _manifest_id(selected_rows)
    return SelectionResult(status="OK", reason="", selected_rows=selected_rows, cards=cards,
                           manifest_id=manifest_id, eligible_lineage_count=len(eligible_by_lineage(eligible)))


def eligible_by_lineage(eligible):
    return {r.recording_lineage_id for r in eligible}


def _build_cards(pilot_seed, sessions, marker_rows, hardness_by_card, montage_by_lineage, anchor_rows):
    """Assemble the frozen, ordered card list across sessions A, P1-P3 (spec B6/B7)."""
    beat_of = {cid: (r, b) for (r, b, cid) in marker_rows}
    cards = []

    # Session A: seven anchor-confirm cards (only if anchors provided)
    for role, arow in zip(ANCHOR_ROLES, anchor_rows):
        cid = anchor_card_id(pilot_seed, role)
        cards.append(CardPlan(cid, "anchor_confirm", "A", 0, track_instance_id(pilot_seed, arow.content_id_locator),
                              None, arow.audio_sha256, arow.recording_lineage_id, role, None, None, None, None, None))

    # Sessions P1-P3
    for sess, lineages in sessions.items():
        base = []
        for r in lineages:
            for cid in montage_by_lineage[r.recording_lineage_id]:
                mr, beat = beat_of[cid]
                base.append(CardPlan(cid, "marker_state", sess, 0, track_instance_id(pilot_seed, r.content_id_locator),
                                     beat, r.audio_sha256, r.recording_lineage_id, hardness_by_card[cid],
                                     None, None, None, beat, beat + WINDOW))
            fcid = family_card_id(pilot_seed, r.recording_lineage_id)
            base.append(CardPlan(fcid, "family_montage", sess, 0, track_instance_id(pilot_seed, r.content_id_locator),
                                 None, r.audio_sha256, r.recording_lineage_id, None, None, None, None, None, None))
        cards.extend(base)  # order fixed below across the whole session
    _assign_repeats_and_order(pilot_seed, cards, sessions)
    return cards


def _assign_repeats_and_order(pilot_seed, cards, sessions):
    """Item 6: 2 marker repeats/session, family repeats 1/1/2, placed non-adjacently."""
    family_quota = {"P1": 1, "P2": 1, "P3": 2}
    # partition base cards by session (anchors already order 0..6 in A)
    by_session = {"A": [c for c in cards if c.session_index == "A"]}
    for s in ("P1", "P2", "P3"):
        by_session[s] = [c for c in cards if c.session_index == s]

    order_counter = 0
    ordered = []
    # Session A keeps hash order of anchors
    a_cards = sorted(by_session["A"], key=lambda c: selection_hash(pilot_seed, c.card_id, "order"))
    for c in a_cards:
        c.order_index = order_counter
        order_counter += 1
        ordered.append(c)

    for s in ("P1", "P2", "P3"):
        base = sorted(by_session[s], key=lambda c: selection_hash(pilot_seed, c.card_id, "order"))
        markers = [c for c in base if c.card_type == "marker_state"]
        montages = [c for c in base if c.card_type == "family_montage"]
        # lottery over original cards for this session
        rep_markers = sorted(markers, key=lambda c: selection_hash(pilot_seed, c.card_id, "repeat"))[:2]
        rep_montage = sorted(montages, key=lambda c: selection_hash(pilot_seed, c.card_id, "repeat"))[:family_quota[s]]
        repeats = []
        for src in rep_markers:
            repeats.append(_repeat_card(pilot_seed, src, "marker_repeat", s))
        for src in rep_montage:
            repeats.append(_repeat_card(pilot_seed, src, "family_repeat", s))
        placed = _place_repeats(pilot_seed, base, repeats)
        for c in placed:
            c.order_index = order_counter
            order_counter += 1
            ordered.append(c)
    cards[:] = ordered


def _repeat_card(pilot_seed, src, card_type, sess):
    rid = repeat_instance_id(src.card_id)
    return CardPlan(rid, card_type, sess, 0, src.track_instance_id, src.marker_beat, src.audio_sha256,
                    src.recording_lineage_id, src.anchor_role, src.display_left_id, src.display_right_id,
                    src.card_id, src.clip_start_beat, src.clip_end_beat)


def _place_repeats(pilot_seed, base, repeats):
    """Deterministic non-adjacent placement via spaced float keys (>=1 card between)."""
    positions = {c.card_id: (i + 1) * 1000 for i, c in enumerate(base)}
    gaps = [500] + [(i + 1) * 1000 + 500 for i in range(len(base))]
    for rep in sorted(repeats, key=lambda r: selection_hash(pilot_seed, r.card_id, "repeat-place")):
        src = positions[rep.repeat_of_card_id]
        used = set(positions.values())
        valid = [g for g in gaps if abs(g - src) >= 1500 and g not in used]
        h = int(selection_hash(pilot_seed, rep.card_id, "repeat-pos"), 16)
        positions[rep.card_id] = valid[h % len(valid)]
    everything = base + repeats
    return sorted(everything, key=lambda c: positions[c.card_id])


# --- item 8: manifest id + validation ----------------------------------------
class ManifestError(ValueError):
    """A post-selection relationship/overlap discovery — a gate-1 hard FAIL."""


def _manifest_id(selected_rows):
    rows = sorted((r.to_dict() for r in selected_rows), key=lambda d: d["track_instance_id"])
    return sha256_hex(rows)


def validate_manifest(selected_rows, *, related_groups=()):
    """Post-selection checks (spec B3 item 8). Raises ManifestError on hard FAIL."""
    tids = [r.track_instance_id for r in selected_rows]
    if len(set(tids)) != len(tids):
        raise ManifestError("duplicate track_instance_id in manifest")
    split_of = {r.recording_lineage_id: r.split_role for r in selected_rows}
    for group in related_groups:
        splits = {split_of[l] for l in group if l in split_of}
        if len(splits) > 1:
            raise ManifestError(f"related group crosses splits: {sorted(group)} -> {sorted(splits)}")
    return _manifest_id(selected_rows)
