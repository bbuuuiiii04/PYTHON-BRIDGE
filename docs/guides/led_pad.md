---
doc_status: current
truth_level: software-tested
last_verified_commit: a8d92c0
last_verified_date: 2026-07-11
validation_scope: LED Pad Phases 1-3, Template Lab Phase 2, Template Lab Round 1 (live-apply + variant switch + preview), Round 2 (param_specs sliders/toggles, slot swatches, JSON demoted to Advanced), Round 3 (rejected-drafts filter, draft delete), QR same-network access, the iOS/iPad touch pass, the editor unset-param-defaults fix, the AWR-193 pad/lab overhaul (accept snapshot, decoupled preview, archive flow, fn fallback, effective bounds, color pickers + regime badges, reconnect, freshness watchdog + live fingerprint + no-cache), and the AWR-202 commit read-modify-merge with the gate fix that tracks look CONTENT (`touched`) separately from role-bank PLACEMENT (`moved`) so a params-only edit keeps the look's LIVE bank while an explicit pad move still applies; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED
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

## Picking up code changes (freshness contract, AWR-193)

The pad now restarts itself for code freshness. A watchdog thread in `run_server`
(`tools/led_pad_web.py`) samples the mtimes of an explicit watched-module list every 5 s:
`govee_frame_renderer.py`, `led_pad_controls.py`, `govee_realtime_runner.py`,
`led_color_engine.py`, `led_config.py`, `tools/led_pad_web.py`, `tools/led_pad_lab.py`,
`tools/led_pad_playback.py`, `tools/pad_access.py`. When any watched file changes (or goes
missing) and the change has been stable for >= 3 s, the pad logs
"source changed on disk — restarting for freshness" and exits with code 3; launchd
(`KeepAlive.SuccessfulExit=false`) relaunches it. The restart decision is the pure function
`freshness_restart_due` and it refuses while playback is running or while the pad owns the
LEDs — a pad-owned restart would drop the room dark, so that path is impossible by
construction. Open pages heal through the shared reconnect helper (below). All HTTP
responses (JSON and static assets) carry `Cache-Control: no-cache`, so browsers re-fetch
assets after a restart.

Manual force-reload still works when the pad is mid-playback or pad-owned (the watchdog
refuses then):

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
- Derive renderer controls from `REALTIME_EFFECT_PARAM_KEYS` and validate the MERGED result (see
  next bullet) before writing live config.
- Apply is a read-modify-merge, never a wholesale overwrite (AWR-202, fixing the 2026-07-10 14:29
  data loss where a stale draft Apply wiped `f2`/`f4`/`cfx_sweep`/`drop_presentation`/
  `scripted_mode`/`blank_role_hold`, 17 looks, and six `loop_beats`). Commit re-reads
  `config/led_look_director.json` fresh, keeps EVERY top-level block from LIVE — including blocks
  the pad does not manage (`f2`, `f4`, `cfx_sweep`, `automation`, `safety`, and any block the pad
  has never heard of) — and overlays only what THIS pad session changed. Content and
  placement are tracked separately in `_pad_meta.pad_session` (AWR-202 gate fix): `touched` names
  the looks whose CONTENT the pad edited/created (look body + the three per-look `color_engine`
  maps `slot_fill_strategy_by_look` / `slot_mono_chance_by_look` / `locked_palette_by_look`);
  `moved` names the looks whose role-bank PLACEMENT the pad changed or created; `deleted` names the
  looks removed through the pad. So a params-only edit is `touched` but NOT `moved`, and commit
  keeps that look's LIVE bank placement — if live moved the look to another bank after the draft
  went stale, the stale draft placement is not replayed; an explicit pad move still repositions it.
  Looks the pad never touched keep their LIVE contents, and looks it never moved keep their LIVE
  bank, so a stale draft can no longer wipe f2/f4 or move looks the operator didn't touch. The
  tracking is persisted with the draft (survives a pad-server restart) and rebases to empty after
  each commit. The merged result is validated before any write; a `.bak-*` backup of live is taken
  first. A history restore marks every restored look both `touched` and `moved`, so a restore
  brings back the backup's look content AND bank placement while unmanaged live blocks and
  live-only looks still survive.
