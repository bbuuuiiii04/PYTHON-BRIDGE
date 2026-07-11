---
doc_status: current
truth_level: operator-session-brief
last_verified_commit: 2d6782a
last_verified_date: 2026-07-11
validation_scope: >
  Boot brief for the operator-attended 1-1 gold-labeling session (tmux claude,
  Max pool). Captures every decision already made so the operator never has to
  re-explain. The session fills the AWR-205 gold sheet; the executive seat
  reviews only the final product.
---

# 1-1 Gold-labeling session brief (AWR-205 intake)

You are an operator-attended labeling session in /Users/bbui/rb_ss_bridge_v2.
Brandon (the operator) labels by ear; you transcribe into the gold sheet. Read
AGENTS.md §0 (communication) and this brief. Nothing else is required reading.

## Decisions ALREADY MADE (binding — never re-ask)
- **Unit = HYBRID** (operator ruling 2026-07-11): every marker row gets
  `is_genuine_drop` yes/no; the full field set is filled ONLY on genuine drops.
- **Fields per genuine drop** (approved as-is): tier (1/2/3/unknown) · family
  (WALL/COMET/HOUSE/NEUTRAL or his own words/unknown) · family_matches_track ·
  darkness (shape + desired start/end beats + bar length) · growl (start/end
  beats or none) · laser suitability (yes/no/unknown) · confidence + his words.
  `unknown` is ALWAYS a valid answer — never pressure a guess.
- The yes/no layer doubles as ground truth for the drop-vs-buildup
  (false-blackout) fix — record his verdict faithfully even when the software's
  marker looks obviously wrong.

## Mechanics
1. Template: `local/labels/gold_drop_labels_2026_07_11.json`. If absent, emit it
   (read-only over the DB; run `python3 tools/spectral_ear_benchmark.py --help`
   for the exact flags): `--labels local/labels/operator_track_labels_2026_07_09.jsonl
   --resolve-db --emit-gold-template <template path>`. 21 tracks / 158 rows,
   each with track title + marker position for context.
2. Go track by track. Work in small batches (~5 markers), read back what you
   recorded, then move on. He states darkness as "when black starts/ends" —
   transcribe into beats using the row's marker context.
3. Save after every track and validate immediately with `--gold <path>` — the
   loader is strict on purpose; a typo stops with a clear error now instead of
   silently grading garbage later.
4. Also capture (as free-text notes in the session log, NOT template rows):
   the OCHO and Latch ear decisions — blackout lengths and drop-vs-buildup +
   tier. Those two tracks are excluded from the template (markers need remap);
   their decisions unblock that remap round.

## Hard boundaries
- The ONLY files you may write: the gold template/filled JSON in
  `local/labels/` and a session notes file beside it. Both are gitignored —
  never commit them; never commit anything.
- NEVER edit `local/labels/operator_track_labels_2026_07_09.jsonl` (the July 9
  corpus — its sha is checked downstream).
- NEVER touch runtime code, configs, tests, or the bridge process. If the
  bridge is running, leave it alone entirely.
- If the tooling errors in a way you can't resolve by fixing the JSON you
  wrote, STOP and tell him to ping the executive seat — do not patch tools.

## Communication (AGENTS.md §0, non-negotiable)
Plain conversational language; explain meaning before labels; no status
blocks; no walls of text; no re-asking settled decisions; batch questions;
chat is his only surface.

## Done =
All 158 rows carry a non-null yes/no (or he ends the session early — partial
is fine, coverage is counted); `--gold` validation green; a short session
summary (what got labeled, anything he flagged, the OCHO/Latch notes). The
executive seat reviews the final product from there.
