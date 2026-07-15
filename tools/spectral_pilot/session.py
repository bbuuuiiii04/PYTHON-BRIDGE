"""Human-session card runner for the Phase-0 pilot (spec B6).

Owns the only file I/O in the package: a durable, append-only ledger under a
workspace directory. Two logs:
- ``responses.jsonl`` — committed answers (B7 ResponseRow), hash-chained.
- ``playbacks.jsonl`` — durable ``playback``/``skip`` rows (B6 requires a durable
  first-playback row per card; B7 does not name its file, so it lives here so
  responses.jsonl keeps its exact B7 schema).

Time and machine-local date are injected as callables so the runner is
deterministic under test — no wall-clock call lives inside it. Active time is
reconstructed from the durable rows' UTC stamps, so a crashed segment never
erases listened time (spec B6): at most the tail after the last durable row is
uncounted.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from .canonical import canonical_bytes, jsonl_line, sha256_hex
from .schemas import SCHEMA_VERSION, ResponseRow

MAX_DECISIONS = 113
GENESIS = "0" * 64

# Which questions a card may answer, and the order they close in (spec B6).
QUESTIONS = {
    "anchor_confirm": ("anchor",),
    "marker_state": ("state", "hardness"),
    "marker_repeat": ("state", "hardness"),
    "family_montage": ("family",),
    "family_repeat": ("family",),
}


class Gate1Error(ValueError):
    """A setup hard FAIL: order drift, missing card, or hash-chain tampering."""


class WorkloadError(RuntimeError):
    """A commit past the 113-decision ceiling or a per-card maximum."""


def _safe_path(workspace: Path, name: str) -> Path:
    """Resolve ``name`` under ``workspace``; refuse anything that escapes it (B11b)."""
    ws = workspace.resolve()
    p = (ws / name).resolve()
    if p != ws and ws not in p.parents:
        raise ValueError(f"refusing write outside workspace: {p}")
    return p


def verify_predictions_frozen(workspace: Path, expected_methods) -> None:
    """prediction_hashes.json must exist and cover every method before the first card.

    Reads only the hashes file — never a prediction's contents (spec B6 response
    independence).
    """
    p = _safe_path(Path(workspace), "prediction_hashes.json")
    if not p.exists():
        raise Gate1Error("prediction_hashes.json missing before first card")
    data = json.loads(p.read_text(encoding="utf-8"))
    have = set(data.get("method_hashes", {}))
    missing = set(expected_methods) - have
    if missing:
        raise Gate1Error(f"prediction_hashes.json incomplete, missing: {sorted(missing)}")


def _card_closed(card_type: str, answers: dict) -> bool:
    if answers.get("__skipped__"):
        return True
    if card_type in ("marker_state", "marker_repeat"):
        if "state" not in answers:
            return False
        if answers["state"] == "genuine":
            return "hardness" in answers
        return True
    if card_type in ("family_montage", "family_repeat"):
        return "family" in answers
    if card_type == "anchor_confirm":
        return "anchor" in answers
    return False


@dataclass
class ResumeState:
    first_unanswered_index: Optional[int]     # None => session complete
    re_exposed_card_ids: list
    torn_tail: bool
    decisions_total: int


class SessionRunner:
    """Runs one pilot workspace across sessions A/P1-P3 and resumed segments."""

    def __init__(self, workspace, card_manifest, *, pilot_seed,
                 clock: Callable[[], str], local_date: Callable[[], str]):
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.cards = list(card_manifest)                      # frozen order (dicts)
        self.card_by_id = {c["card_id"]: c for c in self.cards}
        self.order_of = {c["card_id"]: i for i, c in enumerate(self.cards)}
        self.pilot_seed = pilot_seed
        self.clock = clock
        self.local_date = local_date
        self.card_manifest_hash = sha256_hex(self.cards)
        self.responses_path = _safe_path(self.workspace, "responses.jsonl")
        self.playbacks_path = _safe_path(self.workspace, "playbacks.jsonl")
        self.segment_index = 0
        self._load()

    # --- durable-log loading + integrity (spec B6 recovery) ------------------
    def _read_jsonl(self, path: Path):
        """Return (rows, torn_tail). A durably committed row always ends with ``\\n``
        (``_append`` writes ``jsonl_line``); an unterminated final line means a torn
        write, so it is dropped and flagged even when it happens to be valid JSON
        (spec B6 amended). An interior undecodable line is gate-1 tampering.
        """
        if not path.exists():
            return [], False
        raw = path.read_text(encoding="utf-8")
        if raw == "":
            return [], False
        torn = not raw.endswith("\n")
        lines = raw.split("\n")
        if lines and lines[-1] == "":
            lines.pop()          # normal terminator
        if torn and lines:
            lines.pop()          # drop the unterminated final line (valid JSON or not)
        rows = []
        for ln in lines:
            try:
                rows.append(json.loads(ln))
            except json.JSONDecodeError:
                raise Gate1Error(f"corrupt interior line in {path.name}")
        return rows, torn

    def _load(self):
        resp, self._resp_torn = self._read_jsonl(self.responses_path)
        for r in resp:
            ResponseRow.from_dict(r)          # strict: reject any off-schema row
        self._verify_chain(resp)
        self.responses = resp
        self.playbacks, self._pb_torn = self._read_jsonl(self.playbacks_path)
        self._answers = {}
        for r in resp:
            self._answers.setdefault(r["card_id"], {})[r["question"]] = r["canonical_response"]
        for pb in self.playbacks:
            if pb.get("kind") == "skip":
                self._answers.setdefault(pb["card_id"], {})["__skipped__"] = True
        self._last_hash = sha256_hex(resp[-1]) if resp else self.card_manifest_hash
        # Continue segment numbering across restarts so a resumed segment is unique.
        segs = [row["segment_index"] for row in (self.responses + self.playbacks)]
        self.segment_index = max(segs) if segs else 0
        self._verify_order(resp)

    def _verify_chain(self, resp):
        prev = self.card_manifest_hash
        for i, r in enumerate(resp):
            if r["prev_row_hash"] != prev:
                raise Gate1Error(f"hash-chain break at response row {i} (tampering)")
            prev = sha256_hex(r)

    def _verify_order(self, resp):
        """Answered cards must appear in frozen-manifest order (subsequence)."""
        last = -1
        for r in resp:
            cid = r["card_id"]
            if cid not in self.order_of:
                raise Gate1Error(f"response for unknown card {cid}")
            idx = self.order_of[cid]
            if idx < last:
                raise Gate1Error(f"card order drift: {cid} answered out of frozen order")
            last = idx

    # --- session lifecycle ----------------------------------------------------
    def start_session(self, session_index: str, *, resume=False):
        """Open a session or a resumed segment.

        A NEW session may not start on a local date that already holds any commit
        (spec B6, one session per calendar day). A resumed segment inherits its
        origin session and bypasses that rule.
        """
        today = self.local_date()
        if not resume:
            for r in self.responses:
                if r.get("local_date") == today:
                    raise WorkloadError(
                        f"local date {today} already holds a commit; one session per day")
        self.segment_index += 1
        self.current_session = session_index
        return self.segment_index

    # --- durable actions ------------------------------------------------------
    def play(self, card_id: str):
        """Append a durable first-playback row (idempotent per card)."""
        if any(pb["card_id"] == card_id and pb.get("kind") == "playback" for pb in self.playbacks):
            return
        row = {"schema_version": SCHEMA_VERSION, "pilot_seed": self.pilot_seed, "kind": "playback",
               "card_id": card_id, "utc": self.clock(), "session_index": self.current_session,
               "segment_index": self.segment_index}
        self._append(self.playbacks_path, row)
        self.playbacks.append(row)

    def skip(self, card_id: str):
        """Record a skipped card (zero decisions, becomes unavailable truth)."""
        row = {"schema_version": SCHEMA_VERSION, "pilot_seed": self.pilot_seed, "kind": "skip",
               "card_id": card_id, "utc": self.clock(), "session_index": self.current_session,
               "segment_index": self.segment_index}
        self._append(self.playbacks_path, row)
        self.playbacks.append(row)
        self._answers.setdefault(card_id, {})["__skipped__"] = True

    def commit(self, card_id: str, question: str, displayed_response: str,
               canonical_response: str, *, recognized: bool, response_seconds: float):
        """Append one immutable committed answer (spec B6). Never a re-commit."""
        card = self.card_by_id.get(card_id)
        if card is None:
            raise Gate1Error(f"commit for unknown card {card_id}")
        if question not in QUESTIONS[card["card_type"]]:
            raise ValueError(f"question {question!r} invalid for {card['card_type']}")
        answers = self._answers.get(card_id, {})
        if question in answers:
            raise ValueError(f"immutable: {card_id}/{question} already committed")
        if len(self.responses) >= MAX_DECISIONS:
            raise WorkloadError(f"commit past {MAX_DECISIONS}-decision ceiling refused")

        row = ResponseRow(
            schema_version=SCHEMA_VERSION, pilot_seed=self.pilot_seed, card_id=card_id,
            commit_index=len(self.responses), question=question,
            displayed_response=displayed_response, canonical_response=canonical_response,
            recognized=recognized, response_seconds=float(response_seconds),
            commit_utc=self.clock(), local_date=self.local_date(),
            session_index=self.current_session, segment_index=self.segment_index,
            prev_row_hash=self._last_hash, card_manifest_hash=self.card_manifest_hash,
        ).to_dict()
        self._append(self.responses_path, row)
        self.responses.append(row)
        self._answers.setdefault(card_id, {})[question] = canonical_response
        self._last_hash = sha256_hex(row)
        return row["commit_index"]

    def _append(self, path: Path, row: dict):
        with path.open("ab") as fh:
            fh.write(jsonl_line(row))

    # --- recovery + metrics ---------------------------------------------------
    def resume(self) -> ResumeState:
        """Re-open at the first unanswered card; mark cards played-but-uncommitted."""
        first = None
        for i, c in enumerate(self.cards):
            if not _card_closed(c["card_type"], self._answers.get(c["card_id"], {})):
                first = i
                break
        committed_ids = {r["card_id"] for r in self.responses}
        played_ids = {pb["card_id"] for pb in self.playbacks if pb.get("kind") == "playback"}
        re_exposed = sorted(
            cid for cid in played_ids
            if not _card_closed(self.card_by_id[cid]["card_type"], self._answers.get(cid, {}))
            and cid not in committed_ids
        )
        return ResumeState(first_unanswered_index=first, re_exposed_card_ids=re_exposed,
                           torn_tail=self._resp_torn or self._pb_torn,
                           decisions_total=len(self.responses))

    def decisions_total(self) -> int:
        return len(self.responses)

    def active_seconds(self) -> float:
        """Sum per-segment (last durable UTC - first durable UTC) across all segments."""
        by_seg = {}
        for row in self.playbacks + self.responses:
            seg = row["segment_index"]
            utc = row.get("utc") or row.get("commit_utc")
            t = datetime.fromisoformat(utc).timestamp()
            lo, hi = by_seg.get(seg, (t, t))
            by_seg[seg] = (min(lo, t), max(hi, t))
        return sum(hi - lo for lo, hi in by_seg.values())
