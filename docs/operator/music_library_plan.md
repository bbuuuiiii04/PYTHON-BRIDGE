---
doc_status: current
truth_level: operator-working-file
last_verified_date: 2026-07-08
validation_scope: Brandon's music-library organization system, designed conversationally in the 1-1 lane. No repo code changes; no rekordbox DB writes — all library changes happen by Brandon's hands in the rekordbox UI.
---

# Brandon's Music Library Organization Plan

Working file for the 1-1 lane. Resume from here; don't make Brandon re-explain.

## The problem (agreed)
- ~800+ tracks, rekordbox 7.x, macOS.
- Adds ~40 at a time, only mixes the newest batch; the older hundreds get forgotten (recency bleed).
- Genre folders fail — tracks span many genres, so the folder never decides the next track.
- Inattentive ADHD: needs low-decision, checklist-shaped external structure, not willpower.
- More problems underneath, to be elicited a couple at a time.

## Agreed direction
Attack the **recency bleed first** (loudest problem), before any big reorg. Build a self-maintaining
"forgotten tracks" rekordbox intelligent playlist that resurfaces old/unplayed tracks on its own.
Then design the "what track goes where in a set" system on top.

## Verified rekordbox facts (2026-07-08, web-confirmed)
- Intelligent (smart) playlists exist. Path: right-click the **Playlists** section (lower-left) →
  **Create new Intelligent Playlist** → name → add conditions (criteria / operator / value) with +/− → OK.
- Available criteria include **DJ play count** and **Date Added**. There is **no "last played" date** field.
- Uncertain / to confirm on his screen: exact Date Added operators (does it support a rolling
  "older than N months", or only a fixed calendar date?), and whether the dialog has a match ALL/ANY toggle.

## Forgotten list — DONE (step 1)
Built "Forgotten" intelligent playlist, rule: **DJ play count = 0**. Result: **131 tracks** of ~800.
→ Confirmed: DJ play count IS populated in his library, so it's a usable signal. List self-maintains
(a track leaves it once he plays it out). Refinements (older-than-N-months, loosen to ≤1) deferred.

## The REAL problem (surfaced 2026-07-08, his words)
Finding the next track mid-mix eats ~**80% of his live time**. Genre organization actively hurts:
the tracks that mix well together cross genres. He named dubstep, trap, bass house, "in-between",
jersey club, ISOXO/Juelz-type trap, tech house — and good transitions jump between these (bass house →
jersey → ISOXO trap → tech house). Genre folders never answer the only live question: "what goes next?"

## Proposed direction (PENDING his veto)
Stop sorting by genre. Make **energy level the primary axis** — one label per track for how hard it hits
(e.g. 1–5, chill→peak). Rationale: mid-mix the real question is hold / lift / drop the energy, and energy
is the one axis that crosses all his genres (a bass house, jersey, and trap track can all be "a 4", any
works next). He filters to "show me my 4s" → every fitting track across genres, one glance.
- Mechanism (default, not yet his choice): rekordbox **MyTag** (multi-tag, native, nothing to install;
  scales to a second "feel" axis later).
- Anti-mountain: he does NOT hand-rate 800 tracks. Bridge already measures per-track energy → auto-fill
  is a real option → write up for the executive-manager chat (`docs/plans/active/music_library_automation_ideas.md`),
  don't build here. Today only: agree the energy labels.
- Next tiny step if he says yes: propose what the energy levels mean, he vetoes/adjusts.

## Boundaries
- No rekordbox DB writes; Brandon clicks in the UI, guided step by tiny step.
- Automation ideas (auto-tagging from spectral profiles, forgotten-gems surfacing tool) → write to
  `docs/plans/active/music_library_automation_ideas.md` and hand to his executive-manager chat; don't build here.
