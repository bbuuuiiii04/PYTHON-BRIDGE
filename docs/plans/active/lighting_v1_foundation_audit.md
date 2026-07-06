---
doc_status: current
truth_level: audit findings — read-only, adversarially verified against code
last_verified_commit: 030bc63
last_verified_date: 2026-07-06
validation_scope: read-only software audit of v1 lighting code on LIGHTING ENGINE v2's F1–F4 path; every CONFIRMED/AMBIGUOUS finding traced to a file:line at HEAD and adversarially verified (reproduce / intent / golden-test lenses); no bridge behavior changed, no hardware validation
---

# LIGHTING v1 Foundation Audit — stabilize the baseline before LIGHTING ENGINE v2

**Bottom line: the v1 lighting foundation is fundamentally sound.** Across the whole
on-v2-path surface (color/palette/identity engine, LED dispatch + drop presentation, the
Govee frame renderer + fade primitives, the StateManager LED seams, and the Stream Deck
surface) the audit found exactly **one real bug** (a fail-open gap that can leave the room
dark on a rare stop path) plus **one docstring drift**. Everything else is either an
operator-taste decision with no authority behind it, or intended v1 behavior the finders
correctly cleared.

Crucially for v2: **no golden / byte-identical test currently freezes a confirmed buggy
behavior**, so the "v2-off ⇒ v1 byte-identical" guarantee will lock in a *correct*
baseline once the one real bug is fixed.

This is a Codex/Claude-facing record. The operator decision lives in chat, not here.

## Verdict tally

| Verdict | Count | Meaning |
|---|---|---|
| **CONFIRMED** (on-v2-path) | 2 | Reproduces AND an authoritative v1 doc/test mandates the other behavior → the fix spec (`lighting_v1_foundation_fix_spec.md`) covers these. |
| **AMBIGUOUS** (operator decision) | 10 | Reproduces, but no authority defines the intended behavior → needs the operator's eyes; not fixed, not assumed. |
| **REJECTED** (checked & cleared) | 10 | Doesn't reproduce as a defect, is intended v1 behavior, or is a future-v2-only expectation. Several carry a hardening note. |

Method: 5 coverage finders (one per subsystem grouping) → adversarial 3-lens verification
(reproduce / intent / golden-test) per candidate → completeness critic. 28 subagents, 0
errors. Full test baseline **green: 3269 tests OK** (skipped 6, 1 expected failure) at HEAD.
Every load-bearing claim below was re-checked directly against code by the author (Opus),
not taken on a subagent's word.

---

## 1. CONFIRMED bugs (on-v2-path) — the fix-spec scope

### C-1 · DD1 — Reader-stale stop leaves the room dark (fail-open violation) · **medium**

- **Symptom (what the room does wrong):** during a **Laser Solo / pre-dark window** (Govees
  intentionally held dark so the lasers own the moment), if the Rekordbox reader goes
  **stale** (RB momentarily unreadable) while the deck was playing, the LEDs stay dark and
  the lasers get stopped — a genuinely black room — and it does **not** self-recover until
  the reader comes back *and* the drop window naturally ends.
- **Where:** `state_manager.py:3536-3559` (the reader-stale stop branch) → `_do_stop`
  (`state_manager.py:4357`). The only code that releases the LED dark-hold is
  `_drop_presentation_apply_actions` via `_drop_presentation_tick` (sole call site
  `state_manager.py:4117`), which the stale branch's early `return` (3559) skips.
- **Traced mechanism (verified directly at HEAD):**
  1. A `lasers_only`/pre-dark window holds the LEDs dark: `drop_spotlight` is in
     `_led_blackout_owners` (`led_dispatch_policy.py:430`) and
     `_drop_presentation_led_dark_held = True` (`state_manager.py:2393`).
  2. Reader goes stale with `os.was_playing=True` → stale branch at `state_manager.py:3536`
     → `_do_stop` at 3540. `_do_stop` (4357-4386) resets the lasers
     (`reset_runtime_state(reason="stop")`, 4382-4385) but **never** discards the
     `drop_spotlight` owner nor clears `_drop_presentation_led_dark_held`.
  3. `_dispatch_led_idle_ambient(reason="stale_stop")` (3554) then gates out at
     `led_dispatch_policy.py:990-992` because `_led_blackout_active()` (253) is still True
     (owner held) — so it renders **nothing**.
  4. `return` at 3559 short-circuits before `_drop_presentation_tick` (4117). The
     WindowMachine never sees `stopped=True`, so its universal fail-open never fires and
     `LED_CLEAR_BLACKOUT reason=drop_spotlight` (2396) is never emitted.
  - Net: lasers stopped **and** LEDs gated dark → black room until reader recovery + natural
    window end.
