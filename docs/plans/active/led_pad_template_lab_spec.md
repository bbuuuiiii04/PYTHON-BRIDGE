---
doc_status: current
truth_level: implementation-spec, code-grounded (citations verified at 4077794)
last_verified_commit: 4077794
last_verified_date: 2026-07-03
validation_scope: spec only until phases land; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Codex Implementation Spec — LED Pad + Template Lab (AWR-113)

Authoritative design + rationale: `docs/architecture/led_pad_template_lab_design.md` (read §3–§8
before Phase 1). This spec is the execution contract. Implement **only the phase named in the
operator instruction you were given**, in task order, then stop and report.

## Phase status (update this table when a phase lands)

| Phase | Scope | Status |
|---|---|---|
| 0 | Bridge prep: param value validation, gitignore, contract | implemented/software-tested |
| 1 | LED Pad MVP: controls module, playback engine, web server + UI, launcher, tests, docs | implemented/software-tested |
| 2 | Template Lab: /lab route, lab loader/registry, skill file, tests, docs | pending |
| 3 | Locked Palette + renderer param unlocks | pending |

---

## Part A — Context & hard facts (verified; read, do not re-derive)

- [confirmed] Any LED config error disables ALL LED (`led_config.py:118-124`); an un-allowlisted
  static param key on a look is such an error (`led_config.py:409-412`). Every pad write path
  must validate with `load_led_look_director_config_from_dict` before persisting; Commit must
  refuse to write live config on any error.
- [confirmed] `LEDLookDirector` automation reads only `banks["default"]`
  (`led_look_director.py:59,194,269`). Looks absent from `banks.default.*` role lists are
  automation-invisible.
- [confirmed] Standalone playback pattern (production runner + synthetic BeatAnchor, no bridge,
  no Rekordbox): `scripts/direct_rt_groove_chase.py:55-96`. Reuse this shape.
- [confirmed] Runner semantics: color-sig params (`_COLOR_SIG_KEYS`,
  `govee_realtime_runner.py:22-29`) update in place; any other param/effect/seed/sync change
  reconfigures from local beat 0 (`govee_realtime_runner.py:303-324,449-454`). BPM lives in the
  BeatAnchor → tempo changes never restart. Runner accepts injected `time_fn`/`sleep_fn`
  (`govee_realtime_runner.py:52-70`).
- [confirmed] Ownership levers: JSONL commands `led_blackout`/`led_clear_blackout`
  (`runtime_status.py:405-446`) — the blackout path emergency-stops the bridge's realtime runner
  and force-releases its owner machine (`led_dispatch_coordinator.py:63-67`). The command reader
  seeks to EOF at startup, so commands written while the bridge is down never replay
  (`runtime_status.py:312-313`). Bridge liveness: `/tmp/rb_ss_bridge_v2_status.json` with a 5 s
  staleness rule (`tools/laser_pad_web.py:428-446`, `STATUS_PATH` from `runtime_status.py:16`).
- [confirmed] Server pattern to mirror: `tools/laser_pad_web.py` (ThreadingHTTPServer, service
  under one `Lock`, JSON routes, static assets dir, atomic save with `.bak-<µs>` backups via
  `save_config_atomically`, history list/diff/restore), launcher `scripts/laser_pad.py`.
- [confirmed] 54 realtime render names = `REALTIME_EFFECT_NAMES`
  (`govee_frame_renderer.py:1825`); param allowlists `REALTIME_EFFECT_PARAM_KEYS`
  (`govee_frame_renderer.py:972-996,1842-1864`); strobe set `REALTIME_STROBE_EFFECTS`; slot cues
  `SLOT_EFFECTS` (`govee_frame_renderer.py:1796-1811`); descriptions `EDM_BUILDS`
  (`govee_frame_renderer.py:900-930`).
- [confirmed] Engine color injection: `LedColorEngine.resolve_color` / `resolve_slot_colors`
  with `set_palette(name)` + `lock()` for deterministic palette selection
  (`led_color_engine.py:507-733`); slot output is always 6 slots, slot 5 pure white.
- [assumed — hardware-unvalidated] Razer deactivate returns the strip to its pre-activation
  state. Never claim otherwise in UI copy or docs; say "releases the strip".

## Part B — Tasks

### Absolute rules (all phases)

