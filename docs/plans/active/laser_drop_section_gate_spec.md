---
doc_status: active-spec
truth_level: implementation-spec, code-grounded (diagnosis 2026-07-07, Fable 5; operator decision 2026-07-07)
last_verified_commit: 35e0a90
last_verified_date: 2026-07-07
validation_scope: spec only until tasks land; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Codex Implementation Spec — LED-only drops keep the laser dark for the WHOLE drop section

Contract keys: `drop_presentation` (`docs/agents/change_contracts.yml:346`) +
`soundswitch_pack_player` (`:450`, for the status-label fix). **Operator decision, already made —
do not re-litigate:** an LED-only drop must keep the laser dark until the phrasing's real section
end (role leaves `drop`/`post_drop`); a long backstop (~96 beats) exists purely as insurance
against a stuck flag, never to cap normal drops.

## Part A — Context & Root Cause (verified; read, do not implement)

- ~60% of true drops are LED-only by plan: `plan_track()` gives the top
  `ceil(laser_ratio * n)` drops lasers (`drop_presentation.py:293,311`, `laser_ratio=0.4`), the
  rest `LEDS_ONLY`. On impact the WindowMachine enters `in_window` and stamps
  `_window_end_beat = abs_beat + drop_window_cap_beats` (`drop_presentation.py:650-656`, cap
  default 32 at `:92`). `base_suppressed = (presentation == LEDS_ONLY)` (`:661`) keeps the laser
  base dark via `player.set_base_suppressed(...)` (`state_manager.py:2694`). [confirmed]
- Release is an **OR** (`drop_presentation.py:699-712`): role leaves
  `_WINDOW_ACTIVE_ROLES={drop, post_drop}` (`:42`, `:701`) OR `abs_beat >= _window_end_beat`
  (`:703-705`). On any drop section longer than 32 beats the cap fires FIRST → the laser pops
  back on mid-section. That is the operator-visible bug. [confirmed]
- The section-end signal already exists and is already the primary release branch: `role` is
  computed at `state_manager.py:2574-2578` (`smart_drop_crossing` → one-tick `"drop"`, then
  `"post_drop"` while `current_phrase_is_chorus` OR `smart_post_drop_active`), passed into
  `WindowInputs(drop_role=...)` at `:2640`. **No new plumbing is needed — this is a cap-value
  change.** [confirmed]
- Universal fail-opens already cover the stuck cases: `scripted_mode | stopped | track_changed |
  active_deck_changed | manual_interaction` reset the machine in any phase
  (`drop_presentation.py:671-676`), plus `_drop_presentation_release_on_stop()`
  (`state_manager.py:2697-2723`). The 96-beat backstop is a second-layer hang guard on top of
  these. [confirmed]
- Mislabel: when the base is suppressed, the pack player emits diagnostic `base_suppressed`
  (`soundswitch_laser_player.py:479-484`), but `finalize_native_autoloop_render()` has no branch
  for it and the catch-all reports `status="unsupported_layout"`
  (`native_autoloop_resolver.py:144-145`) — an intended dark-laser drop reads as a broken pack.
  The existing intended-empty pattern is `empty_dark_look` (`native_autoloop_resolver.py:146-162`).
  [confirmed]
- Known limit (state honestly, do not "fix" here): on tracks with no/short chorus phrase markers,
  `role` leaves `post_drop` ~`post_drop_beats` (default 8, `state_manager.py:826`, personality
  override `:2265-2267`) after impact — the role branch can release EARLY on markerless tracks.
  That is today's behavior too; this change neither fixes nor worsens it. [confirmed mechanics]

## Part B — Tasks (implement exactly, in order)

### Absolute Rules
- Touch ONLY: `drop_presentation.py`, `native_autoloop_resolver.py`,
  `config/led_look_director.example.json`, the live gitignored `config/led_look_director.json`
  (local edit, never committed), the pinned tests listed below, and Part E docs.
- Contract `drop_presentation` forbidden assumptions hold verbatim (zero RNG; suppression ≠
  blackout; no tick-path I/O; scripted tracks get zero policy activity; `enabled:false` renders
  every drop leds_plus_lasers byte-identically).
- Do not change: the release OR-structure, `_WINDOW_ACTIVE_ROLES`, the LASERS_ONLY /
  LEDS_PLUS_LASERS paths, pre_dark behavior, `laser_ratio`, or any fail-open.

