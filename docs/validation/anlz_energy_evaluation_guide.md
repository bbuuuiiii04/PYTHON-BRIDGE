# ANLZ Energy Evaluation Guide

Status: CURRENT SUPPORTING

Use this guide to validate the bridge-local ANLZ energy tooling with a small,
human-reviewed corpus before trusting any future automation.

## Goal

Answer two different questions separately:

1. **Marker quality**: did Rekordbox identify the right event at the right beat?
2. **Energy quality**: given a correct event beat, is the energy label useful?

Do not collapse those into one judgment.

## Recommended Corpus Size

Start with **8-10 tracks** only.

That is enough for a first-pass answer to:

- is the tooling useful at all?
- are the labels directionally right?
- are some genres obviously mis-anchored by Rekordbox?

Prefer diversity over size.

Recommended mix:

- 2 house / tech house
- 2 bass house
- 2 dubstep
- 2 techno / hard techno
- optional 1-2 wildcard tracks you know very well

## Commands

### 1. Tag inventory

```bash
python3 tools/anlz_tag_dump.py --json --limit-samples 8 /path/to/ANLZ0000.DAT
```

### 2. Direct single-track analysis

```bash
python3 tools/analyze_anlz_energy_corpus.py \
  --anlz /path/to/ANLZ0000.DAT \
  --jsonl-out scratch/anlz_single.jsonl \
  --report-out scratch/anlz_single.md
```

### 3. Manifest-based batch analysis

```bash
python3 tools/analyze_anlz_energy_corpus.py \
  --manifest scratch/anlz_energy_manifest.json \
  --jsonl-out scratch/anlz_energy_corpus.jsonl \
  --report-out scratch/anlz_energy_corpus_report.md
```

## Minimal Manifest Shape

Use this when Rekordbox markers are wrong or when you want to override them.

```json
[
  {
    "track_filepath": "/path/to/track.mp3",
    "anlz_path": "/path/to/ANLZ0000.DAT",
    "drop_beats": [128, 320],
    "breakdown_beats": [96],
    "buildup_beats": [112, 304],
    "beatgrid_times_ms": [],
    "total_ms": 0
  }
]
```

Notes:

- If `waveform_values` / `energy_values` are missing and `anlz_path` exists, the
  analyzer will extract waveform data itself.
- Manifest beatgrid and marker fields win when present.
- Extraction errors degrade to warnings plus `low_confidence` rows.

## Human Review Rubric

For pass 1, do **not** label every marker in detail unless needed.

Per track, answer only:

1. Biggest drop in the track:
   - `low` / `medium` / `high` / `peak`
2. Deepest breakdown in the track:
   - `low` / `medium` / `high` / `peak`
3. Strongest buildup in the track:
   - `low` / `medium` / `high` / `peak`
4. Overall vibe:
   - `groove` / `drive` / `contrast` / `peak` / `unknown`

## Genre-Aware Scoring Notes

### House

- often lands as `groove`
- some big chorus hits can be `high` / `peak`
- not every drop should be `peak`

### Bass House

- can land as `groove`, `contrast`, or `peak`
- many tracks stay hot, so grade events by **local change**, not absolute force

### Dubstep

- often feels `peak` overall
- breakdowns may still be very loud in absolute terms
- only call a breakdown `high` / `peak` if it creates a real low-energy valley

### Techno / Hard Techno

- often feels `drive` overall
- many transitions are forceful without being dramatic drop-payoff moments
- plenty of events may be `medium` / `high` without being `peak`

## The Most Important Rule

Do **not** ask:

- "is this section intense?"

Ask:

- "how strong is the change around this marker relative to the nearby track
  context?"

That avoids labeling every dubstep or hard techno event as `peak`.

## How To Handle Wrong Rekordbox Markers

If Rekordbox phrase analysis is wrong:

- mark the event as **bad anchor**
- do not use it as evidence against the energy classifier
- either skip it or override the beat/type through the manifest

Examples of bad anchor cases:

- wrong type (`breakdown` that is really a `buildup`)
- wrong timing (8 or 16 beats early/late)
- missing important marker
- extra marker that does not matter musically

## Suggested Evidence Table

Keep a simple sheet like this:

| Track | Genre | RB anchor quality | Biggest drop | Deepest breakdown | Strongest buildup | Overall vibe | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Artist - Title | dubstep | bad / mixed / good | peak | medium | high | peak | RB drop 8 beats early |

## What Good Early Results Look Like

Promising first-pass outcomes:

- biggest drops usually score `high` or `peak`
- techno/hard techno often lands as `drive`
- groove-forward house often lands as `groove`
- tracks with obvious breakdown/rebuild structure often land as `contrast`
- clearly ambiguous cases fall back to `low_confidence` instead of overclaiming

## What To Conclude If Rekordbox Is Weak

If bass house, dubstep, and some techno show bad Rekordbox anchors, the right
conclusion is:

- ANLZ waveform energy still looks useful
- Rekordbox phrase markers are not reliable enough to be the only anchor source
- future work should evaluate better anchor sources separately from energy logic

That is still a successful validation result.

## Merge-Safe Current Conclusion

At the current project stage, the safe recommendation is:

- keep the tooling offline and advisory
- validate with a small human-reviewed corpus
- trust energy scoring more than phrase anchors for weak Rekordbox genres
- do not move to runtime automation until local evidence is convincing
