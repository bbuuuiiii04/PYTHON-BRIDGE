---
doc_status: current
truth_level: design-intent, code-grounded (all file:line citations verified at 4077794)
last_verified_commit: 4077794
last_verified_date: 2026-07-03
validation_scope: design only — nothing implemented; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED repo status unchanged
---

# LED Pad + Template Lab — Design, Delivery Plan, and Codex Spec

Status: **planned** (design artifact — nothing here is implemented). All references verified
against HEAD `4077794` on 2026-07-03. Repo status remains SOFTWARE-VALIDATED ONLY /
HARDWARE-UNVALIDATED; nothing in this document upgrades that.

Claim labels used throughout: **[confirmed]** = read in current code this session,
**[assumed]** = reasonable inference, not proven, **[decision]** = design choice this doc makes.

---

## 1. Executive summary

LED Pad is a browser tool (mirroring Laser Pad's architecture: standalone local HTTP server +
draft/commit/history over the live JSON config) for creating, tuning, and organizing Govee LED
looks — banks-first, with a live-playing editor that drives the strip through the **production
renderer/runner code**, no Rekordbox required. Template Lab is a second route in the same server
where an AI agent and Brandon co-create *new renders* (new Python effect functions) in an
isolated, gitignored sandbox that the bridge never imports; accepted lab drafts get promoted into
`govee_frame_renderer.py` through the normal Codex/tests/contract pipeline and only then become
LED Pad templates.

The three keystone findings from code:

1. **Standalone live playback already works.** `scripts/direct_rt_groove_chase.py` proves the
   exact pattern: production `GoveeRealtimeRunner` + `GoveeRealtimeTransport` + a synthetic
   `BeatAnchor` at a fixed BPM plays any realtime look on the strip with no bridge and no
   Rekordbox [confirmed, scripts/direct_rt_groove_chase.py:64-96]. LED Pad playback is this
   pattern behind an HTTP server.
2. **The runner already implements Brandon's live-edit semantics.** The runner splits an
   `EffectSpec` into a motion signature and a color signature; color-only changes apply in place,
   any motion change re-configures the engine from beat ~0 [confirmed,
   govee_realtime_runner.py:303-324,449-454]. "Simple controls update in place / structural
   changes restart from beat 0" is largely free.
3. **Output ownership has an existing, software-tested lever.** The bridge's `led_blackout`
   runtime command routes to the dispatch coordinator's operator-blackout path, which
   emergency-stops the bridge's realtime runner, force-releases the owner state machine, and
   latches emergency blackout until `led_clear_blackout` [confirmed,
   led_dispatch_coordinator.py:63-67, led_look_director.py:99-114]. LED Pad uses this as its
   takeover/handback protocol; the command reader tails the JSONL file from EOF, so stale
   commands can never replay at next bridge start [confirmed, runtime_status.py:312-313].

---

## 2. Confirmed design requirements (from Brandon, preserved verbatim in intent)

Banks-first UI with banks **drafts, ambient, groove, buildup, drop, post_drop, breakdown,
utility**; `pre_drop` hidden in the normal UI; `drafts` manual-only and never automation-selected.
A look lives in exactly one bank; Move removes from the old bank; Duplicate creates an
independent copy. Bridge keeps ownership of all cycling/rotation — LED Pad invents none.

Card actions: Play (plays live + opens editor), Edit (opens editor, no play), Duplicate, Move,
Delete. Playing another card switches playback and opens its editor. The editor is the tuning
surface (no separate Tune button) with Play, Stop, Save, Cancel, Undo; all tunable settings
visible; edits auto-apply while playing; only one LED Pad playback at a time; Stop restores the
previous LED state and keeps the editor open; Save writes to the LED Pad draft (never live
config); Cancel discards changes since editor open and closes (dirty Cancel confirms).
Laser-Pad-style draft/commit/history: global Commit writes draft → live config with
backup/history; global Discard reloads live config; Commit/Discard/Delete/Undo/dirty-Cancel
confirm; Play/Stop never confirm. Dirty indicators: global, per look, per bank.

Works with no Rekordbox, no decks, no track. Global session controls: BPM, Test Palette, Loop.
Cue length saved per look in beats (4/8/16/32 common). Loop off → play cue length then restore;
loop on → repeat until Stop/switch. BPM changes apply live; cue-length/template/target changes
restart from beat 0; simple controls update in place.

Color model: operator field **Automation Color** with options **Follow Show Color** (default;
automation uses the bridge color engine's current palette; in pad playback uses the global Test
Palette) and **Locked Palette** (always uses a saved named palette; ignores Test Palette). No
custom RGB picker in v1. Palette names come only from the existing color-engine config; no second
palette system.

Renderer model: include **all** current renders; group them sanely; per-render editable controls
= that render's real config ("renderer config"/"controls", never "render params" in UI); derive
from code and allowlists; explicitly identify hardcoded values worth unlocking; slots are 6 with
slot 5 white-reserved and slot count never exposed; slot controls limited to fill strategy and
mono chance where applicable.

**UI platform (operator constraint, 2026-07-03):** a local browser UI following the existing
Laser Pad pattern (local HTTP server + static assets, loopback by default); normal LED Pad and
Template Lab as separate routes/pages in the same server. No desktop app, no terminal-first UI.
Nothing in current code makes this unsafe or notably harder — Laser Pad already proves the whole
stack (stdlib `ThreadingHTTPServer`, vanilla JS assets, draft/commit/history, status-file
mirror), and §4.1/§6.1 follow it directly.

Template Lab: separate from normal LED Pad (may be a route in the same server); lab drafts
survive restart (gitignored files); playable live but never automation-selected; AI agents may
edit Python renderer code during lab tuning; placeholder colors for drafts; promotion requires
tests + normal config/schema/docs updates; Fable decides hot-load vs restart and bridge
coexistence; explicit Govee output ownership design; no hidden Rekordbox dependency.

---

## 3. Current-code findings

### 3.1 Full render inventory — 54 realtime render names [confirmed]

`REALTIME_EFFECT_NAMES = frozenset(_EFFECTS.keys() | SLOT_EFFECTS.keys())`
[govee_frame_renderer.py:1825].

**Generic frame effects** (10) [govee_frame_renderer.py:887-898]:
`solid, blackout, beat_chase, beat_strobe, drop_burst, breathe, gradient_sweep, sparkle,
color_pulse, bar_wipe`.

**EDM baked frame effects** (29, from `EDM_BUILDS`) [govee_frame_renderer.py:900-930]:
`buildup_ramp_1/2/3, buildup_white_zone_strobe, buildup_white_half_strobe,
buildup_freestyle_nebula, groove_chase_blue/cyan/red/green/cyan_white, groove_freestyle_nebula,
drop_chase_blue/cyan/red/green/cyan_white, drop_center_burst_blue_cyan,
drop_chase_freestyle_nebula, post_drop_chase_blue/cyan/red/green/cyan_white,
post_drop_center_comet_blue_cyan, post_drop_freestyle_nebula, drop_white_aggressive,
post_drop_white_shatter, twinkle_blue`.

**Baked bypass-colorizer effect** (1): `breakdown_star_twinkle_sand`
[govee_frame_renderer.py:1822].

**Slot effects** (14, `SLOT_EFFECTS`, colors injected as 6 slots, slot 5 pure white)
[govee_frame_renderer.py:1796-1811]:
`rt_groove_chase, rt_groove_nebula, rt_post_drop_chase, rt_post_drop_nebula, rt_drop_chase,
rt_drop_nebula, rt_drop_center_burst, rt_post_drop_center_comet, rt_twinkle,
groove_center_chase, groove_center_burst_retract, post_drop_firework_chase,
breakdown_full_breathing, breakdown_star_twinkle`.