- **Intent violated (authoritative):** `docs/architecture/drop_presentation_authority.md`
  §Presentation Mechanics (lines 135-138): *"Fail-open, always: LEDs restore and suppression
  releases on ANY of: … stop … laser-output loss mid-window … The policy can never latch a
  fixture dark."* That doc is marked IMPLEMENTED / SOFTWARE-TESTED (current v1 behavior), and
  this gap is **not** one of its two documented known limitations. The bug violates the
  guarantee on two counts — the "stop" fail-open and the "laser-output loss mid-window"
  fail-open (the lasers are stopped in the same `_do_stop`).
- **Classification:** on-v2-path — the latch lives in the shared v1 LED blackout-owner +
  idle-ambient dispatch machinery the v2 LED render path builds directly on.
- **Confidence:** CONFIRMED. Adversarial verification *strengthened* rather than refuted it.
- **Exposure / why medium not high:** narrow trigger (reader must go stale *during* a
  solo/pre-dark window, and solos are rare), and the dark state is **bounded** by window-end
  after recovery, not permanent. But it is a real dark-room failure mode in code v2 inherits.
- **Golden-test status:** **none.** The existing fail-open tests
  (`tests/test_drop_presentation.py::test_stop`, `::test_laser_output_loss_mid_window`) call
  `_drop_presentation_tick` directly and assert the *correct* WindowMachine behavior; none
  drives the stale push-loop branch, so **no golden test freezes the buggy output**. The fix
  needs no re-baselining — only a new test for the stale path.
- **Fix (root cause, one chokepoint):** release the drop-presentation dark hold inside
  `_do_stop` — every stop path (stale or healthy) routes through it. Reuse the existing
  release pattern (`WindowMachine.tick(stopped=True…)` → `_drop_presentation_apply_actions`,
  exactly as the scripted-mode branch at `state_manager.py:2251-2259` already does), gated on
  `cfg.enabled`. Detailed in the fix spec, Task 1.

### C-2 · PI2 — `lock()` docstring contradicts the code (and the authority) · **low**

- **Symptom:** `led_color_engine.py:784` `lock()` docstring reads
  *"Freeze palette (suppresses drift + drop-snap + queued apply)."* The **"queued apply"**
  clause is false: a queued palette **does** apply under lock and the lock transfers to it.
  It's a comment that traps anyone reasoning about or modifying lock behavior. Runtime is
  correct; only the docstring lies.
- **Where / traced:** `begin_dispatch` (`led_color_engine.py:389-395`) applies
  `_queued_palette` via `_apply_palette_now` **before** and independent of the
  `elif not self._lock:` dwell branch (396), and `_apply_palette_now` never mutates
  `self._lock` — so the queue commits regardless of lock and the lock stays on the new
  palette. Verified directly.
- **Intent violated:** `palette_control_authority.md` Rule 8 (lines 118-120): *"A queued
  palette applies at the boundary even while locked, and the lock transfers to it"* (and the
  Required Behavior line 257). Code agrees with the authority; the docstring disagrees with
  both — a pure doc-vs-code drift (`AGENTS.md §1`: code wins).
- **Classification:** on-v2-path — `lock()`/`queue_palette()` are the palette-control surface
  v2 F1 reuses. **Confidence:** CONFIRMED.
- **Golden-test status:** none pins the false claim.
- **Fix:** one-line docstring correction (fix spec, Task 2). No behavior change, no
  re-baselining.

---

