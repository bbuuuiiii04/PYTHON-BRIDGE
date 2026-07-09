---
doc_status: current
truth_level: implementation-spec
last_verified_commit: d106492
last_verified_date: 2026-07-09
validation_scope: >
  Implementation spec for two live-mix defects reported by the operator mid-mix
  2026-07-09 and diagnosed by the executive seat (superman3): (1) continuous-mode
  realtime looks render off the beat grid; (2) firework-remnants embers are
  invisible in dark palette zones. STAGE ONLY — no bridge restart, no
  self-activation; the executive batches the restart with the operator.
---

# RT beat-phase + ember-visibility fixes (2026-07-09, live round)

**LIVE-CRITICAL (Bug 1 touches the frame-engine child render path). The executive
gate reads this line by line before activation.** Implementer: Opus lane. Contract:
`led_govee` (`docs/agents/change_contracts.yml` — `beat_sync_engine.py` and
`govee_frame_renderer.py` are in its code_globs; no contract extension needed).

## Ground truth (all verified at HEAD d106492, 2026-07-09)

- CONFIRMED `beat_sync_engine.py` `configure()`: `self._mode = sync_mode if sync_mode
  in VALID_SYNC_MODES else "continuous"` — absent `sync_mode` ⇒ continuous.
- CONFIRMED live + example config: `rt_groove_center_chase` and
  `rt_post_drop_firework_chase` have `params = {}`, no `sync_mode` ⇒ continuous ⇒
  ONE instance spawned at the dispatch moment.
- CONFIRMED `beat_sync_engine.py:206` (`_render_list`): `local_beat = local_t *
  (inst.born_bpm / 60.0)` — beats since SPAWN. Renderers receive it as `beat_pos`
  (`govee_realtime_runner.py:487`), so every `cue_beat % 1` cyclical animation
  phase-locks to the dispatch instant, not the beat grid: a constant per-dispatch
  phase error. Retrigger/overlap instances spawn via TriggerClock at
  floor(abs_beat/division) crossings, which is why those looks read synced.
- CONFIRMED `AnimInstance.born_abs_beat` (`beat_sync_engine.py:29,185`) is already
  recorded and unused at render time.
