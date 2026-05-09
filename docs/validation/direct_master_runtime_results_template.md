# Direct Master Runtime Results Template

Status: VALIDATION REFERENCE

Use one copy of this template per live run.

## Run Metadata

- Date/time:
- Machine:
- Rekordbox version:
- Bridge branch/commit:
- Capture file:
- Operator:

## Scenario

Select one:

- [ ] startup into playback
- [ ] stable window, no master change
- [ ] intentional single master switch

Planned master behavior:

-

## Captured Runtime Lines

Paste the relevant `[RBMASTER][RUNTIME]` lines.

```text
phase=start:
phase=initial:
phase=first_valid:
phase=mismatch: none
phase=summary:
```

## Summary Fields

Copy these from the `phase=summary` line exactly as logged.

- `outcome`:
- `final_direct_master`:
- `final_tl_master`:
- `transition_count`:
- `mismatches`:
- `first_valid_elapsed_s`:
- `comparison_source`:
- `authority`:

Expected fixed values:

- `comparison_source=tl_master_snapshot`
- `authority=tl_log`

## Result Classification

Select one:

- [ ] encouraging
- [ ] inconclusive
- [ ] concerning

Reason:

-

## Notes

Anything unusual in logs, timing, operator actions, or Rekordbox state:

-

Follow-up needed:

-
