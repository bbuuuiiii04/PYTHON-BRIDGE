---
doc_status: current
truth_level: software-tested
last_verified_commit: 22490a06
last_verified_date: 2026-07-16
validation_scope: LED Pad Phases 1-3, Template Lab Phase 2, Template Lab Round 1 (live-apply + variant switch + preview), Round 2 (param_specs sliders/toggles/selects, slot swatches, JSON demoted to Advanced), Round 3 (rejected-drafts filter, draft delete), QR same-network access, the iOS/iPad touch pass, the editor unset-param-defaults fix, the AWR-193 pad/lab overhaul (accept snapshot, decoupled preview, archive flow, fn fallback, effective bounds, color pickers + regime badges, reconnect, freshness watchdog + live fingerprint + no-cache), the AWR-202 commit read-modify-merge with the gate fix that tracks look CONTENT (`touched`) separately from role-bank PLACEMENT (`moved`) so a params-only edit keeps the look's LIVE bank while an explicit pad move still applies, AWR-240 pad offline v2 stand-down so Test Palette still injects slot_colors, AWR-241 Template Lab beat meter + metronome click (preview exact / live server-synced), AWR-242 Template Lab UX overhaul (search/filter/group draft list, target_role phrase tags, settable timing_mode, detail restructure, health strip + self-test), AWR-243 Template Lab functional fix round (collision banner gate, selected-draft list pin, ownership takeover catch, applied:false hint, live test_palette for lab play, header/phone/preview/health/utility UX), AWR-245 Template Lab Strip|Room preview hookup (pad serves sim view JS + profile read-only; fail-soft; preview-only honesty), AWR-247 Template Lab preview length (default full cue_beats; 2/4 bars / full control), AWR-248 Pad|Lab|Sim cross-nav (plain links to :8767), AWR-250 Lab Room preview re-fetches sim profile on Preview / Room toggle so active_layout changes from Sim show without reload, AWR-254 pad look-editor close dirty check (compares against last Save, not editor-open snapshot), AWR-255 pad+lab banner when live config is newer than the running bridge, AWR-258 data-integrity (lab registry lock + optimistic concurrency, pad locked_palette save parity, beforeunload + reconnect stash, rotating lab backups), AWR-259 pad integrity tail (same-look stale_look 409, Discard-all copy, persisted last_applied Accept snapshot, EDITOR_FIELDS parity), AWR-260 lab Accept wire-in, AWR-261 status freshness, AWR-262 pad control truth, AWR-263 lab control truth + New clone flow, AWR-264 language+hierarchy rename-only (musician labels, human-name tiles, jargon gate), AWR-269 pad-process live-play mirror (TeeTransport + SSE `/api/mirror/stream` + Lab Watch live playback; not bridge show output), AWR-270 R8 one-shell chrome (shared LIGHTING CONSOLE header + Pad|Lab|Sim nav with N9 relative pad↔lab / absolute sim links, pad lands on first non-empty phrase shelf, honest empty copy; zero playback/save/engine change), AWR-271 R9a Lab editor mounts inside Pad shell (shared `index.html` + `shell.js` view switch; one `lab.js` store; Accept pipeline untouched), AWR-272 R9b one verb pair (Save draft = unpublished look; Accept = only promotion; Reject keeps out of show; Pad push demoted under Pad look edits; scary Save-to-show modal removed), and AWR-273 R9c single live-fire + `/lab` redirect (Pad tile Play = primary looping live-fire; Lab **Play once on lights** = guarded one-shot `loop=false` on existing `/api/lab/play`; `/lab` 302 → `/?view=lab`; Preview is the Lab headline verb), and AWR-274 R11 Setup demotion + Diagnostics corner (sim Layout/Calibrate behind Setup; lab health under collapsed Diagnostics; beat meter stays; cold screens zero banned telemetry); SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED
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

Template Lab is at `http://127.0.0.1:8766/?view=lab`
(bookmarks to `/lab` 302-redirect there — never 404).

