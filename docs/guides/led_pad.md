---
doc_status: current
truth_level: software-tested
last_verified_commit: 6aa44fa
last_verified_date: 2026-07-03
validation_scope: LED Pad Phases 1-3, Template Lab Phase 2, QR same-network access, the iOS/iPad touch pass, and the editor unset-param-defaults fix; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# LED Pad

LED Pad is a local browser UI for editing and dry-running Govee realtime LED looks through the
production renderer/runner path. It is software-tested only. It does not prove room-visible
Govee behavior, strip restore behavior, or show readiness.

## Launch

```bash
cd /Users/bbui
python3 -m rb_ss_bridge_v2.scripts.led_pad --host 127.0.0.1 --port 8766 --dry-run
```

Open `http://127.0.0.1:8766/`.

Template Lab is at `http://127.0.0.1:8766/lab`.

For the always-on login server, install the tracked LaunchAgent:

```bash
cp launchagents/com.bbui.led-pad.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.bbui.led-pad.plist
```

The bridge menu bar includes **LED Pad...**, which opens `http://127.0.0.1:8766`.

Options:
- `--host` / `--bind`: bind address, default `127.0.0.1`.
- `--port`: default `8766`.
- `--config`: explicit LED config path. Otherwise `RBSS_LED_CONFIG` or `config/led_look_director.json`.
- `--dry-run`: use the realtime dry-run transport. This is the safe local software smoke path.

## Verification

- `launchctl list | grep led-pad` shows the LaunchAgent loaded.
- Clicking menu bar **LED Pad...** opens `http://127.0.0.1:8766` in the default browser.
- `curl -sS http://127.0.0.1:8766/api/config | jq .config.schema` returns a number or `null` for older configs.

## Open on another device (QR)

The transport bar has a 📱 button ("Open on another device"). It calls `GET /api/access`,
which reports the pad's current bind address; it never changes bind behavior by itself —
exposing the pad to the LAN stays an explicit operator action taken elsewhere (`--host`).

Three states:
- **LAN URL available** (pad bound to a non-loopback host): shows a QR code and a
  selectable plain URL for the pad's LAN address, plus a warning that anyone on the same
  Wi-Fi can edit config through this page.
- **Loopback only** (default `--host 127.0.0.1`): no QR. Explains that reaching the pad
  from another device requires restarting it with `--host lan`, or editing
  `~/Library/LaunchAgents/com.bbui.led-pad.plist` and running
  `launchctl kickstart -k gui/$UID/com.bbui.led-pad`, and that doing so exposes pad
  control to the whole network.
- **No LAN address detected**: bound non-loopback but LAN IP detection failed — check
  Wi-Fi.

This is plain HTTP, not HTTPS — the QR/URL is a convenience for typing a LAN address on
a phone, not a security boundary. Firewalls or Wi-Fi client (AP) isolation can still
block another device from reaching the LAN URL even when one is detected.

## Picking up code changes

The LaunchAgent only restarts on crash (`KeepAlive.SuccessfulExit=false`). After editing
`scripts/led_pad.py`, `tools/led_pad_*.py`, `tools/led_pad_assets/**`, or pad control helpers,
force the agent to reload:

```bash
launchctl kickstart -k gui/$UID/com.bbui.led-pad
```

Manual debugging launches must first unload the agent to avoid port 8766 collision:

```bash
launchctl unload ~/Library/LaunchAgents/com.bbui.led-pad.plist
python3 -m rb_ss_bridge_v2.scripts.led_pad --host 127.0.0.1 --port 8766 --dry-run
# when done:
launchctl load ~/Library/LaunchAgents/com.bbui.led-pad.plist
```

Logs are written to `/tmp/led_pad.log` and `/tmp/led_pad.err`.

## What It Can Do

- Show banks first: Drafts, Ambient, Groove, Buildup, Drop, Post-Drop, Breakdown, Utility, plus
  a read-only Other chip for `pre_drop` or unknown memberships.
- Duplicate, move, delete, save, discard, and apply LED looks through
  `config/led_look_director.draft.json`.
- Preview realtime-razer looks with synthetic BPM, Test Palette, and Loop settings. Cloud scenes
  are shown but not previewed.
- Lock a look to a named color-engine palette. Locked looks ignore the session Test Palette
  during pad playback and keep using their saved palette until cleared.
- Derive renderer controls from `REALTIME_EFFECT_PARAM_KEYS` and validate the full draft before
  writing live config.
- Apply the draft to `config/led_look_director.json` with a `.bak-*` backup.

## Editor unset-param defaults (2026-07-03)

Most saved looks store no `params` at all — an unset key means "the renderer uses its built-in
default," which is what actually plays, both in bridge automation and pad preview. The editor
drawer now shows that real default instead of the control's minimum:

- An unset control shows a small outline **default** tag next to its value. If the renderer has
  no single fixed fallback for that control on the selected renderer (varies by renderer, or is
  never actually read from `params`), the value reads **auto** instead of a guessed number.
- Editing a control pins the value into the saved look (tag disappears) - this already matched
  `save_look`'s behavior of only writing params actually set; only the display was wrong before.
- A ghost **↺** "Reset to default" button appears once a control is set. Clicking it deletes the
  key from the editor draft, which puts the row back to showing the renderer default/auto.