This matches the prompt's expected list plus two the prompt didn't name: `sparkle` variants were
named, and additionally `breakdown_star_twinkle_sand` (baked warm-palette twinkle) and the
color-suffix EDM families are enumerated in full above.

### 3.2 Param allowlists = the renderer config surface [confirmed]

`REALTIME_EFFECT_PARAM_KEYS` [govee_frame_renderer.py:972-996, 1842-1864]:

- Every effect also accepts `_SYNC_PARAM_KEYS = {sync_mode, beat_division, travel_beats, width,
  trail_beats, heads, max_pulses, spawn_on_wrap, reverse}` [govee_frame_renderer.py:987-992].
- Generic per-effect keys: `solid: color` · `blackout: —` · `beat_chase: color,bg,trail,span_beats`
  · `beat_strobe: color,subdivision,duty` · `drop_burst: color,bg,decay` ·
  `breathe: color,period_beats,floor` · `gradient_sweep: color_a,color_b,speed` ·
  `sparkle: color,bg,density` · `color_pulse: color,bg` · `bar_wipe: color,bg`.
- EDM builds: `duration_beats` (+ `color` for the five `groove_chase_*`).
- Slot cues: `duration_beats`, plus `burst_beats` (groove_center_burst_retract) and
  `breath_beats`, `drift_beats` (breakdown_full_breathing).
- `slot_colors` and all fade keys (`fade_beats`, `*_from/_to`) are **runtime-injected only**,
  deliberately not allowlisted [govee_frame_renderer.py:1837-1841].

**Fail-closed rule (critical):** a look with any un-allowlisted static param key is a config
error, and *any* config error makes the whole LED config unavailable → **all LED disabled**
[confirmed, led_config.py:409-412 + led_config.py:118-124]. LED Pad must therefore validate the
full draft with `load_led_look_director_config_from_dict` before every Commit, exactly as Laser
Pad validates via its loader.

Value validation for params lives in `_validate_realtime_params` [led_config.py:516-563]:
`trail` int ≥0; `span_beats/decay/period_beats/speed/density/duration_beats/duty/floor` ≥0 with
`floor/duty/density` additionally in [0,1]; `subdivision ∈ {1,2,4,8}`;
`sync_mode ∈ {retrigger, overlap, continuous}`; `beat_division > 0`; `travel_beats/width > 0`;
`heads/max_pulses` int ≥1; `spawn_on_wrap/reverse` bool. **Gap found:** `burst_beats`,
`breath_beats`, `drift_beats` are allowlisted but their *values* are never validated; a
non-numeric value passes config validation and would crash the 40 fps render thread at play time
(e.g. `_slot_groove_center_burst_retract` divides by `burst_beats`
[govee_frame_renderer.py:1602-1603]). The Codex spec includes the hardening fix.

Strobe gating: effects in `REALTIME_STROBE_EFFECTS` require `look.allow_strobe=true` **and**
`safety.allow_strobe=true` [led_config.py:600-604].

### 3.3 Runtime/playback machinery [confirmed]

- `GoveeRealtimeRunner` renders at config fps on its own daemon thread; needs a
  `beat_provider() -> BeatAnchor|None`; renders only while `anchor.permitted and anchor.playing
  and anchor.bpm > 0` [govee_realtime_runner.py:266-272]. Synthetic anchors are proven by
  `scripts/direct_rt_groove_chase.py:72-83`.
- Motion vs color signature split [govee_realtime_runner.py:449-454]: color keys
  (`color, color2, color_a/b, *_from/_to, fade_beats, gradient_stops, slot_colors*`) update in
  place; everything else (including `bg`) re-configures the beat-sync engine → restart from local
  beat 0. BPM lives in the anchor, not the spec → BPM changes apply live without restart.
- `stop()`/`force_deactivate()` blackout + deactivate the transport; deactivating razer mode
  returns the strip to whatever state it held before activation [**assumed** — consistent with
  the WI-6 reconcile design in govee_realtime_runner.py:112-125 but hardware-unvalidated].
- Transport is a tiny per-process UDP sender — nothing prevents two processes from streaming to
  the same strip; cross-process exclusivity must be a protocol, not a mechanism [confirmed,
  govee_realtime_transport.py:25-57].
- Bridge wiring: realtime is built only when `RBSS_GOVEE_REALTIME=1` and a target has
  `realtime.enabled` [__main__.py:676-679]; the runner's anchor comes from
  `StateManager.get_active_beat_anchor` [__main__.py:1238, state_manager.py:844-858].
- Ownership levers: coordinator operator-blackout path = `emergency_stop()` +
  `owner.force_release()` + cloud blackout [led_dispatch_coordinator.py:63-67]; JSONL commands
  `led_blackout` / `led_clear_blackout` / `set_led_look_director` / `led_scene` exist today
  [runtime_status.py:405-446]; command reader seeks to EOF at startup → no stale replay
  [runtime_status.py:312-313]; bridge liveness is observable via
  `/tmp/rb_ss_bridge_v2_status.json` freshness (Laser Pad uses a 5 s staleness rule)
  [tools/laser_pad_web.py:428-446].

### 3.4 Config & color engine [confirmed]

- Banks in config are named LEDBank objects each holding all 8 role lists;
  `LEDLookDirector` reads **only `banks["default"]`** for automation
  [led_look_director.py:59, 194, 269]. So: anything not referenced by `banks.default` role lists
  is automation-invisible. This is what makes a pad-only `drafts` bank trivially safe.
- Look schema: `target, action, scene_ref, fallback, safety_class, brightness, allow_strobe,
  backend, params, param_profile, color_source, diy_color` [led_models.py:42-56,
  led_config.py:1299-1314]. `action="realtime"` requires `backend="realtime_razer"` and a known
  `scene_ref` [led_config.py:383-390]. `safe_default`/`blackout` must be cloud_diy looks; the
  `utility` role accepts only cloud_diy looks [led_config.py:610-613, 639-646].
- Unknown root-level config keys are tolerated (the shipped example carries `metadata`)
  [confirmed via example config + absence of unknown-key rejection in `_validate`]. A root-level
  `_pad_meta` block therefore round-trips safely, mirroring Laser Pad's `_pad_meta` in
  `laser_director.json`.
- Color engine: palettes are named entries (`range` over scale stops, `white`, `spread`,
  `weight`, `dwell`, `focus_modes`) [led_models.py:58-67]; current example palettes:
  `blue_cyan, deep_ocean, indigo, violet, crimson`. Engine resolves per-cue `color`
  (+`color_a/b`) and 6-slot `slot_colors` with slot 5 pure white
  [led_color_engine.py:507-713]; `set_palette(name)` + `lock()` give deterministic palette
  selection [led_color_engine.py:719-733]. `color_source != "engine"` → engine injects nothing
  [led_color_engine.py:529-531]. Slot fill strategy/mono chance live in
  `color_engine.slot_fill_strategy_by_look` / `slot_mono_chance_by_look`
  [led_models.py:111-113].
- Laser Pad architecture to mirror [confirmed, tools/laser_pad_web.py]: stdlib
  `ThreadingHTTPServer` + `BaseHTTPRequestHandler`, in-memory draft under a `Lock`, `/api/config`
  returns draft + validation, `/api/draft` deep-merge patch, `/api/commit` validates then
  `save_config_atomically` with `.bak-<µs-timestamp>` backups, `/api/history*` list/diff/restore,
  `/api/runtime_status` reads the bridge status file, static assets from a sibling directory,
  loopback-by-default binding, launcher in `scripts/`.

---

## 4. LED Pad design

### 4.1 Architecture [decision]

Mirror Laser Pad exactly where possible:

```
scripts/led_pad.py                      # launcher (argparse → run_server), port 8766
tools/led_pad_web.py                    # LedPadService + HTTP handler + routes
tools/led_pad_playback.py               # PadPlayback: runner+transport+synthetic anchor+takeover
tools/led_pad_assets/                   # index.html, pad.css, pad-*.js (vanilla, no deps)
config/led_look_director.json           # live config (existing, gitignored)
config/led_look_director.json.bak-*     # commit backups (existing pattern, gitignored)
config/led_look_director.draft.json     # NEW: persisted pad draft (gitignored)
```

One deliberate divergence from Laser Pad: the draft is **persisted** to
`led_look_director.draft.json` on every mutation and reloaded at server start (falling back to
live config when absent). Justification: LED Pad's Save-vs-Commit split means multi-day draft
sessions, and Template Lab explicitly requires restart-surviving drafts; an in-memory-only draft
(Laser Pad's model) would silently lose Saved-but-uncommitted work on restart.
`# ponytail: single draft file, no draft history — commit backups are the history`.

The pad process **never sends cloud DIY commands and never touches `GOVEE_API_KEY`** in v1.
Playback is realtime-razer only.

### 4.2 Banks model [decision]

- Pad bank *X* (ambient, groove, buildup, drop, post_drop, breakdown, utility) ≡ membership in
  `banks.default.<X>` in the (draft) config. Renames nothing, invents no new rotation — the
  bridge's existing cursor/shuffle rotation over `banks.default` remains untouched
  [led_look_director.py:297-328].
- Pad bank **drafts** ≡ the look list `_pad_meta.drafts` (root-level `_pad_meta` block).
  Drafts-bank looks exist in `looks` (fully validated) but appear in **no** `banks.default` role
  list, so automation can never select them [confirmed by §3.4 director-reads-default-only].
- `pre_drop` stays a real role in config; the pad UI simply doesn't render a pre_drop bank tab.
  A look found in `banks.default.pre_drop` (none today) is shown under a small "other" chip so
  it is never invisible-but-editable-elsewhere. `legacy_color_suffix` bank is untouched and
  hidden.
- Exactly-one-bank invariant: enforced by the pad service on every Move/Duplicate/Delete — a
  look name may appear in exactly one of {the 8 role lists of `banks.default`} ∪
  {`_pad_meta.drafts`}. `safe_default`/`blackout` looks are undeletable and unmovable out of
  `utility` (config cross-checks require them cloud_diy [led_config.py:610-613]).
- Move validation runs the full config validator; e.g. moving a realtime look into `utility`
  fails with the loader's own error, shown verbatim.

### 4.3 Card and editor semantics [decision]

Per Brandon's confirmed flow, with the following bindings to code reality:

- **Play** builds an `EffectSpec` from the *editor's current (unsaved) state* — not the draft —
  so tuning is live. `seed` = stable hash of look name (same as the coordinator's
  `_stable_seed`), `sync_mode`/`beat_division` from params or renderer defaults, exactly as
  `LEDDispatchCoordinator._spec_from_decision` does [led_dispatch_coordinator.py:219-231].
- **Auto-apply while playing:** every editor change POSTs the new control set; the playback
  engine swaps the spec via `runner.set_desired(...)`. The runner's signature split then gives
  Brandon's exact contract: color-ish updates in place, structural edits restart at beat 0
  [§3.3]. Cue length and Loop are pad-side (see below), so changing them also restarts by
  design (the pad rebuilds the spec).
- **Stop** = `runner.set_desired(None)`; after the 0.25 s idle grace the runner deactivates
  razer mode and the strip returns to its prior state [§3.3 assumption noted]. Editor stays
  open.
- **Cue length & Loop:** the runner has no duration concept — the *bridge* owns live durations —
  so the pad owns preview duration: a monotonic deadline `cue_beats × 60/BPM` seconds after
  play-start; on expiry with Loop off the pad performs Stop; with Loop on playback simply
  continues (all current renders are periodic; `duration_beats` wraps EDM/slot cues
  [govee_frame_renderer.py:362-364]). Cue length is stored per look at
  `_pad_meta.looks.<name>.cue_beats` (pad concept, deliberately not a renderer param).
- **Save** merges the editor state into the draft (look fields + params + color-engine per-look
  keys + `_pad_meta` fields) and persists the draft file. **Cancel** restores the editor-open
  snapshot (and if playing, pushes the restored spec — i.e. the strip follows the cancel), then
  closes. **Undo** = revert to last Save (or editor-open) snapshot, client-side.
- **Dirty tracking:** draft-vs-live diff computed server-side per look (normalized JSON
  compare), aggregated per bank and globally. This gives all three dirty indicators from one
  diff pass.
- **Global Commit** = validate draft via `load_led_look_director_config_from_dict`; on success
  atomic-write live config with a `.bak-<timestamp>` backup (Laser Pad's
  `save_config_atomically` pattern), delete/refresh the draft file. **Global Discard** = reload
  draft from live config, delete draft file. History list/diff/restore identical to Laser Pad
  (`/api/history*`), restore loads into the **draft** only.
- Confirmations exactly per Brandon's list; Play/Stop never confirm.

### 4.4 Session controls [decision]

`BPM` (default 128, persisted in `_pad_meta.ui.bpm`), `Test Palette` (default first palette name,
persisted in `_pad_meta.ui.test_palette`), `Loop` (default on, persisted in `_pad_meta.ui.loop`).
BPM feeds the synthetic anchor directly → live tempo change without restart [§3.3]. Test Palette
drives color resolution for Follow-Show-Color looks (§5.3). Bridge not required for any of this.

### 4.5 Hot reload note [confirmed context]

The bridge's config hot-reload only logs `restart_required` — it does not live-swap LED config
[docs/guides/laser_pad.md:120-129]. So after Commit, **live bridge behavior changes only at the
next bridge restart**; the pad UI must say exactly that on successful commit ("Committed — bridge
restart required to take effect"). Committing during a live set is safe (the running bridge keeps
its loaded config) but the restart itself is a live-safety event governed by existing rules
(`pgrep -f rb_ss_bridge_v2 | wc -l` must be 1).

---

## 5. Renderer config / control model

### 5.1 Operator-facing groups (all 54 renders, grouped; registry name shown as fine print)

| Group | Renders |
|---|---|
| Solid & utility (2) | solid, blackout |
| Ambient & breakdown (8) | breathe, gradient_sweep, sparkle, twinkle_blue, rt_twinkle, breakdown_full_breathing, breakdown_star_twinkle, breakdown_star_twinkle_sand |
| Groove (13) | beat_chase, bar_wipe, color_pulse, groove_chase_blue/cyan/red/green/cyan_white, groove_freestyle_nebula, rt_groove_chase, rt_groove_nebula, groove_center_chase, groove_center_burst_retract |
| Buildup (6) | buildup_ramp_1, buildup_ramp_2, buildup_ramp_3, buildup_white_zone_strobe, buildup_white_half_strobe, buildup_freestyle_nebula |
| Drop (13) | beat_strobe, drop_burst, drop_chase_blue/cyan/red/green/cyan_white, drop_center_burst_blue_cyan, drop_chase_freestyle_nebula, drop_white_aggressive, rt_drop_chase, rt_drop_nebula, rt_drop_center_burst |
| Post-drop (12) | post_drop_chase_blue/cyan/red/green/cyan_white, post_drop_center_comet_blue_cyan, post_drop_freestyle_nebula, post_drop_white_shatter, rt_post_drop_chase, rt_post_drop_nebula, rt_post_drop_center_comet, post_drop_firework_chase |

UI labels are humanized ("Groove Center Chase", "Post-Drop Firework Chase"); descriptions for the
EDM family come from the existing `EDM_BUILDS` text [govee_frame_renderer.py:900-930]. Slot-based
renders carry a "show-colored" badge (they follow the palette engine); baked renders carry a
"fixed colors" badge (`breakdown_star_twinkle_sand`, the color-suffix EDM cues,
`drop_white_aggressive`, `post_drop_white_shatter`, etc.).

### 5.2 Control derivation (single source of truth) [decision]

A new small module `led_pad_controls.py` (bridge package, import-safe, no I/O) exposes
`controls_for(scene_ref) -> list[ControlSpec]` derived mechanically from
`REALTIME_EFFECT_PARAM_KEYS[scene_ref]` plus a static metadata map
`{param_key: label, control type, min/max/step/choices, help}` whose ranges are copied from
`_validate_realtime_params` (§3.2). Unknown/future param keys fall back to a raw numeric field —
the pad never silently drops an allowlisted key. Terminology in metadata:

- `travel_beats` → **Motion Beats** (comet/chase travel), `loop_beats` (new, §5.4) → **Motion
  Beats** for looping chases, `breath_beats` → **Breath Beats**, `burst_beats` → **Burst Beats**,
  `duration_beats` → **Cycle Beats**, `width` → **Head Width**, `trail_beats` → **Trail Beats**,
  `heads` → **Comet Count**, `density` → **Sparkle Density**, `duty` → **Strobe Duty**,
  `subdivision` → **Strobe Rate**, `sync_mode` → **Motion Pattern sync** (retrigger / overlap /
  continuous), `reverse` → **Reverse Direction**.
- Comet = the visual object; Motion Pattern = how it moves — the editor's motion section is
  titled "Motion Pattern" and hosts sync_mode/beat_division/travel/width/trail/heads.
- RGB-typed params (`color`, `bg`, `color_a/b`) are **not shown as pickers in v1** (no custom RGB
  picker). For engine-colored looks they're runtime-injected anyway; for baked looks the editor
  shows a read-only "fixed colors" note. Existing static RGB values in config are preserved
  untouched.
- Slot-based renders additionally show **Slot Fill** (`gradient_even` /
  `random_with_replacement` / `random_with_mono_chance` →
  `color_engine.slot_fill_strategy_by_look[look]`) and **Mono Chance** (0–1, only when strategy
  is `random_with_mono_chance` → `color_engine.slot_mono_chance_by_look[look]`). Slot count and
  the white slot are never exposed.
- Look-level fields in the editor: Renderer (grouped picker), Bank (via Move), Brightness
  (0–100), Strobe allowed (with the safety.allow_strobe cross-check surfaced), Automation Color
  (§5.3), Cue Length (beats; pad meta), plus the renderer's controls.

### 5.3 Automation Color [decision]

- **Follow Show Color** ≡ `color_source: "engine"` (current default). During automation the
  bridge engine injects colors as today. During pad playback the pad instantiates
  `LedColorEngine(draft.color_engine)`, calls `set_palette(test_palette)` + `lock()`, then
  `resolve_slot_colors(...)` / `resolve_color(...)` per play/restart with a synthetic
  section id, and merges the result into the spec params — the same injection shape the bridge
  uses. Changing Test Palette while playing re-resolves and updates in place (colors are
  color-sig keys).
- **Locked Palette** ≡ `color_source: "engine"` **plus** a new color-engine mapping
  `color_engine.locked_palette_by_look: {look_name: palette_name}`. Engine change (small): in
  `resolve_color` and `resolve_slot_colors`, when the look has a locked palette, resolve using
  that palette's interval/white instead of the journey palette (focus window degraded to the
  full palette interval). Automation then always renders that look in its saved palette; pad
  playback ignores Test Palette for it. This is the smallest design that satisfies "no second
  palette system" — palette names remain exclusively `color_engine.palettes` keys, validated by
  the existing loader extension.