The top-bar **Pad | Lab | Sim** route tabs jump between the pad (:8766),
Template Lab (`/?view=lab`), and the H612D LED Studio sim (`http://127.0.0.1:8767/`,
canonical default). **AWR-270 / N9:** Pad↔Lab links are relative (same server);
links to/from Sim stay absolute on `:8767` / `:8766` until a later round mounts
Sim under one server. **AWR-271 / R9a + AWR-273 / R9c:** Pad and Lab are one shell
document — clicking Pad|Lab switches the view in-place (same header, same session
controls, same `lab.js` editor store). `/` serves the shell; `/lab` 302-redirects
to `/?view=lab`. Sim’s Lab tab points at `http://127.0.0.1:8766/?view=lab` (no
double-hop). All three pages share the **LIGHTING CONSOLE** eyebrow and
matched route-tab chrome. Pad’s first paint opens the first phrase shelf that
already has looks (not an empty Untagged tab); true empties say what to do next
in plain words. Sim is a plain same-tab link; the sim page mirrors the same
cluster back to Pad and Lab.

**AWR-274 / R11:** Lab health dots (server / lab code / playback) and the
draft self-test live under a collapsed **Diagnostics** corner — not on the cold
Lab header. The beat meter stays visible when Preview or Play-once is running
(musician tool). Sim’s Layout and Calibrate tools are under **Setup**; FPS /
provenance / frame counters sit in Sim Diagnostics the same way.

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
`tools/led_pad_playback.py`, `tools/led_pad_mirror.py`, `tools/pad_access.py`. When any watched file changes (or goes
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

- Show banks first: Untagged, Ambient, Groove, Buildup, Drop, Post-Drop, Breakdown, Utility, plus
  a read-only Other chip for `pre_drop` or unknown memberships.
- Duplicate, move, delete, save, discard, and apply LED looks through
  `config/led_look_director.draft.json`.
- Preview realtime-razer looks with synthetic BPM, Test Palette, and Loop settings. Cloud scenes
  are shown but not previewed. When `color_engine.v2.enabled` is true, pad/lab play still builds a
  fresh offline `LedColorEngine` with no live dressing, so `_inject_engine_colors` calls
  `set_scripted_stand_down(True)` before the Test Palette fill — otherwise v2 returns empty
  `slot_colors` and slot cues paint black (AWR-240). Software-tested only; not a bridge runtime change.
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
renderer fallback fails that test instead of silently drifting from the pad UI.

**AWR-262 (control truth).** The pad editor no longer lists every allowlisted key.
`controls_for(scene_ref)` returns the curated `EFFECT_VISIBLE_KEYS` surface only — comet-motion
looks get BeatSyncEngine motion knobs; continuous/strobe looks get that effect's real params;
`heads` (Comet Count) is removed from the UI (still tolerated in saved configs / validation).
Choice enums render as word-labeled dropdowns. Switching the renderer warns before dropping
params that don't apply. Advanced motion hides when empty. Permanent drift test:
`tests/test_awr262_control_truth.py`. Allowlist/`REALTIME_EFFECT_PARAM_KEYS` unchanged (A1).
Software-tested only; no bridge restart by implementer.

## Template Lab

Template Lab is a second route in the same LED Pad server. It loads draft render code only in the
pad process from `config/led_lab/effects_lab.py` and tracks draft metadata in
`config/led_lab/drafts.json`. The bridge never imports lab code.

### Beat-sync truth and BPM scope (AWR-214.TLAB)

`/api/renders` now labels every production effect with `timing_mode` (`beat`, `time`, `mixed`, or
`static`) and `beat_synced`. LED Pad look cards show the matching badge. Template Lab entries carry
the same timing fields in `/api/lab/list`. The detail header has a **Timing** select
(`beat` / `mixed` / `time` / `static`) that writes `timing_mode` on Save — that is how you clear
"timing unknown" on older drafts. Beat-sync BPM is enabled only for `beat` and `mixed`; when the
selected draft's timing is still unset, a short hint under BPM says **Set timing (header) to enable
BPM**. Mixed means BPM changes the beat-driven layer while a wall-clock layer keeps its
seconds-based rate.

Each draft also stores optional `target_role` (empty or one of the pad role banks: ambient, groove,
buildup, pre_drop, drop, post_drop, breakdown, utility). The Phrase select in the detail header
writes it on Save; list rows show a 3-letter phrase chip so you can see which moment a draft is for.

### Lab UI layout (AWR-242 / AWR-243)

The Lab view (`/?view=lab`, and `/lab` bookmarks that 302 there) is reorganized:

- **Draft list.** Sticky search (name / brief / notes substring only — never params or `fn`),
  status chips (Iterating on by default; Accepted /
  Rejected off — Rejected also covers archived/`promoted`), and a Phrase dropdown (All / Untagged /
  eight roles). Rows group by status with counts, sort by updated desc inside each group, and stay
  one line: phrase chip · name (ellipsis) · status dot · relative date. Timing badges and full
  status pills are gone from the list. Under 900px the list is a **Drafts ▾ (N)** drawer above the
  detail panel (one left-aligned inline label); picking a draft closes it. **The selected draft
  always stays in the list** even when its status chip is off (Accept with Accepted=off no longer
  makes the row vanish); it drops out only after you select something else or change filters.
  An **exact-name** search hit also surfaces even when its status chip is off (same pin rule).
  Search is plain case-insensitive **substring** over name + brief + notes only (never
  subsequence/fuzzy, and never params/`fn`). A query that hits none of those three fields
  yields an empty list — the open draft is not kept as a ghost row.
- **Detail (top → bottom).** Header flows title → Phrase/Timing → collision banner **only when**
  `production_collision` is true → preview hero (Strip|Room toggle + strip/room canvases; AWR-245;
  64px / 48px phone strip with a dim “press Preview” placeholder until frames arrive +
  **◉ Preview** (headline / primary) / **▶ Play once on lights** (secondary guarded one-shot) /
  **■ Stop** + AWR-241 beat meter IDs unchanged; Room mode scrolls the hero into view after Preview)
  → tuning card (labeled sliders; on phone, label+value on one line and full-width track below with
  ≥32px thumbs; cue segmented control; **Save draft** + dirty; dim hint when `/api/lab/update` returns
  `applied:false`: “Preview updates as you tune — Play once sends to the real lights (one cue, no loop)”) → **Accept — adds it
  to your show** (solid green) / **Reject — keep out of show** (outline red) verdict bar → Brief (2 rows)
  + Notes in a collapsed details →
  Advanced JSON / Traceback → footer **Reload effect code** (transient “Loaded N effects ✓”) · Archive draft · Delete
  (Archive/Delete/Save draft/Accept/Reject disabled with no selection). When another lab scene is already
  live, Play-once becomes amber **⇄ Switch live lights**.
- **Live-fire (AWR-273 / D5).** Pad look-tile **▶ Play** is the primary looping live-fire (honors
  session Loop). Lab **Play once on lights** always calls `/api/lab/play` with `loop=false` (one cue
  length, then idle) — same ownership gate, same dry-run path, same AWR-269 mirror tee. No second
  save path and no duplicate playback state.
- **Save contract (AWR-251 + AWR-272).** What you see is what's saved; anything named is persisted; slider
  tweaks are live-apply + editor-local until Save draft / Accept / Reject. **Save draft** writes the
  unpublished look only (never the show). **Accept** is the only promotion (AWR-260 wire-in). Reject
  flips status and keeps the cue out of the show. Accept and Reject both write
  the current editor fields (params, phrase, timing, brief, notes, cue) then flip status. Switching
  drafts keeps unsaved edits in session memory per draft (restored when you click back) and writes
  nothing to `drafts.json`. `/api/lab/update` remains runtime-only.
- **Data integrity (AWR-258 + AWR-259).** Lab registry writes (`/api/lab/save|accept|reject|archive|delete`)
  take the pad service lock so two concurrent saves cannot silently discard each other (adversary
  repro: 60/60 losses → 0/60 under test). Saves that carry an entry `updated` stamp are rejected
  with HTTP 409 `stale_entry` when disk moved on; the Lab UI offers Reload vs Overwrite. Every
  successful drafts write also rotates `.bak-*` snapshots of `drafts.json` and `effects_lab.py`
  (keep 5). Pad Save sends `locked_palette` with the other editor fields (shared `EDITOR_FIELDS`
  list with the dirty snapshot). Pad look Save also carries per-look `_pad_meta.looks[<name>].updated`;
  a mismatch returns HTTP 409 `stale_look` and the Pad UI prompts Reload (re-opens the editor fresh)
  — two-tab same-look lost updates fail safe. Secondary **Pad look edits** → **Undo all changes**
  confirms it deletes every unsaved Pad look edit across N dirty looks (whole draft) and reloads
  the lighting file; looks already in the show stay as they are (editor-drawer discard copy unchanged).
  Lab Accept persists last-applied params to
  `config/led_lab/last_applied.json` so a pad restart still Accept-what-you-hear; param-less Accept
  without a snapshot returns `snapshot_fallback: true` and the Lab UI shows “Accepted saved values —
  your last live-tuned values weren't available”. Closing/reloading a dirty Lab or Pad tab prompts
  via `beforeunload`; Lab reconnect stashes dirty editor fields before rebuilding the detail pane.
- **Health strip (client-only).** Top-bar right cluster with title tooltips:
  - **Server** — green `ok` when last `/api/runtime_status` succeeded &lt;3s ago; red `stale` otherwise.
  - **Lab code** — amber `not loaded yet` before first successful reload/play/preview; green
    `loaded ✓` after any of those succeed; red `load failed` (click opens traceback). Self-test
    pass also sets green.
  - **Playback** — green `playing <name>` while a look is up; gray `idle` otherwise.
  Plus **Self-test** (reload → preview 2 beats → checks ok / frames / not-all-black / slot_colors
  for slot kind). No new backend endpoints.
- **Ownership takeover (AWR-243).** `pad-core.js` `request()` attaches the JSON payload on thrown
  `{ok:false, error}` errors so Lab Play can catch `ownership_required` and show the PadModal
  takeover confirm (Pad route already used catch-based handling).

While a `lab_*` scene is playing, changing **Test Palette** re-resolves colors and pushes a
color-only update through the existing lab update path (lab play/switch clear the pad editor
pointer, so the pad-look session path alone was not enough).

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
Rejected status chip covers rejected + promoted, folding the old Archived toggle). Drafts play as
`lab_<name>` through the same standalone playback slot as LED Pad looks, so starting a lab draft
preempts pad playback and starting a pad look preempts lab playback. Play and preview resolve the
effect name-first with the entry's `fn` as fallback (AWR-193 Task 2), so a renamed draft keeps
rendering while `effects_lab.py` still registers the original fn.