- Detect live config moving underneath the draft (AWR-193): a gitignored fingerprint sidecar
  `config/led_look_director.draft.base` records the sha256 of the live config the draft is based
  on (written when the draft is first created from live, on Apply/Discard/history restore, and
  refreshed while the draft is clean). `/api/config` gains `"live_changed"`; when true the pad
  shows "Live config changed underneath this draft (bridge or agent edit). Review before Apply —
  Discard reloads live." and repeats that line in the Apply confirm. Apply now merges rather than
  overwrites (AWR-202), so an external edit to an unmanaged block or an untouched look survives the
  Apply; the banner still warns because an external edit to the SAME look the pad is editing would
  lose to the pad's version.
- Render rgb-kind controls as native color pickers with a live swatch (AWR-193; previously
  skipped). On engine-colored looks, rgb-kind and color-signature rows carry the badge
  "palette overrides this in the room" — the controls still edit stored params, the badge states
  the audition truth.
- Survive pad-server restarts (AWR-193): both pages route their 2 s runtime polls through the
  shared `PadHealth` helper (`pad-core.js`) — two consecutive poll failures show a persistent
  "Pad server unreachable — reconnecting…" banner with backoff (2 s → 5 s cap); the first success
  after downtime runs a full page refresh and clears the banner.

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
fallbacks into `led_pad_controls.py::CONTROL_META` (keys whose fallback differs by scene_ref —
`travel_beats`/`width`, the AWR-156 strobe `duty`, and AWR-187's `drop_firework_explosion_2`
surge/hold/ember keys — carry per-scene rows in `PARAM_DEFAULT_OVERRIDES`);
`tests/test_led_pad_controls.py::LedPadControlDefaultsTests` pins every
hand-extracted value against the exact renderer source text, so an unrelated future change to a
renderer fallback fails that test instead of silently drifting from the pad UI. Several
sync-timing keys (`sync_mode`, `heads`, `max_pulses`, `spawn_on_wrap`, `reverse`) are allowlisted
on every scene via `_SYNC_PARAM_KEYS` but are not actually consumed by most renderers; those show
as auto rather than an invented number. Software-tested only; no runtime/API/save-format change.

## Template Lab

Template Lab is a second route in the same LED Pad server. It loads draft render code only in the
pad process from `config/led_lab/effects_lab.py` and tracks draft metadata in
`config/led_lab/drafts.json`. The bridge never imports lab code.

### Beat-sync truth and BPM scope (AWR-214.TLAB)

`/api/renders` now labels every production effect with `timing_mode` (`beat`, `time`, `mixed`, or
`static`) and `beat_synced`. LED Pad look cards show the matching badge. Template Lab entries carry
the same timing fields in `/api/lab/list`; its draft list and detail panel show **beat sync**,
**beat + time**, **time driven**, **static**, or **timing unknown**. The Template Lab control is now
labeled **Beat-sync BPM**. It is enabled only for `beat` and `mixed` drafts; mixed means BPM changes
the beat-driven layer while a wall-clock layer keeps its seconds-based rate. Time/static/unknown
drafts disable the control and say why.

The AWR-194 wave-1 sweep rendered every draft for 16 seconds at 20 fps through `LabRenderer`:
25/25 rendered without an exception, 25/25 changed across the sampled cue, and none were
static-but-rendering. Timing inventory: 19 beat-driven; `remnant_ember_drift` mixed; and five
time-driven (`sparkle_ember_soft`, `wall_duo_flip`, `wall_white_punch`, `wall_split_strobe`,
`starfield_drift`). No wave-1 draft function was changed because the software sweep found no
render failure to repair. This is software evidence only, not a room-visible or hardware result.

