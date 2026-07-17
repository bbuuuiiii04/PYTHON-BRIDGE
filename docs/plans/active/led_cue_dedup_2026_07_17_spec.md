# Implementation Spec — LED cue dedup: delete the comet-train clones, name the sparkle honestly

status: planned (spec) — implementation target: software-tested
owner: operator-approved 2026-07-17 (chat); planner: Claude (Fable seat); implementer: Claude tmux seat
contract: `led_govee` (+ `config_schema` for example-config edits) — see Part E

## Part A — Context & Root Cause (verified; read, do not implement)

Operator ran the post-drop bank live 2026-07-17 and rejected the comet-train family as
indistinguishable repeats. Frame-level verification agrees:

- [confirmed] `_slot_post_drop_chase` (govee_frame_renderer.py:1514) and `_slot_post_drop_nebula`
  (:1547) are the same comet train; nebula differs only by white on odd spawn indices. Both gate
  through `_hz_strobe_on`.
- [confirmed] `_slot_drop_chase` (:1620) / `_slot_drop_nebula` (:1654) are the same shape with an
  8-beat sparkle intro; nebula = white-alternate variant. Both gated.
- [confirmed] `post_drop_freestyle_nebula` and `drop_chase_freestyle_nebula` are dispatch aliases
  to the v1 baked-color prototypes `_post_drop_nebula` / `_drop_nebula`
  (govee_frame_renderer.py:1150-1158 in `_edm_dispatch`).
- [confirmed] The sparkle everyone likes is `_slot_rt_post_drop_firework_remnants` (:2106); its
  look was already renamed `rt_post_drop_sparkle` in live config (config round, landed 2026-07-17).
- [confirmed] Effect registry names that are also (or were) look names caused repeated operator
  confusion. Naming rule now in force: looks say WHEN, effects say WHAT, no name in both layers.
- [confirmed] Legacy frame effect `"sparkle"` (registered :1181, param keys :1266, member of
  `_RETRIGGER_EFFECTS` :1304, entries in led_pad_controls.py:202/292/381) is referenced by zero
  looks in live or example config.
- [confirmed] `drop_firework_explosion` (v1) has zero config users; superseded by
  `drop_firework_explosion_2` (comment govee_frame_renderer.py:2244).
- [confirmed] None of the effects touched here appear in `_OVERLAP_EFFECTS` or
  `REALTIME_STROBE_EFFECTS` EXCEPT `post_drop_freestyle_nebula` and `drop_chase_freestyle_nebula`,
  which ARE in `REALTIME_STROBE_EFFECTS` and are being deleted.
- [confirmed] Live config (post config-round state): drop bank = 6 looks incl.
  `rt_drop_chase_freestyle_nebula`; post_drop bank = 9 looks; f2.drop_look_routing tier-1 cells
  all `[]`; tier-2 HOUSE = [rt_drop_chase_freestyle_nebula, rt_drop_strobe], tier-2 NEUTRAL =
  [rt_drop_chase_freestyle_nebula, rt_drop_firework_explosion].
- [assumed] LED Pad launchd label is `com.bbui.led-pad` (memory). Verify via
  `launchctl list | grep -i led` before kickstart; if absent, report blocked — do not guess.

## Part B — Tasks (implement exactly, in order)

### Absolute Rules
- Out of scope: `groove_freestyle_nebula`, `buildup_freestyle_nebula` (similar names, NOT on the
  kill list); every laser/SoundSwitch/rekordbox module; the bridge process (must stay off — do
  not start it); `config/led_lab/**`; `tools/apply_*.py` one-shot migration tools and
  `experiments/**` (historical — leave stale references there untouched, never run them);
  the three dead params on the sparkle look (`sparkle_density`, `sparkle_life_s`,
  `sparkle_size`) stay in look params AND stay allowlisted this round.