The Lab page supports draft brief/notes, param controls (see below), cue length, Play/Stop, Reload
code, Accept/Reject/Archive status, health strip + self-test, and a plain-language error banner (the
raw traceback panel is agent-facing and renders only with `?dev=1` in the URL; a failed Lab-code
health dot also opens it). Accepting a draft does not promote code by itself; promotion is a later
agent task — see the runbook below.

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

- **Accept wires into the show (AWR-260).** Accept still implies Save (AWR-251), but it also
  writes a production look (`scene_ref=lab:<draft>`, `color_source=engine`, saved params +
  cue_beats), places it in the phrase bank matching `target_role` (or the **Untagged** pad shelf
  when untagged — manually playable, excluded from automation), auto-Applies via the existing
  commit path (timestamped `.bak` by design), and appends `led_reload_looks` so a running bridge
  picks it up without a restart. The Lab UI confirms with “Live — added to Drop bank” or
  “Live — untagged shelf; tag a phrase to join rotation.” Reject stays a status flip: “Rejected —
  stays out of the show. You can reopen it anytime.”
- **Accept-what-you-hear / Accept-what-you-see (AWR-251).** Accept and Reject both imply Save:
  the UI posts the current editor payload (params, phrase/`target_role`, timing, brief, notes,
  cue). Server merges those fields, then flips status. If the payload has no `params` (name-only
  Accept after Play — agent path), `_lab_play_spec`'s last APPLIED pre-injection snapshot is used
  as before (`snapshotted: true`); palette-injected colors are never saved. The dirty chip next to
  Save reads "Unsaved tweaks" / "Saved" from comparing the editor against the saved entry — and
  stays truthful because slider auto-apply no longer writes `drafts.json`.