## 2. AMBIGUOUS — operator decisions (reproduce, but no authority defines "correct")

These are **not** fixed and **not** assumed. Each reproduces against real code, but no
authoritative doc/test mandates the other behavior — so per the audit's grounding rule they
are the operator's call ("bug or intended?"). Listed worst-first within each bucket.

### On-v2-path (7)

| ID | file:line | What reproduces | Room impact | Why ambiguous |
|---|---|---|---|---|
| **govee PI1** | `govee_scene_adapter.py:443` | `post_drop` looks are classified "high-impact" via a `"drop"` **substring** match, so a cloud post-drop look can be rate-limited (`high_impact_rate_limited`) for up to 12 s after the drop. | A cloud post-drop room-return look could be silently dropped — **but latent**: every shipped `post_drop` look is a realtime look that bypasses this cloud adapter, so no shipped config reaches the branch. | No authority says a paired post_drop must be exempt from the high-impact cooldown. |
| **DD2** | `led_dispatch_coordinator.py:108` | The min-dwell throttle returns bare `False`, which the policy treats as an **adapter rejection**: `last_error="adapter_rejected"`, `rejected_count++`, LED status flips to `degraded`, and an `[RGB] adapter-rejected` **warning** logs. | Observability only — no frame/look change. A healthy throttle reads as "degraded" and spams a warning. | No authority defines the intended status for a dwell throttle; two layers just have mismatched semantics. |
| **govee PI4** | `govee_realtime_runner.py:271` | When a deck is **paused** mid comet color-crossfade, the paused branch passes `abs_pos=None`; `resolve_fade` then returns the target color, so the still-flying comet **snaps** from its blended mid-fade color to the destination. | A brief color pop on a finishing comet during a pause. | The None-path (comet free-runs untied to the beat grid while paused) is a documented, test-pinned design choice; no authority says the mid-fade color must persist. |
| **govee PI3** | `govee_frame_renderer.py:415, 447-448, 1784-1786` | Three **baked** effects truncate RGB with bare `int()` instead of the renderer's `_clamp_channel` rounding → up to 1 level darker per channel. | Sub-1-level, not room-visible. | The baked effects deliberately bypass the colorizer and preserve the operator's prototype `int()` calls "verbatim"; no authority defines round-vs-truncate for baked effects. **Note:** a future v2 byte-identical golden over these looks *would* freeze the truncation — decide before then. |
| **govee PI2** | `govee_frame_renderer.py:1728` | `breakdown_star_twinkle` draws star slots via `randint(0, MAX_SLOTS-1)` = 0-5, so ~1/6 of stars land on **reserved white slot 5** and render pure white; sibling cues use `randint(0,4)`. | ~1/6 of twinkle stars are white instead of palette-colored — a valid color, aesthetically inconsistent. | The cue's docstring defends it as a deliberate byte-identical prototype port; the "slots 0-4 only" rule appears only as comments on *other* cues, not in any authority. Fixing it breaks the deliberate port. |
| **statemgr PI4** | `state_manager.py:4398-4410` | In the **legacy (mixer-authority-disabled)** resume path, an empty-deck→mirror correction swaps `active_deck` but skips arming the LED soft-flip hold and the deck-entry reset (`_reset_for_active_deck_entry`) that the normal deck-switch path runs. | On that rare legacy path, a deck flip skips the soft-repaint and mode re-eval. **Off the default config** (mixer authority is default-on). | The invariant that names this correction (`runtime_invariants.md:145`) governs only the mixer-*enabled* case; no authority says the legacy correction must count as a handover flip. |
| **SMI2** | `soundswitch_midi_input.py:315-346` | The palette-pad gesture emits `phase="down"` on note-on; if the matching **note-off is lost** on the wire, `phase="up"` is never emitted and the bridge's tap-vs-long-press resolution has nothing to fire on. | Only on a hard MIDI drop — the physical deck reliably sends note-off. | The adapter is a pure translator (absent input → absent output); `palette_control_authority.md` puts gesture resolution in the consumer and mandates no adapter-side synthesis of lost messages. |

### Isolated from v2's LED path (3) — deferred, one-line notes

