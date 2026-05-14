# Laser Pad Web UI

Status: CURRENT SUPPORTING

`Laser Pad` is the browser-based configuration and test surface for Laser Director
MIDI scene mappings. It progressively replaces `tools/laser_map_wizard.py` by
sharing the same pure operations in `tools/laser_config_ops.py`.

## Launch

```bash
cd /Users/bbui
python3 -m rb_ss_bridge_v2.scripts.laser_pad --host 0.0.0.0 --port 8765
```

Open:

- `http://127.0.0.1:8765` (desktop)
- `http://<your-mac-lan-ip>:8765` (iPad on same LAN)

## Current capabilities

- Reads in-memory draft from `config/laser_director.json` via `GET /api/config`.
- Injects default additive `_pad_meta` when absent.
- Displays channel-tagged bank tabs and note grid.
- Tap note to test-fire MIDI (`/api/test_note`) honoring `dry_run`.
- Long-press note to open mapping drawer.
- Drawer autosaves to draft via `/api/draft` with `apply_mapping` parity.
- Drawer supports explicit **Set Primary** and **Remove Mapping** parity actions.
- Commit/discard controls (`/api/commit`, `/api/discard`).
- Validate and runtime verify actions (`/api/validate`, `/api/verify`).
- Collapsible validate/verify result panels persist the latest run output.
- Backup history list + diff + restore (`/api/history*`).
- In-app history drawer supports refresh, diff view, and restore-to-draft.
- Drag/drop reassignment is supported on mapped note tiles.
- Drop onto an already mapped target opens an overwrite modal and swaps notes.
- Header controls include MIDI output port selection and `dry_run` toggle.
- Personality timing controls expose phrase length, minimum hold, and buildup lookahead edits.
- Hard duplicate view by `(channel, note)` and soft duplicate warning by `note`.

## Recent updates

- `2026-05-13`: Restoring history now normalizes legacy backups and reinjects required pad/core defaults.
- `2026-05-13`: `GET /api/history` now returns deterministic JSON errors on server-side enumeration failures.
- `2026-05-13`: Drop-mode mapping removal now keeps `post_drop` references synchronized to avoid orphan scene pointers.
- `2026-05-13`: Added UI fetch-failure handling for history, drag/drop reassignment, and MIDI-port refresh actions.
- `2026-05-13`: Split live warning badge state from validate panel snapshots to prevent cross-panel clobbering.
- `2026-05-13`: Added JSON error handling for `GET /api/history/<name>/diff` bad/missing entries.
- `2026-05-13`: Hardened draft patch validation (`_pad_meta` shape) and path traversal checks.
- `2026-05-13`: Made mapping lookup channel-aware so same note can coexist across channels.
- `2026-05-13`: Added unique backup naming with microsecond precision and temp-file cleanup on save failure.

## API summary

- `GET /api/config`
- `POST /api/draft`
- `POST /api/commit`
- `POST /api/discard`
- `POST /api/test_note`
- `POST /api/validate`
- `POST /api/verify`
- `GET /api/history`
- `GET /api/history/<name>/diff`
- `POST /api/history/<name>/restore`
- `GET /api/midi_ports`

Parity tracking is maintained in `docs/laser_pad_parity.md`.

## SoundSwitch channel caveat

SoundSwitch mappings are generally note-centric. If the same note number is used
on Ch1 and Ch2, the bridge can distinguish them (`channel`, `note`) but
SoundSwitch behavior may still collide depending on your SS mapping setup.
Keep note ranges disjoint between channels unless you intentionally overlap.

## Hot reload behavior

Bridge-side config change polling is enabled through
`tools/config_reloader.py` and wired in `__main__.py`.

- If `RBSS_DISABLE_HOT_RELOAD=1`, polling is disabled.
- On file change, bridge logs reload detection.
- Current behavior logs `restart_required` rather than live-swapping runtime
  objects.