Lab names must be lowercase identifiers; a NEW draft cannot take a production realtime render
name, but an existing entry whose name later became a production effect stays fully saveable
(AWR-193 Task 1 — the collision check fires on create only, so promotion no longer bricks the
source draft's Save/Accept/Reject). Such entries are flagged `production_collision` in
`/api/lab/list`, get an "in production" chip and an archive banner in the UI, and can be filed
away with one confirm-gated Archive tap (`POST /api/lab/archive` → status `promoted`; the
Rejected list toggle is now "Archived (n)" covering rejected + promoted). Drafts play as
`lab_<name>` through the same standalone playback slot as LED Pad looks, so starting a lab draft
preempts pad playback and starting a pad look preempts lab playback. Play and preview resolve the
effect name-first with the entry's `fn` as fallback (AWR-193 Task 2), so a renamed draft keeps
rendering while `effects_lab.py` still registers the original fn.

The Lab page supports draft brief/notes, param controls (see below), cue length, Play/Stop, Reload
code, Accept/Reject/Archive status, and a plain-language error banner (the raw traceback panel is
agent-facing and renders only with `?dev=1` in the URL). Accepting a draft does not promote code by
itself; promotion is a later agent task — see the runbook below.

### Promotion runbook (agent-facing)

The old in-page promotion checklist moved here (AWR-193 Task 7; the operator UI no longer carries
agent-facing content). To promote an accepted draft:

1. Move the accepted function into `govee_frame_renderer.py`.
2. Register it and allowlist its params with value validation.
3. Add renderer tests for determinism, clamping, defaults, and slot-5 white if slot-based.
4. Update the example config and LED docs, then run unittest plus the hard docs checks.
5. Restart the bridge only at a safe approved moment.
6. Archive the source draft (AWR-193 Task 1 flow): the Lab detail panel shows an
   "in production" chip and an Archive button once the name collides with a production
   effect, or POST `/api/lab/archive {"name"}` directly. Archiving sets status `promoted`
   and files the draft under the Archived toggle — the entry stays in `drafts.json` as
   the record.
7. Renamed drafts note (AWR-193 Task 2): play/preview resolve a draft's effect name-first,
   then by its stored `fn` — a draft renamed after authoring keeps rendering as long as
   `effects_lab.py` still registers the original fn name.

### AWR-193 overhaul flows (2026-07-10)

- **Accept-what-you-hear.** `_lab_play_spec` records the last APPLIED pre-injection params per
  draft (author params + live UI overrides, snapshotted immediately before engine color
  injection — palette-injected colors are never saved). Accept writes that snapshot into the
  entry in the same save that flips status; the response carries `"snapshotted"` (false when the
  draft was never played this server session, in which case params stay untouched). A dirty chip
  next to Save reads "Unsaved tweaks" / "Saved" from comparing the editor params against the
  saved entry.
- **Decoupled preview.** ◉ Preview no longer saves first — it posts the current editor params
  straight to `/api/lab/preview`. Play keeps save-first, and a save failure shows
  "Save failed: …" in the banner and visibly aborts the play attempt. Auto-apply JSON parse
  failures surface "Params JSON invalid — live apply paused" instead of silently returning.
- **Single-source bounds.** `led_pad_controls.effective_lab_specs()` decorates every
  `/api/lab/list` entry with `effective_param_specs` + `spec_conflicts`: for any spec key that
  also exists in `CONTROL_META`, CONTROL_META's min/max/step/label WIN (kind stays from the
  spec); conflicting stored bounds are reported, and the UI notes "Slider ranges updated from the
  production controls table". Nothing is persisted back into the draft.
- **Color pickers.** Complete `<base>_r/_g/_b` slider triplets collapse into one native color
  picker row with a live swatch; the picker writes all three channel params through the same
  auto-apply path. Incomplete triplets stay sliders. On slot-kind drafts, color rows carry the
  "palette overrides this in the room" badge (slot-kind auditions are palette-fed).
- **Operator-clean surface.** The promotion checklist lives in this doc (above), not the UI. The
  raw traceback panel renders only with `?dev=1`; failures otherwise show a plain-language
  banner. The cue row is labeled "Cue length (beats)" on both pages, and Delete sits in a
  separated danger zone below the panel instead of next to Accept.

### Param controls and slot swatches (Round 2)

A draft's saved `param_specs` (authored by the agent alongside the draft, via `/api/lab/save`) turn
its tunable params into touch-first controls above the raw JSON: a `"slider"` spec
(`{"kind": "slider", "label", "min", "max", "step"}`) renders a `<input type="range">` row with a
live numeric readout, and a `"toggle"` spec renders a checkbox. Dragging a slider or flipping a
toggle updates the underlying params object, writes it back into the Params JSON textarea, and
routes through the same debounced auto-apply path as manual JSON edits — both surfaces call one
`queueAutoApply()` function, so there is no divergent code path between touch and text editing.
`param_specs` is UI metadata only: `LabRegistry.save()` validates and persists it (`ValueError` on
a malformed shape — non-dict, missing `min`/`max`, `max <= min`, `step <= 0`, or an unknown
`kind`), but it never gates or filters what `lab_play`/`lab_update` accept; lab params stay
unvalidated by design.