- New looks default to Follow Show Color. v1 has no RGB picker anywhere.

### 5.4 Hardcoded values worth unlocking (explicit, smallest safe moves)

All are param reads with the current constant as default — zero behavior change for existing
configs; each key must be added to that effect's allowlist entry (and value-validated):

1. `rt_groove_chase` / `rt_groove_nebula`: `loop_beats` (currently hardcoded 4.0
   [govee_frame_renderer.py:1142,1197]) → new allowlisted key `loop_beats`, validated > 0.
   Operator label: Motion Beats.
2. Slot chase family (`rt_drop_chase`, `rt_post_drop_chase`, `rt_drop_nebula`,
   `rt_post_drop_nebula`): comet `travel_beats` and `width` are hardcoded 2.0 / 0.8
   [govee_frame_renderer.py:1341-1343 etc.] even though both keys are *already allowlisted* via
   `_SYNC_PARAM_KEYS` — read them from params with the current defaults. Spawn interval 1.0
   stays hardcoded in v1 (`# ponytail: spawn_interval_beats deferred until asked for`).
3. `groove_center_chase` / `post_drop_firework_chase`: `travel_beats` (hardcoded 1.0) and comet
   width fraction (0.15 of half-strip) — expose `travel_beats` only; width fraction stays.
4. Strobe gate rate (16th-note `int(beat*16)%2` across the drop/post-drop family): **not**
   unlocked in v1 — it is a safety-relevant aesthetic constant; revisit only on explicit
   request.
5. Hardening (not an unlock): add `burst_beats`, `breath_beats`, `drift_beats`, `loop_beats` to
   `_validate_realtime_params` as positive numbers (closes the crash gap in §3.2).

---

## 6. Template Lab design

### 6.1 Shape [decision]

A second route (`/lab`) in the same `led_pad_web.py` server — same session controls, same
playback engine, same single-playback rule (LED Pad and Lab share one playback slot, so they can
never fight each other). Separate visual identity so drafts are unmistakable.

### 6.2 Lab draft storage [decision]

```
config/led_lab/                      # gitignored directory
  effects_lab.py                     # AI-edited Python module with draft render functions
  drafts.json                        # lab draft registry (survives restart)
```

`drafts.json` entries: `{name, kind: "slot"|"frame", fn: "<function name in effects_lab.py>",
params: {...}, cue_beats, notes, brief, status: "iterating"|"accepted"|"rejected",
created, updated}`. Lab drafts are playable but exist nowhere in `led_look_director.json`, so
they are structurally invisible to automation.

### 6.3 Lab code loading — hot-load, and why [decision]

The **bridge never imports lab code** — that is the load-bearing safety property. Only the pad
process loads `config/led_lab/effects_lab.py`, via `importlib` spec-from-file, on every Play and
on an explicit "Reload code" button. Registration is **process-local**: the pad wraps the loaded
functions in its own overlay registry and resolves lab scene_refs (`lab_<name>`) itself; slot-kind
draft functions get their MotionField run through the production `universal_colorizer` with
palette slots resolved exactly as §5.3 (placeholder colors = current Test Palette). A syntax/
runtime error in lab code fails the Play request with the traceback shown in the Lab UI — the
pad server stays up, the bridge is never involved.

Decision: **hot-load (reload-per-Play), no restarts** for lab iteration. Restart-based flows
would add minutes to every tuning round-trip for zero safety gain, since the lab module is
already process-isolated from the bridge. Bridge restarts happen only at promotion time (new
renderer code in `govee_frame_renderer.py`).

Draft render functions must match the production signatures (`EffectFn`/`SlotEffectFn`
[govee_frame_renderer.py:11-19]) from day one, so promotion is a move, not a rewrite.

### 6.4 Promotion pipeline [decision]

Promotion is a **Codex/agent task, not a pad button** (it changes bridge code):

1. Move the accepted function into `govee_frame_renderer.py`; register in `SLOT_EFFECTS` or
   `_EFFECTS`; add its param-allowlist entry; add to `REALTIME_STROBE_EFFECTS` if it strobes.
2. Tests in `tests/test_govee_frame_renderer.py`: determinism (same inputs → same frame), frame
   length/clamping, slot-5-white reservation for slot cues, param defaults, strobe-set
   membership.
