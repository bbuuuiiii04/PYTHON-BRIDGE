---
doc_status: current
truth_level: implementation-spec
last_verified_commit: 17ba826
last_verified_date: 2026-07-10
validation_scope: >
  AWR-193 (pad lane, 00:05 wave) — LED Pad + Template Lab overhaul. Authored from
  current-code inspection at 17ba826: every file:line below was read at HEAD on
  2026-07-10 by the pad-lane manager. All ten defects were live-verified by the
  operator/executive on 2026-07-09 night (dispatch brief
  docs/prompts/active/pad_overhaul_brief_2026_07_10.md); the mechanisms were
  independently re-derived from code before this spec was written. No code
  implemented at authoring time. SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.
---

# Codex Implementation Spec — LED Pad / Template Lab overhaul (AWR-193)

Contract key: `led_pad` (docs/agents/change_contracts.yml). Executes the operator
orders: "the LED Pad … shouldn't EVER be outdated" + "the Template Lab is INCREDIBLY
unintuitive and inefficient." The ten defects below are the acceptance list — all ten
were reproduced live at the executive desk on 2026-07-09 night.

## Part A — Context, root causes, design decisions (verified; read, do not implement)

The pad server (`tools/led_pad_web.py`, stdlib ThreadingHTTPServer on :8766) serves
two pages from `tools/led_pad_assets/`: the Pad (index.html + pad-ui.js, edits
`config/led_look_director.json` via a draft file) and the Template Lab (lab.html +
lab.js, authors draft effects in `config/led_lab/drafts.json` + `effects_lab.py` via
`tools/led_pad_lab.py`). Playback goes through `tools/led_pad_playback.py`
(`PadPlayback`, ownership gate vs the bridge). It is launchd-supervised
(`launchagents/com.bbui.led-pad.plist`, KeepAlive/SuccessfulExit=false → relaunches
on NON-ZERO exit only). All claims below [confirmed] at 17ba826 unless labeled.