- Out of scope, do not touch: `state_manager.py`, `__main__.py`, `led_look_director.py`,
  `led_dispatch_coordinator.py`, `govee_realtime_runner.py`, `govee_realtime_transport.py`,
  `beat_sync_engine.py`, `govee_scene_adapter.py`, `govee_runtime_sender.py`, all laser/*,
  soundswitch/*, rekordbox-reader, smart-phrasing, and streamdeck modules, and all existing
  tests except where a task names them. Phase 3 additionally opens exactly:
  `led_models.py`, `led_config.py`, `led_color_engine.py`, `govee_frame_renderer.py`.
- Behavior that must not change: bridge automation selection/rotation; rendering of existing
  looks (frame-identical when new params are absent); loading of every currently-valid config;
  `python3 -m unittest discover tests` green throughout.
- Error handling: fail closed and surface. No broad try/except in service logic; the HTTP layer
  returns `{"ok": false, "error": "<real message>"}` (Laser Pad handler pattern). Playback
  errors stop playback and surface; never retry silently, never fall back to fake success.
- The pad never imports `govee_runtime_sender.py`, never reads `GOVEE_API_KEY`, never sends
  Govee cloud commands.
- No secrets, IPs, or device IDs in code, tests, or docs. Never commit
  `config/led_look_director.json`, `config/led_look_director.draft.json`, or `config/led_lab/`.
- Dirty worktree: never revert files you did not create; no destructive git.
- Work directly on `main`. Commit at the end of the phase with a message naming the phase.

### Phase 0

**Task 0.1 — `led_config.py`: value-validate slot-cue numeric params.**
In `_validate_realtime_params`, validate `burst_beats`, `breath_beats`, `drift_beats` as
finite numbers > 0 (same shape as the existing `travel_beats`/`width` block at
`led_config.py:550-554`). Extend `tests/test_led_config.py`: one rejecting case per key (string
value → error message names the key) and one accepting case (valid numbers load).

**Task 0.2 — `.gitignore`:** add `config/led_look_director.draft.json` and `config/led_lab/`.

**Task 0.3 — contracts.** Add contract key `led_pad` to `docs/agents/change_contracts.yml` and
the human table in `docs/agents/change_contracts.md`: code globs `tools/led_pad_web.py`,
`tools/led_pad_playback.py`, `tools/led_pad_lab.py`, `tools/led_pad_assets/**`,
`scripts/led_pad.py`, `led_pad_controls.py`; docs_update `docs/guides/led_pad.md`,
`docs/subsystems/led_govee.md`, `docs/architecture/doc_index.md`,
`docs/status/active_work_registry.md`. Match the existing YAML schema exactly (copy an existing
entry's field set). If the checker requires listed docs to exist, create
`docs/guides/led_pad.md` as a stub with the standard frontmatter and a "populated in Phase 1"
line.

### Phase 1

**Task 1.1 — `led_pad_controls.py` (new module at repo root, pure, no I/O).**
- `CONTROL_META: dict[str, dict]` — one entry per param key that appears in any
  `REALTIME_EFFECT_PARAM_KEYS` value. Fields: `label` (operator wording, Part U §U6 table),
  `kind` (`"number" | "int" | "bool" | "choice" | "rgb"`), `min`, `max`, `step`, `choices`,
  `help` (one sentence), `advanced` (bool), `color_sig` (bool — True iff key ∈ runner
  `_COLOR_SIG_KEYS`). Ranges must match `_validate_realtime_params` exactly; where the
  validator has no upper bound, choose a sane slider max but allow numeric entry beyond it
  (input clamps only to validator rules).
- `RENDER_GROUPS: dict[str, tuple[str, ...]]` — exactly the six groups and memberships in the
  design doc §5.1 (enumerate all 54 names literally). Module-level assert:
  `set(itertools.chain.from_iterable(RENDER_GROUPS.values())) == set(REALTIME_EFFECT_NAMES)` so
  any future renderer addition fails imports loudly in tests (assert under `if __debug__` is
  fine; also covered by a unit test).
- `RENDER_LABELS: dict[str, str]` — humanized names ("rt_groove_chase" → "Groove Chase
  (show-colored)" style per Part U §U6).
- `controls_for(scene_ref: str) -> list[dict]` — ordered control specs (non-advanced first).
- `render_catalog() -> list[dict]` — `{name, label, group, description, slot_based, strobe,
  color_source_capable}` where `description` comes from `EDM_BUILDS` when present,
  `slot_based = name in SLOT_EFFECTS`, `strobe = name in REALTIME_STROBE_EFFECTS`.
- Tests `tests/test_led_pad_controls.py`: catalog covers every `REALTIME_EFFECT_NAMES` member;
  every allowlisted key has metadata; strobe/slot flags match renderer sets; every
  `color_sig=True` key is in the runner's `_COLOR_SIG_KEYS`.

**Task 1.2 — `tools/led_pad_playback.py` (new).**
Class `PadPlayback` composed of pure pieces + a thin transport shell:
- Construction: takes the parsed `LEDConfig`; selects the first target with
  `realtime.enabled` (error surface if none); builds `GoveeRealtimeTransport` exactly as
  `scripts/direct_rt_groove_chase.py:55-63` (or `GoveeRealtimeDryRunTransport` when
  `dry_run=True` is passed by the server flag); builds
  `GoveeRealtimeRunner(transport, GoveeFrameRenderer(), segments=rt.segments, fps=rt.fps)`.
- Synthetic anchor: internal `{bpm: float, playing: bool}` state; beat provider returns
  `BeatAnchor(deck=0, abs_beat_pos=(now-epoch)*bpm/60 integrated across bpm changes, bpm=bpm,
  captured_monotonic=now, playing=True, permitted=True)` while playing else `None`. Integration
  must accumulate at bpm changes (keep `(anchor_beat, anchor_time)` and advance) so tempo
  changes never jump the beat position. Pure class `SyntheticClock` with injected `time_fn`.
- Cue timer: pure `CueTimer` (deadline = start + cue_beats*60/bpm, recomputed on bpm change from
  beats-elapsed) polled by a 100 ms daemon loop; on expiry with loop off → `stop()`.
- Ownership: pure FSM `OwnershipGate` with states `free | bridge_owned | pad_owned`, inputs
  (status-file mtime+content, takeover/release requests, poll ticks). Bridge live = status file
  parses and `time.time()-written_at <= 5.0`. Takeover: append
  `{"cmd":"led_blackout","reason":"led_pad"}\n` to `/tmp/rb_ss_bridge_v2_commands.jsonl`
  (open with `os.O_CREAT|os.O_WRONLY|os.O_APPEND`, mode `0o600` — the pattern at
  `runtime_status.py:641-644`), wait 1.5 s (injected sleep), then allow playback; while
  pad_owned, poll every 2 s and re-append the takeover command if a fresh bridge status appears
  without `led_look_director.emergency_blackout` true; release: `stop()` then append
  `{"cmd":"led_clear_blackout"}\n`. Register `atexit` release. If bridge not live → play
  directly, write nothing.
- Public API: `play(spec: dict, *, cue_beats: float, loop: bool)`, `update(spec: dict)`,
  `set_bpm(float)`, `set_loop(bool)`, `stop()`, `emergency_stop()` (synchronous blackout +
  deactivate + clear desired — mirror `force_deactivate` semantics), `ownership()` and
  `status()` snapshots, `request_takeover()`, `release()`. Spec dict → `EffectSpec` with
  `seed = blake2b(look_name)` (the `_stable_seed` shape from
  `led_dispatch_coordinator.py:19-21`), `sync_mode`/`beat_division` falling back to
  `default_sync_mode`/`default_beat_division`.
- Strobe gate: refuse `play` of a `REALTIME_STROBE_EFFECTS` scene_ref unless the look dict has
  `allow_strobe` true AND draft `safety.allow_strobe` true; error message says which gate failed.
- Tests `tests/test_led_pad_playback.py`: SyntheticClock integration across bpm changes;
  CueTimer stop/loop behavior with fake clocks; OwnershipGate transitions incl. re-assert and
  release (fake file readers/appenders — capture appended lines, no real /tmp writes); strobe
  gate; spec building. All transport via `GoveeRealtimeDryRunTransport` or fakes; zero network,
  zero sleeps.

**Task 1.3 — `tools/led_pad_web.py`, `tools/led_pad_assets/`, `scripts/led_pad.py` (new).**
Mirror the Laser Pad server skeleton (`tools/laser_pad_web.py`): `LedPadService` under one
`Lock`, `_LedPadHandler(BaseHTTPRequestHandler)`, `_GET_ROUTES`/`_POST_ROUTES` dicts, static
assets under `/static/`, loopback default, port **8766**.

Service state: `self._draft: dict` loaded from `config/led_look_director.draft.json` when
present else from live `config/led_look_director.json` (via `RBSS_LED_CONFIG` resolution:
reuse `led_config._resolve_path`); every mutating route atomically rewrites the draft file.
Draft-vs-live dirty computation: normalized (`json.dumps(..., sort_keys=True)`) per-look compare
plus `_pad_meta`/bank-membership compare → `{global: bool, banks: {bank: bool}, looks: [names]}`.

Bank model: pad banks = the 8 role lists of `banks.default` plus the pad-only drafts list at
`_pad_meta.drafts` (root-level `_pad_meta` object in the same JSON). Invariant enforced on every
mutation: a look name appears in exactly one of those 9 lists. `safe_default` and `blackout`
looks: undeletable, unmovable. Looks referenced by `drop_pairs`: undeletable (error names the
pair). `pre_drop` and unknown-bank memberships surface under the `other` pseudo-bank (read-only
chip in UI).

Routes (`/api/...`), all JSON:
- `GET config` → `{config: draft, errors, warnings, dirty}` (validate via
  `load_led_look_director_config_from_dict` on every call).
- `GET renders` → `render_catalog()` plus `controls_for` per render.
- `GET palettes` → palette names from draft `color_engine.palettes` (engine absent → `[]` +
  warning string).
- `POST look/save` `{name, look: {...}, params: {...}, cue_beats, slot_fill, mono_chance}` —
  merge into `draft.looks[name]`, `color_engine.slot_fill_strategy_by_look[name]`,
  `color_engine.slot_mono_chance_by_look[name]`, `_pad_meta.looks[name].cue_beats`; validate;
  persist; return `{ok, errors, warnings, dirty}`. Reject unknown param keys for the chosen
  scene_ref *before* merging (use `REALTIME_EFFECT_PARAM_KEYS`).
- `POST look/duplicate` `{source, new_name}` — deep copy look + per-look engine keys + pad meta;
  new look joins `_pad_meta.drafts`; name must be a new, non-empty, `[a-z0-9_]+` identifier.
- `POST look/move` `{name, bank}` — bank ∈ the 8 roles ∪ `drafts`; enforce invariant; validate
  (a realtime look moved to `utility` must fail with the loader's own error).
- `POST look/delete` `{name}` — guards above; removes from banks/looks/engine keys/pad meta.
- `POST play` `{name, editor?: {params, look, cue_beats}, takeover: bool}` — editor state wins
  over draft when provided. Color injection when `look.color_source == "engine"`: build
  `LedColorEngine(ColorEngineConfig from draft)` (fresh instance, `set_seed=0` for determinism),
  `set_palette(session.test_palette)`, `lock()`, then `resolve_slot_colors(role=<bank>,
  section_id="led_pad", cycle=0, look_name=name, color_source="engine")` when
  `scene_ref in SLOT_EFFECTS` else `resolve_color(...)`; merge injection into spec params.
  Ownership: if bridge-owned and `takeover` false → HTTP 200 `{ok:false,
  error:"ownership_required"}`; with `takeover` true → `request_takeover()` then play.
- `POST update` — same param pipeline, `PadPlayback.update` only (no ownership change).
- `POST stop`, `POST emergency_stop`.
- `POST session` `{bpm?, test_palette?, loop?}` — persist under `_pad_meta.ui`; bpm →
  `set_bpm`; test_palette while playing → re-resolve colors and `update`; loop → `set_loop`.
- `POST commit` — validate; on errors return them and DO NOT write; on success atomic-write
  live config with `led_look_director.json.bak-<µs>` backup (port `save_config_atomically`'s
  pattern from `tools/laser_config_ops.py`), then reset draft file to committed content. Reply
  includes `restart_note: "Committed — bridge restart required to take effect live."`
- `POST discard` — reload draft from live config, delete draft file.
- `GET history`, `GET history/<name>/diff`, `POST history/<name>/restore` — Laser Pad
  equivalents against `led_look_director.json.bak-*` (restore → draft only).
- `GET runtime_status` — bridge status-file summary + `{ownership, playing_look, playback:
  PadPlayback.status()}`.
- `GET /` serves `index.html`; `GET /lab` serves `lab.html` (Phase 2; in Phase 1 return 404).

Frontend: implement Part U exactly (files: `index.html`, `pad.css`, `pad-core.js`,
`pad-ui.js`; vanilla JS, no frameworks, no build step, fetch-based, ES2020 fine).

`scripts/led_pad.py`: argparse launcher mirroring `scripts/laser_pad.py`
(`--host/--bind/--port/--config/--dry-run`, default `127.0.0.1:8766`; `--dry-run` forces the
dry-run transport regardless of config).

**Task 1.4 — service tests `tests/test_led_pad_service.py`.**
Tmpdir configs (copy `config/led_look_director.example.json` as the live fixture). Cover: draft
load/persist round-trip; exactly-one-bank on move/duplicate/delete; safe_default/blackout/
drop_pairs guards; unknown-param rejection on save; commit-blocks-on-invalid (inject bad param
straight into draft dict, assert live file byte-unchanged); commit writes backup + resets draft;
discard; dirty computation (global/bank/look); play spec building (engine slot look → exactly 6
slot_colors, slot 5 == [255,255,255]; deterministic across calls with same session palette);
`ownership_required` reply; session persistence. Use the service class directly (no HTTP), plus
one thin HTTP smoke test using `http.client` against a server on an ephemeral port with
`--dry-run` semantics.

**Task 1.5 — docs.** Populate `docs/guides/led_pad.md` (launch, capabilities, ownership/
takeover protocol + recovery one-liner `{"cmd":"led_clear_blackout"}`, commit→restart note,
software-only status). Update `docs/subsystems/led_govee.md` (pad exists; where; contract
pointer), `docs/architecture/doc_index.md` guide row, `docs/status/active_work_registry.md`
AWR-113 phase status. Update the Phase status table in THIS spec. Run all four check tools.

### Phase 2

**Task 2.1 — `tools/led_pad_lab.py` (new).**
- `LabRegistry` over `config/led_lab/drafts.json`: entries `{name, kind: "slot"|"frame",
  fn, params, cue_beats, notes, brief, status: "iterating"|"accepted"|"rejected", created,
  updated}`; atomic writes; create dir `0o700` on first use; name rules: `[a-z0-9_]+`, must NOT
  collide with `REALTIME_EFFECT_NAMES` and is always played as scene_ref `lab_<name>`.
- `load_lab_effects(path) -> {"ok": bool, "effects": dict[str, callable], "error": str,
  "traceback": str}` via `importlib.util.spec_from_file_location` + fresh exec on every call
  (hot reload). The module contract: top-level callables matching `EffectFn`/`SlotEffectFn`
  signatures; a top-level dict `LAB_EFFECTS = {"name": (kind, fn)}` is the registration surface.
- `LabRenderer`: wrapper used ONLY by the pad playback path — resolves `lab_*` scene_refs from
  the loaded overlay (slot-kind → MotionField → `universal_colorizer(field, slot_colors)`;
  frame-kind → call directly), everything else delegates to `GoveeFrameRenderer`. Clamp + pad
  frames to segment count exactly like `GoveeFrameRenderer.render`. Never mutate the module
  registries `_EFFECTS`/`SLOT_EFFECTS`.
- Playback: `PadPlayback` gains an optional `renderer` constructor arg (default
  `GoveeFrameRenderer()`); the server passes the `LabRenderer` so both pad and lab playback run
  through one playback slot. Lab plays resolve colors like any engine slot look (Test Palette
  placeholder colors).
**Task 2.2 — `/lab` route + UI** per Part U §U8 (`lab.html`, `lab.js`, shared `pad.css`).
Draft CRUD (create metadata entry, edit brief/notes/cue_beats/params JSON textarea), Play/Stop
(shared slot — playing a lab draft stops pad playback and vice versa), "Reload code" button
(re-import + report), error/traceback panel, Accept/Reject status buttons, promotion checklist
panel (static text per design doc §6.4).
**Task 2.3 — `.claude/skills/template-lab/SKILL.md`**: create with the exact content of design
doc §7's fenced skill block (adjust only formatting needed for a valid skill file).
**Task 2.4 — tests `tests/test_led_pad_lab.py`.** Registry round-trip + name-collision
rejection; hot reload picks up an edited temp module; broken module → structured error (server
survives); LabRenderer: lab slot draft renders via colorizer with slot-5 white, unknown lab name
fails dark, production names untouched; playback-slot exclusivity (lab play preempts pad play).
Docs: lab section in `docs/guides/led_pad.md`; spec phase table; registry row; checks.

### Phase 3

**Task 3.1 — `led_models.py`:** add `locked_palette_by_look: Dict[str, str] =
field(default_factory=dict)` to `ColorEngineConfig`.
**Task 3.2 — `led_config.py`:** validate `color_engine.locked_palette_by_look` is an object of
`look_name -> palette name` where the palette exists in `color_engine.palettes` (error text
names the look); parse it in `_parse_color_engine`.
**Task 3.3 — `led_color_engine.py`:** in `resolve_color` AND `resolve_slot_colors`, when
`look_name in self._config.locked_palette_by_look` (and that palette exists), resolve using
that palette's full p-interval as the focus window and that palette's `white`, leaving ALL
journey state (current palette, dwell, focus, RNG streams) untouched. The per-cue/per-fill RNG
seeding stays identical in shape.
**Task 3.4 — `govee_frame_renderer.py` param unlocks (defaults = current constants, frame-parity
when absent):** `rt_groove_chase`/`rt_groove_nebula` read `loop_beats` (default 4.0);
`rt_drop_chase`/`rt_post_drop_chase`/`rt_drop_nebula`/`rt_post_drop_nebula` read `travel_beats`
(default 2.0) and `width` (default 0.8); `groove_center_chase`/`post_drop_firework_chase` read
`travel_beats` (default 1.0). Allowlist additions: `loop_beats` for the two groove rt cues.
`led_config.py`: validate `loop_beats` > 0.
**Task 3.5 — pad editor:** enable Automation Color fully (Locked Palette radio + palette select
writes/clears `color_engine.locked_palette_by_look[look]` through look/save; pad playback of a
locked look uses its locked palette and ignores Test Palette).
**Task 3.6 — tests.** Engine: locked look resolves deterministically from the locked palette
while an unlocked look on the same engine instance still follows the journey palette; absent
mapping → byte-identical outputs vs a control engine (same `set_seed`). Renderer: for each
unlocked param, params-absent output equals pre-change recorded frames (write the parity test
by rendering with `{}` and with the explicit default and asserting equality, plus a
changed-value test asserting difference). Config: locked-palette validation negative/positive.
Docs: led_govee card param table, config docs, spec phase table, registry; checks.

---

## Part U — UI design spec (authoritative; implement, don't reinterpret)

Design intent: a dark, high-contrast rehearsal tool that reads at a glance from a DJ booth or
couch — banks first, one always-visible transport/session bar, unmistakable ownership and dirty
states, zero decorative chrome. Every interactive target ≥ 40×40 px (iPad on LAN is a
first-class user, per Laser Pad precedent).

### U1. Tokens (put verbatim in `pad.css` `:root`)

```css
:root {
  --bg: #0e1116;         /* page */
  --surface: #151b23;    /* cards, bars */
  --surface-2: #1d2530;  /* drawer, modals, inputs */
  --border: #2a3441;
  --text: #e6edf3;
  --text-dim: #9aa7b4;
  --accent: #35b6ff;     /* primary actions, focus */
  --accent-ink: #062033; /* text on accent */
  --play: #3fd68f;       /* playing state */
  --warn: #e8b13f;       /* dirty, bridge-owned */
  --danger: #f25f5c;     /* destructive, emergency */
  --lab: #b48cff;        /* Template Lab identity */
  --radius: 10px; --radius-sm: 6px;
  --gap: 12px; --pad: 16px;
  --font: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --mono: ui-monospace, SFMono-Regular, Menlo, monospace;
}
```

Type scale: 20px/600 page title, 16px/600 section headers, 14px/400 body, 12px/400 meta.
Focus: `:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }` on ALL
interactive elements. `@media (prefers-reduced-motion: reduce)` disables the playing-pulse
animation (state stays visible via the solid LIVE chip).

Bank hue ticks (3px left border on tab + card): drafts `--lab` **dashed**, ambient `#4cc9c0`,
groove `#35b6ff`, buildup `#e8b13f`, drop `#f25f5c`, post_drop `#b48cff`, breakdown `#6f9bd1`,
utility `#8b98a5`.

