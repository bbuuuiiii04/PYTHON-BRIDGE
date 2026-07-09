---
doc_status: current
truth_level: design (planned; nothing here is implemented)
last_verified_commit: f95a53b
last_verified_date: 2026-07-09
validation_scope: >
  F3 (LIGHTING ENGINE v2 Feature 3 — the blend) complete design: state machine,
  per-phase LED/laser behavior, F2 interaction table, precedence, fail-toward-today.
  Every current-behavior claim was verified at HEAD f95a53b with file:line evidence.
  Evidence appendix measured from the 2026-07-09 live session recording. DESIGN ONLY —
  no implementation authorized; the Part A–E spec skeleton lives at
  docs/plans/active/f3_blend_spec.md. SOFTWARE-VALIDATED claims below refer to the
  seams F3 composes with, never to F3 itself.
---

# F3 blend design — mixing two songs (LIGHTING ENGINE v2 Feature 3)

Status: **planned** (design complete; implementation NOT authorized).
Parent authorities: `lighting_engine_v2_authority.md` §7 (the operator blend contract),
`LIGHTING_ENGINE_V2_DESIGN.md` §6/§7/§15.6 (arbiter rank 4, kill matrix row, operator
F3 decisions), `active_deck_authority.md` (which deck leads — F3 never overrides it).

## 0. What F3 is, in one paragraph

Today the room follows exactly one deck: the active-deck authority picks a leader from
the operator's upfaders + LOW-EQ, and on a flip the LED identity soft-flips to the new
track (`led_color_engine.py:1068-1084`). The transition itself is invisible — the room
doesn't know a blend is happening. F3 makes the blend a designed moment: as the
operator's hands bring the incoming track into the mix (fader rising, LOW opening), the
incoming track's colors enter the room the same way — accents first, then the base wash,
then a one-bar resolve when the mix commits. The operator's hands are the boss: the
lights never take longer than his fader ride; a slam snaps. F3 is a **color-only
painter** — it never decides which deck leads, never fires or moves a moment, never
changes intensity, and when its signals die it degrades to exactly today's behavior.

## 1. Ground truth at HEAD (all confirmed, f95a53b)

| Fact | Evidence |
|---|---|
| Mixer reads exist: per-tick `MixerAuthoritySnapshot` with deck 1/2 `upfader_raw` (0–1023) + `low_raw` (0–255) → norms + labels | `rb_state_reader.py:534-596` (`_tick_mixer`, `_mixer_reading`) |
| Snapshot consumed centrally: stored on `StateManager`, reruns the resolver; fail-closed `valid=False` snapshots on missing offsets/unreadable chains | `state_manager.py:1401-1405`; `rb_state_reader.py:544-569` |
| CFX isolation pattern to copy: store-only, no resolver rerun, no authority coupling, inert-by-construction when chains absent | `rb_state_reader.py:598-618`; `state_manager.py:1407-1412` |
| Active-deck authority is a pure resolver over playing + upfader label + LOW label, 0.15 s stability, 1.0 s mixer-stale window | `active_deck_resolver.py:7-14,59-215` |
| Fader labels: `down` ≤ 0.02, `top` ≥ 0.98, else `audible`; LOW `neutral` = 0.5 ± 0.03 | `active_deck_resolver.py:7-11,45-56` |
| On a 1↔2 flip: gearshift check, LED hold engaged, per-deck runtime reset | `state_manager.py:2042-2064` |
| F1 identity + soft flip are implemented: on active track-key change the engine fades outgoing slot colors over `soft_flip_beats`; hard pivots may insert a palate reset | `led_color_engine.py:1068-1092` |
| Identities install **lazily on first active dispatch** — a loaded-but-inactive deck has no identity yet | `led_color_engine.py:1077-1078` (`_v2_install_default` only inside the track-key-change branch) |
| Per-frame slot-color interpolation exists (`slot_colors_from/to`) | `govee_frame_renderer.py:74-97` (`resolve_fade`) |
| F2 plans attach per (deck, load_gen) and are consumed for the active deck; the shared pre-drop transition window is already plan-driven | `state_manager.py:279,1556-1559,5006-5007`; `lighting_moments_v2.py:811-827` (`transition_window_for`) |
| Drop presentation fails open on active-deck change and never latches dark; gear-shift solo (tier 5) fires at handover | `drop_presentation_authority.md` (verified current 2026-07-09); `state_manager.py:2058,2066-2068` |
| The operator mixes with per-deck upfaders + LOW-EQ + filter, never the crossfader | operator-locked (`LIGHTING_ENGINE_V2_DESIGN.md:1009-1011`); confirmed in the live recording (appendix §12) |
| Blend painter is entirely NEW — today the room hard-cuts/soft-flips to the single active deck's palette; no two-track state exists | `LIGHTING_ENGINE_V2_DESIGN.md:1016-1019`, confirmed by the `led_color_engine.py` read above |

