# ANLZ Waveform Tag Inventory

Status: OFFLINE REFERENCE (advisory)

This document records read-only observations from local ANLZ files using
`tools/anlz_tag_dump.py`. It does not modify Rekordbox, ANLZ content, or runtime
bridge behavior.

## Scope

- Input files: Rekordbox ANLZ sidecars (`.DAT`, `.EXT`, `.2EX`).
- Parser: `pyrekordbox.anlz.AnlzFile` in read-only mode.
- Goal: identify tags useful for offline energy scoring.

## Observed Tag Families

- `PWV3`, `PWAV`: compact waveform-like entries. For these tags, usable energy
  height is `int(entry) & 0x1F`.
- `PQT2`, `PQTZ`: beatgrid timestamps for beat-aligned windows and ms mapping.
- `PSSI`: phrase-like semantic markers (drops, breakdowns, buildups depending on
  mood and kind mapping).
- `PWV4`, `PWV5`: waveform-adjacent tags observed but not yet used by the
  conservative energy model.
- `PCO2`, `PCOB`, `PPTH` and others: metadata/cue/path oriented tags currently
  ignored for first-pass energy scoring.

## Tag Usefulness For Energy

- **Primary**: `PWV3` / `PWAV` for normalized energy time series.
- **Primary**: `PQT2` / `PQTZ` for beat-aligned windows and inferred
  milliseconds-per-waveform-entry.
- **Secondary**: `PSSI` for marker anchors (`drop`, `breakdown`, `buildup`) in
  corpus reports.
- **Deferred**: `PWV4`/`PWV5`/`PWV6`/`PWV7`/`PWV8` until additional structure is
  validated across a larger corpus.

## Ignored Tags (Current PR) And Why

- Cue/path/library tags (`PCO2`, `PCOB`, `PPTH`, similar): not directly needed
  for local waveform intensity estimation.
- Unknown/unsupported tags: retained in dumps for inventory but not interpreted
  in scoring logic to avoid overfitting.

## Limitations And Uncertainty

- Sparse beatgrids (for example only 2 timestamps in a `PQT2`) are not reliable
  for duration inference.
- `PWV3`/`PWAV` resolution depends on inferred total duration; small duration
  errors shift ms-per-entry.
- `PSSI` semantics differ by `mood`; the current mapping is conservative and
  aligned with existing parser behavior in `anlz_reader.py`.
- Classification output is advisory until validated on a larger corpus.

## Example Dump Excerpt

Command used locally:

```bash
python3 tools/anlz_tag_dump.py --json --limit-samples 4 --out scratch/anlz_sample_dump.json "/Users/bbui/Library/Pioneer/rekordbox/share/PIONEER/USBANLZ/eac/ed59d-f6a1-4814-a850-312b003de118/ANLZ0000.DAT"
```

Excerpt (`scratch/anlz_sample_dump.json`):

```json
{
  "path": "/Users/bbui/Library/Pioneer/rekordbox/share/PIONEER/USBANLZ/eac/ed59d-f6a1-4814-a850-312b003de118/ANLZ0000.EXT",
  "size_bytes": 139548,
  "tag_types": ["PCO2", "PCOB", "PPTH", "PQT2", "PSSI", "PWV3", "PWV4", "PWV5"],
  "tag_counts": {"PQT2": 1, "PSSI": 1, "PWV3": 1},
  "inferred_track_duration_ms": 289323.0
}
```
