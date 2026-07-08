---
doc_status: current
truth_level: code-verified
last_verified_commit: 1b51c66
last_verified_date: 2026-07-08
validation_scope: implementation spec only — nothing here is implemented; every file:line claim re-verified at 1b51c66 this session; live config is READ-ONLY for Codex (mirror is operator-gated)
---

# Codex Implementation Spec - LED white-knob round 1 (AWR-152 approved knobs #2 #3 #6 #7 #8 #10)

Operator-approved subset of the AWR-152 audit
(`docs/research/led_color_quality_audit_2026_07_08.md`). Audit knob #1 was
**vetoed** (the three freestyle nebulas STAY in the default banks — do not
touch `exempt_looks` or bank membership of any nebula). Knobs #4/#5/#9 are
visual-test-gated and are NOT in this spec.

## Part A - Context & Root Cause (verified; read, do not implement)

The operator's standing taste verdict: too much white leaks into non-buildup
cues. The approved mechanisms, all [confirmed] at `1b51c66`:

1. **Slot 5 is hardcoded pure white in v2.** `derive_dressing` appends the
   module constant `WHITE = (255, 255, 255)` (`led_identity_v2.py:43`) as
   slot 5 of every zone's dressing (`led_identity_v2.py:198`). White accents
   (nebula comets, fireworks) are therefore clinical pure white in every zone.
2. **The per-zone `white` config key is dead.** Parsed into
   `ZoneRampConfig.white` (`led_config.py:1391`, model `led_models.py:79`) and
   consumed by nothing (verified by search across the engine, identity module,
   renderer, dispatch, adapter).
3. **The v1 `palette.white` knob is dead in practice.** `_blend_white`
   (`led_color_engine.py:120-126`) is applied at `led_color_engine.py:676,
   686, 688, 801, 815, 832, 844`, but every live AND example palette sets
   `white: 0.0` (identity blend), and v1 only runs during scripted
   stand-down. Operator confirmed he never used it. Delete the knob.
4. **Palate reset dims everything except white.** The v2 slot path rebuilds
   `slots = [dimmed slots 0-4] + [(255, 255, 255)]` (`led_color_engine.py:1185`)
   while the single-color path dims all six (`led_color_engine.py:1142`).
   Slot-5 cues flash full white inside the deliberately-dim reset.
5. **Under v2, cloud DIY filtering runs on a frozen, meaningless palette.**
   `_led_diy_eligible_predicate` (`led_dispatch_policy.py:1666-1668`) returns
   `engine.diy_eligible` whenever the engine is enabled; `diy_eligible`
   compares tags against the **v1** `_current_palette`
   (`led_color_engine.py:517-556`), which never advances under v2
   (`begin_dispatch` returns early into the v2 branch,
   `led_color_engine.py:415-427`). Meanwhile `white`-tagged looks always pass
   the sentinel (`led_color_engine.py:537`). Net: color-tagged cloud scenes
   can be silently dropped from banks all session while white-tagged ones
   always survive. **Approved shape: under v2 the predicate returns `None`
   (no tag filtering — every banked cloud scene rotates evenly). Re-wiring
   tags to v2 zones was NOT requested.** The predicate is the single
   producer; both consumers (`led_dispatch_policy.py:1177` context and
   `:1654` drop-substitute path) route through it. [confirmed]
6. **`breakdown_star_twinkle` picks white stars.**
   `rng.randint(0, MAX_SLOTS - 1)` (`govee_frame_renderer.py:1728`) includes
   slot 5, so ~1/6 of breakdown stars are pure white; the sibling
   `_slot_twinkle` stops at 4 (`govee_frame_renderer.py:842`), and the
   slot-5-reserved operator decision comments (`govee_frame_renderer.py:1636,
   1682`) say slot 5 is white-reserved. Unintended.