### U2. Page shell (both routes)

Sticky **top bar** (two rows on <900px, one row otherwise):
- Left: title "LED Pad" (or "Template Lab" with a `--lab` badge), route tabs `Pad · Lab`.
- Center (session controls, shared state across routes): **BPM** (number input 60–200 step 1 +
  `−/+` steppers), **Palette** (`<select>` of palette names, label "Test Palette"), **Loop**
  (toggle switch with visible on/off label).
- Right: **ownership pill** — `Free` (gray) / `Bridge owns LEDs` (amber) / `Pad owns LEDs`
  (green) — with adjacent button `Take over` / `Release` as applicable; then **STOP** button
  (danger-outline, square icon ■, `aria-label="Emergency stop"`, always enabled). Emergency
  stop is never more than one click/tap away and never inside a menu.

Second sticky row (Pad route): **bank tabs** in fixed order Drafts, Ambient, Groove, Buildup,
Drop, Post-Drop, Breakdown, Utility (+ conditional read-only "Other" chip when pre_drop/unknown
memberships exist). Each tab: name + count + amber dirty dot when the bank has uncommitted
looks. Right-aligned: `Commit` (primary, shows count badge "n") and `Discard` (ghost) — both
with confirm modals.

### U3. Look cards

Responsive grid (`repeat(auto-fill, minmax(240px, 1fr))`, gap `--gap`). Card = `--surface`,
radius `--radius`, bank hue tick, padding `--pad`:

