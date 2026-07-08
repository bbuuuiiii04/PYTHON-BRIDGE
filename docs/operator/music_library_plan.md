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

## Current step (in progress)
Build ONE intelligent playlist with a single rule: **DJ play count is 0** (never played out).
Purpose is double: it's the truest "forgotten" signal, AND the match count tells us whether DJ play
count is even populated in his library.
- **Open question / gate:** how many of the ~800 tracks land in it?
  - A sane fraction (roughly a few hundred) → play count is a real signal, build on it.
  - ~all 800 or ~0 → play count isn't tracked in his workflow; pivot to a Date Added–based rule.

## Next steps (not started)
- Depending on the count, refine the forgotten rule (add "older than ~2 months", loosen to play count ≤ 1, etc.).
- Then the set-position / energy system (measured audio character per track is or will be available
  from the repo's spectral pipeline — organization by measured vibe/energy is a real option).

## Boundaries
- No rekordbox DB writes; Brandon clicks in the UI, guided step by tiny step.
- Automation ideas (auto-tagging from spectral profiles, forgotten-gems surfacing tool) → write to
  `docs/plans/active/music_library_automation_ideas.md` and hand to his executive-manager chat; don't build here.
