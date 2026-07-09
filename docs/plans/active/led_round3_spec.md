---
doc_status: current
truth_level: code-verified
last_verified_date: 2026-07-09
last_verified_commit: HEAD-2026-07-09-overnight
validation_scope: implementation spec for LED round 3 (operator override 2026-07-09: ships tonight at executive defaults instead of pad-A/B gating; all rates dialable for morning tuning); grounded in the AWR-152/156 verdict trail and the lab-verified fixes; bridge DOWN and stays down
---

# Codex Implementation Spec - LED round 3: Hz migrations + rainbow/firework promotions + center-burst fix (AWR-161)

Operator override (2026-07-09 overnight): round 3 ships tonight WITH round 2's
conventions. The earlier pad-A/B gating for feel-changing migrations is
OVERRIDDEN — land at the executive reference defaults (hz 6.0 / duty 0.3
equivalents), everything dialable per look for morning tuning.

## Part A - Context (verified)

1. `_hz_strobe_on` (AWR-156) is the production Hz gate — time-based, frame-
   timing-aware, caps 10 Hz / 0.5 duty. The remaining BEAT-TIED gates use
   `int(beat * 16.0) % 2 == 0` (~17 Hz at 128 BPM, BPM-dependent): five
   legacy frame-effect sites (`govee_frame_renderer.py` — drop chase :456
   area, post-drop chase :493 area, post-drop nebula :514 area, drop
   white-shatter :525 area, drop nebula :660 area at pre-156 numbering) plus
   the same-idiom slot-cue gates (`_slot_post_drop_chase`,
   `_slot_post_drop_nebula`, `_slot_drop_chase`, `_slot_drop_nebula`,
   `_slot_post_drop_center_comet`) — RE-LOCATE ALL SITES AT HEAD by grepping
   `int(beat * 16.0) % 2` and `int(cue_beat * 16.0) % 2`; line numbers have
   shifted since AWR-156. The buildup strobes are ALREADY time-based sine
   ramps — EXCLUDED, do not touch (executive-verified).
2. Lab-verified promotions ready (gitignored `config/led_lab/effects_lab.py`
   is the reference — port logic, never import):
   - `comet_rainbow_ordered`: ordered spectrum by strip position + time
     cycle; `travel_per_beat` param = beat-locked pixel advance (operator
     accepted the movement fix; absent param = legacy `loop_beats` pace —
     the accepted-as-is post-drop feel).
   - `drop_firework_explosion_2`: beat-tied surge (the hit) + time-based
     ember field; RENDER-REGRESSION FIX verified in lab: surge resolves down
     to `bg_hold` (0.7) and embers blend-replace — measured ember contrast
     164/255 (was 35, invisible).
3. `_slot_drop_center_burst` lights EVEN pixels only (`if idx % 2 != 0:
   continue`) — gappy on the 60-segment strip (round-3 residual from the
   audit skeleton verdicts).
4. Contracts: `led_govee` + `config_schema`.

## Part B - Tasks (one commit each, explicit paths)

### Absolute Rules
- Parallel lanes own `rb_state_reader.py`/`rb_memory.py` (Track A) and
  `state_manager.py`/`drop_presentation.py` (Track B) — do NOT touch those
  files. Shared docs (registry, matrices, doc_index, subsystem cards):
  re-read FRESH immediately before each edit, explicit-path commits, expect
  HEAD-lock races (retry, never rewrite). Auto-sync may fragment commits —
  verify via git log, never treat as failure.
- NO bridge starts; live config read-only; `config/led_lab/**` reference-only.
- Must not change: buildup strobes; `_hz_strobe_on` itself; nebula slot-5
  white semantics (AWR-156 Task 9 state); knob #4 per-spawn mapping; AWR-149
  rotation mechanics; emergency/manual/tactical blackout paths.

### Task 1 - Hz-gate migration (all remaining beat-tied strobe gates)
Replace every located `int(beat*16)%2`/`int(cue_beat*16)%2` strobe gate with
`_hz_strobe_on(local_t, params)`. Per-effect params default hz 6.0 /
duty 0.3 (the accepted reference feel); add `hz`, `duty` to each affected
effect's `REALTIME_EFFECT_PARAM_KEYS` allowlist entry so every look can be
dialed morning-after without code. Sparkle re-seed `beat_bucket` uses of
`int(beat*16)` are NOT strobe gates — leave them.

