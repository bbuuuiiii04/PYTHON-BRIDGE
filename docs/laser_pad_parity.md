# Laser Pad Parity Matrix

Status: CURRENT SUPPORTING

This matrix tracks parity between terminal wizard actions and the Laser Pad web UI/API.

| Wizard action | Laser Pad UI/API path | Status | Notes |
| --- | --- | --- | --- |
| Show current mappings | Note grid + drawer labels | Implemented | `GET /api/config` drives role/safety/labels per note. |
| Add or update mapping | Long-press note → drawer → autosave/apply | Implemented | Uses `/api/draft` mapping payload and shared `apply_mapping`. |
| Edit existing mapping note | Drawer note context + drag/drop note reassignment | Implemented | Drag/drop preserves scene metadata and reassigns notes/channels. |
| Edit behavior / hold length | Drawer behavior + hold fields | Implemented | Supports `pulse`, `hold_beats`, `hold_ms`, `note_on`, `note_off`. |
| Remove mapping from bank | Drawer **Remove Mapping** button | Implemented | Removes scene and updates role bank/primary via `/api/draft` patch. |
| Set as primary | Drawer **Set Primary** button | Implemented | Reorders role bank and updates role primary scene field. |
| Timing / cooldowns | Header timing card + drawer cooldown field | Implemented | Personality timing + per-note cooldown are patchable from UI. |
| Advanced Safety Metadata | Drawer `safety_class` selector | Implemented | Mirrors wizard expert safety edit path. |
| Verify mappings actually work | Header **Verify** + verify result panel | Implemented | Calls `POST /api/verify`. |
| Validate mappings | Header **Validate** + validate result panel | Implemented | Calls `POST /api/validate`. |
| Test a MIDI note | Header quick-test + tap tile | Implemented | Calls `POST /api/test_note`. |
| Set MIDI output port | Header port selector + refresh | Implemented | Uses `GET /api/midi_ports` and `/api/draft` patch. |
| Toggle `dry_run` | Header `Dry Run` checkbox | Implemented | Writes `dry_run` through `/api/draft`. |
| Save and exit | **Commit** | Implemented | Uses `/api/commit` with validation gating. |
| Exit without saving | **Discard** | Implemented | Uses `/api/discard` reload-from-disk semantics. |
| Backup history diff/restore | History drawer | Implemented | Uses `/api/history`, `/api/history/<name>/diff`, `/api/history/<name>/restore`. |

## Scope notes

- Runtime behavior remains unchanged by UI-only parity features.
- All parity actions are draft-first and only persisted through explicit commit.
- Terminal wizard remains available during deprecation period.