Below the param controls, a row of six fixed-size color chips shows the Test Palette colors
actually driving the draft (`slot_colors`), with the sixth chip (index 5) labeled "white" to match
the renderer's slot-5-is-white convention. The swatches populate after Play, Switch, and Preview
and clear when a different draft is selected. Frame-kind drafts inject `color_a`/`color_b` instead
of `slot_colors`, so an empty/missing swatch row for those is expected, not an error.

The raw Params JSON textarea still exists and still drives everything underneath (`param_specs`
controls just write into the same textarea) — it now lives collapsed under an **Advanced (raw
JSON)** disclosure instead of being the primary editing surface, per the operator direction that
raw JSON should never be the first thing offered to a touch-first (iPad/phone) session.

### Live tuning (`/api/lab/update`) and variant switching (`/api/lab/switch`)

While a lab draft is playing, editing its Params JSON in the UI auto-applies after a short debounce
(`POST /api/lab/update {"name", "params"}`) instead of requiring a Play click — no cue-timer or
clock restart, just a live re-apply through the same path production pad-look tuning already uses.
The agent API can call `/api/lab/update` directly for talk-mode tuning. `cue_beats` changes still
only take effect on the next Play.

Selecting a different draft while one is already playing turns the Play button into **⇄ Switch**;
clicking it calls `/api/lab/switch {"name"}` to seamlessly swap the live scene without stopping the
beat (`CueTimer`/`SyntheticClock` untouched) — this is the A/B/C variant-comparison workflow.
`lab_switch` only applies when a `lab_*` scene is already playing; if a pad look is playing instead,
the UI falls back to the existing `/api/lab/play` request, which carries the normal preempt and
ownership handling.

### Offline preview (`/api/lab/preview`)

`POST /api/lab/preview {"name", "params"?, "beats"?, "bpm"?}` renders a draft's frames offline —
no transport, no ownership check, no UDP, and it never swaps the live `LabRenderer`'s effects (it
builds a fresh one). The Lab page's **◉ Preview** button calls this endpoint and animates the
returned frames on a canvas strip in the detail panel, so a draft can be eyeballed in the browser
before it ever reaches the physical strip. A broken `effects_lab.py` returns
`{"ok": false, "error", "traceback"}` and the UI shows the traceback panel instead of animating.

### Rejected filter and delete (Round 3)

The drafts list hides `rejected`-status entries by default; a `Rejected (n)` chip next to **New**
toggles them back into view (`n` = the rejected count). The filter is pure UI — `GET /api/lab/list`
always returns every entry regardless of status, so an agent driving the API directly still sees
rejected drafts (the "don't re-pitch this" record) even while the operator's list view hides them.
Selecting a draft that the filter later hides keeps it selected; only the list row disappears, the
detail panel is unaffected.

`POST /api/lab/delete {"name"}` removes a draft's `drafts.json` entry only — it never touches the
function inside `effects_lab.py` (that cleanup stays a separate manual/agent step) and it refuses
while that exact draft is the one currently playing (`{"ok": false, "error": "stop_playback_first"}`)
instead of stopping playback on the operator's behalf. The Lab page's **Delete draft** button lives
in a separated danger zone at the bottom of the detail panel (AWR-193 Task 7 — no longer in the
Accept/Reject action row), confirms through the shared `PadModal`, shows "Stop playback first." on
refusal, and otherwise clears the selection and refreshes the list.

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

Phases 1-3, Template Lab Phase 2, Template Lab Round 1 (`/api/lab/update`, `/api/lab/switch`,
`/api/lab/preview`, auto-apply, preview strip), Template Lab Round 2 (`param_specs`
slider/toggle controls, slot swatches, JSON demoted under Advanced), Template Lab Round 3
(rejected-drafts filter, `/api/lab/delete`), and the AWR-193 overhaul (collision unbrick +
archive, fn fallback, accept snapshot + dirty chip, decoupled preview, effective bounds, color
pickers + regime badges, operator-clean surface, reconnect helper, freshness watchdog +
live-changed fingerprint + no-cache) are implemented/software-tested. AWR-193's JS/UI behavior
has no automated harness — it is code-review + manual-smoke covered only.
Locked Palette and renderer param unlock behavior is covered by software tests only. All LED Pad
and Template Lab playback/UI claims are SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED. The
iOS/iPad touch pass is implemented/software-tested only; on-device verification is pending.