- The Renderer dropdown for cloud-scene looks (a `scene_ref` not in the local realtime render
  list) now shows the scene ref with a cloud icon instead of rendering blank.

Defaults were hand-extracted from `govee_frame_renderer.py`'s literal `params.get(key, DEFAULT)`
fallbacks into `led_pad_controls.py::CONTROL_META` (`travel_beats`/`width` differ by scene_ref via
`PARAM_DEFAULT_OVERRIDES`); `tests/test_led_pad_controls.py::LedPadControlDefaultsTests` pins every
hand-extracted value against the exact renderer source text, so an unrelated future change to a
renderer fallback fails that test instead of silently drifting from the pad UI. Several
sync-timing keys (`sync_mode`, `heads`, `max_pulses`, `spawn_on_wrap`, `reverse`) are allowlisted
on every scene via `_SYNC_PARAM_KEYS` but are not actually consumed by most renderers; those show
as auto rather than an invented number. Software-tested only; no runtime/API/save-format change.

## Template Lab

Template Lab is a second route in the same LED Pad server. It loads draft render code only in the
pad process from `config/led_lab/effects_lab.py` and tracks draft metadata in
`config/led_lab/drafts.json`. The bridge never imports lab code.

Lab names must be lowercase identifiers and cannot collide with production realtime render names.
They play as `lab_<name>` through the same standalone playback slot as LED Pad looks, so starting
a lab draft preempts pad playback and starting a pad look preempts lab playback.

The Lab page supports draft brief/notes, params JSON, cue length, Play/Stop, Reload code,
traceback display, Accept/Reject status, and a static promotion checklist. Accepting a draft does
not promote code by itself; promotion is a later agent task that moves tested code into
`govee_frame_renderer.py`, updates allowlists/docs/tests, and then requires a safe bridge restart.

## Ownership And Recovery

If the bridge is not live, LED Pad can play directly. If the bridge status file is fresh, the
pad treats the bridge as owning the LEDs until the operator explicitly takes over. Takeover
appends this JSONL command to the runtime command file:

```json
{"cmd":"led_blackout","reason":"led_pad"}
```

Release appends:

```json
{"cmd":"led_clear_blackout"}
```

Recovery one-liner if the bridge side remains blacked out after a pad session:

```bash
printf '%s\n' '{"cmd":"led_clear_blackout"}' >> /tmp/rb_ss_bridge_v2_commands.jsonl
```

## Apply Behavior

The Apply button (the UI word for the draft commit; the API route stays `/api/commit`)
writes the draft to the live config only after
`load_led_look_director_config_from_dict()` accepts the full draft. A committed config affects
the running bridge only after a bridge restart. Restarting the bridge remains a live-operation
approval gate; do the existing single-process check before any restart:

```bash
pgrep -f rb_ss_bridge_v2 | wc -l
```

Expected value is `1`.

## iOS/iPad touch pass

The pad and Template Lab pages carry code-level iOS/iPad accommodations: `viewport-fit=cover` plus
`env(safe-area-inset-*)` padding around the topbar, editor drawer footer, and toast so content
does not sit under the iOS Safari toolbar or home indicator; a `dvh`-with-`vh`-fallback height on
the editor drawer; and a `@media (pointer: coarse)` rule that raises buttons, selects, and number
inputs to a 44px touch target without changing desktop density. `window.PadModal`
(`tools/led_pad_assets/pad-core.js`) replaces the pad's and Template Lab's previous
`prompt()`/`confirm()` calls with the app's own in-page modal (lazily-created DOM shared by both
pages) so dialogs render consistently instead of relying on native browser prompts. This is
code-level only — no iPad/iOS Safari device verification has been performed.

## Visual reskin (2026-07-03)

The pad and Template Lab pages carry a "stage console" visual reskin (software-tested only, no
runtime/API behavior change):

- Shared design-token block in the `:root` of `tools/led_pad_assets/pad.css` (surfaces, AA text
  tiers, semantic colors, a shared per-role color vocabulary, spacing scale); legacy var names
  (`--play`, `--gap`, `--pad`, `--mono`, `--font`) are aliased to the new tokens. The LED pad's
  identity mark is a cyan square before the "LED Pad" title; the Lab route keeps violet accents.
- Vendored Archivo variable font at `tools/led_pad_assets/archivo-var.woff2`, served at
  `/static/archivo-var.woff2` (no CDN or runtime network dependency).
- UI vocabulary: the draft-commit button now reads **Apply** (confirm dialog "Apply draft to live
  config"); the editor's look-level button stays **Save**, and `#dirtyText` reads "Draft saved" /
  "Unsaved changes". API routes are unchanged (`/api/commit` keeps its name).
- Bank tabs use a 3px bottom rail in the bank's role color and scroll inside the tab strip on
  narrow viewports. This also fixes a pre-existing defect the frontend test harness caught at
  baseline: the unwrapped tab row previously forced horizontal page scroll at iPhone width
  (`tests/frontend/test_pad_touch.py::test_led_pad_loads_at_iphone_width_without_console_errors`).
- Card load stagger and hover transitions are disabled under `prefers-reduced-motion: reduce`.

## Status

Phases 1-3 and Template Lab Phase 2 are implemented/software-tested. Locked Palette and renderer
param unlock behavior is covered by software tests only. All LED Pad and Template Lab playback/UI
claims are SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED. The iOS/iPad touch pass is
implemented/software-tested only; on-device verification is pending.