**Non-negotiable inherited laws** (authority §1): manual always wins (law 2); markers
authoritative (law 3); decorate-never-decide (law 4); drops full-scale (law 5); no double
drops (law 7). Authority §7 adds: fader-is-the-boss, near-glide/distant-trade, dipless +
single-axis, abandoned-blend-breathes-out, deck 1/2 only.

## 2. Signals — presence and the blend scalar

F3 reads **only** what already flows: the stored `MixerAuthoritySnapshot` (upfader +
LOW norms for decks 1/2), `active_deck` + its resolver reason, per-deck `playing`, the
active deck's beat clock, and the per-deck F1 identity / F2 plan. **No new reader work,
no new events** — the CFX discipline (`rb_state_reader.py:598-618`) applied one level up:
F3 is a pure consumer of a snapshot that already exists.

**Presence** — how much one deck's audio is "in the room" through his real controls
(upfader volume, LOW-EQ body):

```
presence(d) = upfader_norm(d) × (LOW_FLOOR + (1 − LOW_FLOOR) × min(low_norm(d) / 0.5, 1.0))
```

- `LOW_FLOOR = 0.35` (TUNE-LIVE): a fader-top deck with LOW fully cut still carries
  mids/highs — it is audibly present, just bodiless. 0 would call it absent (wrong);
  1 would ignore the LOW swap entirely (wrong — the bass swap is the heart of his blend).
- A non-playing deck has presence 0 regardless of fader (matches resolver eligibility,
  `active_deck_resolver.py:218-219`).
- Boosted LOW (> 0.5 norm) caps at 1.0 — boost is emphasis, not extra presence.

**The blend scalar** β ∈ [0, 1] — the incoming deck's share of the room:

```
β = presence(incoming) / (presence(incoming) + presence(leader))     (0 when the sum < 0.05)
```

Relative share, not absolute fader height, because his blends move both hands: incoming
fader rising while the outgoing LOW drops moves the *ear's* balance faster than either
control alone, and β tracks that. β is computed continuously (every mixer snapshot) but
**paints through bar-quantized presence steps** (§4) so color ownership moves bar by bar,
per the locked authority language — with one exception:

**Slam bypass** (fader-is-the-boss): if β moves ≥ `SLAM_DELTA = 0.5` within ≤ 1 beat,
quantization is bypassed and the painter snaps to the target state on the next frame.
Chops (repeated fast cuts) therefore chop the room along — each cut is a slam.

## 3. The blend state machine

One instance, decks 1/2 only. **Leader** = `active_deck` per the authority — F3 never
picks it, never argues with it, and rides *within* its transitions. **Incoming** = the
other deck while it qualifies. All thresholds are TUNE-LIVE starting values; the
appendix-measured shapes (§12) informed them.