### Task 1 — cap 32 → 96 (backstop semantics)
- `drop_presentation.py:92`: `drop_window_cap_beats` default `32.0` → `96.0`; update the field's
  comment to say it is a hang-guard backstop, not the expected release (the role branch is).
- `config/led_look_director.example.json` drop_presentation block (`:384-395`):
  `"drop_window_cap_beats": 96`.
- Live `config/led_look_director.json` (gitignored, drop_presentation block at `:1473-1484`):
  same edit locally; NEVER commit this file (repo invariant).

### Task 2 — `native_autoloop_resolver.py`: label intentional suppression correctly
Immediately before the catch-all at `:144`, add:
```python
if diagnostic == "base_suppressed":
    return replace(decision, status="base_suppressed", diagnostic=diagnostic)
```
Then grep every consumer of native-autoloop `status` values (`state_manager.py` heartbeat/status
lines — the `[SM] native-autoloop status=… diag=…` emitter — `runtime_status.py`, and
`tools/check_docs_drift.py`'s status-string list) and add `base_suppressed` wherever status strings
are enumerated, so the drift check and status surfaces stay consistent. Treat `base_suppressed`
like `empty_dark_look` (intended-dark, not an error) in any health/severity classification found.

### Task 3 — Tests
- Update the pinned-32 assertions: `tests/test_led_config.py:166`,
  `tests/test_drop_presentation.py:46, 468, 621, 630, 643`,
  `tests/test_state_manager_drop_presentation.py:71` (32 → 96 or config-driven).
- Add (pure WindowMachine tests, existing style in `tests/test_drop_presentation.py`):
  1. LEDS_ONLY window with role still `post_drop` at beat +40: `base_suppressed` still True
     (would have failed before this change).
  2. Role leaves `post_drop` at +48: released on that tick (role branch, before backstop).
  3. Role artificially stuck in `post_drop` past +96: backstop releases at +96.
  4. `finalize_native_autoloop_render` with diagnostic `base_suppressed` returns
     `status="base_suppressed"`, not `unsupported_layout`.

## Part C — Invariants That MUST Still Hold

- All five fail-open inputs still reset the machine in any phase; `_drop_presentation_release_on_stop`
  untouched. A stuck phrasing flag can hold the laser dark for at most 96 beats.
- Suppression is not blackout: LED behavior during LED-only drops unchanged; blackout/mute owners
  untouched.
- Scripted mode still fails open (`state_manager.py:2542-2553`).
- `enabled:false` config still renders every drop leds_plus_lasers exactly as today.
- No RNG, no tick-path I/O added.

## Part D — Tests

Covered in Task 3 — all pure in-memory WindowMachine / resolver tests; no files, no subprocess.

## Part E — Acceptance (definition of done)

- [ ] Tasks 1–3 implemented exactly.
- [ ] Contract `drop_presentation` test list passes: `python3 -m unittest tests.test_drop_presentation`,
      the sibling suite list at `change_contracts.yml:375-377`, full `discover tests` (documented
      env reds excepted), `check_docs_metadata.py`, `check_agent_contracts.py`, `check_docs_drift.py`.
- [ ] `docs_update` for BOTH contracts: `docs/subsystems/led_govee.md`, `docs/subsystems/laser.md`,
      `docs/architecture/drop_presentation_authority.md`,
      `docs/plans/active/streamdeck_palette_control_design_spec.md` (only if its claims mention the
      32-beat cap), `docs/status/active_work_registry.md`, plus the pack-player contract's docs if
      the status-string addition touches their claims.
- [ ] Status language: `implemented` / `software-tested`; the "laser stays dark for the whole
      section" outcome is HARDWARE-UNVALIDATED until Brandon watches an LED-only drop live.

## When You Finish

Report changed files, tests/checks, and the operator summary: expected live behavior ("on an
LED-only drop the lasers stay dark until the drop/chorus section actually ends; only a stuck
phrasing flag can bring them back early, at 96 beats"), unchanged behavior (laser drops, Solos,
blackout, scripted tracks), watchpoint (`[SM] native-autoloop status=base_suppressed` now appears
during LED-only drops — that is intended, not an error), known limit (tracks without chorus
markers still release ~8 beats after impact, same as before), rollback (revert commit + restore
live-config value 32; restart required for config to take effect).