7. **One cloud scene is all-white in a colored role.**
   `groove_diy_bright_white_chase` sits in the default groove bank
   (example config `config/led_look_director.example.json:162`; look def and
   `white` tag at `:203`). Cloud scene content is engine-unreachable
   (`govee_scene_adapter.py` has no color-param handling [confirmed]); bank
   membership is the only lever. Approved: move it to the buildup bank
   (white is the buildup language).

[assumed, Codex must verify while implementing]: the config loader ignores
unknown keys inside palette and zone dicts (no allowlist rejection), so
legacy `white` keys remaining in the operator's live gitignored config load
harmlessly after the knob deletion. If any validation rejects unknown
palette/zone keys, STOP and report — do not add a compatibility shim silently.

## Part B - Tasks (implement exactly, in order; one commit per task)

### Absolute Rules

- **Do not touch:** `exempt_looks` (veto), any bank membership except Task 5's
  single move, `config/led_look_director.json` (LIVE, gitignored — read-only;
  the operator mirrors it later), `config/led_lab/**` (gitignored lab
  workspace), the v1 slot-5 pure-white constants
  (`led_color_engine.py:761, 767, 805, 817, 835, 847`), the v2 manual paths
  (`led_color_engine.py:1174-1176`), `REALTIME_EFFECT_PARAM_KEYS` /
  `REALTIME_STROBE_EFFECTS`, the runner/transport, `state_manager.py`,
  laser/SoundSwitch/Rekordbox subsystems.
- **Behavior that must not change:** blackout/emergency semantics; AWR-150
  substitute flow; the 6-slot invariant; v1 scripted-mode output EXCEPT the
  removal of an identity blend (`white=0.0`); DIY filtering under v1
  (predicate unchanged when the v2 latch is off); bloom/flip-fade fields and
  windows.
- **Error handling:** config validation failures fail closed with an error in
  the existing `errors` list pattern (`led_config.py`) — never a silent
  default for MALFORMED values; ABSENT `slot5_white` takes the pure-white
  default (that absence-default is what keeps an un-mirrored live config
  byte-identical to today). No broad try/except anywhere.

### Task 1 - `led_models.py`: replace the dead zone knob, delete the dead palette knob

- `ZoneRampConfig` (`led_models.py:75-80`): remove `white: float = 0.0`; add
  `slot5_white: RGB = (255, 255, 255)`.
- `Palette` (`led_models.py:62-72`): remove the `white: float = 0.0` field.

### Task 2 - `led_config.py`: parsing + validation

- Zone parse (`led_config.py:1385-1393`, `_build_identity_v2_config`): stop
  reading `data.get("white", ...)`; read
  `slot5_white=data.get("slot5_white", (255, 255, 255))`, validated as a
  length-3 sequence of ints each 0-255 → build a tuple. Malformed →
  append an error (fail closed, matching the surrounding zone validation
  style). Absent → default `(255, 255, 255)`.
- Palette validation (`led_config.py:1188-1192`): delete the
  `palette_data.get("white", ...)` number/range checks.
- Palette parse (`led_config.py:1455-1462`): delete `white=float(p.get("white", 0.0))`.
- Legacy `white` keys still present in configs are ignored (verify the
  [assumed] above).

### Task 3 - `led_identity_v2.py`: zone-tinted slot 5

- `derive_dressing` (`led_identity_v2.py:170-199`): replace the `(WHITE,)`
  tail with `(tuple(zone_cfg.slot5_white),)`. The tinted white is used
  **verbatim** — do NOT pass it through `_adjust_rgb` (the sat_floor would
  destroy a near-white; that is the point of the knob).
- Remove the `WHITE` module constant (`led_identity_v2.py:43`) if nothing
  else references it after the change; update any test imports.

### Task 4 - `led_color_engine.py`: dim slot 5 during palate reset + delete `_blend_white`