```
┌─────────────────────────────┐
│ groove_nebula_a        ● (dirty, amber, title-row right)
│ Groove Nebula · show-colored ⚡   (renderer label + badges, 12px dim)
│ 16 beats                     (cue chip)
│ [▶ Play]  ✎  ⧉  ⇄  🗑        (footer)
└─────────────────────────────┘
```

- Badges: `⚡ strobe` (amber outline) when strobe-classed; `show-colored` (small 5-stop gradient
  dot) vs `fixed colors` (gray dot); `☁ cloud` (dim) for non-realtime looks.
- Playing card: 2px `--play` border + pulsing glow (reduced-motion: static border) + `LIVE`
  chip; the previous playing card reverts automatically.
- `▶ Play` = filled accent button (≥40px). `✎ Edit`, `⧉ Duplicate`, `⇄ Move`, `🗑 Delete` =
  icon buttons with `aria-label` + `title`; Delete is `--danger` on hover only.
- Cloud looks: Play disabled with tooltip "Cloud scene — not previewable in the pad".
- Duplicate → inline name prompt (pre-filled `<source>_copy`), lands in Drafts, opens editor.
- Move → popover with the 8 banks as radio list; immediate on select (no confirm; validator
  errors toast + revert).
- Empty bank: dim message. Drafts: "New looks land here. Automation never plays drafts."