- **Live apply is not Save.** Debounced slider/JSON auto-apply calls `/api/lab/update` only
  (runtime). Draft-switch stashes editor fields per draft in session memory and restores on return;
  disk is untouched until Save / Accept / Reject.
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

### Param controls and slot swatches (Round 2 + AWR-263)

A draft's saved `param_specs` (authored by the agent alongside the draft, via `/api/lab/save`) turn
its tunable params into touch-first controls above the raw JSON:

- `"slider"` — `{"kind":"slider","label","min","max","step"}` → range input + live readout
- `"toggle"` — checkbox
- `"select"` (AWR-263) — `{"kind":"select","label","options":[{"value","label"}, …]}` → worded
  dropdown (Zone / Texture / Color Mode upgrade automatically via `effective_lab_specs` even when
  the saved draft still has the old 0…N slider shape)

Dragging a slider, flipping a toggle, or picking a select updates the underlying params object,
writes it back into the Params JSON textarea, and routes through the same debounced auto-apply
path as manual JSON edits — both surfaces call one `queueAutoApply()` function. While **Preview**
is running, that path re-POSTs `/api/lab/preview` (~400 ms debounce) so the strip retunes live;
the hint reads "Preview updates as you tune — Play once sends to the real lights (one cue, no loop)." Blurring the
Advanced JSON box re-renders the controls from the JSON (JSON remains the save source of truth).