- Reset slot path (`led_color_engine.py:1182-1185`): replace the
  `[:5]`-plus-pure-white rebuild with all six slots dimmed:
  `slots = [self._scale_rgb(rgb, dim) for rgb in neutral.slot_rgbs]` —
  exactly the single-color path's treatment (`led_color_engine.py:1139-1142`).
  Slot 5 becomes the NEUTRAL zone's `slot5_white`, dimmed.
- Delete `_blend_white` (`led_color_engine.py:120-126`) and all seven call
  lines (`:676, :686, :688, :801, :815, :832, :844`) — each is
  `rgb = _blend_white(rgb, palette.white)`; the assignment line disappears,
  the surrounding `_p_to_rgb` result flows through unchanged. Update the
  module docstring paragraph that describes the per-palette `white` blend
  (`led_color_engine.py:37-43`).

### Task 5 - `config/led_look_director.example.json`: approved config changes

- Move `"groove_diy_bright_white_chase"` from `banks.default.groove`
  (example `:162`) into `banks.default.buildup` (keep its look definition,
  `diy_color_tags` entry, and `safety_class` untouched — `safety_class` is a
  free string with no bank cross-validation, `led_config.py:442-444, 1690`
  [confirmed]).
- Delete every palette-level `"white": 0.0` key.
- In each `v2.zones` block: delete the dead `"white"` key and add
  `"slot5_white"` with these example defaults (operator taste defaults from
  the audit — he vetoes on the strip, values are not sacred):
  GLACIER `[200, 235, 255]`, DEEP_POOL `[185, 215, 255]`,
  TWILIGHT `[230, 215, 255]`, ION `[220, 255, 225]`, VOLT `[235, 215, 255]`,
  EMBERCORE `[255, 225, 200]`, NEUTRAL `[220, 240, 255]`.

### Task 6 - `led_dispatch_policy.py`: remove the stale DIY filter under v2

Replace `_led_diy_eligible_predicate` (`led_dispatch_policy.py:1666-1668`):

```python
def _led_diy_eligible_predicate(self) -> Any:
    # AWR-152 #6: under v2 the v1 palette is frozen at init, so tag filtering
    # is arbitrary (and white-tagged looks always pass) — filter nothing.
    if bool(getattr(self, "_led_v2_latch", False)):
        return None
    engine = self._led_color_engine
    return engine.diy_eligible if (engine is not None and engine.enabled) else None
```

Mirror the latch-read pattern of `_led_look_preference_predicate`
(`led_dispatch_policy.py:1671`). The latch flips live via the `led_engine`
runtime command (`state_manager.py:1766-1768`); the predicate is re-evaluated
at each call site (`:1177`, `:1654`), so v1↔v2 switches take effect on the
next dispatch with no new state. `engine.diy_eligible` itself is untouched.

### Task 7 - `govee_frame_renderer.py`: no white stars in breakdown twinkle

`govee_frame_renderer.py:1728`: `color_slot = rng.randint(0, MAX_SLOTS - 1)`
→ `color_slot = rng.randint(0, 4)` (match `_slot_twinkle`,
`govee_frame_renderer.py:842`). One line; the docstring's "across slots"
stays true (slots 0-4).

## Part C - Invariants That MUST Still Hold (live safety)

- The 200 Hz push loop gains no blocking I/O (nothing here touches it).
- Slot vectors stay exactly 6 long on every path (Task 4's rebuild keeps
  `len(neutral.slot_rgbs) == 6`).
- An **un-mirrored live config** (still carrying legacy `white` keys, no
  `slot5_white`) must load clean and render byte-identical to today
  everywhere except: reset-window slot-5 dimming (Task 4, first branch) and
  the breakdown star slot range (Task 7). This is the release-safety
  invariant — the operator restarts before mirroring.
- Emergency blackout, manual overrides, AWR-145 keepalive, AWR-150 substitute
  + staged takeover: unchanged.
- v1 scripted stand-down keeps pure-white slot 5 and its full resolve
  behavior (minus the identity `white=0.0` blend).
