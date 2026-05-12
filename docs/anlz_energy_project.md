# ANLZ Energy Project

Status: CURRENT SUPPORTING

Audited against the current checkout on 2026-05-12.

This document describes the bridge-local ANLZ energy investigation toolkit. The
project is intentionally offline and advisory-only: it helps evaluate musical
energy around drops, breakdowns, and buildups without changing live bridge
behavior.

## Purpose

The bridge already knows where some interesting musical events happen:

- `filepath_resolver.py` resolves ANLZ paths and beatgrid metadata.
- `anlz_reader.py` extracts ANLZ phrase markers and waveform-derived shadow
  hints for runtime use.
- `StateManager` already consumes `ANLZ_DATA` containing drop, breakdown, and
  buildup indices plus `mood` and `energy_shadow`.

What the bridge did **not** have was a separate offline workflow for answering:

- how strong is this drop?
- is this breakdown truly low-energy?
- is this buildup actually rising?
- is blackout-mask musically justified?
- what laser intensity might fit this event?
- what whole-track vibe should an operator expect?

This project adds that missing offline toolkit.

## Non-goals

This project does **not**:

- change runtime OS2L behavior
- change runtime MIDI / laser behavior
- modify `StateManager`, `SmartPhrasingEngine`, or `SoundSwitchEngine`
- patch Rekordbox or SoundSwitch
- write to Rekordbox DB or ANLZ files
- bypass DRM or encrypted protections

Everything here is evidence gathering and analysis only.

## Files

### Core module

- `energy_model.py`

Pure computation only. No filesystem, no subprocess, no DB access, no network,
no SoundSwitch, no Rekordbox process access.

Provides:

- normalized energy series
- beat/index/ms mapping helpers
- marker-centered energy windows
- event intensity classification

Shared event intensity labels:

- `low`
- `medium`
- `high`
- `peak`
- `low_confidence`

These labels are reused across:

- drops
- breakdowns
- buildups

The labels always mean "how strong is the local energy change around this
marker?" The direction depends on marker type:

- drop: upward payoff / release
- breakdown: downward reduction / valley
- buildup: upward ramp / tension growth

### Read-only CLI tools

- `tools/anlz_tag_dump.py`
- `tools/analyze_anlz_energy_corpus.py`

`anlz_tag_dump.py` inventories ANLZ tags and safe samples.

`analyze_anlz_energy_corpus.py` turns ANLZ + marker inputs into:

- per-track JSONL
- per-marker JSONL
- Markdown reports

### Supporting docs

- `docs/re/anlz_waveform_tag_inventory.md`
- `docs/validation/anlz_energy_corpus_report.md`
- `docs/validation/anlz_energy_evaluation_guide.md`

## Data Model

The project relies on three ANLZ information layers:

1. Beatgrid timing (`PQT2` / `PQTZ`)
2. Waveform-like energy (`PWV3` / `PWAV`)
3. Phrase markers (`PSSI`) when available

The energy model does not require `PSSI` specifically. It only requires:

- a beat to analyze
- beatgrid times
- waveform energy values

That means the energy scorer can work with:

- Rekordbox phrase markers
- manually corrected manifest markers
- future custom marker detectors

## What The Current Model Actually Measures

The current model is **marker-centered**, not full-phrase-aware.

For each marker beat:

- take a fixed beat window before the marker
- take a fixed beat window after the marker
- compare the average normalized waveform energy on both sides

So the model currently answers:

- "how strong is this event?"

It does **not yet** answer:

- "how energetic is the entire phrase section?"
- "how does the whole previous phrase compare to the next phrase?"

That distinction matters for heavy genres where the whole track can remain hot
even while relative event contrast is small.

## Track-level Vibe Labels

The current operator-facing whole-track labels are:

- `groove`
- `drive`
- `contrast`
- `peak`
- `unknown`

Intended meaning:

- `groove`: steady danceable movement, not dominated by giant payoff hits
- `drive`: sustained pressure / rolling intensity
- `contrast`: shaped by strong breakdown versus payoff contrast
- `peak`: built around repeated high-impact drop payoffs
- `unknown`: insufficient evidence

These are advisory heuristics derived from marker outcomes, not authoritative
genre labels.

## Current Limitations

### 1. Rekordbox phrase markers are genre-dependent

Current local operator findings suggest Rekordbox phrase markers are weaker for:

- bass house
- dubstep
- some techno / hard techno

That means two separate quality questions must be tracked:

1. **anchor quality**: did Rekordbox put the right marker at the right beat?
2. **energy quality**: given a correct beat, is the energy label useful?

The energy model can still be valuable even when Rekordbox markers are not.

### 2. High-energy tracks can have low-contrast events

In dubstep, bass house, and some hard techno, the track may stay intense for a
long time. In those cases:

- the whole track vibe may be `peak` or `drive`
- a "breakdown" can still be high-energy in absolute terms
- but the **breakdown event strength** may still only be `low` or `medium`

The model is designed to capture **relative transition strength**, not simply
absolute loudness or aggression.

### 3. `low_confidence` is expected

`low_confidence` is not a failure by itself. It usually means:

- missing waveform data
- missing or short beatgrid
- too few samples around the marker
- weak evidence for clear contrast

This is intentionally conservative.

## Recommended Validation Mindset

For evaluation, use:

- **overall vibe** for whole-track personality
- **event intensity** for local transition strength

Do not ask:

- "is this section energetic?"

Ask:

- "how strong is the change around this marker compared with nearby context?"

That is especially important for dubstep and hard techno.

## Preferred Evaluation Workflow

1. Generate a real report with `tools/analyze_anlz_energy_corpus.py`
2. Review only a small but diverse set of tracks first
3. Separate:
   - wrong Rekordbox marker
   - correct marker but weak energy classification
4. Override bad Rekordbox markers through a manifest when needed
5. Treat results as advisory until local corpus validation is convincing

See `docs/validation/anlz_energy_evaluation_guide.md` for the detailed
operator workflow.

## Future Work (Not Implemented)

Possible later phases, intentionally out of scope for the current PR:

- phrase-aware full-section scoring
- custom marker anchoring for genres where Rekordbox is weak
- manual-correction manifest helpers
- future runtime integration, only after evidence is strong

None of those are live today.

## Summary

This project is best understood as:

- a read-only ANLZ waveform energy toolkit
- useful for scoring event strength
- promising for advisory decisions
- not yet a runtime authority
- only as good as its marker source unless markers are corrected manually