3. Config: add the look to `config/led_look_director.example.json` (drafts-equivalent placement);
   update `docs/subsystems/led_govee.md` cue table; contract `led_govee` docs_update list; run
   the three hard checks + `python3 -m unittest discover tests`.
4. Restart the bridge at a safe moment (single-process check), then the look appears in LED
   Pad's **drafts** bank for final placement by Brandon.
5. Rejected drafts: mark `status: "rejected"` in `drafts.json` (kept for archaeology; delete on
   request).

### 6.5 Bridge coexistence [decision]

Template Lab and LED Pad playback follow one rule — the **takeover protocol** (§8). Lab may run
while the bridge runs, but Govee output requires either (a) bridge not running / LED lane dark,
or (b) explicit operator takeover. No implicit stealing, ever.

---

## 7. AI-agent Template Lab skill / workflow

Deliverable: new repo skill `.claude/skills/template-lab/SKILL.md` (content below, condensed to
its operative core; the Codex spec Task 14 creates it verbatim-equivalent).

```markdown
---
name: template-lab
description: Use when Brandon asks for a new LED cue/template or wants to tune one — the
  AI-assisted flow for creating draft Govee renders in Template Lab, playing them live with
  placeholder colors, iterating on Brandon's feedback, and promoting accepted drafts into
  govee_frame_renderer.py via tests + contracts. Not for laser or SoundSwitch work.
---

# Template Lab — agent workflow

## 0. Ground rules (live safety first)
- Never start Govee playback yourself without confirming output ownership: bridge status file
  fresh (<5s) → ask Brandon before takeover; the pad UI's takeover button is his call.
- Never edit `govee_frame_renderer.py`, `led_config.py`, or any bridge module during lab
  iteration. Lab code lives ONLY in `config/led_lab/effects_lab.py`.
- Never touch `GOVEE_API_KEY`, device IDs, or live config. Never commit `config/led_lab/`.
- Respect strobe limits: if the draft strobes, say so, keep duty/rate within the patterns
  already in the renderer, and flag that promotion will need allow_strobe gating.
- Label claims: rendered-in-lab ≠ validated-on-hardware ≠ show-ready. Use §10 status words.

## 1. Interview Brandon (short, concrete)
Ask at most: (1) which moment (groove/buildup/drop/post-drop/breakdown/ambient)?
(2) what does it look like in one sentence (object + motion + energy)? (3) nearest existing
render (play 1-2 references from the pad if unsure)? (4) beat relationship (per-beat hits,
N-beat cycle, continuous)? (5) white accents or palette-only?
Translate to: Comet(s) = visual objects; Motion Pattern = how they move; Motion Beats /
Breath Beats = timing. Confirm the sentence back before writing code.

## 2. Start from existing patterns
Read the closest existing effect in govee_frame_renderer.py and copy its skeleton
(slot-based unless Brandon explicitly wants fixed colors). Reuse the house primitives:
center-out comets, `_drop_chase_spawn_times`, sub-pixel slot mapping (slots 0-4, slot 5
white-reserved), strobe gates, `_rng` stable seeding. Deterministic by construction:
no wall-clock, no global random.

## 3. Smallest runnable draft
One function, production signature (SlotEffectFn preferred), hardcode everything except what
Brandon will obviously tune. Register it in config/led_lab/effects_lab.py, add a drafts.json
entry, set cue_beats to the natural cycle.

## 4. Play + tune loop
Play through /lab with Test Palette placeholder colors at Brandon's BPM. One change per
iteration; describe what changed in plain language ("comets now die at the ends instead of
wrapping"). Prefer param-izing a constant over rewriting the shape. Keep a running list of
which constants Brandon actually adjusted — those become the promoted render's exposed
controls; everything he never touched stays hardcoded.

## 5. Accept / reject
Accepted = Brandon says so while watching it. Then hand promotion to the normal pipeline
(codex-spec skill): move code, allowlist params (value-validate every new numeric key),
strobe-set membership, tests in tests/test_govee_frame_renderer.py, example-config look,
led_govee card cue-table row, contract checks, unittest run. Rejected = status flip in
drafts.json, one line on why (so the next agent doesn't re-pitch it).

## 6. Forbidden
Editing bridge modules mid-lab; running/restarting the bridge without the single-process
check; sending Govee cloud commands; inventing palette systems or scene names; upgrading
status language; leaving playback running when Brandon steps away (Stop is free).
```

---

## 8. Safety / output ownership model

**Invariant: at most one process streams razer UDP to the strip at any moment.** The transport
cannot enforce this (§3.3), so it's a protocol with three states:

1. **Bridge-owned (default live state).** Bridge status file fresh + LED lane enabled. The pad
   shows "Bridge owns LEDs" and disables Play. No pad output.
2. **Pad-owned (explicit takeover).** Operator clicks "Take over Govee" → pad appends
   `{"cmd":"led_blackout","reason":"led_pad"}` to `/tmp/rb_ss_bridge_v2_commands.jsonl` → bridge
   latches emergency blackout, emergency-stops its realtime runner, force-releases its owner
   machine, sends one cloud blackout [confirmed path, §1.3]. Pad waits ~1.5 s, then activates its
   own transport. While latched, every bridge automation decision resolves to blackout and the
   coordinator's operator-blackout branch (idempotent, cloud-deduped) — the bridge cannot
   re-acquire razer mode. On pad Stop-all/exit (incl. `atexit`): deactivate transport, then
   append `{"cmd":"led_clear_blackout"}` → bridge automation resumes at the next role entry.
3. **Free (bridge not running).** Status file missing/stale >5 s → pad plays directly. Commands
   written now are never replayed later (EOF-tail semantics [runtime_status.py:312-313]).

Failure analysis: pad crash while owning → strip stays dark on the bridge side (fail-dark, the
correct direction); recovery is one JSONL line (`led_clear_blackout`) or the existing menubar/
CLI tooling. Bridge starts *during* pad ownership → bridge comes up with no blackout latch and
could dispatch on role entry; therefore the pad also polls the status file every 2 s while
playing and, if a fresh bridge appears without the latch, re-sends the takeover command and
surfaces a warning banner. Residual risk (accepted, documented): a ~seconds-wide window where
both could emit; the pad's re-assert plus razer-activate reconcile mirrors the bridge's own WI-6
self-heal approach [govee_realtime_runner.py:112-125].

Additional gates: pad never runs `dry_run` overrides (it honors the target's realtime block
as-is); strobe-classed renders play only if the draft look and draft safety allow strobe (same
rule the config loader enforces for automation); the emergency stop in the pad UI (always
visible) does blackout + deactivate + clear-desired synchronously — same semantics as
`force_deactivate` [govee_realtime_runner.py:130-158].

Live-mixing reasoning: LED Pad/Lab are rehearsal tools. During an actual set the operator has no
reason to take over; if they do, SoundSwitch/laser lanes are untouched (LED commands don't cross
lanes [docs/led_look_director_design.md:80-83]), and LED-side worst case is "LEDs dark until
clear" — never "LEDs strobing uncontrolled".

---

## 9. Phased delivery plan

Each phase is independently shippable, Codex-implemented, software-tested only.

- **Phase 0 — Bridge-side prep (tiny, no behavior change).**
  Param value validation for `burst_beats/breath_beats/drift_beats` (+ future `loop_beats`);
  `.gitignore` entries (`config/led_look_director.draft.json`, `config/led_lab/`); change-
  contract entry `led_pad`. Exit: hard checks green, unittest green.
- **Phase 1 — LED Pad MVP (the big one).**
  `led_pad_controls.py`; `tools/led_pad_playback.py` (runner+transport+synthetic anchor+cue
  timer+takeover protocol); `tools/led_pad_web.py` + assets (banks UI, cards, editor,
  draft/commit/history, dirty indicators, session controls); `scripts/led_pad.py`. Follow-Show-
  Color playback via Test Palette. Locked Palette **UI-hidden** (engine support lands in Phase
  3). Exit: service-layer unit tests green; manual checklist (below) passes with bridge stopped
  and with takeover.
