# PSSI mood 2/3 UP mapping spike (2026-05-10)

Purpose: confirm mood `2/3` UP-kind mapping from real local Rekordbox ANLZ data
before wiring Laser Director buildup gating.

## Method

- Added `scripts/dump_pssi_phrases.py` and ran it against real local
  `ANLZ0000.DAT` paths (with sibling `.EXT/.2EX` scan).
- Focused on tracks where PSSI `mood` is `2` or `3`.
- Inspected marker order around the first `kind==9` (CHORUS/drop) marker.
- Candidate UP kinds inspected: `4`, `5`, `10`, `11`, `12`.

## Observations

- Confirmed existing mappings remain:
  - mood `2/3`: `kind==8` -> LOW/breakdown, `kind==9` -> CHORUS/drop.
- In real mood `2/3` tracks, kinds `4` and `5` appear in pre-drop buildup
  sections before `kind==9`.
- `kind==10` appears in some tracks but was not observed as a pre-first-drop UP
  marker in this spike.
- `kind==11` and `kind==12` were not observed in the sampled mood `2/3` tracks.

## Result used for implementation

- mood `2/3` confirmed UP kinds for this implementation: `4` and `5`.