- DIY filtering under v1 (latch off) is byte-identical to today.

## Part D - Tests (pure seams; no disk, no subprocess)

Extend the named suites; every algorithm below is testable with in-memory
config objects:

1. `tests/test_led_identity_v2.py`: `derive_dressing` returns the configured
   `slot5_white` verbatim as slot 5 (not sat-floored, not hue-shifted);
   default `(255, 255, 255)` when the zone config omits it.
2. `tests/test_led_config.py`: `slot5_white` parse (valid / absent-default /
   malformed-fails-closed with an error string); legacy `"white"` keys in
   palettes AND zones are ignored without error; example config loads clean;
   `groove_diy_bright_white_chase` is in `banks.default.buildup` and not in
   `banks.default.groove`.
3. `tests/test_led_color_engine.py`: during an active palate reset the slot
   path returns ALL six slots dimmed by `palate_reset_dim` (slot 5 included,
   derived from NEUTRAL's `slot5_white`); remove/update any tests
   constructing `Palette(white=...)` or asserting `_blend_white` behavior.
4. `tests/test_led_state_manager.py`: `_led_diy_eligible_predicate` returns
   `None` when `_led_v2_latch` is truthy and the engine predicate when it is
   falsy; a v2-latched automation tick keeps color-tagged cloud looks in the
   bank (no filtering).
5. `tests/test_govee_frame_renderer.py`: `_slot_breakdown_star_twinkle`
   emits zero intensity in slot-5 column across a multi-cycle render sweep;
   update any determinism fixtures whose expected slot picks shift with the
   new randint range.

## Part E - Acceptance (definition of done)

- [ ] Tasks 1-7 implemented exactly; one commit per task, explicit paths.
- [ ] Contract-first: this change falls under `led_govee` and
  `config_schema` in `docs/agents/change_contracts.yml`. Update EVERY
  `docs_update` doc: `docs/subsystems/led_govee.md`,
  `docs/status/feature_status_matrix.md`, `docs/status/support_matrix.md`,
  `docs/status/validation_matrix.md`,
  `docs/validation/hardware_validation_log.md`,
  `docs/validation/software_test_inventory.md`,
  `docs/status/active_work_registry.md` (AWR-152 row: implemented /
  software-tested), `docs/architecture/palette_control_authority.md` (only if
  the palette-knob deletion touches its claims — verify, do not assume),
  `docs/plans/active/streamdeck_palette_control_design_spec.md` (same),
  `docs/agents/task_playbooks/change_led_govee_behavior.md`,
  `docs/subsystems/config.md`, `docs/setup/configuration.md`.
- [ ] Contract tests: `python3 -m unittest tests.test_led_state_manager`,
  `tests.test_led_identity_v2`, full `python3 -m unittest discover tests`
  (known pre-existing environmental reds excepted — do NOT fix unrelated
  reds), `python3 tools/check_docs_metadata.py`,
  `python3 tools/check_agent_contracts.py`, `python3 tools/check_docs_drift.py`.
- [ ] The [assumed] unknown-key tolerance verified and stated in the report.
- [ ] Status language: implemented / software-tested / hardware-unvalidated
  only.
- [ ] LIVE config untouched; live mirror listed as an operator-gated step.

## When You Finish

Report: changed files per task, test/check output, the unknown-key
verification result, and any deviation.

Plain-language operator summary to include: after your next config mirror +
menubar restart — the bright-white chase scene moves from grooves to
buildups; white sparkles/comets/fireworks take on each zone's tint (icy in
blue zones, warm in ember) instead of clinical white; the dim moment on a
hard track change now dims the white accents too; breakdown twinkles stop
throwing random pure-white stars; and every cloud scene you built rotates
evenly again instead of a random subset. Buildups stay white. Nothing changes
until you mirror the live config and restart via the menubar; if it feels
wrong, restoring your previous config restores today's behavior exactly.
