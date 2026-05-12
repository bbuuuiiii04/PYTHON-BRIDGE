# ANLZ Energy Corpus Report Template

Status: VALIDATION TEMPLATE (offline/advisory)

This report format is for offline evidence collection only. It does not change
runtime `StateManager`, Smart Phrasing decisions, OS2L behavior, or MIDI output.

## Generate A Real Report Locally

From repository root:

```bash
python3 tools/analyze_anlz_energy_corpus.py \
  --manifest /path/to/anlz_energy_manifest.json \
  --jsonl-out scratch/anlz_energy_corpus.jsonl \
  --report-out scratch/anlz_energy_corpus_report.md
```

Direct ANLZ mode (single track group):

```bash
python3 tools/analyze_anlz_energy_corpus.py \
  --anlz "/path/to/ANLZ0000.DAT" \
  --jsonl-out scratch/anlz_energy_single.jsonl \
  --report-out scratch/anlz_energy_single.md
```

## Expected Interpretation (Advisory)

- `peak` drop: candidate for blackout-mask and high laser intensity.
- `medium` drop: normal smart-drop behavior.
- `subtle` drop: avoid blackout-style treatment.
- true low breakdown (`major`/`peak` breakdown class): prefer clear/minimal look.
- `low_confidence`: no automatic behavior change.

## Performance Profile Label Hints

- `high_energy_peak`: multiple major/peak drops.
- `standard_dance`: mixed energetic events with moderate confidence.
- `breakdown_heavy`: repeated strong breakdown evidence and weak drop evidence.
- `chill_minimal`: limited strong drops and generally restrained dynamics.
- `unknown`: insufficient markers or insufficient confidence.

## JSONL Output Schema

Each line is one JSON object (`record_type` is either `track` or `marker`).

- Track record fields:
  - `record_type`: `"track"`
  - `track_index`, `track_id`
  - `track_filepath`, `anlz_path`
  - `waveform_source`
  - `total_ms`
  - `beatgrid_count`, `total_beats`
  - `drop_marker_count`, `breakdown_marker_count`, `buildup_marker_count`, `marker_count_total`
  - `performance_profile_hint`
  - `warnings` (when extraction or input issues are detected)
- Marker record fields:
  - `record_type`: `"marker"`
  - `track_index`, `track_id`
  - `track_filepath`, `anlz_path`
  - `marker_kind`, `beat`, `elapsed_ms`
  - `waveform_source`
  - `pre_mean`, `post_mean`, `lift`
  - `confidence`, `class_name`, `recommended_action`
  - `performance_profile_hint`
  - `warning` (present on degraded/low-confidence fallback rows)

## Auto-generated Section Anchor

The analyzer writes Markdown output independently. Copy or append generated
content below this heading when preserving a run in-repo.

---

<!-- AUTO-GENERATED REPORT CONTENT BELOW -->