`param_specs` is UI metadata only: `LabRegistry.save()` validates and persists it (`ValueError` on
a malformed shape — non-dict, missing `min`/`max`, `max <= min`, `step <= 0`, select with fewer
than two options, or an unknown `kind`), but it never gates or filters what `lab_play` /
`lab_update` accept; lab params stay unvalidated by design. Shared keys with `CONTROL_META` take
CONTROL_META's min/max/step; **draft labels are preserved** (so `cycle_beats` no longer shows the
old pad-wide "Rainbow Cycle Beats" on non-rainbow cues — CONTROL_META's label is now
"Color cycle (beats)").

**New cue (AWR-263):** the New button asks for any display name (auto-slugified to `[a-z0-9_]+`,
collisions get `_2`) and a "start from" picker of previewable drafts (default = the selected
draft). Create clones the starter's `fn` / `kind` / `params` / `param_specs` under the new name
with `brief` = display name and status `iterating`, then previews immediately. An advanced
"Empty shell — an AI agent must write its render code before it can preview" option keeps the
old blank-draft path for agent workflows.

Firework drafts whose specs still expose dead `color_b_*` / `sparkles_per_beat` knobs are
decorated at list time with the live `spark_a` / `spark_b` family (`FIREWORK_EXPLOSION_LAB_SPECS`).
Search that hits drafts hidden by status chips auto-shows them with a dim note
("N hidden matches shown (status filters relaxed for this search)"); clearing search restores
chip behavior. Changing the selected draft clears the self-test panel.

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
builds a fresh one). When `beats` is omitted, the server defaults to the draft's full `cue_beats`
(still capped at 32). The Lab page's **◉ Preview** button posts the chosen preview window length
and animates the returned frames on the strip/room canvases. A broken `effects_lab.py` returns
`{"ok": false, "error", "traceback"}` and the UI shows the traceback panel instead of animating.

### Preview length (AWR-247)

Previously every Preview was silently capped at 8 beats (2 bars), so 32-beat cues never showed a
full cycle in the browser. The transport row now has a compact length control:

| Choice | Beats posted |
| --- | --- |
| **2 bars** | 8 |
| **4 bars** | 16 |
| **Full cue** (default) | the draft's current cue length (editor value, ≤32) |