### U4. Editor drawer

Right-side drawer, 420px (100% overlay <720px), `--surface-2`, slides in 150ms, `role="dialog"`
`aria-label="Look editor"`. Structure top→bottom:

1. **Header**: look name (16px/600), renderer registry name (12px `--mono` dim), `LIVE` chip
   when playing, close ✕ (= Cancel semantics).
2. **Transport row** (sticky under header): `▶ Play` / `■ Stop` (state-swapped), **Cue Length**
   segmented control `4 · 8 · 16 · 32 · ✎` (✎ = free numeric input), hint text
   "Loop is {on|off} (session)".
3. **Renderer** section: grouped `<select>` (optgroups = the six groups); description line under
   it (from catalog). Changing renderer keeps only params valid for the new renderer (drop the
   rest silently in the editor state; Save persists the pruned set) and restarts playback.
4. **Color** section: `Automation Color` segmented control [`Follow Show Color` | `Locked
   Palette`] — Phase 1: Locked disabled with tooltip "Coming with Phase 3"; Phase 3: enabled +
   palette `<select>`. Below: `Brightness` slider 0–100 + numeric readout; `Strobe allowed`
   toggle — disabled with reason text when `safety.allow_strobe` is false; when the renderer is
   strobe-classed and strobe is off, Play is blocked with inline text (server enforces too).