### Task 2 - Rainbow pair promotion
Port `comet_rainbow_ordered` into `govee_frame_renderer.py` as frame effect
`rainbow_ordered` (hue from position + time; brightness only dims; heads via
the AWR-156 peak-normalized helper; `travel_per_beat` beat-locked when
present, `loop_beats` legacy pace when absent). Allowlist `{"width",
"cycle_beats", "rainbow_span", "travel_per_beat", "loop_beats",
"duration_beats"} | _SYNC_PARAM_KEYS`. Example config: looks
`rt_rainbow_drop` (drop bank; params width 6, cycle_beats 1,
travel_per_beat 30, color_source baked) and `rt_rainbow_post_drop`
(post_drop bank; width 2, cycle_beats 8, NO travel_per_beat — accepted
as-is legacy pace); `drop_pairs` entry `rt_rainbow_drop → rt_rainbow_post_drop`.

### Task 3 - Firework explosion promotion, contrast-gated
Port `drop_firework_explosion_2` as frame effect `drop_firework_explosion`
(surge → bg_hold resolve-down; time-based ember field reusing the remnants'
ember machinery where sensible; palette-tied spark params). Allowlist its
params. Example config look `rt_drop_firework_explosion` (drop bank, baked
off-white bg + amber/white sparks per the lab entry) with `drop_pairs` →
`rt_post_drop_firework_remnants` (the AWR-149 explosion→remnants arc, now
real). **GATE: a renderer test must MEASURE post-surge ember contrast — max
per-pixel deviation from the background ≥ 60/255 at default params. If the
ported effect cannot pass, DROP Task 3 entirely (no look, no pair), note it
in the report and registry row, and continue — the operator's condition is
promote only-if-verified.**

### Task 4 - Center-burst pixel fix
`_slot_drop_center_burst`: remove the even-pixels-only gate so every pixel
inside the pulse renders (geometry otherwise unchanged). Update any
determinism fixtures that encoded the gaps.

### Task 5 - Tests
Hz migrations: every migrated effect flashes at hz-derived rate independent
of BPM (reuse the AWR-156 gate-test idiom), params dialable, allowlists
present (C5 guard). Rainbow: beat-locked travel advances travel_per_beat px
per beat at two BPMs; legacy path byte-stable for the post-drop look; hue
independent of brightness. Explosion: the contrast measurement test (the
Task 3 gate); ember time-base. Center burst: all-pixel coverage; slot-band
discipline (main 0-2 / accent 2-4) unchanged.

### Task 6 - Contract docs (final commit)
`led_govee` + `config_schema` docs_update in full (fresh re-reads before
each shared-doc edit); AWR-161 registry row (implemented / software-tested;
note the explosion gate outcome explicitly); suite (known six reds) + three
hard checks.

## Part C - Invariants
- Strobe ceiling: nothing exceeds 10 Hz / 0.5 duty (gate caps); every
  strobing effect stays in `REALTIME_STROBE_EFFECTS`.
- Slot 5 discipline unchanged (nebulas tinted, `BAKED_WHITE_SLOT5_EFFECTS`
  baked, remnants background tinted).
- An un-mirrored live config: migrated gates run at code defaults (6.0/0.3)
  — this is the operator-overridden intended change; everything else needs
  the mirror to appear.
- AWR-150 substitute pool stays non-empty in the drop bank.

## Part E - Acceptance
- [ ] Tasks 1-6 (Task 3 possibly dropped by its gate — explicitly reported
  either way), one commit each, explicit paths.
- [ ] Suite at known-six-reds; hard checks green; C5 allowlists tested.
- [ ] Operator summary: every remaining strobe now runs on the wall-clock
  Hz dial (same feel at any BPM, tunable per look in the morning); the
  rainbow drop/post-drop pair is a real look pair with the beat-locked
  speed he approved; the firework explosion joined only after the fix
  passed its measured visibility check (or a clear note that it stayed in
  the lab); the center burst stops skipping every other pixel.
- [ ] Print exactly AWR161-DONE with real suite numbers above it, or
  AWR161-BLOCKED plus the reason.