| # | Defect (operator-verified) | Root cause at HEAD | Design decision |
|---|---|---|---|
| 1 | Accept ≠ what you hear | `lab_accept` (tools/led_pad_web.py:603-604) only flips status via `LabRegistry.set_status`; the audited sound is `entry.params` merged with live UI params at play/update time (`_lab_play_spec`, led_pad_web.py:624-626) — server never snapshots what actually played | Accept-what-you-hear: service records the last APPLIED pre-injection params per draft; Accept writes them into the entry in the same save that flips status. UI gets a dirty chip (editor vs saved). |
| 2 | Preview silently saves first | lab.js:214 `previewDraft()` runs `await save()`; a save failure (e.g. defect 3's collision) aborts Preview; lab_preview already accepts a `params` overlay (led_pad_web.py:696-698) that lab.js never sends | Decouple: Preview posts current editor params/cue directly, no implicit save. Where save-first stays (Play), its failure is surfaced as "Save failed: …". |
| 3 | Promotion never retires the draft | `LabRegistry._validate_name` (tools/led_pad_lab.py:151-156) rejects names in `REALTIME_EFFECT_NAMES`; `set_status` routes through `save()` → `_validate_entry` → same check (led_pad_lab.py:106-111,158-165), so promoting an effect under its draft name bricks that draft's Save/Accept/Reject. LIVE NOW: drafts `buildup_balloon_comet` and `drop_firework_explosion` collide with production names (config/led_lab/drafts.json vs RENDER_GROUPS, led_pad_controls.py:179,196) | Collision check applies to NEW names only (create/rename); existing entries always save. New status `promoted` + `/api/lab/archive`; server flags collisions in `lab_list`; UI offers one-tap "Archive draft". |
| 4 | `fn` field dead in lookup | Entries store `fn` (led_pad_lab.py:88, validated :162) but play/preview/render resolve by NAME: led_pad_web.py:622-623 (`name not in effects`), :694-695, led_pad_lab.py:242 (`effects.get(text.removeprefix("lab_"))`). Field evidence: per-name wrappers + aliases in config/led_lab/effects_lab.py:591-631 exist only to work around this | Resolve name-first, `fn`-fallback (preserves every current rendering; renamed drafts start working). Validation checks `fn` resolvable, not name. |
| 5 | Triple-source param bounds | Renderer clamps (govee_frame_renderer.py, physics), `CONTROL_META` min/max (led_pad_controls.py:54-111), per-draft `param_specs` (led_pad_lab.py:128-149) — three copies; tonight two moved, the stale third floored the operator's slider | For any spec key that exists in CONTROL_META, CONTROL_META's bounds/label/step WIN (pure function + decorated `lab_list` output). Renderer↔CONTROL_META stays covered by the existing audit tests (tests/test_led_pad_controls.py pattern). Conflicts reported, not silently absorbed. |
| 6 | Raw R/G/B sliders in B-G-R order, no swatches | Color channels are separate `<base>_r/_g/_b` slider specs; drafts.json is written `sort_keys=True` (led_pad_lab.py:36) so the UI renders b,g,r (lab.js:161-178). Pad side: rgb-kind controls are skipped entirely (pad-ui.js:218 `continue`) | Native `<input type="color">` per triplet (lab) / per rgb key (pad) + live swatch. Regime badges: slot-kind lab drafts and engine-colored pad looks mark color controls "palette overrides this in the room" (CONTROL_META already carries `color_sig`, led_pad_controls.py:113-114). |
| 7 | Agent-facing content in operator UI | Promotion checklist hardcoded in lab.html:71-80; raw Traceback `<details>` at lab.html:67-70 | Checklist moves to docs/guides/led_pad.md (agent runbook, + new archive step). Traceback becomes plain-language error banner; full trace only with `?dev=1`. |
| 8 | Unlabeled controls; Delete next to Accept | Cue row 4/8/16/32 has no visible label (lab.js:77-82, lab.html:54); Delete sits in the same action row as Accept (lab.html:59-61). Both deletes ARE already confirm-gated (lab.js:262, pad-ui.js:140) — keep the gates, fix layout/labels | Visible "Cue length (beats)" label; Delete moves out of the Accept/Reject row into a separated danger area. |
| 9 | Page corpses on server restart | One `refresh()` at load; 2s polls either reject unhandled (lab.js:281-282) or swallow errors (pad-ui.js:367); no reconnect, no state refetch after the server returns | Shared reconnect helper: consecutive poll failures → "reconnecting" banner + backoff; first success after downtime → full `refresh()` + banner clear. Both pages. |
| 10 | Stale by construction | (a) Catalog surface (`REALTIME_EFFECT_NAMES`, `CONTROL_META`, …) is import-time module state; the launchd process outlives code changes — tonight's running pad predated the evening's effects. (b) `_load_initial_draft` (led_pad_web.py:237-244) prefers a stale draft file over moved live config, silently. (c) Browsers may cache assets | (a) Freshness watchdog: mtime watch over the explicit module list; restart (exit 3 → launchd relaunch) ONLY when playback idle and pad does not own the LEDs; UI heals via defect-9 reconnect. (b) live-fingerprint sidecar → `live_changed` banner + guarded Apply. (c) `Cache-Control: no-cache` on all responses. Freshness contract pinned by tests. |

Rejected alternatives: hot `importlib.reload` of the renderer web (fragile shared
singletons; restart-when-idle is deterministic and launchd already supervises);
auto-merging a stale draft with moved live config (silent data loss risk — surfacing
+ one-tap discard is honest); server-computed per-play `overridden_keys` for the
color-regime badges (the static rule — slot-kind lab drafts and engine-colored looks
are palette-fed — matches the injection mechanics at led_pad_web.py:518-549 and needs
no new plumbing).

Integration fence (ledsim): the separate `ledsim` round owns the accurate
room-simulation ENGINE. The preview CONTRACT here — POST `/api/lab/preview` response
`{frames, fps, bpm, beats, segments, slot_colors}` rendered client-side onto a canvas
— is the swap point. Do not change that response shape; do not build any simulation.

## Part B — Tasks (implement exactly, in order; ONE commit per task, explicit paths, never `-a`)

### Absolute rules
- Touch ONLY: `tools/led_pad_web.py`, `tools/led_pad_lab.py`, `led_pad_controls.py`,
  `tools/led_pad_assets/{lab.js,lab.html,pad-ui.js,pad-core.js,pad.css,index.html}`,
  `tests/test_led_pad_service.py`, `tests/test_led_pad_lab.py`,
  `tests/test_led_pad_controls.py`, `.gitignore` (Task 9's one line ONLY), and the
  Part E docs. NOTHING else — explicitly
  out: `govee_frame_renderer.py`, `led_color_engine.py`, `govee_realtime_runner.py`,
  any dispatch/policy/bridge runtime file, `tools/led_pad_playback.py`,
  `scripts/led_pad.py`, `launchagents/*.plist`, `config/**` (INCLUDING
  `config/led_lab/*` — live operator data; migrations happen via UI actions, never
  by editing the data in this round), `tools/laser_pad*`, `streamdeck/**`.
- Behavior that must not change: ownership gate semantics (takeover/release/
  emergency_stop paths), strobe gating (`allow_strobe` plumbing; lab play keeps
  `allow_strobe: False`, led_pad_web.py:633), commit/discard/history semantics,
  the preview response contract above, `_lab_play_spec` name-first resolution for
  entries whose name IS registered in LAB_EFFECTS.
- Error handling: propagate/fail closed/surface. No broad try/except, no
  success-shaped fallbacks, no silent early returns. UI failures must reach the
  error banner, never console-only.
- Do not restart the pad server, the bridge, or any launchd job during the build.
  Staged/tooling-only; activation is the manager's step after the gate.
- An improvement you notice outside these tasks = a NOTE in your report, never an edit.

### Task 1 — `tools/led_pad_lab.py` + web/UI: unbrick collisions, archive flow (defect 3)
- `_validate_name(name, *, check_collision: bool = True)`: the
  `REALTIME_EFFECT_NAMES` check (led_pad_lab.py:155-156) runs only when
  `check_collision`. `save()` passes `check_collision=False` when an entry with that
  name already exists (updates), `True` when creating. `_validate_entry` calls it
  with `check_collision=False` (it validates stored entries).
- Add `"promoted"` to `_STATUSES` (led_pad_lab.py:23). Add
  `LabRegistry.archive(name)` → `set_status(name, "promoted")`.
- `list()` output: decorate each entry (do not persist) with
  `"production_collision": bool` — name or `lab_{name}` in `REALTIME_EFFECT_NAMES`.
- `tools/led_pad_web.py`: service method `lab_archive` + POST route
  `/api/lab/archive`.
- UI (lab.js/lab.html/pad.css): entries with `production_collision` and status not
  `promoted` show a chip "in production" on the list row and a banner in the detail
  panel: "This name is now a production effect — archive the draft." with an Archive
  button (confirm-gated). The Rejected toggle becomes "Archived (n)" covering
  rejected + promoted.
- Failure behavior: archive of unknown name → 400 with the registry's error.

### Task 2 — honor `fn` (defect 4)
- `LabRenderer.__init__` gains `fn_for: Callable[[str], str] | None = None`;
  `render()` (led_pad_lab.py:238-252) resolves
  `found = self.effects.get(key) or self.effects.get(fn_for(key))` (name first, fn
  fallback; `fn_for` errors must not raise out of render — a resolver miss means
  fallback to name-only, i.e. current behavior).
- `LedPadService`: build a non-throwing resolver (registry lookup → entry `fn`, else
  the name itself) and pass it to BOTH LabRenderer constructions
  (led_pad_web.py:214 and :690).
- `_lab_play_spec` (led_pad_web.py:619-623) and `lab_preview` (:694-695): compute
  `fn = str(entry.get("fn") or name)`; registered check becomes
  `name in effects or fn in effects`, error message names both.

### Task 3 — accept-what-you-hear + dirty chip (defect 1)
- Service: `self._last_lab_applied: dict[str, dict[str, Any]] = {}` in `__init__`.
  In `_lab_play_spec`, immediately BEFORE `_inject_engine_colors`
  (led_pad_web.py:628), store `self._last_lab_applied[name] = copy.deepcopy(params)`
  (pre-injection = author params + live UI overrides; palette-injected colors must
  NOT be snapshotted).
- `lab_accept`: fetch the entry; if the draft has a `_last_lab_applied` snapshot,
  set `entry["params"] = snapshot` and save entry with `status="accepted"` in ONE
  `LabRegistry.save` call (no separate set_status round-trip). Response gains
  `"snapshotted": bool`.
- lab.js: dirty chip near Save — compare current editor payload params vs
  `state.current.params` (the pad page's `setDirty` pattern, pad-ui.js:35-40);
  states "Unsaved tweaks" / "Saved". After Accept, `refresh()` (existing) shows the
  snapshotted params. `queueAutoApply` JSON-parse failures surface "Params JSON
  invalid — live apply paused" in the banner instead of silently returning
  (lab.js:151).

### Task 4 — decouple Preview from save; loud save errors (defect 2)
- lab.js `previewDraft()` (lab.js:212-241): remove `await save()`; call
  `api.labPreview({name, params: <current editor params>, cue_beats: cue()})`.
- lab.js `play()` (lab.js:96-118): keep save-first; on save failure show
  `Save failed: <message>` in the banner and abort the play attempt visibly.
- No server change.

### Task 5 — single-source param bounds (defect 5)
- `led_pad_controls.py`: pure function
  `effective_lab_specs(param_specs: dict) -> tuple[dict, list[str]]` — returns
  (decorated specs, conflict keys). For each key in `param_specs` that is also in
  `CONTROL_META`: replace `min`/`max`/`step`/`label` with CONTROL_META's values
  (kind stays from the spec); a key whose stored bounds differ from CONTROL_META's
  goes in the conflicts list. Keys not in CONTROL_META pass through unchanged.
- `tools/led_pad_web.py` `lab_list`: decorate each entry (do not persist) with
  `"effective_param_specs"` and `"spec_conflicts"` via that function.
- lab.js `renderParamControls` (lab.js:161-178) renders from
  `effective_param_specs`; when `spec_conflicts` is non-empty show a one-line note
  "Slider ranges updated from the production controls table".

### Task 6 — color pickers, swatches, regime badges (defect 6)
- lab.js: among slider specs, group complete `^(.+)_(r|g|b)$` triplets → render ONE
  `<input type="color">` row per base (label = humanized base) + a live swatch
  showing the current value; picker writes all three channel params (0-255) and
  routes through the existing `applyParamControl`/auto-apply path. Incomplete
  triplets stay as sliders.
- pad-ui.js `renderControls`/`controlRow` (pad-ui.js:213-253): stop skipping
  `kind === "rgb"`; render a color picker + swatch bound to the `[r,g,b]` list param
  (default handling, reset button, and "default" tag consistent with existing rows).
- Regime badges: in the Lab, when the selected draft's `kind == "slot"`, every color
  picker/slider row gets the badge "palette overrides this in the room" and inert
  styling (controls stay enabled — they still edit the stored params — but the badge
  states the audition truth). On the Pad, when the look's
  `color_source == "engine"`, rgb-kind and `color_sig` control rows get the same
  badge ([confirmed] engine injection overwrites those at play:
  led_pad_web.py:518-549).
- pad.css: swatch, badge, danger-zone, banner styles as needed.

### Task 7 — operator-clean lab surface (defects 7 + 8)
- lab.html: delete the promotion-checklist `<aside>` (lab.html:71-80); its content
  (plus "archive the source draft — Task 1 flow" and the Task 2 fn-resolution note)
  moves into a "Promotion runbook (agent-facing)" section of docs/guides/led_pad.md.
- Traceback: default UI shows a plain-language banner "Your effect code failed to
  load: <first line of the error>" when reload/list reports a failure; the raw
  `<details>` traceback panel renders only with `?dev=1` in the URL.
- Cue row: visible label "Cue length (beats)" (lab.html:54 group + lab.js:77-82;
  same label on the pad editor's cue group, index.html/pad-ui.js:187-201).
- Move Delete out of the Accept/Reject row (lab.html:59-61) into a visually
  separated danger area (e.g. bottom of the detail panel with a divider). Keep the
  existing confirm modal.

### Task 8 — survive restarts (defect 9)
- pad-core.js: shared reconnect helper (e.g. `window.PadHealth`) used by BOTH pages'
  2s polls: after ≥2 consecutive poll failures show a persistent banner "Pad server
  unreachable — reconnecting…" and back off (2s → 5s cap); on the first success
  after a downtime, run the page's full `refresh()` and clear the banner. lab.js's
  unhandled `setInterval(updateRuntime, 2000)` (lab.js:281) and pad-ui.js's
  swallowed catch (pad-ui.js:367) both route through it.
- User actions while down still fail — they must show the banner error, not hang.

### Task 9 — never-stale by construction (defect 10)
- `tools/led_pad_web.py`:
  - Pure decision seam: `freshness_restart_due(baseline: dict[str, float],
    current: dict[str, float], *, playing: bool, pad_owned: bool,
    stable_age_s: float, min_stable_s: float = 3.0) -> bool` — True iff any watched
    mtime differs from baseline AND the newest change is ≥ `min_stable_s` old AND
    not `playing` AND not `pad_owned`.
  - Watched list (explicit constant, absolute via `_REPO_ROOT`):
    `govee_frame_renderer.py`, `led_pad_controls.py`, `govee_realtime_runner.py`,
    `led_color_engine.py`, `led_config.py`, `tools/led_pad_web.py`,
    `tools/led_pad_lab.py`, `tools/led_pad_playback.py`, `tools/pad_access.py`.
    A missing watched file counts as changed once stable.
  - `run_server`: daemon thread samples every 5s; when due, log
    "source changed on disk — restarting for freshness" and `os._exit(3)`
    ([confirmed] launchd KeepAlive/SuccessfulExit=false relaunches non-zero exits;
    the UI heals via Task 8). `playing` from `service._playback.status()`,
    `pad_owned` from `service._playback.ownership()`.
  - `Cache-Control: no-cache` header on `_send_json` and `_send_file`.
- Draft-vs-live fingerprint: sidecar `led_look_director.draft.base` (sha256 hex of
  `_normalized(live)`) next to the draft file. Add exactly one `.gitignore` line for
  `config/led_look_director.draft.base` ([confirmed] at 17ba826 the live config and
  draft are ignored at .gitignore:34-35 but this new path is NOT — without the line,
  auto-sync would commit live-config-derived data, breaking AGENTS.md §6). Written when the draft is first
  created from live, on `commit`, `discard`, and `history_restore`. On
  `get_config_payload`: if `dirty["global"]` is False, refresh the sidecar to the
  current live hash; payload gains `"live_changed": bool` (current live hash !=
  sidecar). UI (pad-ui.js): when `live_changed`, show a warning banner "Live config
  changed underneath this draft (bridge or agent edit). Review before Apply —
  Discard reloads live." and include the same warning line in the Apply confirm
  modal. No auto-merge, ever.

### Task 10 — docs + registry + contract close-out
- `docs/guides/led_pad.md`: Lab section rewritten for the new flows (accept
  snapshot + dirty chip, decoupled preview, archive/promotion runbook, effective
  bounds rule, color pickers + regime badges, reconnect behavior, freshness
  contract: watchdog list + fingerprint + no-cache). Keep the existing CONTROL_META
  audit-table section intact.
- `docs/subsystems/led_govee.md`: update the pad/lab paragraph(s) to match.
- `docs/status/active_work_registry.md`: update the AWR-193 row (the manager
  created it at spec commit) to the built state with commits + test counts.
- `docs/architecture/doc_index.md`: add this spec file's classification row.
- Bump `led_pad` contract `last_verified_commit` in
  `docs/agents/change_contracts.yml` if the staleness checker flags it.

## Part C — Invariants that MUST still hold (live safety)
- The pad NEVER starts, stops, or restarts the bridge; the watchdog restarts ONLY
  the pad process, ONLY when playback is idle AND the pad does not own the LEDs.
  A pad restart while pad-owned would drop the room dark — that path must be
  impossible by construction (the pure decision function refuses it).
- Ownership precedence unchanged: bridge_owned requires explicit takeover;
  emergency_stop and release paths byte-identical in behavior.
- Strobe safety unchanged: `safety.allow_strobe` gating and lab `allow_strobe:
  False` stay as-is.
- No blocking I/O added to any playback/render tick path; the watchdog and
  fingerprint work happen on the HTTP/watchdog threads only.
- Live config writes stay atomic-with-backup (`save_config_atomically` untouched).
- Fail open, not dark: reconnect/banner failures must never leave a page that
  can't reach STOP — the emergency stop button keeps working whenever the server
  is reachable.

## Part D — Tests (extend the named files; unittest, no new frameworks)
- tests/test_led_pad_lab.py: collision check fires on CREATE with a production
  name, does NOT fire on update/status-change of an existing colliding entry;
  archive sets `promoted`; `list()` flags `production_collision`; renderer
  resolution falls back to `fn` (module registering only the fn name renders a
  renamed draft; name-registered entries keep resolving by name).
- tests/test_led_pad_service.py: accept snapshots last-applied pre-injection params
  (play with param overlay → accept → entry params == overlay merge, palette-
  injected keys absent; accept without play → `snapshotted` False, params
  unchanged); `/api/lab/archive` route; `live_changed` False on fresh draft → True
  after live file mutated externally → False again after discard/commit;
  `Cache-Control: no-cache` on a JSON and a static response; lab_preview honors
  posted params without a prior save.
- tests/test_led_pad_controls.py: `effective_lab_specs` overrides shared-key bounds
  and reports conflicts; passes through lab-only keys; existing audit tests stay
  green and unmodified.
- Pure watchdog: `freshness_restart_due` cases — no change → False; change but
  playing → False; change but pad_owned → False; fresh change (< min_stable_s) →
  False; stable change + idle + not owned → True; missing file → True once stable.
- JS has no test harness in this repo: Tasks 4, 6, 7, 8 UI behavior is covered by
  code review + the manager's manual smoke at activation. Say so in your report —
  do not claim tested UI.

## Part E — Acceptance (definition of done)
- [ ] All ten defect behaviors addressed per Part B; each task = one commit with
      explicit paths; commit messages `AWR-193 Task N: <what>`.
- [ ] Scoped tests green per task; full `python3 -m unittest discover tests` from
      repo root green EXCEPT exactly the five NAMED environmental baseline reds:
      `test_drop_slot_color_smoke_and_snap` (error), both
      `test_export_pack_parity_self_heal` fails,
      `test_ddj_slots_8_16_17_24_exact_ch1_ch19`, parity-oracle
      `test_autoloop_capture_rows_identify_passes_and_blockers`. Reconcile BY NAME;
      any other red = stop and report, never re-attribute.
- [ ] Hard checks green: `python3 tools/check_docs_metadata.py`,
      `python3 tools/check_agent_contracts.py`, `python3 tools/check_docs_drift.py`
      (+ staleness advisory noted).
- [ ] Part C invariants re-checked against your final diff.
- [ ] Report (see below) written; you do NOT declare the round shipped.

## When you finish
Report: commits (hash + files), per-task test evidence (names + counts), the full-
suite reconciliation BY NAME, hard-check output, Part C self-check, anything you
noticed but did not touch, and any place reality diverged from this spec. The
manager adversarially reviews; the executive gates; the operator activates.
Evidence class everywhere: SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.