5. **Slot colors** section (slot-based renderers only): `Slot Fill` select — labels: `Even
   gradient`, `Random per slot`, `Random with solid chance`; `Solid chance` slider 0–1 step 0.05
   (visible only for the third option). Never mention slot counts; slot 5/white is invisible
   here by design.
6. **Motion Pattern** section: the renderer's non-advanced controls from `controls_for`, each as
   label + control + numeric readout on one 40px row (sliders for bounded numbers, steppers for
   ints, switches for bools, selects for choices). **Advanced motion** `<details>` holds
   `advanced: true` controls (`sync_mode`, `beat_division`, `heads`, `max_pulses`,
   `spawn_on_wrap`, `reverse`, `trail_beats`…).
7. **Sticky footer**: `Save` (primary, disabled when clean), `Undo` (reverts to last
   Save/open snapshot; confirm modal), `Cancel` (ghost; dirty → confirm modal), dirty text
   "Unsaved changes" (amber) / "Saved" (dim).

Live-apply contract: while playing, any control change → debounce 150 ms → `POST update`.
Color-sig controls (per `CONTROL_META.color_sig`) + Test Palette changes update seamlessly;
everything else visibly restarts from beat 0 — add a subtle "restarted" flash on the LIVE chip
so the restart reads as intentional. Editor-open state is the tuning buffer: Play uses editor
state, Save persists it, Cancel discards it.

