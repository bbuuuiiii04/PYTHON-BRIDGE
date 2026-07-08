---
doc_status: current
truth_level: proposal
last_verified_date: 2026-07-08
validation_scope: Idea handoff for Brandon's executive-manager chat. No repo code changes and no rekordbox DB writes were made. Nothing here is built.
---

# Music Library Auto-Tagging — proposal for the executive-manager chat

## Why this exists
Brandon needs his ~800-track rekordbox library findable by feel (his own families: **Banger / Chill /
Euphoric / Mainstage / Tech House**) WITHOUT hand-tagging 800 tracks. Manual tagging is exactly the
willpower-marathon his ADHD bounces off — the 1-1 session ended on that friction ("this was no help").
The unlock is a tool that **proposes** tags so he only confirms, never grinds.

## What we already learned (verified 2026-07-08 — do NOT re-derive)
- The bridge's v4 spectral cache (~660/801 tracks, `~/Library/Application Support/RBSS Bridge/spectral_cache/v4/`)
  stores 8 acoustic **texture** scalars — grit, punch, drama, brightness_med, loudness_ref_db, + derived
  bass_duty — **not felt energy**. Refs: `audio_spectral_features.py:118-121`, `spectral_cache.py:284-296`.
- Those scalars do **not** match Brandon's ear. Proof: his CHILL pick "Utopia" = highest punch (1.48) and top
  drama (19.3); his BANGER "Force Majeure" = lowest drama (8.0). A naive scalar→energy mapping mislabels him.
- A real per-track vibe labeler **exists but has never been run**: `energy_model.py` +
  `tools/analyze_anlz_energy_corpus.py` (labels groove/drive/contrast/peak). Zero output on disk today.

## Proposed path (cheapest first)
1. **Alignment probe (read-only — do this first).** Run the existing labeler on the v4 cache. Make a table of
   Brandon's 17 hand-labeled tracks (listed in `docs/operator/music_library_plan.md`) vs the tool's label.
   Report how well they agree. If it matches his ear → use it to propose tags. Cheap; tells us if this is alive.
2. **If the labeler doesn't align → learn HIS mapping.** Brandon hand-labels ~50–100 tracks (he does this in
   seconds by ear). Train a small model on the cached scalars + ANLZ features to predict his vibe-family for the
   rest as **suggestions**. Must generalize across his whole EDM catalog, not per-track tuning (operator rule).
3. **Output = suggestions he approves, never silent DB writes.** Hard boundary: do NOT write rekordbox's DB
   directly. Deliver as an approve-list he clicks in the rekordbox UI, or a rekordbox XML/USB import he reviews.
   His ear is the authority; the tool is a first-pass draft he overrides.

## Non-goals
- Replacing his ear. Auto-tags are a draft, not truth.
- Building any of this inside rb_ss_bridge_v2 without an operator-sanctioned spec. This file is the idea only.