| ID | file:line | What reproduces | Why isolated |
|---|---|---|---|
| **PI4** | `led_color_engine.py:827` | `advance_fade` interpolates toward `_palette_center()` even when the fade target is a **fixed_rgb** palette (`white_sand`, no `range` key → defaults to blue/cyan), so the **laser** color slides toward blue/cyan during a fade-to-white_sand, then snaps to white at commit. | Effect is **laser-only** — the LED render reads `palette.rgb`/focus windows, never `_anchor_p`, so LEDs are unaffected. Laser color-map is the isolated subsystem. Cosmetic transient the length of the fade. |
| **statemgr PI5** | `beat_sync_engine.py:128` | `reset()` clears `_clock`/`_instances`/`_spawn_seq` but not `_spawn_count`, so the reported spawn count is lifetime-cumulative across resets. | `_spawn_count` is status-only; drives no render decision, so no v2 render/golden output depends on it. Reads as deliberate (`_spawn_seq` per-activation vs `_spawn_count` lifetime). |
| **SDK1** | `streamdeck/streamdeck_midi.py:770` | The deck-local `active_keys` set is mutated by the HID read-thread callback and the supervision loop with no lock → a rare, self-healing wrong **pad latch** render. | Separate deck-script process; the outbound MIDI note fires *before* any latch mutation, so the bridge's LED path can never misbehave. Cosmetic on the Elgato's own display only. |

---

## 3. REJECTED — checked and cleared (10)

Each reproduced-or-not was traced; none is a v1 bug. Several carry a **hardening note**
worth surfacing even though they are not defects today.