- **Phase 2 — Template Lab.**
  `/lab` route, `config/led_lab/` loader with per-Play reload, lab draft registry CRUD, lab
  playback through the shared playback slot, promote/reject bookkeeping; the `template-lab`
  skill file; docs. Exit: a scripted demo draft (checked into nothing — created by the test as a
  temp file) loads, renders deterministic frames through the overlay, and never touches bridge
  modules.
- **Phase 3 — Locked Palette + renderer unlocks.**
  `locked_palette_by_look` in ColorEngineConfig + engine resolution + validation; renderer
  param reads for `loop_beats`/`travel_beats`/`width` per §5.4 with allowlist + validator +
  tests; pad editor exposes Automation Color fully. Exit: engine tests prove locked-palette
  resolution and journey-palette non-regression; renderer tests prove default-value parity
  (identical frames when params absent).
- **Phase 4 — polish (optional, demand-driven).**
  LaunchAgent (mirroring `com.bbui.laser-pad.plist`), cloud-look preview via
  `GoveeRuntimeSender`, per-bank reorder, draft history. Not scheduled until asked for.

---

## 10. Codex-executable implementation spec

# Codex Implementation Spec — LED Pad + Template Lab (Phases 0–2 concrete; Phase 3 outlined)

## Part A — Context & Root Cause (verified; read, do not implement)

- LED subsystem code paths, registries, allowlists, validation, runner semantics, ownership
  levers: see §3 of the accompanying design doc; every claim there carries file:line and a
  confirmed/assumed label. Key hard facts you must not violate:
  - [confirmed] Any config error disables ALL LED (led_config.py:118-124); unknown static param
    keys are config errors (led_config.py:409-412). Every pad write path must validate via
    `load_led_look_director_config_from_dict` before touching the live file.
  - [confirmed] `LEDLookDirector` reads only `banks["default"]` (led_look_director.py:59,194,269).
  - [confirmed] Standalone playback pattern: scripts/direct_rt_groove_chase.py:55-96.
  - [confirmed] Takeover levers: runtime_status.py:405-446 (commands), 312-313 (EOF tail),
    led_dispatch_coordinator.py:63-67 (operator blackout path), STATUS_PATH freshness pattern
    tools/laser_pad_web.py:428-446.
  - [confirmed] Laser Pad architecture to mirror: tools/laser_pad_web.py (service+handler+routes,
    atomic save with .bak-timestamp backups), scripts/laser_pad.py launcher, assets dir.
  - [assumed] Razer deactivate returns the strip to its pre-activation state; treat as
    hardware-unvalidated and never claim otherwise in docs or UI copy.

## Part B — Tasks (implement in order; one commit per phase)