- Behavior that must not change: every SURVIVING effect renders byte-identical frames — this
  round is deletions and re-keying only, zero body edits. Survivors include: `palette_comet`,
  `rainbow_ordered`, `rt_drop_center_burst`, `rt_post_drop_center_comet`,
  `post_drop_firework_chase`, `rt_twinkle`, the `rt_groove_*` family, `breakdown_*`, the
  buildup family, `drop_white_aggressive`, `post_drop_white_shatter`, `drop_strobe_colorway`,
  and the two renamed effects.
- Error handling: every config mutation asserts its precondition and fails closed (restore
  backup, report). No broad try/except. A failing suite/check is a stop, not a workaround.
- Git: work directly on main; NEVER `git clean`; commit by explicit paths only.

### Task 1 — `govee_frame_renderer.py`: delete the comet-train effects
Delete, with their registry entries, `REALTIME_EFFECT_PARAM_KEYS` entries, entries in the
effect-description dict (the string table at govee_frame_renderer.py:1192-1212 — verify its
actual name before editing), and `REALTIME_STROBE_EFFECTS` entries where present:
- SLOT_EFFECTS: `rt_post_drop_chase` (`_slot_post_drop_chase`), `rt_post_drop_nebula`
  (`_slot_post_drop_nebula`), `rt_drop_chase` (`_slot_drop_chase`), `rt_drop_nebula`
  (`_slot_drop_nebula`).
- `_EFFECTS` names `post_drop_freestyle_nebula` + `drop_chase_freestyle_nebula`: remove their
  `_edm_dispatch` branches (:1150-1158) and registry/param/description/strobe-list entries.
- Cascade: after the above, grep-prove `_post_drop_nebula`, `_drop_nebula`, and
  `_drop_chase_spawn_times` have zero remaining callers; delete each that proves orphaned. KEEP
  `_drop_chase_sparkle_field` (used by the sparkle effect).

### Task 2 — `govee_frame_renderer.py`: delete legacy `sparkle` + v1 firework, then rename
- Delete legacy `"sparkle"`: registry (:1181), param keys (:1266), `_RETRIGGER_EFFECTS` member
  (:1304), and the `_sparkle` function if grep proves it orphaned.
- Delete `drop_firework_explosion` (v1): function + `_EFFECTS` entry + param/description entries.
- Rename effect key `rt_post_drop_firework_remnants` → `sparkle` (SLOT_EFFECTS, its
  `REALTIME_EFFECT_PARAM_KEYS` key — keep the key SET identical, including the three dead
  sparkle_* keys — descriptions, and the function to `_slot_sparkle`).
- Rename effect key `drop_firework_explosion_2` → `firework_burst` (same sweep; function
  `_drop_firework_explosion_2` → `_firework_burst`).

### Task 3 — `led_pad_controls.py`: mirror the registry
Remove entries for all deleted effect names (incl. legacy `sparkle` at :202/:292/:381); re-key
the two renamed effects' entries (visible keys for `sparkle`: `ember_hold_beats`,
`ember_decay_beats` — same as today's remnants entry). The AWR-262 drift unittest is the gate.

### Task 4 — `tools/led_pad_web.py`: re-key any effect-name references
[confirmed] it references `drop_firework_explosion_2`; grep for every name in Tasks 1-2 and
re-key or delete accordingly (no logic changes).

### Task 5 — tests
- Delete test cases whose subject is a deleted effect (determinism/frame tests for the four
  slot comet-trains, freestyle aliases, legacy sparkle, v1 firework).
- Re-key tests for the two renamed effects.
- Tests that use a dead name merely as a fixture string get re-pointed at a surviving effect.
- Add: `default_sync_mode('sparkle') == 'continuous'` (guards the name against the removed
  `_RETRIGGER_EFFECTS` entry) and `'sparkle' in SLOT_EFFECTS`.

### Task 6 — `config/led_look_director.example.json`
Delete example looks/bank entries/drop_pairs that reference deleted effects or the deleted
looks below; re-key scene_refs for the two renames. Example must load warning-free.

