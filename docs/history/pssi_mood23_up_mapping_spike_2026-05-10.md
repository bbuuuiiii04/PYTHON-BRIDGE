# PSSI mood 2/3 UP mapping spike (2026-05-10)

Status: HISTORICAL spike record (2026-05-10); evidence only.

Purpose: confirm mood `2/3` UP-kind mapping from real local Rekordbox ANLZ data
before wiring Laser Director buildup gating.

## Method

- Added `scripts/dump_pssi_phrases.py` and ran it against real local
  `ANLZ0000.DAT` paths (with sibling `.EXT/.2EX` scan).
- Focused on tracks where PSSI `mood` is `2` or `3`.
- Inspected marker order around the first `kind==9` (CHORUS/drop) marker.
- Candidate UP kinds inspected: `4`, `5`, `10`, `11`, `12`.

## Raw evidence excerpts (real mood 2/3 tracks)

Notes:
- `source_ref` is a redacted relative reference under Rekordbox `USBANLZ`.
- `evidence_id_path_sha1_12` is SHA1 of `source_ref` (first 12 hex chars).
- `evidence_id_file_sha1_12` is SHA1 of file bytes (first 12 hex chars).
- `elapsed` is from beatgrid when available; `n/a` when unavailable in this
  compact slice.

### Evidence 1

- track: `HUMAN EVIL EDIT FINAL 1.2 - SNAPT`
- source_ref: `112/d384c-e563-4a34-97dc-bf242d5298d0/ANLZ0000.EXT`
- mood: `2`
- evidence_id_path_sha1_12: `2a72b91c7548`
- evidence_id_file_sha1_12: `2bb9c455e68c`
- first `kind==9` CHORUS/drop bridge beat: `288`
- pre-first-drop candidate rows seen: `(80,4,2,n/a)`, `(128,5,2,n/a)`

Compact rows around first `kind==9`:

```text
bridge_beat, kind, mood, elapsed
80,  4, 2, n/a
128, 5, 2, n/a
192, 6, 2, n/a
256, 7, 2, n/a
288, 9, 2, n/a   <- first CHORUS/drop
352, 2, 2, n/a
384, 3, 2, n/a
416, 4, 2, n/a
432, 9, 2, n/a
```

### Evidence 2

- track: `soundcloud:tracks:1476661285`
- source_ref: `202/afd60-6c89-489a-96f8-847323cba5fe/ANLZ0000.EXT`
- mood: `2`
- evidence_id_path_sha1_12: `9c3b6c6e2dd8`
- evidence_id_file_sha1_12: `94c2087aacf1`
- first `kind==9` CHORUS/drop bridge beat: `201`
- pre-first-drop candidate rows seen: `(137,4,2,n/a)`, `(169,5,2,n/a)`

Compact rows around first `kind==9`:

```text
bridge_beat, kind, mood, elapsed
37,  2, 2, n/a
57,  3, 2, n/a
137, 4, 2, n/a
169, 5, 2, n/a
201, 9, 2, n/a   <- first CHORUS/drop
265, 9, 2, n/a
297, 9, 2, n/a
333, 9, 2, n/a
```

### Evidence 3

- track: `GRiZ - Side Quest Vol. 1 - 14 I Remember - Deadmau5 & Kaskade (GRiZ flip)`
- source_ref: `239/0dbd1-ee69-485b-a0b5-57fd58dac726/ANLZ0000.EXT`
- mood: `3`
- evidence_id_path_sha1_12: `0e3b8b89cfd2`
- evidence_id_file_sha1_12: `8ec58137dd85`
- first `kind==9` CHORUS/drop bridge beat: `160`
- pre-first-drop candidate rows seen: `(96,4,3,n/a)`, `(128,4,3,n/a)`,
  `(136,8,3,n/a)`

Compact rows around first `kind==9`:

```text
bridge_beat, kind, mood, elapsed
36,  3, 3, n/a
96,  4, 3, n/a
128, 4, 3, n/a
136, 8, 3, n/a   <- LOW/breakdown marker
160, 9, 3, n/a   <- first CHORUS/drop
176, 9, 3, n/a
192, 9, 3, n/a
208, 9, 3, n/a
```

### Evidence 4

- track: `01 - Crankdat x Kompany - MOVE B-TCH (CRANKDAT & KOMPANY REMIX)`
- source_ref: `318/4e5db-88fb-40f3-959a-388d0264f68b/ANLZ0000.EXT`
- mood: `3`
- evidence_id_path_sha1_12: `8316b067b1af`
- evidence_id_file_sha1_12: `295d5d712f2a`
- first `kind==9` CHORUS/drop bridge beat: `147`
- pre-first-drop candidate rows seen: `(127,8,3,n/a)`

Compact rows around first `kind==9`:

```text
bridge_beat, kind, mood, elapsed
0,   1, 3, 0
15,  1, 3, n/a
79,  2, 3, n/a
127, 8, 3, n/a   <- LOW/breakdown marker
147, 9, 3, n/a   <- first CHORUS/drop
179, 3, 3, n/a
207, 2, 3, n/a
223, 2, 3, n/a
271, 8, 3, n/a
```

### Evidence 5

- track: `tidal:tracks:72500654`
- source_ref: `3fe/bfb29-0bde-40ae-8a89-4cda7190d695/ANLZ0000.EXT`
- mood: `2`
- evidence_id_path_sha1_12: `428753f32617`
- evidence_id_file_sha1_12: `07baa006e34d`
- first `kind==9` CHORUS/drop bridge beat: `260`
- pre-first-drop candidate rows seen: `(64,4,2,n/a)`, `(128,5,2,n/a)`,
  `(224,4,2,n/a)`

Compact rows around first `kind==9`:

```text
bridge_beat, kind, mood, elapsed
64,  4,  2, n/a
128, 5,  2, n/a
156, 6,  2, n/a
192, 7,  2, n/a
224, 4,  2, n/a
260, 9,  2, n/a   <- first CHORUS/drop
288, 8,  2, n/a   <- LOW/breakdown marker
308, 2,  2, n/a
320, 10, 2, n/a   <- candidate present but after first drop
```

## Observed mapping conclusion from excerpts

- Confirmed existing mapping:
  - mood `2/3`: `kind==8` -> LOW/breakdown
  - mood `2/3`: `kind==9` -> CHORUS/drop
- Confirmed UP candidates before first CHORUS/drop:
  - `kind==4` observed pre-first-drop (multiple tracks above)
  - `kind==5` observed pre-first-drop (Evidence 1 and 2)
- `kind==10` appears in sampled mood `2/3` tracks, but not as a confirmed
  pre-first-drop UP marker in these excerpts.
- `kind==11` and `kind==12` were not observed in sampled mood `2/3` tracks.

## Result used for implementation

- mood `2/3` confirmed UP kinds for implementation: `4` and `5`.
