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
- The master **Lasers enabled** toggle writes the enabled value to the draft and appends one
  runtime command line to the bridge command file:
  `{"cmd":"set_laser_director","enabled":true|false}`. That is the only Laser Pad draft patch that
  directly changes the running bridge. If the command append fails, the API reports an error instead
  of pretending the live toggle succeeded; the draft save remains durable.
- Injects default additive `_pad_meta` when absent.
- Displays channel-tagged bank tabs and note grid.
- Tap note to test-fire MIDI (`/api/test_note`) honoring `dry_run`.
- Long-press note to open mapping drawer.
- Drawer autosaves to draft via `/api/draft` with `apply_mapping` parity.
- Drawer supports explicit **Set Primary** and **Remove Mapping** parity actions.
- Commit/discard controls (`/api/commit`, `/api/discard`), including a header
  **Discard** button next to **Apply** that opens an in-app confirm
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
- The mapping drawer's "Move to pad" select is a touch fallback for drag/drop reassignment (iOS
  Safari does not support HTML5 drag/drop): it goes through the same reassignment path a drop
  would take, including the overwrite dialog and undo bar. Disabled for system-managed
  (blackout) pads, matching "Move to bank".
- Header controls include MIDI output port selection and `dry_run` toggle.
- Personality timing controls expose phrase length, minimum hold, and buildup lookahead edits.
- Hard duplicate view by `(channel, note)` and soft duplicate warning by `note`.

## Recent updates

- `2026-07-03`: Audit P4 live-toggle truth pass — the master **Lasers enabled** toggle now says
  "Immediate live toggle + saved to draft" and does both things. `/api/draft` still persists the
  enabled value to the durable draft file, and enabled patches also append the canonical
  `set_laser_director` runtime command using `runtime_status.COMMANDS_PATH`. Append failures return
  `ok: false` with `reason: runtime_command_append_failed`; tests cover successful command-line
  writing and append failure reporting. Software-tested only; no bridge restart or laser hardware
  validation was performed.
- `2026-07-03`: Visual reskin (software-tested only, no runtime/API behavior change) — Laser Pad
  now shares the LED Pad's "stage console" design system: the same `:root` token block (surfaces,
  AA text tiers, semantic colors, shared per-role color vocabulary, spacing scale) in
  `tools/laser_pad_assets/pad.css`, with `pad-overrides.css` emptied out (it previously carried a
  second, competing "premium aesthetic" theme with a Google Fonts `@import` — now removed, no CDN
  dependency). The Laser Pad's identity mark is a green square before the "LASER PAD" title (LED's
  is cyan). Vendored the same Archivo variable font at `tools/laser_pad_assets/archivo-var.woff2`.
  The header "💾 Save & Apply" button is renamed **Apply** (same `.primary-action` class, same
  explanatory `title` attribute, `POST /api/commit` route unchanged); `tests/frontend/test_pad_smoke.py`
  and `tests/test_laser_pad_web.py` were updated to match the new button text (copy assertions
  only). The header's personality select + new/rename/info icon trio were removed from row 2 — the
  toolbar next to the note grid (`.pad-editor-toolbar`) already had its own "Editing" personality
  select, so the icon trio moved there instead of staying duplicated in the header. Bank tabs now
  use the LED pad's 3px-bottom-rail tab treatment with a contained horizontal scroll strip. Note
  tiles: note number moved to top-left, personality chips moved to top-right, a 3px left rail in
  the mapped scene's role color, firing state now rings in the pad's identity green, verify-fail
  rings in danger red (previously a small corner dot). Fixed two latent bugs surfaced while
  reviewing the reskin's screenshots, both pre-existing in the shipped Alpine markup and unrelated
  to the visual changes themselves: (1) the note tile's `:class` binding used a mixed
  string+object array (`:class="[roleClass(note), {...}]"`) that the vendored `alpine.min.js`
  build does not merge — it fell back to `String(array)` and literally rendered the class
  `[object Object]`, silently no-op'ing every state class (`mapped`, `in-active-personality`,
  `pad-dim`, `drop-target`, `firing`, `pressing`, `verify-fail`); replaced with a single
  string-returning `tileClasses(note)` selector in `pad-selectors.js`. (2) `isFiring`/`isPressing`
  compared `Number(this.firingNote)`/`Number(this.pressProgress.note)` (both initialized to `null`)
  against the note number with `===`; since `Number(null) === 0`, MIDI note 0 (a real pad — bank 1
  starts at note 0) rendered as permanently firing/pressing from page load. Both now null-guard
  first.
- `2026-07-03`: Hygiene pass — removed stale frontend assets (`index.granite.html`, `index.html.bak`,
  `pad.css.bak`, `pad-overrides.granite.css`, the one-line `pad.js` compatibility stub) and the last
  unpkg Alpine.js CDN references they carried; the vendored `alpine.min.js` is the only Alpine source
  now. Removed dead CSS (`.control-strip` media-query rule with no matching markup; base
  `.icon-action`/`.settings-trigger` size/border/background declarations fully superseded by
  `pad-overrides.css`). Added LED-pad semantic CSS variable aliases (`--surface`, `--surface-2`,
  `--border`, `--text-dim`) in `:root` for future shared components — no visual change, nothing
  consumes them yet.
- `2026-07-03`: iOS/iPad touch pass (code-level, on-device verification pending): `viewport-fit=cover`
  plus `env(safe-area-inset-*)` padding on the body and mobile drawer, a `dvh`-with-`vh`-fallback
  drawer height, a `@media (pointer: coarse)` rule that raises interactive controls to a 44px touch
  target without changing desktop density, a narrow-viewport (`max-width: 640px`) header stack so
  the header no longer overflows horizontally on a phone, and a "Move to pad" select in the mapping
  drawer as a touch-friendly alternative to HTML5 drag/drop reassignment (which iOS Safari does not
  support) — it reuses the same reassignment code path as a drop, including the overwrite dialog
  and undo bar.
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