### Task 7 — live config `config/led_look_director.json` (backup first, same discipline as the
landed config round: assert-per-step, atomic write, chmod 0600, full-tree survivor scan)
- Delete looks: `rt_post_drop_chase`, `rt_post_drop_nebula`, `rt_post_drop_freestyle_nebula`,
  `rt_post_drop_remnant_chase`, `rt_post_drop_remnant_nebula`, `rt_drop_nebula`,
  `rt_drop_chase_freestyle_nebula` — plus their bank entries, `_pad_meta.looks` entries, and
  color_engine per-look map entries.
- post_drop bank must end exactly: [rt_post_drop_center_comet, rt_post_drop_firework_chase,
  rt_post_drop_sparkle, rt_post_drop_palette_comet]; drop bank exactly:
  [rt_drop_white_aggressive, rt_drop_center_burst, rt_drop_strobe, rt_drop_firework_explosion,
  rt_drop_palette_comet].
- drop_pairs: delete `rt_drop_chase_freestyle_nebula` entry. All other pairs unchanged.
- f2.drop_look_routing: remove `rt_drop_chase_freestyle_nebula` from every tier list it appears
  in; assert HOUSE tier-2 == [rt_drop_strobe] and NEUTRAL tier-2 == [rt_drop_firework_explosion]
  after (non-empty is mandatory).
- scene_refs: `rt_post_drop_sparkle` look → `sparkle`; `rt_drop_firework_explosion` look →
  `firework_burst`.
- Survivor scan: zero occurrences of ANY deleted/old effect or look name anywhere in the tree
  (no allowed survivors this round). Loader must return zero errors, zero warnings.

### Task 8 — pad restart + resync
Verify label (`launchctl list | grep -i led`), `launchctl kickstart -k gui/$(id -u)/<label>`,
wait for :8766, then GET /api/runtime_status (ok:true) and /api/config (65-7=58 looks; sparkle
scene_ref present; no deleted name present). Bridge stays off throughout.

## Part C — Invariants that MUST still hold
- Bridge not started; exactly zero bridge processes before and after (`pgrep -f rb_ss_bridge_v2`).
- C5 fail-safe never trips: the renamed `sparkle` allowlist keeps every key the live look's
  params carry (including the three dead sparkle_* keys).
- No renderer body logic edited — only deletions and re-keying; surviving effects byte-identical
  (the determinism tests are the proof).
- Push-loop/runtime modules untouched (`state_manager.py`, `led_dispatch_policy.py`, …).
- Secrets/live config never committed (config/led_look_director.json is gitignored — keep it so).

## Part D — Tests
`python3 -m unittest discover tests` green from repo root, plus contract checks:
`python3 tools/check_docs_metadata.py`, `check_agent_contracts.py`, `check_docs_drift.py`,
`check_ui_jargon.py`. The renamed-sparkle sync-mode test (Task 5) is the pure-function seam.

## Part E — Acceptance
- [ ] Tasks 1-8 done in order; suite + all four hard checks green.
- [ ] Contract docs updated (`led_govee` docs_update): `docs/subsystems/led_govee.md` cue table
  (remove deleted rows, rename two), status matrices row for this change,
  `docs/status/active_work_registry.md` (this spec, status: implemented/software-tested),
  plus `docs/subsystems/config.md` if example-config schema text names any dead effect.
- [ ] Report: changed files; suite/check outputs; before/after look+effect counts; the pad
  /api/config assertion results; plain-language operator summary (what changed on the pad, what
  is byte-identical, that everything lands on next bridge start); explicit note of anything
  skipped or blocked. Status language: software-tested at most.

## When you finish
Signal per your dispatch message contract. Everything here is verified against HEAD cc771452 +
the landed config round; if the tree moved underneath you, re-verify Part A file:lines before
editing and report any mismatch instead of adapting silently.