| State | Entry condition | What the room shows |
|---|---|---|
| **SETTLED** | default; incoming disqualified or β below enter | Leader's F1 identity, untouched. F3 paints nothing — byte-identical to today. |
| **INCOMING** | other deck playing AND upfader label ≠ `down` AND β ≥ `BETA_ENTER = 0.10` sustained `ENTER_BEATS = 4` | First accent step: incoming's accent pair (slots 3–4) begins taking offbeat hits / comet spawns at step-1 weight. |
| **BLENDING** | from INCOMING automatically (same conditions holding) | Presence steps rise/fall bar-by-bar with β (§4). Past `BETA_MID = 0.5` sustained 4 beats, the base wash (slots 0–2) starts morphing (near-glide) or trading (distant, §4). |
| **COMMIT** | β ≥ `BETA_COMMIT = 0.85` sustained 4 beats AND `active_deck` == incoming | One-bar **resolve bloom** (arbiter rank 4 — skipped entirely if it lands inside a rank 1–3 claim; skip-not-queue). Then → SETTLED on the new leader. |
| **ABANDON** | from INCOMING/BLENDING: β < `BETA_ENTER` sustained `ABANDON_BEATS = 4`, or incoming stops / fader hits `down` | Presence steps release bar by bar (breathe out, same staircase down). No resolve. → SETTLED on the unchanged leader. |

Transitional facts the table can't show:

- **The authority flip is not the commit.** `active_deck` can flip mid-blend (bass
  dominance, fader top — `active_deck_resolver.py:125-172`) while β sits at 0.6. F3 then
  swaps its leader/incoming roles *in place* — β re-expresses as the new incoming's share
  (β′ = 1 − β), painted state is continuous (no visual event at the flip itself). COMMIT
  requires both the flip AND β ≥ commit — "crossed and held", per the authority's
  no-resolve-unless-crossed-and-held rule.
- **A flip without any blend** (instant cut, both-faders-top tie flip, resolver fallback
  flip) — β never entered: F3 stays SETTLED and the flip renders exactly as today: F1's
  soft flip (`led_color_engine.py:1080-1084`). F3 adds nothing to a non-blend flip.
- **Re-entry during ABANDON** (he brings it back): β ≥ `BETA_ENTER` again → straight back
  to BLENDING at the current (partially-released) step — no restart, no flicker.
- **Beat clock**: bar quantization runs on the leader's beat clock; on a mid-blend flip it
  re-anchors to the new leader. One step boundary may shift by a fraction of a bar —
  accepted (steps are presence weights, not scheduled cues).
- **Track load mid-blend** (either deck): that deck's identity/plan re-derive on load as
  today (`load_gen` bump, `state_manager.py:2210-2229`). A load on the *incoming* deck
  resets the blend to INCOMING re-detection (its presence usually collapses anyway since
  RB stops the deck on load); a load on the *leader* is today's behavior (LED hold,
  `state_manager.py:2217-2218`) and F3 releases to SETTLED.

## 4. What paints, per phase (LEDs)

F3 speaks **only** the color-slot contract (design §8): slots 0–2 base ramp, 3–4 accent
ramp, 5 white. It is a transform on the slot colors the F1 identity supplies — applied at
the existing single conduit (`params` → `_v2_resolve_color` path, `led_color_engine.py:1101+`),
never a new render path.

1. **Accents first** (INCOMING → BLENDING below midpoint): slots 3–4 draw from the
   incoming identity's accent pair, weighted by the current presence step (8 steps,
   bar-quantized). Step weight = fraction of accent events (offbeat hits, comet spawns)
   drawing incoming colors — ownership alternation, not per-frame color mixing.
   Slots 0–2 and 5 untouched.
2. **Base morph past midpoint** (BLENDING ≥ mid):
   - **Near identities** (same zone or adjacent — reuse the `is_hard_pivot` distance,
     `led_color_engine.py:1088`): slots 0–2 glide in palette space between the two base
     ramps, driven by smoothed continuous β (the per-frame lerp seam already exists:
     `resolve_fade`, `govee_frame_renderer.py:74-97`).
   - **Distant identities**: never smear through grey (locked). Bases alternate ownership
     with rising incoming share (same staircase idiom as accents) and **snap-commit** to
     the incoming base at COMMIT. No frame shows a muddy in-between.
3. **Resolve** (COMMIT): a single one-bar bloom — brightness swell inside the incoming
   identity's colors, the "we're in the new track now" marker. Arbiter rank 4: skipped
   (not queued) inside pre-drop/drop/landing claims.
4. **Breathe out** (ABANDON): the accent/base staircases step back down bar by bar. No
   bloom, no flourish — the room just settles back.
5. **Dipless + single-axis** (locked): F3 never changes total room brightness mid-blend —
   every painted change is a color change. The only intensity F3 ever touches is the
   rank-4 resolve bloom, which is itself skipped inside any window where intensity is
   already in motion.