Choice persists in `localStorage` key `labPreviewLength`. Strip and Room (AWR-245) share the same
preview RAF clock and frame set — length does not diverge by view mode. The AWR-241 beat meter
still derives bar/beat from `frameIndex * bpm / (60 * fps)`, so longer windows just count higher
bars; no meter rewrite.

### Room view preview (AWR-245)

The preview hero has a **Strip | Room** toggle (default Strip; choice persisted in
`localStorage` key `labPreviewMode`). Room mode reuses the LED Studio room canvas as-is — it does
not fork the simulator:

- Pad serves `GET /static/sim/ledsim-view.js` read-only from `tools/led_sim_assets/ledsim-view.js`
  (404 if missing; never crashes the pad).
- **AWR-266:** Pad also serves `GET /static/sim/ledsim-player.js` (shared preview clock) the same
  way. Lab + Sim both step frames with
  `Math.floor((ts - start) / 1000 * fps) % frames.length` — one player module, no zoh/slew on
  screen.
- Pad serves `GET /api/sim/profile` with the same example-inherited merge shape as the sim's
  `LedSimService.profile_state()` (JSON-only; no Python import of `led_sim_engine` / `led_sim_web`,
  so the AWR-193 pad↔sim cycle fence stays intact). Failures return `{"ok": false, "error": …}`.
- Lab dynamically imports the view module, creates `createLedSimView(canvas, profile)` on a second
  stage-sized canvas, and feeds it the **same** preview frames / playback clock as the strip
  canvas (only the visible canvas renders). Toggle destroys/recreates the view so ResizeObservers
  do not leak. The AWR-241 beat meter keeps working identically in both modes.
- **AWR-250 freshness.** Lab re-fetches `/api/sim/profile` on every Preview click and whenever the
  toggle switches to Room (~2s TTL otherwise). The room canvas rebuilds only when the active
  layout fingerprint changes. Failures keep the last good profile when one exists; first-load
  failures still fall back to Strip with the dim note.
- **Fail-soft.** If the module import or profile fetch fails, Lab stays in Strip with a dim note:
  “Room view unavailable — simulator assets not found.”
- **Honesty.** Room mode shows “Room view · simulator layout · preview only.” Offline Preview is
  still a local render. **Watch live playback** (AWR-269) is the separate mirror of what this pad
  process is sending right now — it does not change the lights, and it is not a mirror of the
  bridge show output.
- **Editor chrome hidden — presentation mode (AWR-253 + AWR-266).** Lab creates the view with
  `createLedSimView(canvas, profile, {presentation: true})`. The Sim Play stage uses the same
  mode by default. Editor chrome stays off: segment ticks, room-size/measurement text, vertex
  handles, unplaced warnings. What remains: walls, path, LEDs, junction, start/end. Sim Layout
  tab calls `setPresentation(false)` so handles/ticks return for editing.

### Watch live playback (AWR-269)

While the pad/lab is **Playing** to the real lights (or dry-run transport), Template Lab can
**Watch live playback** on the same stage. This is a read-only mirror of frames this pad process
is sending — not the bridge's show output (that remains a separate future decision).

- **Tee at the transport boundary.** `tools/led_pad_mirror.py` wraps dry-run and real transports
  inside `PadPlayback` with `TeeTransport`. Each `send_frame` still goes to the wrapped transport
  unchanged; the runner thread only O(1)-appends `(monotonic_ts, immutable RGB list)` into a
  bounded `collections.deque`. No shared lock with readers, no I/O on the runner thread. A stalled
  browser client must not change playback cadence.
- **SSE fan-out.** `GET /api/mirror/stream` on the pad web server (ThreadingHTTPServer — one handler
  thread per client) snapshots the newest ring entry at ~30 fps and emits plain SSE JSON
  (`ts`, `rgb`, `playing`, `playing_look`). No websocket dependency. Handlers exit when the pad
  service shuts down.