Switching cards with a dirty editor → 3-way modal: `Save & switch` / `Discard & switch` /
`Stay`.

### U5. Modals, toasts, errors

- Confirm modals (Commit / Discard / Delete / Undo / dirty-Cancel): title, one consequence
  sentence ("Discard reloads the live config and deletes your draft changes — 3 looks
  affected."), destructive button in `--danger`, cancel is the default focus. Esc = cancel.
- Commit success toast: "Committed ✓ — bridge restart required to take effect live."
- Errors: persistent dismissible banner (not toast), loader messages verbatim in `--mono`.
- Ownership dialog on `ownership_required`: "The bridge owns the LEDs right now. Take over?
  LEDs go dark on the bridge side until you release." [Take over] [Cancel].

### U6. Operator wording (bind to `CONTROL_META` labels)

`travel_beats`→Motion Beats · `loop_beats`→Motion Beats (loop) · `breath_beats`→Breath Beats ·
`burst_beats`→Burst Beats · `drift_beats`→Color Drift Beats · `duration_beats`→Cycle Beats ·
`width`→Head Width · `trail_beats`→Trail Beats · `trail`→Trail Length · `heads`→Comet Count ·
`span_beats`→Span Beats · `period_beats`→Breath Beats · `floor`→Minimum Glow ·
`density`→Sparkle Density · `duty`→Strobe Duty · `subdivision`→Strobe Rate · `speed`→Sweep
Speed · `decay`→Fade Decay · `sync_mode`→Sync Mode · `beat_division`→Beat Division ·
`max_pulses`→Max Comets · `spawn_on_wrap`→Spawn on Loop Wrap · `reverse`→Reverse Direction.
Never render the string "render params" anywhere; sections say "controls".

### U7. Accessibility checklist (acceptance-gating)

Contrast ≥ 4.5:1 for text (tokens above satisfy this); every icon button has `aria-label`;
drawer traps focus and returns it to the invoking card on close; Esc closes drawer via Cancel
path; all controls keyboard-operable (native inputs only — no div-sliders); state never encoded
by color alone (dirty = dot + "Unsaved changes" text; ownership pill has text; strobe badge has
the word); `prefers-reduced-motion` respected; touch targets ≥ 40px.

### U8. Template Lab route (`/lab`)

Same shell + session bar; `--lab` accent replaces `--accent` for primary actions; cards/panels
get dashed borders — the page must be unmistakably "not production". Two-pane layout (stacked
<900px): left = draft list (rows: name, status pill `iterating`/`accepted` (green)/`rejected`
(gray-struck), updated date); right = detail panel: `brief` (textarea), `notes` (textarea),
kind + function name (read-only `--mono`), `params` JSON textarea (validated on blur), cue
length segmented control, `▶ Play`/`■ Stop`, `⟳ Reload code`, Accept / Reject buttons,
collapsible error panel (`--danger` border, `--mono`, full traceback), and a static "Promotion
checklist" panel (from design §6.4). Lab playback shares the ownership rules and the LIVE
indicators of the pad.

---

## Part C — Invariants that MUST still hold

1. No bridge-process code changes in Phases 1–2 beyond Phase 0's validator; StateManager and
   the 200 Hz push loop untouched; nothing in the pad imports lab code into the bridge.
2. Pad Commit can never write a config `load_led_look_director_config` rejects.
3. No draft/lab identifier ever enters `banks.default.*`, `drop_pairs`, `safe_default`, or
   `blackout`.
4. Single razer streamer: pad output only when bridge is absent or explicitly stood down via
   `led_blackout`; release on stop/exit (`atexit`); poll + re-assert while owning.
5. Existing looks render frame-identically when new params are absent (Phase 3 parity tests).
6. Strobe playback obeys `look.allow_strobe && safety.allow_strobe` in the pad exactly as the
   loader enforces for automation.
7. Secrets/IPs/device IDs never in code, tests, docs, or committed config; gitignored files stay
   gitignored.

## Part D — Tests

Per-task lists above are the contract. All algorithmic logic (clock, cue timer, ownership FSM,
bank invariant, control metadata, lab overlay, locked-palette resolution) must be testable with
no sockets, no real `/tmp`, no sleeps (inject `time_fn`/`sleep_fn`/writers). Phase gate:
`python3 -m unittest discover tests`.

## Part E — Acceptance (per phase)

1. `python3 -m unittest discover tests` green (record count).
2. `python3 tools/check_docs_metadata.py && python3 tools/check_agent_contracts.py && python3
   tools/check_docs_drift.py` green; `python3 tools/check_docs_staleness.py --report` reviewed.
3. Contract `led_pad` docs_update satisfied; Phase status table in this spec updated.
4. Phase 1+: dry-run smoke — `python3 -m rb_ss_bridge_v2.scripts.led_pad --port 8766
  --dry-run` (background), then `curl` `/api/config`, `/api/renders`, `POST /api/play` for an
  `rt_*` look, `/api/runtime_status` shows `frame_index` advancing, `POST /api/stop`; kill the
  server. Record the outputs in the report.
5. Status language: `implemented` / `software-tested` at most.

## When you finish (each phase)

Report: files changed; tests/checks run with real output; the dry-run smoke transcript
(Phase 1+); deviations from this spec (if any, with reason); open risks. Plain-language operator
summary: what works now, what needs a bridge restart, what remains hardware-unvalidated.
Then commit on `main`: `LED Pad phase <N>: <one-line scope> (AWR-113)`.