| ID | file:line | Claim | Why rejected | Hardening note |
|---|---|---|---|---|
| **PI1** | `led_color_engine.py:834` | Override-fade slides only `_anchor_p`; the Govee LED per-cue render never tracks the in-flight fade (LEDs hold outgoing palette until commit). | **Intended v1.** The smooth LED per-cue blend is the explicit **future-v2 "blend painter"** (`LIGHTING_ENGINE_V2_DESIGN.md:622-629`). Authority rule 5 describes the fade in p-space (which is `_anchor_p`, feeding laser+deck-preview); rule 23 + the deck script explicitly accept `current_palette` staying outgoing until commit. Not a hard jump (per-cue crossfade softens it). | This is exactly the v2 F1/F2 work item — the LED render must learn to interpolate on fades. |
| **PI3** | `led_color_engine.py:179` | `white_sand`/`rainbow` manual-only guarantee rests only on config `weight=0`, no name-based exclusion; a `random()==0.0` draw could auto-pick them. | **Doesn't reproduce** under real config: `white_sand`/`rainbow` are placed **last**, and a trailing weight-0 palette is mathematically unreachable in `_weighted_choice`. Intent (`palette_control_authority.md:45`, Rule 11) is genuinely doc-backed but not violated today. | **Latent fragility:** reordering the config (or a live config that lists a weight-0 palette first) would break the guarantee. Hardening: skip `weight<=0` in `_pick_palette`. |
| **PI5** | `led_palette_control.py:323` | Override right before a phrase boundary yields a ~1-beat "abrupt" fade. | **Intended & test-pinned.** Operator rule 2026-07-05 chose phrase-boundary landing over minimum length; `test_override_fade_ends_on_phrase_grid_not_press_plus_32` pins it. Never a hard jump (guard keeps end>start). | — |
| **DD3** | `drop_presentation.py:687` | The pre-dark "impact passed without drop" fail-open is gated on `abs_beat` being known → could latch dark on a position dropout. | **Unreachable in the integrated path:** when `abs_beat` is None, `role` collapses to "none" → `laser_visible=False` → the `not laser_visible` reset fires and restores. The never-latch-dark invariant holds via a different path. | Belt-and-suspenders: add `or inputs.abs_beat is None` to the pre_dark reset — defensive nit only. |
| **statemgr PI1** | `state_manager.py:569` | `_palette_feedback_sig` is never cleared on any teardown. | **No wrong output.** The sig only gates whether `maybe_publish()` is *called*; `_publish_feedback` independently dedups against `_last_feedback_body`, so a stale sig at worst skips a redundant publish — never a stale file. | **v2-time hygiene:** once v2's byte-identical teardown is load-bearing, clear this (and `_last_feedback_body`) on stop/idle/deck-entry. Not needed for v1. |
| **statemgr PI2** | `led_dispatch_policy.py:669` | The 2026-07-05 fix advances the fade during emergency blackout / disabled / scripted, broader than the authority's two named cases. | **Intended v1.** `palette_control_authority.md` rule 5 sanctions advancing "every playing tick, independent of LED role dispatch"; emit is still blocked at the gate, so the emergency>manual>automation precedence is intact. Pinned by `AdvancePaletteFadeAndPublishTests`. | — |
| **statemgr PI3** | `led_dispatch_policy.py:747` | Missing-phrase-data active-content hold holds the previous look indefinitely. | **Documented intended v1** (`led_govee.md:129, :227`) and pinned by `test_missing_phrase_data_holds_previous_look_until_crossing`. Stale-look, not room-dark. | Pre-existing "needs operator visual sign-off" caveat (`led_govee.md:129`) — a taste item, not code drift. |
| **SMI1** | `soundswitch_midi_input.py:102` | `stale_timeout_ms` is accepted but never used; no lost-note-off insurance for held layers. | **Intended & test-pinned** no-self-expiry (`test_blackout_hold_does_not_self_expire_without_note_off`). Lost input is handled by port-gone/panic/reload/stop clearing. | Genuinely **dead param** (`controller_hold_timeout_ms` plumbing) — mildly misleading; remove or comment. |
| **SMI3** | `soundswitch_midi_input.py:309` | `_emit_pad_event` calls the external `event_sink` while holding the adapter's `_lock`. | **No wrong output.** Production sink is a non-blocking `put_nowait`; the deadlock needs a future synchronous re-entrant sink that doesn't exist. The "holds a hot-path lock" claim is false (snapshot() takes no lock). | Defensive: build the event under lock, dispatch the sink outside it — only if a synchronous sink is ever added. |
| **critic PI1** | `govee_frame_renderer.py:884` | `_edm_dispatch` falls back to a white buildup ramp for an unmatched EDM name, contradicting "fail dark". | **No live repro:** all 30 `EDM_BUILDS` keys match a branch; the fallback is unreachable today. The "fail dark" contract is scoped to *unregistered* names, which do fail dark. | Optional: make `_edm_dispatch:884` return `_empty()` so a *future* unbranched registered name fails dark instead of white. |

---

## 4. The byte-identical trap — explicit result

The mission's central worry is that a v2 golden ("v2-off ⇒ v1 byte-identical") could freeze a
v1 bug as "correct." Result of the per-finding golden-test check:

- **No golden / snapshot / byte-identical / frame-equality test currently encodes a
  CONFIRMED buggy behavior.** DD1's existing fail-open tests assert the *correct* WindowMachine
  behavior (they call `_drop_presentation_tick` directly, never the stale branch); PI2 has no
  test pinning the false docstring. So **the fix pass needs zero golden re-baselining.**
- **Two AMBIGUOUS items are byte-identity *risks* for the future, not today:** `govee PI2`
  (star_twinkle slot-5 white) and `govee PI3` (baked-effect `int()` truncation). No test pins
  them now, but if v2 adds byte-identical goldens over those specific looks, they would freeze
  the current behavior — so the operator's bug/intended call on them should be made **before**
  any such golden is written, not after.
- The tests that *do* pin fade/hold behavior (`AdvancePaletteFadeAndPublishTests`,
  `test_override_fade_ends_on_phrase_grid_not_press_plus_32`,
  `test_missing_phrase_data_holds_previous_look_until_crossing`) pin **intended** behavior —
  good pins, not traps.

---

## 5. Coverage — what was audited, and the named gaps

Audited by a dedicated finder **and** a completeness pass:
- **palette / identity / config:** `led_color_engine.py`, `led_palette_control.py`,
  `led_models.py`, `led_config.py` (incl. the committed 2026-07-05 phrase-grid fade fix).