- CONFIRMED `govee_frame_renderer.py:1712` chase burst gate `(cue_beat % 4.0) >= 3.0`
  rides the same shifted clock, and if the post-drop window rotates before local
  beat 3 the gate never fires at all (operator's "no sparkles" on the chase variant).
- CONFIRMED `_ember_field` (`govee_frame_renderer.py:2008`): `slot =
  cyc_rng.randrange(max(1, num_slots))` with `num_slots=5` ⇒ embers write only
  palette slots 0–4. In dark zones (live DEEP_POOL `base_ramp` starts
  `[5,10,60]`) embers render single-digit RGB = invisible, while the slot-5 white
  background (`[185,215,255]`) dims 1→0 over `dim_beats=8` — exactly the operator's
  "dims to darkness, no sparkles".
- CONFIRMED live `drop_pairs` maps `rt_drop_firework_explosion` →
  `rt_post_drop_firework_remnants`; pairing works, visibility is the bug.

## Bug 1 — grid-quantize the continuous-mode beat origin (RULED FIX SHAPE)

In `_render_list` (`beat_sync_engine.py:202-213`), for **continuous mode only**:

```
local_beat = (inst.born_abs_beat % 1.0) + local_t * (inst.born_bpm / 60.0)
```

which equals `abs_beat - floor(born_abs_beat)` under steady BPM — the executive's
ruled shape. Every beat-cyclical continuous look becomes grid-true.

Hard constraints:
- **`InstanceRender.progress` must stay spawn-relative** (`elapsed_beats /
  travel_beats`, exactly today's value). If progress inherits the quantized origin,
  retrigger/overlap comets start mid-sweep. Compute elapsed beats once; derive
  `progress` from elapsed, `local_beat` from the quantized origin.
- Retrigger/overlap modes: `local_beat` unchanged (spawn-relative, as today).
  Their TriggerClock spawns are already grid-locked.
- `local_t` and time-based looks and Hz strobes: untouched.
- Known ceiling (pre-existing, unchanged): `born_bpm` is frozen at spawn, so long
  continuous instances drift under live BPM changes exactly as they do today.

Tests (new, in `tests/test_beat_sync_engine.py` or the module's existing home):
- Continuous instance spawned at `abs_beat=32.6` ⇒ at spawn `local_beat % 1.0 ==
  0.6` (grid-true), and advances with elapsed beats.
- Continuous `progress` at spawn == 0.0 (not 0.6/travel_beats).
- Retrigger instance: `local_beat` and `progress` byte-identical to current
  behavior (regression pin).

Verify list — continuous looks this fix must make grid-true (all confirmed
`params = {}` / no `sync_mode` in live config): `rt_groove_center_chase`,
`rt_post_drop_firework_chase`, `rt_drop_center_burst` (operator: pulses
off-beat, executive-confirmed same class).

## Bug 2 — ember contrast guarantee (flavor = operator desk verdict)

Mechanism options the operator picks from (do not implement until the verdict is
recorded in this spec):
- (a) luminance floor: blend ember color toward the zone's `slot5_white` until a
  minimum perceived luminance is met (keeps hue in bright zones, guarantees
  visibility in dark ones). **Recommended default.**
- (b) route embers to accent slots 3–4 + slot 5.
- (c) embers on slot 5 pure white; background moved to slots 0–4. (Executive note:
  this flavor also makes twinkles read OVER the dimming background — the operator's
  "sparkles don't last 8 beats" report is this same visibility bug: embers hold
  8 + decay 2 mathematically, but the slot-5 background dies at exactly 8 while
  the dark-slot embers were never visible.)

OPERATOR VERDICT (desk, 2026-07-09 mid-mix): **(b) accent slots** — embers route to
accent slots 3–4 + slot 5 instead of `randrange(0..4)`. Test asserts minimum ember
luminance in a DEEP_POOL-dark palette (accents `[40,0,160]`/`[0,60,200]` + slot-5
white `[185,215,255]` all clear it; base-ramp slots would not).

Whichever flavor: the change lives in `_ember_field` / its caller in
`_slot_rt_post_drop_firework_remnants`, must generalize across all zones (no
per-zone special cases), and needs a test asserting a minimum ember luminance in a
DEEP_POOL-dark palette.

## Part C — gentle-drop routing + legacy retirement from the general pool
(operator directive + desk verdicts, 2026-07-09 mid-mix)

Operator verdicts (verbatim intent): legacy `drop_diy_*` chase cues serve as PART
of the rotation for low-energy drops; AND they leave the general drop rotation now.

**Mechanics constraint (verified `led_dispatch_policy.py:2029-2043`):** the
`drop_look_routing` (family, tier) sets are preference predicates that only NARROW
the drop bank, fail-open — an empty intersection keeps the FULL bank. Therefore
bank surgery (deleting legacy from `banks.default.drop`) would make any routing
cell that names them silently no-op. The correct shape:
- Legacy cues STAY in `banks.default.drop`.
- `f2.drop_look_routing` (live config, currently `{}`) gets a full table: the
  low-tier cells (tier 1; families per the operator's gentle intent, at minimum
  NEUTRAL) include the 8 legacy chases PLUS the modern gentle looks; every other
  (family, tier) cell lists the modern set EXCLUDING the 8 legacy names — which
  removes legacy from the general rotation exactly as verdicted, without the
  fail-open trap.
- Legacy cues are cloud-backend: the drop-look rate-limit machinery must keep
  applying (verify, do not bypass).
- Fallback honesty: with no F2 plan (scripted decks, missing v4), routing returns
  None ⇒ full bank INCLUDING legacy — state this to the operator; if he wants
  legacy gone there too, that IS bank surgery plus moving them to a dedicated
  gentle bank, a bigger change staged separately.
- This part is LIVE-CONFIG content (gitignored): stage as an idempotent apply
  script + example-config mirror of the table shape; the executive applies at the
  batched restart. No live-config edit before that.

## Part D — firework mirrors the legacy sparkle half (design, desk-tuned)

Operator (desk, verbatim intent): the legacy drop chase cues had two parts —
sparkle, then strobe chase; the firework should mirror the FIRST half, the sparkle
effect. This is a by-eye character change to `rt_drop_firework_explosion` (and its
remnants pairing feel), tuned with him at the desk over iterations. BOUNDARY: the
Govee DIY-look extraction workstream is deferred and Opus-manager-only — mirror by
observed character and his verdicts, never by decoding DIY scene content. Not part
of this implementation round; design brief follows after Bugs 1–2 and Part C stage.

## Part E — baked-color leak (AWR-180 scope; diagnosis in progress, desk input needed)

Operator (mid-mix): cues holding colors NOT in the palette (not DIY looks).
Findings so far (all reproduced 2026-07-09 against live config):
- CONFIRMED with live config the color engine constructs `_v2_active=True`, so all
  slot resolves take `_v2_resolve_slot_colors` (`led_color_engine.py:1145`).
- CONFIRMED the v2 path emits `slot_colors_from/to` ONLY during bloom/flip fades
  (`_v2_apply_fade_fields`); the baseline-red
  `test_drop_slot_color_smoke_and_snap` (KeyError `slot_colors_from`) asserts the
  LEGACY snap contract and went stale when v2 went live — test drift, likely not
  the operator's bug itself.
- CONFIRMED the baked-color mechanism: `resolve_slot_colors` returning `{}` means
  no palette injection and the cue renders its baked colors. In the v2 path `{}`
  happens when `_v2_active_dressing()` is None (no identity dressing for the
  current deck at dispatch), besides the designed exempt/color_source cases.
- UNKNOWN which trigger the operator actually saw — leading candidate: looks
  dispatched in the window between track load and the identity record arriving
  (site-2 read latency), or a deck/record mismatch. NEEDS: which cues showed
  wrong colors (operator, next desk moment), then log correlation.

## Part F — mid-section strobe demotion (operator verdict ~16:3x, AWR-180)

Operator (verbatim intent): wall drop strobe cues should not fire in the middle of
a drop section unless the track is aggressive (isoxo/dubstep class). Trigger case:
Sexy ~4:50 chorus marker fired a wall strobe mid-drop-section (Sexy aggression
reads 0.12).

Seams (verified at HEAD): `_led_drop_impact_allowed`
(`led_dispatch_policy.py:2181-2196`) already distinguishes section-start impacts
(`previous in _LED_DROP_IMPACT_PREDECESSORS` = up/low/buildup/breakdown, :174) from
chorus→chorus re-hits (allowed as impact #2 via `LED_MAX_DROP_IMPACTS = 2`).
Per-track `aggression` exists in `led_identity_v2.py` identity scores
(`AGGRESSION_SPLIT` already a named constant).

Rule shape (general, aggression-gated class demotion — never per-track): when the
drop impact is a MID-SECTION re-hit (the chorus-re-hit branch, not the predecessor
set, not a smart-drop crossing) AND track aggression < threshold, demote look
selection away from strobe-class looks. Natural seam: a new narrowing term in
`_led_look_preference_predicate` (:2031) — fail-open like every other term, so an
all-strobe bank never empties. Strobe-class membership from look config
(`allow_strobe`), not a hardcoded name list. Threshold: operator desk calibration;
start from `AGGRESSION_SPLIT` and let his verdicts move it. Related parked design
(smart-drop main-vs-continuation classification) gets its first concrete demand
here — note the connection, do not build the full classifier this round.

## Doctrine note (laser, for the record)

Operator correction: growl is NOT a hard laser rule — "one of the many elements
that warrant a laser drop. violence tier is also a factor." Any eventual
laser-gate consumer (post-P1) is multi-factor (tier AND growl AND future earned
elements), never growl-only.

## Round protocol

1. Implement Bug 1 now; Bug 2 after the flavor verdict lands in this spec.
2. Suite at the named five-red repo-root baseline (`python3 -m unittest discover
   tests` from repo root). Extra reds: STOP and report, do not fix unrelated tests.
   Hard checks: `tools/check_docs_metadata.py`, `check_agent_contracts.py`,
   `check_docs_drift.py`.
3. **STAGE ONLY**: commit to main, do NOT restart the bridge, do NOT touch live
   config or the running process. The executive batches the restart with the
   operator.
4. Reviewer (this lane's Fable lead) reads the diff before the staged report goes
   to superman3.
