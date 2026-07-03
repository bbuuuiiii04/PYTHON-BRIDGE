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
- The in-memory draft is durably backed by `config/laser_director.draft.json`
  (gitignored). Every successful draft mutation (`/api/draft`, personality
  create/rename/duplicate/delete, bank reset, role cooldown, history restore)
  atomically writes the draft file while holding the service lock. On startup,
  if the draft file exists it is loaded (and self-healed with the same
  normalizers as `restore_history`) instead of the live config, so unsaved
  mapping work survives a LaunchAgent crash/restart. If the draft file is
  unreadable (bad JSON, non-dict root, or an OS read error), it is renamed in
  place to `<name>.draft.json.corrupt` (overwriting any previous quarantine),
  a warning is printed to stderr, and the service falls back to the live
  config — it never crash-loops the LaunchAgent and never silently discards
  the bad file. `POST /api/commit` deletes the draft file after a successful
  save; `POST /api/discard` reloads from the live config and deletes the
  draft file.
- Injects default additive `_pad_meta` when absent.
- Displays channel-tagged bank tabs and note grid.
- Tap note to test-fire MIDI (`/api/test_note`) honoring `dry_run`.
- Long-press note to open mapping drawer.
- Drawer autosaves to draft via `/api/draft` with `apply_mapping` parity.
- Drawer supports explicit **Set Primary** and **Remove Mapping** parity actions.
- Commit/discard controls (`/api/commit`, `/api/discard`), including a header
  **Discard** button next to **Save & Apply** that opens an in-app confirm
  modal (danger-styled) before reverting all unapplied edits to the last
  applied config.
- Validate and runtime verify actions (`/api/validate`, `/api/verify`). The ▶
  button is labeled "Check mappings — no lasers fired": it runs `/api/verify`
  against a mock MIDI backend (`_DryCheckMidiOutput`) and never fires
  hardware. The results panel heading reads "Mapping check results".
- The save badge distinguishes an unsaved draft ("Draft saved …") from a
  committed config ("Applied …") so the badge never implies unsaved work has
  reached the running bridge.
- Alpine.js is vendored at `tools/laser_pad_assets/alpine.min.js` (no CDN
  dependency) — the pad UI now loads and functions with no internet access.
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

- `2026-07-03`: Vendored Alpine.js (`tools/laser_pad_assets/alpine.min.js`, SRI-verified against the previous CDN pin) so the pad works with no internet access. Added a durable `config/laser_director.draft.json` draft file (atomic writes, corrupt-file quarantine + fallback, cleared on commit/discard) so unsaved mapping work survives a LaunchAgent crash. Added a header Discard button with a confirm modal. Renamed the ▶ button/results panel to make clear the mapping check never fires lasers, and split the save badge into "Draft saved" vs "Applied" states.
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
- `GET /api/access`

Historical parity notes are maintained in `docs/guides/laser_pad_parity.md`.

## Open on another device (QR)

The header has a 📱 button ("Open on another device"). It calls `GET /api/access`, which
reports the pad's current bind address; it never changes bind behavior by itself —
exposing the pad to the LAN is still the explicit `--host 0.0.0.0` / LaunchAgent edit
described above.

Three states:
- **LAN URL available** (pad bound to a non-loopback host): shows a QR code and a
  selectable plain URL for the pad's LAN address, plus a warning that anyone on the same
  Wi-Fi can edit the laser config draft through this page.
- **Loopback only** (default `--host 127.0.0.1`): no QR. Explains that reaching the pad
  from another device requires restarting it with `--host lan`, or editing
  `~/Library/LaunchAgents/com.bbui.laser-pad.plist` and running
  `launchctl kickstart -k gui/$UID/com.bbui.laser-pad`, and that doing so exposes pad
  control to the whole network.
- **No LAN address detected**: bound non-loopback but LAN IP detection failed — check
  Wi-Fi.

This is plain HTTP, not HTTPS — the QR/URL is a convenience for typing a LAN address on
a phone, not a security boundary. Firewalls or Wi-Fi client (AP) isolation can still
block another device from reaching the LAN URL even when one is detected.

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
