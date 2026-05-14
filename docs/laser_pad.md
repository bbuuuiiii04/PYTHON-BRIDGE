# Laser Pad Web UI

Status: CURRENT SUPPORTING

`Laser Pad` is the browser-based configuration and test surface for Laser Director
MIDI scene mappings. The terminal wizard is retired; Laser Pad is the only
operator mapper.

## Launch

```bash
cd /Users/bbui
python3 -m rb_ss_bridge_v2.scripts.laser_pad --host 127.0.0.1 --port 8765
```

> **iPad on LAN** (optional): for operator access from another device on the same Wi-Fi,
> edit `launchagents/com.bbui.laser-pad.plist` and change `--host 127.0.0.1` to
> `--host 0.0.0.0`, then `launchctl unload` + `launchctl load` the plist. Treat this as
> a deliberate exposure — anyone on your LAN can write the laser config draft.

For the always-on login server, install the tracked LaunchAgent:

```bash
cp launchagents/com.bbui.laser-pad.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.bbui.laser-pad.plist
```

Open `http://127.0.0.1:8765`.

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
- Live runtime mirror from `GET /api/runtime_status`.
- Verify failures mark note tiles inline.
- Long-press note tiles show a progress indicator before opening the drawer.
- Drag/drop reassignment supports undo for the last move.
- Bank validation warns when channel and note ranges overlap.
- Collapsible validate/verify result panels persist the latest run output.
- Backup history list + diff + restore (`/api/history*`).
- In-app history drawer supports refresh, diff view, and restore-to-draft.
- Drag/drop reassignment is supported on mapped note tiles.
- Drop onto an already mapped target opens an overwrite modal and swaps notes.
- Header controls include MIDI output port selection and `dry_run` toggle.
- Personality timing controls expose phrase length, minimum hold, and buildup lookahead edits.
- Hard duplicate view by `(channel, note)` and soft duplicate warning by `note`.

## Recent updates

- `2026-05-14`: `_ensure_personality_exists` now backfills missing default keys on existing personalities (was: return-early). Legacy configs are self-healed on first load; explicitly-omitted defaults will be re-added.
- `2026-05-13`: Retired the terminal wizard and made Laser Pad the only mapper.
- `2026-05-13`: Added always-on LaunchAgent support for the local pad server.
- `2026-05-13`: Added live runtime mirror, inline verify dots, long-press progress, drag/drop undo, and bank overlap warnings.
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
- `GET /api/runtime_status`
- `GET /api/history`
- `GET /api/history/<name>/diff`
- `POST /api/history/<name>/restore`
- `GET /api/midi_ports`

Historical parity notes are maintained in `docs/laser_pad_parity.md`.

## Verification

- `launchctl list | grep laser-pad` shows the LaunchAgent loaded.
- Clicking menu bar **Laser Pad...** opens `http://127.0.0.1:8765` in the default browser within about 1 second.
- `curl -sS http://127.0.0.1:8765/api/config | jq .config.schema` returns a number or `null` for older configs.

## Picking up code changes

The LaunchAgent only restarts on crash (`KeepAlive.SuccessfulExit=false`). After
editing `tools/laser_pad_web.py` or any pad asset, force the agent to reload:

```bash
launchctl kickstart -k gui/$UID/com.bbui.laser-pad
```

Manual debugging launches must first unload the agent to avoid port 8765
collision:

```bash
launchctl unload ~/Library/LaunchAgents/com.bbui.laser-pad.plist
python3 -m rb_ss_bridge_v2.scripts.laser_pad --host 127.0.0.1 --port 8765
# when done:
launchctl load ~/Library/LaunchAgents/com.bbui.laser-pad.plist
```

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