- **UI.** Lab stage button **Watch live playback** subscribes via `EventSource` and paints through
  the same `paintPreviewFrame` / ledsim-view path as Preview. Calm copy when nothing is playing.
- **Gates (software).** Cadence with a stalled client, ring maxlen without clients + clean SSE
  shutdown, and dry-run byte-equal ordered frames — `tests/test_led_pad_playback_mirror.py`.
  HARDWARE-UNVALIDATED.

### Beat meter + metronome click (AWR-241)

Template Lab can verify that a preview or strip play is actually running at the stated BPM, and
whether a pulse is per-beat vs per-2-beats:

- **Preview (exact by construction).** Canvas frame N maps to beat `N * bpm / (60 * fps)` with
  frame 0 = bar 1 beat 1. A beat dot flashes on each integer-beat crossing (bigger/brighter on
  every 4th / bar downbeat), and a counter shows `bar B · beat K` (K = 1..4).
- **Live (server-synced).** `PadPlayback.status()` exposes `beat` from the synthetic clock. The
  UI phase-locks on each `/api/runtime_status` poll and estimates between polls. The counter is
  labeled **beat phase (server)** — it verifies tempo and period, not cue-start = bar 1 (the
  clock's beat 0 predates the cue).
- **Click track.** A 🔊 toggle (off by default; the click is the WebAudio unlock gesture) plays a
  short oscillator blip per beat, louder/higher on bar downbeats. Preview click = **exact**; live
  click = **synced to server clock (± poll jitter)**. Clicks stop when preview/play stops or the
  tab hides.

### Rejected filter and delete (Round 3 → AWR-242 chips)

The drafts list status chips hide `accepted` / `rejected` / `promoted` by default (Iterating on).
Turning on **Rejected** shows rejected + promoted (the old Archived toggle). The filter is pure UI —
`GET /api/lab/list` always returns every entry regardless of status, so an agent driving the API
directly still sees rejected drafts (the "don't re-pitch this" record) even while the operator's
list view hides them. Selecting a draft that the filter later hides keeps it selected; only the
list row disappears, the detail panel is unaffected.

`POST /api/lab/delete {"name"}` removes a draft's `drafts.json` entry only — it never touches the
function inside `effects_lab.py` (that cleanup stays a separate manual/agent step) and it refuses
while that exact draft is the one currently playing (`{"ok": false, "error": "stop_playback_first"}`)
instead of stopping playback on the operator's behalf. The Lab page's **Delete** button lives in the
footer utility row (AWR-242 — no floating danger zone), confirms through the shared `PadModal`, shows
"Stop playback first." on refusal, and otherwise clears the selection and refreshes the list.

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

Lab **Accept** is the promotion path (AWR-260): it persists the draft, writes the production look,
places it in the phrase bank (or Untagged), and auto-commits via `/api/commit`. For Pad-side edits to
looks that are already in the show, open **Pad look edits** (secondary menu) and use **Push pad edits**
(API route still `/api/commit`). That path writes the pad draft to the live lighting file only after
`load_led_look_director_config_from_dict()` accepts the full draft. Your lights will use those Pad
edits at the next bridge start. Restarting the bridge remains a live-operation
approval gate; do the existing single-process check before any restart:

```bash
pgrep -f rb_ss_bridge_v2 | wc -l
```

Expected value is `1`.

**Stale-config banner (AWR-255 + AWR-261 freshness).** Pad and Template Lab both
poll `GET /api/runtime_status`, which includes a `config_stale` object. The pad
treats the bridge status file as live only when it parses **and**
`written_at` is younger than 5 seconds (same freshness rule as
`OwnershipGate`). A missing or stale file sets `bridge.live=False` /
`state=not_running` and shows a calm banner: applied changes will load when the
bridge next starts. A fresh status file compares live
`config/led_look_director.json` mtime to the process start (status
`process.pid` → `ps`; no bridge `started_at` field, and this work does not
change bridge runtime). Config newer than process start → warn to restart from
the menubar. Config older → quiet green "Live config matches the running
bridge." The honest "(Can't tell…)" copy is kept **only** when the status file
is fresh but the pid cannot be resolved. Covered by
`tests/test_led_pad_service.py` (`ConfigStaleComputationTests`,
`ConfigStaleRuntimeStatusTests`).

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
- UI vocabulary (AWR-264 + AWR-272): Lab primary pair is **Save draft** / **Accept — adds it to your
  show** (Reject — keep out of show). Pad draft-commit is secondary under **Pad look edits** →
  **Push pad edits** (API route stays `/api/commit`; confirm speaks plain English about the lighting
  file and next bridge start — no "Save to show" / scary restart wall). Top-bar discard stays
  **Undo all changes**. Editor look-level button stays **Save**; `#dirtyText` reads "Draft saved" /
  "Unsaved changes".
  Musician-legible CONTROL_META labels (Flashes per second / Flash length (%) / Trigger every …
  beats / Match the track / Use set colors). Look tiles lead with the human effect name; machine id
  is one small mono line. AWR-265 FINAL: RT color-suffix clones and the
  `legacy_color_suffix` bank are gone; the pad **Legacy** tab hides when empty.
  Default Drop/Groove/Ambient/Post-Drop banks rotate the palette-fed bases
  (`rt_drop_strobe`, `rt_drop_chase`, `rt_groove_chase`, `rt_post_drop_chase`,
  `rt_drop_center_burst`, `rt_post_drop_center_comet`, `rt_twinkle`); cyan-white /
  blue-ice / blue-twinkle pairs surface under `blue_cyan` via scale_stops order.
  Pad rename/duplicate accept plain display names and auto-slug. Standing gate:
  `python3 tools/check_ui_jargon.py`.
- **Editor close dirty check (AWR-254).** Closing the look editor compares against the last
  successful Save (or the state at open if you never saved). Save then close exits silently; only
  edits since the last save show "Discard unsaved changes?" / "You have edits since your last
  save. Discard them and close?".
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
live-changed fingerprint + no-cache) are implemented/software-tested. AWR-241 adds a Template Lab
beat meter + optional metronome click (preview exact from frame math; live phase-locked to
`status.beat`; JS is manual-smoke only). AWR-242 reworks the `/lab` UI (search/filter/group list,
`target_role` phrase tags, settable `timing_mode`, preview-first detail, health strip + Self-test;
styles scoped under `.lab-route`; Pad route untouched). AWR-243 is the functional fix round on that
UI (collision banner only when `production_collision`, selected-draft list pin, ownership
takeover catch via `err.payload`, `applied:false` slider hint, live Test Palette while a lab scene
plays, plus header/phone/preview/health/utility polish). AWR-245 adds the Strip|Room preview
hookup (pad read-only sim routes + Lab toggle; route unit tests in `tests/test_led_pad_service.py`;
JS toggle/fail-soft is code-review + Claude e2e after pad restart). AWR-247 defaults Preview to the
draft's full `cue_beats` (was silently capped at 8) and adds a 2 bars / 4 bars / Full cue control
(`labPreviewLength`); covered by `test_lab_preview_default_beats_equals_full_cue_beats`.
AWR-254 fixes the pad look-editor close guard so it compares against the last successful Save
(not the snapshot taken when the editor opened); covered by
`tests/frontend/test_led_pad_defaults.py` (`test_close_after_save_skips_discard_modal`,
`test_close_with_unsaved_edits_shows_discard_modal`).
AWR-255 adds a persistent pad+lab banner when the live LED config file is newer than the
running bridge process (or a weaker post-Apply warning when process start cannot be read);
covered by `ConfigStaleComputationTests` in `tests/test_led_pad_service.py`.
AWR-193/241/242/243/245/247 JS/UI behavior otherwise has no automated harness — code-review +
manual-smoke covered only (registry `production_collision` + session lab palette live-update + sim
routes + preview default beats are unit-tested). Locked Palette and renderer param unlock behavior
is covered by software tests only.
All LED Pad and Template Lab playback/UI claims are SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.
The iOS/iPad touch pass is implemented/software-tested only; on-device verification is pending.