6. **Same-vibe hold-tightness** (operator §15.6: "zones are the groups"): when both
   identities share a zone, the base morph is scaled down by `HOLD_TIGHTNESS`
   (default 0.7, runtime-tunable 0..1): accents still trade (the room acknowledges the
   blend), the base drifts only `(1 − 0.7) = 30%` of the way and completes at COMMIT via
   the soft flip. Same-vibe mixes stay smooth; only a cross-zone mix is a real color
   change.
7. **White (slot 5) is never blended**: white is power, not identity (authority §2).
   White share stays whatever the active moment (F2) says it is.

**Integration requirement (new work, F1-side, small):** identities currently install
lazily on first *active* dispatch (`led_color_engine.py:1077-1078`), so the incoming
deck's palette does not exist pre-flip. F3 needs identity derivation at TRACK_LOADED for
both decks. Identity is a pure function of the track and its cached measurements
(authority §3 "permanent across nights"), so pre-deriving is cheap, deterministic, and
changes nothing visible until F3 reads it.

## 5. Lasers, per phase

Safe default: **F3 does not drive lasers.** Rationale: lasers are drop-only punctuation
(drop presentation authority) and rest during blends by the existing scarcity rules;
there is nothing for a blend painter to add without violating rest-vs-fire.

What lasers inherit anyway, by existing plumbing:

- Laser color follows the LED color engine on non-scripted tracks
  (`laser_color_authority.md`). During BLENDING the LED engine's accent slots carry
  incoming colors, so a laser that does fire mid-blend (leader's drop — §6 case A) cuts
  against the *blended* wash. That is correct by construction: the complement pair is
  zone-keyed, and past midpoint the room is visually the incoming zone's room.
  Named taste item (§11 T4): pin laser complements to the leader's zone until COMMIT
  instead, one constant.
- Laser personality re-resolves at the flip (`state_manager.py:2123-2131`) — unchanged.
- Gear-shift solo (tier 5) fires at handover per drop presentation — unchanged; F3's
  painting is suspended-by-mask during any `lasers_only` window (§7).

## 6. F2 interaction table — a drop landing mid-blend

F2 moments belong to the **leader** — plans are per-deck and dispatch reads the active
deck's plan (`state_manager.py:5006-5007`). F3 never creates, cancels, moves, or retimes
any of them (law 4). The composition rules, exhaustive:

| # | Scenario | What happens |
|---|---|---|
| A | **Drop on the leader mid-blend** | F2 fires exactly as designed (rank 1 pre-drop darkness → drop cue full-scale). The drop renders with the room's *current blended slot state* — if accents are half-incoming, the drop cue's accent hits are half-incoming; law 5 (full-scale) is untouched because F3 never scales intensity. **F3 freezes during rank 1–2 claims**: presence steps hold, β keeps computing, and painting resumes (jumping to the current step) when the claim ends. Freezing honors single-axis — intensity is in motion inside a drop window; color must not crawl underneath it. |
| B | **Drop on the incoming deck while it is not yet leader** | Nothing fires — by design, not omission. Markers on a non-active deck have never fired (dispatch follows `active_deck`) and law 7 forbids a second simultaneous drop presentation. The incoming drop's *colors* are already in the room as accents; its *moment* belongs to the deck only if his hands make it leader in time (case C). |
| C | **Handover lands inside the incoming track's pre-drop window** — the operator's signature move: complete the bass swap just before the incoming drop | At the flip the incoming becomes leader and its F2 plan is already attached (built at load, `state_manager.py:279`). The next `transition_window_for` read returns that drop's darkness window; whatever REMAINS of the window fires (flip 2 beats before a 8-beat-planned blackout ⇒ 2 dark beats into the hit). The drop cue itself fires on the marker at full scale regardless — a shortened blackout is cosmetic loss, a missed drop cue would be a real one, and markers are authoritative. F3 contributes nothing here except having already painted the room toward the incoming identity — the drop lands in its own colors. **Design note for the spec:** the F2 window machine must tolerate opening mid-window (elapsed portion skipped, never stretched); resolve bloom is inevitably skipped (rank 1 claim active). |
| D | **True double drop** (both decks in drop sections, both faders up) | Authority picks the leader (bass dominance/tie rules); leader's presentation renders; the other deck stays accent-only; **no special moment fires** (locked, authority §7). F3 treats it as an ordinary BLENDING hold — β typically hovers near 0.5, no commit, no resolve. |
| E | **Resolve bloom collides with a rank 1–3 claim** | Skipped, never queued (arbiter law). The blend still commits — SETTLED without the bloom. |
| F | **`lasers_only` solo / pre-dark / emergency blackout / manual hold mid-blend** | Masks win absolutely (§7). Painting is invisible while masked; the state machine and β keep running (cheap, pure); on release the room shows the current blend state. A gear-shift solo triggered *by* the handover therefore darkens the room right at COMMIT — the resolve bloom is skipped (rank 1), and the room comes back already settled in the new identity. Correct and dramatic. |
| G | **Drop during ABANDON breathing** | Leader's F2 unaffected (it was never touched). Breathing freezes during the claim like case A, resumes after. |
| H | **Stinger / palate reset / first-play bloom mid-blend** | Lower arbiter ranks (5–7) compose unchanged: palate reset only triggers on the *flip's* hard pivot (existing F1 logic, `led_color_engine.py:1085-1092`) — during an F3-committed blend the flip fade + reset compose exactly as they do today; F3's painting yields to any claim that owns intensity. |

## 7. Precedence and masks

Absolute order (nothing new — F3 slots into the existing ladder):

1. **Rank 0** (absolute): emergency blackout, LED mute, manual holds/static overrides,
   Stream Deck manual layers. F3 output is below every mask; a held manual look survives
   the entire blend (law 2). Blackout ownership rules untouched
   (`laser_blackout_authority.md`).
2. **Ranks 1–3** (pre-drop darkness + drop cue; landing move; standalone dip): F3
   freezes painting for the claim duration (case A rule). It never yields *state* — only
   *visibility*.
3. **Rank 4**: F3's resolve bloom — its only claim, one bar, skip-not-queue.
4. **Ranks 5–9** and texture/simmer: compose beneath; F3's painted slots are simply the
   colors those moments read.

F3 owns no intensity, no scheduling, no timing. Its entire output surface is: slot-color
transform + one rank-4 claim + status fields.

## 8. Fail-toward-today (signals unreadable ⇒ F3 inert)

| Failure | Behavior |
|---|---|
| Mixer snapshot `valid=False` or stale > 1.0 s (the resolver's own window, `active_deck_resolver.py:12`) | Painter freezes in place for `FAIL_GRACE_S = 2`, then releases to the leader's own identity over 4 beats (the F1 soft-flip idiom). This is the authority-accepted "time-based stand-in" (§2): a Rekordbox upgrade that silently kills the offsets leaves the room on plain F1 handover behavior — today's behavior, no new dark mode. |
| `active_deck = 0` (idle) | F3 → SETTLED-idle; `_enter_idle_no_audible` already resets all LED state (`state_manager.py:2137-2187`); F3 adds its own reset to that body. |
| Either blend deck is **scripted** | F3 paints nothing for the whole pairing (scripted sovereignty, authority §11 — v2 stands down; a blend *into* a sovereign authored show must not repaint it, and a blend *out of* one has no F1 identity to blend from). Handover = today's. |
| F1 off | Blend auto-collapses to the soft flip; β keeps computing, paints nothing (kill-matrix dependency rule 1, `LIGHTING_ENGINE_V2_DESIGN.md:593-594`). |
| F3 off (own kill switch) | Handover = F1 soft flip only (dependency rule, authority §11). Off ⇒ the F3 code path is never entered ⇒ byte-identical rendering. |
| Realtime transport loss | v2 suspends to v1 fallback exactly as today (authority §11); F3 state keeps computing, invisible. |
| F2 off, F3 on | Legal: the blend paints colors; drops render as v1 cues in those colors. Case C's window logic simply never runs (no plan consumer). |

Nothing in F3 can create a dark room: it has no intensity authority except the rank-4
bloom, which only ever *brightens*.

## 9. Modes and toggles

| Control | Values | Default | Notes |
|---|---|---|---|
| F3 kill switch (`/f3` config block) | on/off | **off at ship** | flips at look boundary like every engine switch |
| Transition mode (operator runtime toggle, delegated design §15.6) | `blend` / `handover` | **`blend`** | `handover` = the full painter stands down and every flip is F1's proven soft flip; the state machine still runs for status/tuning visibility. Default is `blend` because it is the feature — but it ships behind the master F3-off default, so the first live session opts in twice (taste item T1). |
| Within-vibe hold-tightness | 0..1 | **0.7** | §4.6; runtime-tunable, same-zone blends only |
| TUNE-LIVE constants | `LOW_FLOOR`, `BETA_ENTER/MID/COMMIT`, `SLAM_DELTA`, step count, `FAIL_GRACE_S` | §2–§3 values | all named constants in one place, per repo hygiene; starting values sanity-checked against the appendix measurements |

## 10. Observability

Per authority §14 (which already promises a live blend scalar): status exposes
`f3_state` (settled/incoming/blending/abandon + last commit), `blend_beta` (raw + current
step), per-deck presence, `f3_reason` (one line: which signal moved last, or which fail
rule is active — the D§12 reason-string contract). Log INFO on state transitions only;
per-snapshot math stays silent (log-style rule: outcomes at INFO, high-frequency at
DEBUG).

## 11. Operator taste calls (NAMED list — for his desk, not mid-mix)

- **T1 — first live default:** ship F3 off; when he first enables it, `blend` mode is the
  default. Veto shape: "start me in handover mode" (one config default).
- **T2 — LOW_FLOOR = 0.35:** how present a bass-cut deck still is. His bass-swap feel
  lives in this constant. Veto: one number, live-tunable.
- **T3 — hold-tightness default 0.7** (same-vibe blends stay smooth). Veto: one number.
- **T4 — laser complements during a blend** follow the blended LED wash (default) vs pin
  to the leader's zone until commit. One constant (§5).
- **T5 — resolve bloom keep/kill:** the one-bar commit bloom is tasteful-subtle by
  design; if it reads cheesy live, killing it is one switch (the state machine is
  unaffected).
- **T6 — BETA_ENTER = 0.10 / ENTER_BEATS = 4:** how early the incoming colors start
  showing. Earlier = the room telegraphs his blend sooner.

## 12. Evidence appendix — measured blend shapes (2026-07-09 live session)

Source: `local/sessions/f3_live_feedback_20260709.jsonl` (schema 2, 423 MB, gitignored),
recorded from the operator's real afternoon mix; analyzed immediately after it ended.
84,247 valid `mixer_state` snapshots over 3,266 s (54.4 min) at 25.8 snapshots/s — the
signal rate alone retires any "is the read fast enough" concern. Method: read-only
script over the raw records; **β below is computed through §2's own formula**
(`LOW_FLOOR = 0.35`, relative share), so β-numbers describe how the *proposed* scalar
would have read his hands — they are calibration evidence, not resolver facts. Episode =
both decks playing with upfaders above `down`, ≥ 1 s, gaps < 2 s merged.

**Measured: 7 blend episodes — 5 completed handovers, 2 bailouts, 2 slam events.**

| ep | dur | leader | β_max | β@flip | flip at | LOW-swap at | outcome |
|---|---|---|---|---|---|---|---|
| 0 | 29.1 s | 1→2 | 1.00 | 0.74 | +0.4 s | — | handover, long ride-out (~29 s) |
| 1 | 24.0 s | 2 (held) | 0.16 | — | — | — | **bailout** (layering) |
| 2 | 70.9 s | 2 (held) | 0.26 | — | — | — | **bailout** (layering) |
| 3 | 12.4 s | 1→2 | 1.00 | 0.53 | +0.6 s | in-LOW +2.2 s | handover, fastest, 1 slam |
| 4 | 41.1 s | 1→2 | 1.00 | 0.74 | +0.4 s | out-LOW cut at end | handover, ~41 s ride-out |
| 5 | 76.5 s | 1→2 | 1.00 | 0.74 | +36.1 s | out +35.2 s / in +35.4 s | handover, **bass-swap-led**, 1 slam |
| 6 | 38.5 s | 2→1 | 1.00 | 0.73 | +13.0 s | out +8.9 s / in +12.6 s | handover, **bass-swap-led**, reverse direction |

What the numbers say, against the design:

1. **The flip is early; the blend is long — flip ≠ commit is real.** Durations: median
   38.5 s (12.4–76.5 s). In every completed handover the authority flip left 12–41 s of
   genuinely dual-audible tail behind it. A resolve fired at the flip would be wrong five
   out of five times; crossed-and-held (§3 COMMIT) is the correct trigger. β reached 1.00
   in all five handovers, so `BETA_COMMIT = 0.85` fires in all of them, always after the
   flip.
2. **His flip point is consistent: β@flip ≈ 0.74 (0.73/0.74/0.74/0.74, one 0.53).**
   Through the §2 formula, the resolver hands over right around three-quarters incoming
   share. `BETA_MID = 0.5` therefore begins the base morph *before* the flip in his
   normal blends — the room is already leaning incoming when authority moves. The
   staircase between 0.10 and 0.74 has 12–76 s of body to climb in.
3. **The bass swap precedes the flip by 0.4–4.1 s** in the two swap-led handovers (ep5:
   LOW-out +35.2 s → LOW-in +35.4 s → flip +36.1 s; ep6: LOW-out +8.9 s → LOW-in
   +12.6 s → flip +13.0 s). The LOW term in presence (T2, `LOW_FLOOR`) is doing real
   work — an upfader-only scalar would have missed the move that actually decides his
   handovers.
4. **Bailouts are real and long**: 24.0 s at β ≤ 0.16 and 70.9 s at β ≤ 0.26 — he rides
   a second track quietly underneath for a minute-plus without ever handing over. With
   `BETA_ENTER = 0.10`, F3 would show step-1/2 incoming accents through these passages
   and breathe them back out (ABANDON) — arguably the right room behavior (the layer is
   audible; the room acknowledges it quietly). If he finds it chatty, T6 raises
   `BETA_ENTER` above the layering band his bailouts sat in (0.16–0.26 → e.g. 0.30).
5. **Slams exist** (2 events, ≥ 0.5 fader travel in < 0.5 s, one inside the fastest
   12.4 s handover): the §2 slam bypass has real inputs. Cue-style episode starts
   (3 of 5 handovers begin with the incoming fader already high — flip within 0.6 s of
   dual-audible) mean INCOMING may be entered at high β directly; the state machine
   handles that (entry conditions are level-based, not path-based).
6. **Both directions occur** (ep6 is 2→1); nothing in the machine is deck-asymmetric.

Honest limits: n = 5 handovers, one session, one operator (that operator is the entire
user base, but taste varies by night); β numbers are formula-relative; episode edges
depend on the 0.02 audible threshold. All §2–§3 constants stay TUNE-LIVE — this appendix
sets their starting values and proves the signal shapes exist; his eyes stay the gate.

## 13. Provenance and claim labels

- **Confirmed** (code at f95a53b): every row of §1; the lazy-identity-install fact
  (§4 integration requirement); the CFX isolation pattern; resolver constants.
- **Operator-locked / authority** (design inputs, not re-decided here): the seven laws;
  §7 blend contract language (accents-first, fader-is-the-boss, near-glide/
  distant-trade, dipless/single-axis, breathe-out, no-double-drops); "zones are the
  groups"; transition-mode + hold-tightness as delegated toggles; mixer-signal 7.2.11
  pin with time-based degradation accepted.
- **Decided here (delegated design authority, veto-open):** the presence formula and
  relative-share β; bar-quantized 8-step ownership staircase with slam bypass; the state
  machine and its thresholds; freeze-during-claims (case A); the shortened-blackout rule
  (case C); scripted-pair stand-down; lasers untouched by default; the §11 taste list.
- **TUNE-LIVE:** every named constant in §2–§3 and §9. Starting values only; the
  appendix measurements (§12) and his eyes are the calibration path.
- **Unknown:** Govee visual latency during fast slams (inherited unknown); whether
  8 steps reads smooth or stepped on the real strips (live gate).