- **dispatch / drop:** `led_dispatch_policy.py` (incl. the new `_advance_palette_fade_and_publish`
  and `LED_MAX_DROP_IMPACTS`), `led_dispatch_coordinator.py`, `drop_lifecycle.py`,
  `drop_presentation.py`.
- **Govee render / fade primitives / slot contract:** `govee_frame_renderer.py`,
  `govee_realtime_runner.py`, `govee_realtime_transport.py`, `govee_runtime_sender.py`,
  `govee_scene_adapter.py`, `govee_owner_state.py`.
- **StateManager LED seams:** `state_manager.py` LED paths (incl. the new per-tick call site
  and `_palette_feedback_sig`), `active_deck_resolver.py`, `beat_sync_engine.py`.
- **Stream Deck surface:** `streamdeck/streamdeck_midi.py`, `soundswitch_midi_input.py`.

**Named coverage limits** (examined and judged fine, but not exhaustively hand-verified — not
silent gaps):
1. `render_comet` reads `params['color']` via `_edm_color_for_look`, not slot_colors
   (`govee_frame_renderer.py:1878`) — design §8 flags this as a v2 must-fix; whether the v1
   comet path already ignores engine palette colors on the live rig was not traced (it is
   explicitly future-v2 work, not a v1 bug).
2. `_DEFAULT_SLOT_COLORS` substitution when `slot_colors` is None/malformed
   (`govee_frame_renderer.py:1929-1931`) — no current v1 look was confirmed to hit it.
3. `_update_laser_color_from_led` runs every push tick (LED→laser bridge, straddler) —
   confirmed in-memory + try/except-wrapped; per-tick cost not benchmarked.
4. `models.py` `BridgeEvent` is `@dataclass` **not frozen** despite the "Immutable" docstring;
   LED payloads are mutable dicts. No finder found an actual shared-payload mutation, but the
   immutability invariant rests on convention, not enforcement.
5. `config/led_look_director.example.json` vs `led_config.py` loader was not hand-diffed for
   the newer palette/slot keys (`check_docs_drift.py` passes).
6. `runtime_status.py` `led_scene`/`led_blackout` target-routing callbacks
   (`:408-433`) not traced end-to-end into the dispatch policy.
7. Disabling the SoundSwitch pack mid-session and its effect on the palette feedback writer's
   `static_held` republishing was not exercised.
8. `resolve_fade` slot-color interpolation (`govee_frame_renderer.py:74-97`) — the v2 blend
   painter's color path — was not independently exercised beyond the pause-discontinuity case.
9. Remaining `BeatSyncEngine` reset fields (beyond `_spawn_count`) not audited for residual
   cross-engine state a v1-off/v2-off transition must clear.

---

## 6. Method & provenance

- Grounding order (per `AGENTS.md §1`): code > tests > this audit > docs. Every finding is
  tied to a `file:line` read at HEAD `030bc63`; the intent for a v1 finding is an
  authoritative doc/test (`runtime_invariants.md`, `AGENTS.md §6`, `change_contracts.yml`,
  the subsystem card, `palette_control_authority.md`, `drop_presentation_authority.md`) or a
  v1-carryover passage in `lighting_engine_v2_authority.md` / `LIGHTING_ENGINE_V2_DESIGN.md`.
  Future-v2 target behavior was explicitly **excluded** as a v1-bug basis.
- Adversarial verification: every candidate got an independent skeptic running three lenses
  (does it reproduce at the cited lines / does an authority mandate the other behavior / is
  there a golden test freezing current behavior), defaulting to PLAUSIBLE/REJECTED under doubt.
  10 of 22 candidates were rejected — the skeptic pass did real work.
- The one substantive bug (DD1) and both fix-spec items were re-verified line-by-line by the
  author before write-up.
- Scope: v2 is PLANNED, not built — this is an audit of the *current v1 code* v2 will reuse.
  No bridge code was changed. The fix plan (`lighting_v1_foundation_fix_spec.md`) is a
  standalone v1-baseline pass, explicitly **not** folded into the v2 build, and proceeds only
  after operator approval.