### Absolute Rules
- Do NOT touch: `state_manager.py`, `__main__.py`, `led_look_director.py`,
  `led_dispatch_coordinator.py`, `govee_realtime_runner.py`, `govee_realtime_transport.py`,
  `beat_sync_engine.py`, laser/* , soundswitch/* , rekordbox reader modules. (Phase 3 opens
  `led_color_engine.py`, `led_models.py`, `led_config.py`, `govee_frame_renderer.py` for the
  named edits only.)
- Behavior that must not change: bridge automation selection/rotation; existing look rendering
  (frame-identical when new params are absent); config loading for every currently-valid config;
  `python3 -m unittest discover tests` stays green throughout.
- Error handling: fail closed and surface. No broad try/except in service logic; HTTP layer
  returns `{"ok": false, "error": ...}` with the real message (Laser Pad handler pattern).
  Playback errors stop playback and report; they never retry silently.
- The pad never imports `govee_runtime_sender.py` and never reads `GOVEE_API_KEY`.
- Dirty-worktree discipline: never revert or `git checkout --` files you did not create.

### Phase 0
**Task 0.1 — `led_config.py`: value-validate slot-cue numeric params.**
In `_validate_realtime_params`, add `burst_beats`, `breath_beats`, `drift_beats` to the
positive-number group (`must be a number > 0`, matching `travel_beats` handling). Extend
`tests/test_led_config.py` with one rejecting case per key (string value → error mentions the
key) and one accepting case.

**Task 0.2 — `.gitignore`:** add `config/led_look_director.draft.json` and `config/led_lab/`.

**Task 0.3 — contracts:** add contract key `led_pad` to `docs/agents/change_contracts.yml` (+ the
human table in `docs/agents/change_contracts.md`): code globs `tools/led_pad_*`,
`scripts/led_pad.py`, `led_pad_controls.py`; docs_update: `docs/guides/led_pad.md`,
`docs/subsystems/led_govee.md`, `docs/architecture/doc_index.md`,
`docs/status/active_work_registry.md`. Run `python3 tools/check_agent_contracts.py`,
`check_docs_metadata.py`, `check_docs_drift.py`.

### Phase 1
**Task 1.1 — `led_pad_controls.py` (new, repo root, pure).**
`CONTROL_META: dict[str, dict]` mapping every key appearing in any `REALTIME_EFFECT_PARAM_KEYS`
value to `{label, kind: "number"|"int"|"bool"|"choice", min, max, step, choices, help,
color_sig: bool}` with ranges copied from `_validate_realtime_params` and labels from design §5.2.
`RENDER_GROUPS: dict[str, tuple[str, ...]]` exactly as design §5.1 (all 54 names — enumerate them
literally; add a module-level assertion `set(flatten(RENDER_GROUPS)) == set(REALTIME_EFFECT_NAMES)`
so a future renderer addition fails loudly here, not silently in the UI).
`controls_for(scene_ref) -> list[dict]`; `render_catalog() -> list[dict]` (name, group, label,
description from `EDM_BUILDS` when present, `slot_based = name in SLOT_EFFECTS`,
`strobe = name in REALTIME_STROBE_EFFECTS`). Unit tests: catalog covers every
`REALTIME_EFFECT_NAMES` member; every allowlisted key has metadata; strobe/slot flags match the
renderer sets.

**Task 1.2 — `tools/led_pad_playback.py` (new).**
Class `PadPlayback` owning: `GoveeRealtimeTransport` (built from the config's realtime-enabled
target exactly as scripts/direct_rt_groove_chase.py:55-63, including `header_bytes`, `stretch`,
`activate_pt`, `deactivate_pt`), `GoveeRealtimeRunner(transport, GoveeFrameRenderer(),
segments=rt.segments, fps=rt.fps)`, a mutable `{bpm, playing}` synthetic-anchor state feeding
`set_beat_provider` (BeatAnchor with `deck=0, playing=True, permitted=True`, abs_beat integrated
from monotonic time × bpm/60 — reuse the direct-rt closure shape), and a cue timer thread that
performs Stop at `cue_beats*60/bpm` seconds when loop is off.
Public API: `play(spec_dict, cue_beats, loop)`, `update(spec_dict)` (set_desired only),
`set_bpm(bpm)`, `stop()`, `emergency_stop()`, `status()`.
Takeover protocol (design §8): `acquire(mode)` where mode is derived from
`/tmp/rb_ss_bridge_v2_status.json` freshness (<5 s = bridge live). Bridge live → require
`takeover=True` flag from caller; append `{"cmd":"led_blackout","reason":"led_pad"}` to
`/tmp/rb_ss_bridge_v2_commands.jsonl` (create-safe, 0o600 — reuse the flags/chmod pattern at
runtime_status.py:641-644), sleep 1.5 s, then allow playback; poll status every 2 s while owning
and re-send on fresh-bridge-without-latch; `release()` → runner stop + append
`{"cmd":"led_clear_blackout"}`; register `atexit` release. Bridge absent → play directly, no
commands. Never instantiate `GoveeRealtimeDryRunTransport` implicitly; a `--dry-run` server flag
selects it explicitly for tests/demos.
Pure logic (anchor math, cue-deadline math, takeover state machine transitions) must live in
transport-free functions/classes for unit testing.

**Task 1.3 — `tools/led_pad_web.py` + `tools/led_pad_assets/` + `scripts/led_pad.py` (new).**
Mirror the Laser Pad server skeleton (ThreadingHTTPServer, service under one Lock, JSON routes,
static assets, loopback default, port **8766**).
`LedPadService` state: `self._draft` (dict) loaded from `config/led_look_director.draft.json` if
present else live config; every mutating route persists the draft file atomically.
Routes (all under `/api/`):
- `GET  config` → `{config: draft, errors, warnings, dirty: {global, banks: {…}, looks: […]}}`
  (validation via `load_led_look_director_config_from_dict`; dirty = normalized diff vs live
  file).
- `GET  renders` → `render_catalog()` + `controls_for` output.
- `GET  palettes` → names from draft `color_engine.palettes` (empty engine → empty list + warning).
- `POST look/save` `{name, look_fields, params, pad_meta: {cue_beats}, slot_fill, mono_chance}` —
  merge into draft (`looks.<name>`, `color_engine.slot_fill_strategy_by_look`,
  `color_engine.slot_mono_chance_by_look`, `_pad_meta.looks.<name>`), validate, persist, return
  errors/warnings.
- `POST look/duplicate` `{source, new_name}` (deep copy incl. per-look engine keys and pad meta;
  new look goes to `_pad_meta.drafts`), `POST look/move` `{name, bank}` (enforce
  exactly-one-bank invariant across `banks.default.*` + `_pad_meta.drafts`; reject moves of
  `safe_default`/`blackout`; run validator), `POST look/delete` `{name}` (reject if
  `safe_default`/`blackout` or referenced by `drop_pairs`; remove from bank lists, looks,
  per-look engine keys, pad meta).
- `POST play` `{name?, editor_state?, takeover?}` — build EffectSpec params: start from editor
  params; if look `color_source=="engine"`, resolve colors via
  `LedColorEngine(draft_color_engine)` + `set_palette(session.test_palette)` + `lock()` +
  (`resolve_slot_colors` when `scene_ref in SLOT_EFFECTS` else `resolve_color`) with
  `role=<bank>`, `section_id="led_pad"`, `cycle=0`; seed = blake2b of look name (the
  coordinator's `_stable_seed` shape); `sync_mode`/`beat_division` fall back to
  `default_sync_mode`/`default_beat_division`. Delegate to `PadPlayback.play`. Only one playback:
  a new play replaces the old spec.
- `POST update` (live auto-apply), `POST stop`, `POST session` `{bpm?, test_palette?, loop?}`
  (persist under `_pad_meta.ui`; bpm change → `PadPlayback.set_bpm`; test_palette change while
  playing → re-resolve colors and `update`), `POST commit`, `POST discard`,
  `GET history`, `GET history/<name>/diff`, `POST history/<name>/restore`,
  `GET runtime_status` (status-file read + `takeover_active` flag), `POST emergency_stop`.
Commit: validate; on errors return them (never write); on success atomic-write live config with
`led_look_director.json.bak-<µs timestamp>` backup (reuse/port `save_config_atomically`), reset
draft file to committed content.
UI (vanilla JS, Laser Pad asset conventions): bank tabs (drafts, ambient, groove, buildup, drop,
post_drop, breakdown, utility — no pre_drop tab; "other" chip if pre_drop/unknown membership is
nonempty), look cards with per-card dirty dot + Play/Edit/Duplicate/Move/Delete, editor drawer
per design §4.3/§5.2 (grouped renderer picker, Motion Pattern section, Cue Length chips
4/8/16/32 + free field, auto-apply-on-change while playing, Save/Cancel/Undo/Stop/Play), global
header: BPM, Test Palette select, Loop toggle, Commit/Discard with confirm, ownership banner
("Bridge owns LEDs — Take over?" / "Pad owns LEDs — Release"), always-visible Emergency Stop.
Confirmations exactly: Commit, Discard, Delete, Undo, dirty Cancel. Cloud-backend looks
(`action != "realtime"`): cards render with Play disabled + "cloud scene — not previewable" and
editor exposes only brightness/bank/automation-color-N/A.
`scripts/led_pad.py`: argparse launcher identical in shape to `scripts/laser_pad.py`
(`--host/--bind/--port/--config`, default 127.0.0.1:8766).

**Task 1.4 — tests `tests/test_led_pad_service.py`, `tests/test_led_pad_playback.py` (new).**
Service: draft load/persist round-trip (tmpdir configs); exactly-one-bank enforcement on
move/duplicate/delete; safe_default/blackout guards; commit-blocks-on-invalid (inject an
un-allowlisted param and assert live file untouched); dirty computation; spec building
(engine-colored slot look gets 6 slot_colors with slot 5 = (255,255,255); locked test palette
determinism via `set_seed`); session persistence. Playback: synthetic anchor math; cue-deadline
stop with loop off / continuation with loop on (fake time_fn/sleep_fn — the runner already
accepts injected clocks [govee_realtime_runner.py:52-70]); takeover state machine transitions
(fake status file mtimes + captured command lines) — all with `GoveeRealtimeDryRunTransport` or
fakes; zero network.

**Task 1.5 — docs.** New `docs/guides/led_pad.md` (status header, launch, capabilities, takeover
protocol incl. recovery one-liner, commit→restart-required note); update
`docs/subsystems/led_govee.md`, `docs/architecture/doc_index.md`,
`docs/status/active_work_registry.md`. Run all four check tools.

### Phase 2
**Task 2.1 — Lab storage + loader (`tools/led_pad_lab.py`, new).**
`LabRegistry` over `config/led_lab/drafts.json` (schema design §6.2; atomic writes; create dir
0o700 on first use). `load_lab_effects(path) -> dict[str, callable]` via
`importlib.util.spec_from_file_location` executed fresh on every call (hot-load); wrap import
errors into a structured `{ok: false, traceback}` result. Lab scene_refs are `lab_<draft name>`;
resolution order in the pad's frame path: lab overlay first, then production renderer. Slot-kind
lab functions: run MotionField → `universal_colorizer(field, resolved_slot_colors)`; frame-kind:
call directly; clamp + pad frames to segment count exactly as `GoveeFrameRenderer.render` does
(reuse it: instantiate a renderer subclass or wrapper that checks the overlay dict before
delegating — do NOT mutate the module-level `_EFFECTS`/`SLOT_EFFECTS` dicts).
**Task 2.2 — `/lab` route + UI.** Draft list (name, status, notes, brief), create/edit metadata,
Play/Stop through the shared `PadPlayback` slot (same takeover rules; lab playback and pad
playback preempt each other), "Reload code" button, error/traceback panel, accept/reject status
buttons. Lab drafts never appear in the LED Pad banks UI.
**Task 2.3 — skill file `.claude/skills/template-lab/SKILL.md`** with the §7 content.
**Task 2.4 — tests `tests/test_led_pad_lab.py`.** Registry round-trip; hot-reload picks up an
edited temp module; broken module → structured error, server-safe; overlay resolution prefers
lab names and never shadows production names (reject `lab_` collisions with
`REALTIME_EFFECT_NAMES`); slot-kind draft renders through `universal_colorizer` with slot-5
white. Docs: extend `docs/guides/led_pad.md` with the Lab section; re-run checks.

### Phase 3 (outline — spec to be tightened per §12 decisions before execution)
- `led_models.py`: `ColorEngineConfig.locked_palette_by_look: Dict[str, str]`.
- `led_config.py`: validate values are palette names; parse into the dataclass.
- `led_color_engine.py`: in `resolve_color`/`resolve_slot_colors`, resolve against the locked
  palette's interval (full interval as focus window) when the look is mapped; journey state
  untouched.
- `govee_frame_renderer.py`: param reads per §5.4 items 1–3 with current constants as defaults;
  allowlist additions (`loop_beats`); `_validate_realtime_params` coverage for `loop_beats`.
- Pad editor: Automation Color control writes/clears `locked_palette_by_look`.
- Tests: engine locked-palette determinism + non-regression (`set_seed` fixed, absent mapping →
  byte-identical outputs to current code); renderer default-parity frame tests.

## Part C — Invariants that MUST still hold
1. Bridge hot path gains nothing: no bridge-process code changes in Phases 1–2 beyond Task 0.1's
   validator; the 200 Hz push loop and StateManager are untouched.
2. All-LED-fail-closed: pad Commit can never write a config that
   `load_led_look_director_config` rejects.
3. Automation blindness to drafts: no draft/lab identifier ever enters `banks.default.*`,
   `drop_pairs`, `safe_default`, or `blackout`.
4. Single razer streamer: pad output only in Free or Pad-owned states (§8); takeover only via
   the existing `led_blackout`/`led_clear_blackout` commands; `atexit` release registered.
5. Bridge never imports lab code or the pad modules; `config/led_lab/` and the draft file stay
   gitignored; no secrets/IPs/device IDs in code, tests, or docs.
6. Existing looks render frame-identically when new params are absent (Phase 3 parity tests).
7. Emergency stop (pad UI) is synchronous blackout+deactivate; strobe gating on playback matches
   loader rules (look.allow_strobe && safety.allow_strobe).

## Part D — Tests
Enumerated per task above. All new algorithmic logic (anchor math, cue timer, takeover FSM,
bank-invariant enforcement, overlay resolution, locked-palette resolution) must be testable
pure — no sockets, no real filesystem beyond tmpdir, no sleeps (inject time_fn/sleep_fn).
Broad gate per phase: `python3 -m unittest discover tests`.

## Part E — Acceptance (definition of done, per phase)
- Phase checks: `python3 tools/check_docs_metadata.py && python3 tools/check_agent_contracts.py
  && python3 tools/check_docs_drift.py` green; `python3 tools/check_docs_staleness.py --report`
  reviewed; full unittest run green.
- Contract `led_pad` docs_update list satisfied; `led_govee` contract satisfied for Task 0.1 and
  Phase 3 renderer/engine edits.
- Manual checklist (operator, software-level): pad serves on 8766 with bridge stopped; banks
  render with drafts tab; Play on an `rt_*` look streams frames in `--dry-run` mode
  (frame_index advancing in `/api/runtime_status`); BPM slider changes tempo without restart;
  cue-length change restarts; loop-off stops at N beats; Commit writes backup + validates;
  Discard restores; history diff/restore works; takeover banner appears when a bridge status
  file is fresh.
- Status language: everything documented as `implemented` + `software-tested` at most;
  hardware claims forbidden.

## When you finish
Report: files changed per phase; test/check commands run with results; which §12 open decisions
you consumed as specced vs deferred. Operator summary in plain language: what LED Pad can do
now, what still requires a bridge restart, the takeover/release one-liners
(`led_blackout`/`led_clear_blackout`), and the explicit list of hardware-unvalidated assumptions
(razer deactivate restore behavior, visual quality of every render — all need eyes-on sign-off).

*Adversarial self-review of this spec:* the most dangerous failure would be pad playback fighting
bridge automation mid-set → addressed by defaulting to Play-disabled when the bridge is fresh,
takeover-only-explicit, EOF-tail no-replay, atexit release, and poll-and-reassert; second most
dangerous is a pad Commit bricking all LED via fail-closed config → addressed by validating with
the production loader on every save/commit and blocking commit on any error; third is lab code
crashing the shared server → addressed by process-isolation from the bridge plus structured
import-error capture, and by never mutating the production registries.

---

## 11. Tests / checks / docs per phase

Consolidated view (details inline in Part B):

| Phase | Tests | Hard checks | Docs |
|---|---|---|---|
| 0 | test_led_config.py additions | contracts+metadata+drift | change_contracts.md/yml |
| 1 | test_led_pad_service.py, test_led_pad_playback.py, led_pad_controls tests | all four tools + unittest | docs/guides/led_pad.md (new), led_govee card, doc_index, active_work_registry |
| 2 | test_led_pad_lab.py | same | led_pad guide Lab section, template-lab skill |
| 3 | engine locked-palette + renderer default-parity tests | same | led_govee card, config docs |

---

## 12. Open decisions — my recommendations

1. **Pad draft persistence** (divergence from Laser Pad's in-memory draft): **recommend
   file-backed draft** (`config/led_look_director.draft.json`) as specced — Save-vs-Commit over
   multiple days plus Lab's survive-restart requirement make in-memory drafts a data-loss trap.
2. **Takeover mechanism**: **recommend reusing `led_blackout`/`led_clear_blackout`** (zero
   bridge changes, already software-tested, fail-dark). Ceiling: blackout latch semantics show
   up in status as "emergency", which may read scarier than it is. Upgrade path if that ever
   annoys: a dedicated `led_standdown` command with its own status word — bridge change, defer.
3. **Cloud-DIY look preview in pad**: **recommend defer to Phase 4.** It needs
   `GOVEE_API_KEY` handling and rate-limit care in a second process for a two-field editor
   (brightness + scene_ref). Cards stay manageable (move/duplicate/delete) meanwhile.
4. **Hot-load vs restart for Lab**: **decided hot-load** (§6.3) — reload-per-Play in the pad
   process only; the bridge never imports lab code, so restarts buy nothing.
5. **Lab concurrent with live bridge**: **decided allowed-with-explicit-takeover** (§8). A
   hard "never while bridge runs" rule would kill legitimate soundcheck workflows; the
   protocol + fail-dark direction covers the risk.
6. **Locked Palette representation**: **recommend `color_engine.locked_palette_by_look`**
   (§5.3) — one dict, engine-side resolution, no second palette system, no schema_version bump
   (unknown color_engine keys currently fail that block closed, so the loader must learn the
   key in the same change — that is Phase 3's led_config edit).
7. **Where cue length lives**: **recommend `_pad_meta.looks.<name>.cue_beats`** (pad-only
   concept). Putting it in look params would collide with `duration_beats` (a real renderer
   cycle knob) and confuse automation semantics.
8. **Port**: 8766 (Laser Pad holds 8765). Trivial, flagged only so nobody double-binds.
9. **Editor exposure of `sync_mode`/`beat_division`/`heads`/`max_pulses`**: recommend showing
   them in a collapsed "Advanced motion" section — they're allowlisted and real, but defaults
   are right for nearly every look.
10. **pre_drop**: stays hidden as required; the "other" chip (§4.2) is my recommended guard so
    config-hand-edited pre_drop looks are never unreachable in the UI. Drop the chip if you'd
    rather keep the UI strictly 8-bank.

---

## 13. Explicit non-goals

- No new cycling/rotation logic anywhere in the pad; no automation semantics changes.
- No custom RGB picker, no per-slot color editing, no new palette system, no slot-count control.
- No DMX/SoundSwitch/laser coupling; no Rekordbox dependency of any kind.
- No cloud API usage from the pad in Phases 0–3; no Govee device management/discovery UI.
- No hardware validation claims — every visual outcome needs operator eyes-on sign-off before
  any status upgrade.
- No live-config hot-swap in the bridge (commit → restart-required stands).
- No multi-device/multi-target orchestration beyond what `target_override` already does; the pad
  drives the single realtime-enabled target the config defines.
- Template Lab does not auto-promote; promotion is always an explicit agent+operator pipeline
  with tests and contracts.
