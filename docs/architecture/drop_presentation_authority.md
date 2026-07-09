---
doc_status: current
truth_level: operator-authoritative target behavior
last_verified_commit: HEAD-2026-07-09-awr159
last_verified_date: 2026-07-09
validation_scope: behavior contract, implemented and software-tested against it; no live or hardware validation implied
---

# Drop Presentation Authority

Status: AUTHORITATIVE TARGET BEHAVIOR; IMPLEMENTED / SOFTWARE-TESTED (Package 3 of AWR-119, landed 2026-07-04; AWR-135 section-length hold update, AWR-138 impact re-entry update, AWR-139 true-drop section gate landed 2026-07-07, AWR-159 cancel-wire + honest-arms round landed 2026-07-09). SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED — the operator's live pass is the only remaining gate. Implementation: `drop_presentation.py` (planner/ladder/session/learned-store/window machine), base suppression in `soundswitch_laser_player.py`, wiring in `state_manager.py`, hot-cue tag reading in `filepath_resolver.py`, config in `led_config.py` / `config/led_look_director.example.json`. Known limitations vs. this document, deliberate and reported: (1) **narrowed by AWR-159** — a MANUAL arm's own visibility no longer depends on the Laser Director's `is_enabled()` flag (it fires on `base_live`/unmasked/role alone; the physical lasers run on the SoundSwitch pack path independent of that flag), so a manual arm is no longer inert just because the Director is disabled. The remaining gap: impact detection itself still reuses the Laser Director's own `drop_crossing` decision, so if the Director object is never constructed at all (`None`, truly unconfigured rather than merely disabled), no impact tick ever arrives and NEITHER manual nor auto tiers can fire — matches the operator's actual setup, where the Director is configured and only its enable flag gets toggled; (2) **FIXED by AWR-159** — the "manual interaction" fail-open trigger is now wired: pressing the Solo pad while a window is open (`active` feedback) sets a one-tick request that `_drop_presentation_tick` feeds into the WindowMachine as `manual_interaction=True` the very next tick, which was already implemented and tested at the window-machine level but previously had no caller; (3) a `lasers_only` solo that re-enters from inside an already-open window fires at impact without the LED pre-dark countdown because pre-dark only runs from idle.

This document defines which fixtures fire on which drops. Behavior that
differs from this document is a regression unless this document is
intentionally updated. Code-grounded design detail lives in
`docs/plans/active/streamdeck_palette_control_design_spec.md` Part C.9.

Sibling authorities: `palette_control_authority.md` (the deck surface),
`laser_color_authority.md` (laser color), `laser_blackout_authority.md`
(blackout ownership).

## Meaning

Since the Govee LEDs took over ambient duty, **lasers are drop-only
punctuation — and most drops don't even get them.** Every drop section is dealt
exactly one of three presentations by the true drop that starts the section:

| Presentation | Frequency intent | What the room sees |
| --- | --- | --- |
| `leds_only` | the majority | Govees carry the drop; lasers stay dark. |
| `leds_plus_lasers` | the track's biggest moments | Today's full look. |
| `lasers_only` ("Laser Solo") | rare, always operator-traceable | Govees black out; lasers alone. Preceded by a full-dark beat. |

The operator's governing rule: a Laser Solo is *"the whole club saw it
coming"* AND *"the track everyone came for."* Therefore **a Laser Solo is
never a dice roll** — every solo traces to an operator signal (press, hot cue,
learned history, his own mixing) or a night-relative superlative. **There is
zero randomness anywhere in this policy.**

## Vocabulary

| Term | Meaning |
| --- | --- |
| true drop | For presentation windows, a drop decision whose runway is greater than 0.0 beats: contiguous breakdown (`low`) or buildup (`up`) immediately before the impact. Breakdown-only runways count. A runway-less marker can still drive laser/LED look bursts, but it cannot open or re-enter the section's presentation unless the operator explicitly overrides it with a Solo arm or hot-cue tag. |
| runway | Consecutive beats immediately before an impact whose phrase role is breakdown or buildup, walking backward, stopping at the first beat that is anything else. A groove between breakdown and buildup resets it (tension released = clock restarts). |
| drop window | Impact → end of the smart-phrasing drop role. A newer true-drop impact can re-enter the window with its own planned presentation and re-stamp the cap; a runway-less marker inside the same section leaves the existing presentation alone. `drop_window_cap_beats` is a 192-beat stuck-role backstop, not the expected release. The shared phrase authority — never an LED- or laser-private timer. |
| pre-dark | Govees joining the lasers' existing pre-drop blackout for the final `led_predark_beats` (default 4) before a solo's impact: total darkness into the hit. |
| session | One bridge process lifetime. Damper counters and the runway record reset with it; the learned store persists across sessions. |
| learned store | The persistent per-track memory of the operator's manual solos (`local/state/laser_solo_learned.json`), keyed by `content_id` + the drop's **beat position** (±2-beat lookup tolerance — survives Rekordbox re-analysis reindexing; operator 2026-07-04). |

## The Ladder

First match wins, evaluated per true drop. Auto-solo tiers (4-6) fire at most
**once per track**; manual and hot-cue solos are exempt from that cap.

1. **Mute pads** — absolute manual room state (see `palette_control_authority.md`).
2. **Laser Solo pad** — one-shot manual arm; also the universal **veto**.
3. **Hot-cue tag** — a Rekordbox hot cue named with the marker (default
   `LASER`) on the drop.
4. **Learned solo** — a drop the operator has manually soloed before.
5. **Gear-shift solo** — a ≥ +10 BPM jump in a single mix.
6. **Record-breaker solo** — the night's longest runway, strictly beaten.
7. **Opening damper** — the session's first `opening_tracks` (default 3) force
   `leds_only`; blocks tiers 5-6 and personality lasers; manual, hot-cue, and
   learned solos are exempt (explicit curation fires even early).
8. **Finale guarantee** — a track's last true drop, when actually reached,
   always renders at least `leds_plus_lasers`, never `leds_only` (subject to
   the opening damper, rung 7 — first match wins).
9. **Track personality** — everything else: rank the track's true drops by its
   own dramaturgy (last drop first, then longest runway); the top
   `ceil(laser_ratio × N)` (default 0.4) render `leds_plus_lasers`, the rest
   `leds_only`. A pure function of track structure: **the same track presents
   identically every play** — its lighting identity.

## Solo Source Contracts

**Manual arm (tier 2).** Pressing the Solo pad arms the *next* drop impact on
the active deck — not the current beat, and a press during an already-playing
drop arms the following one. Manual arm is an explicit operator override, so it
can fire even when that marker has no runway, and even when
`plan.decision_for(beat)` has no exact match for the live beat (AWR-159 Task 2
— the plan-unavailable fallback stays for non-manual tiers only). Arming
auto-clears on track change and active-deck change, and on a stop (the arm
KEY and the pad feedback are explicitly cleared, each with one log line —
AWR-159 Task 5; before that fix the pad could keep showing "armed"
indefinitely after the deck it targeted changed). Pressing while armed
disarms. The pad pulses whenever ANY tier has a solo pending (feedback state
`pending`), and that press-to-cancel is the single veto gesture for all of
them. **Pressing while a solo window is already open (feedback state
`active`) cancels it** instead of arming the next drop (AWR-159 Task 1): the
window fails open on the very next tick exactly like any other fail-open
trigger — LEDs restore, base suppression releases — additively, never
replacing the existing automatic release conditions. Four states from the
pad's perspective: arm / disarm / veto-pending / cancel-active.

**Manual visibility and refusal (AWR-159 Task 3).** Unlike auto tiers, a
manual arm's darkness guard does not require the Laser Director enabled —
only `base_live` AND not masked AND role ∈ {drop, post_drop}. When even that
fails at the actual impact (lasers genuinely unpresentable), the arm never
silently downgrades to `leds_plus_lasers`: it refuses visibly instead — the
arm clears, one operator-facing log names the failing gate
(`base_live_false` / `masked` / `role`), and the pad shows a one-tick distinct
`refused` state. The refusal always happens before anything darkens (or
restores atomically if pre-dark had already engaged) — never a stuck-dark
window.

**Hot-cue tag (tier 3).** A hot cue whose name contains the marker
(case-insensitive), matched to the nearest smart drop within ±2 beats, makes
that drop a solo. This is the other explicit operator override, so a tagged
marker can fire even with no runway. No budget: tagging is deliberate — two
tagged anthems back-to-back fire back-to-back. A marker cue that matches no
smart drop is ignored and surfaced in status (never a crash, never a guess). Tags on
scripted tracks are ignored (see Scripted Exemption). Cue names are read from
Rekordbox's database once per track load, off the hot path (the on-disk ANLZ
cue cache is stale by construction and must not be used); a cue edited
mid-set applies the next time the track loads. **Only the configured marker
tags a solo — the operator's existing `DROP`/`BUILDUP` navigation cue names
must never trigger anything.**

**Learned solo (tier 4).** One manual solo teaches: when a pad-armed solo
actually **fires** on a drop, that `(track, drop-beat)` is recorded
(beat-position key, not list index) and auto-solos on every future play. Rules: learning happens at fire, not at arm (an armed
solo that never met a drop teaches nothing); firing on a drop that is already
tagged or learned records nothing new; the veto press on a pending learned
solo cancels it AND un-learns it (the recovery path for a press that shouldn't
stick). A missing or corrupt learned store is treated as empty with a single
logged warning — it must never crash or block the show.

**Gear-shift solo (tier 5).** At a master handover where the incoming deck's
live BPM exceeds the outgoing deck's live BPM at the moment of transition by ≥
`gearshift_bpm_jump` (default +10, upward only), the incoming track's first
true drop solos. **Live BPM on BOTH sides** (a pitched deck plays its live
tempo, not its tag), falling back to tag BPM only where live is
unavailable/stale. The comparison is one mix, never a drift accumulated across
tracks; with no valid outgoing BPM (session's first master), it never fires.

**Record-breaker solo (tier 6).** A drop whose runway strictly exceeds the
night's record solos — but only after `record_min_drops` (default 5) true
drops have been observed this session. The record crossing is detectable
mid-buildup (the accruing runway passes the old record before impact), so
arming and pre-dark engage in time. Records are tracked even when the solo is
suppressed (damper), and tracks without phrase data are invisible to this tier.

## Presentation Mechanics

- **`leds_only` suppresses the laser BASE, never via the blackout mask.** A
  manually-held laser static override must survive an `leds_only` drop, and
  the blackout owner systems must be untouched by presentation decisions
  (`laser_blackout_authority.md`). Suppression must be indistinguishable from
  "no drop autoloop selected."
- **`lasers_only` choreography:** pre-dark for the final `led_predark_beats` →
  impact with Govees dark, lasers alone → automatic restore at window end. A
  pre-dark that resets before impact (`predark → clear`) logs why
  (AWR-159 Task 4): `passed_without_drop` when the beat sailed past the
  target without an impact tick, otherwise which visibility gate failed
  (`director_disabled` / `base_live_false` / `masked` / `role`).
- A true-drop impact that lands while a window is already open asserts its own
  planned presentation and restarts the backstop from that impact beat. A
  runway-less marker inside the open window keeps the current section's
  presentation, while laser drop/post-drop look cycling still runs normally.
  Known limit: a `lasers_only` solo reached this way skips the LED pre-dark
  countdown and fires at impact, because pre-dark only arms from idle.
- **Darkness guard (auto tiers):** before the Govees are cut — checked at
  pre-dark start AND at impact — the bridge must verify lasers will actually
  be visible: laser output live and rendering a drop autoloop, no laser
  blackout/mute held, Laser Director enabled. Failing the guard falls back to
  `leds_plus_lasers`. Only the beat-capped pre-dark may ever be a fully dark
  room, and it hard-restores at impact.
- **Darkness guard (manual arm, AWR-159 Task 3):** the same check MINUS the
  Director-enabled term — `base_live` AND not masked AND role ∈ {drop,
  post_drop}. Failing THIS guard never falls back to `leds_plus_lasers`; it
  refuses visibly instead (see Solo Source Contracts above).
- **Fail-open, always:** LEDs restore and suppression releases on ANY of:
  window end, drop role change, track change, active-deck change, stop,
  manual interaction (a Solo-pad press while `active` — reachable since
  AWR-159 Task 1; the WindowMachine-level trigger predates it but had no
  caller), laser-output loss mid-window, or a predicted impact passing
  without a confirmed drop. A stuck drop/post-drop role is bounded by the
  192-beat cap. The policy can never latch a fixture dark.
- `enabled: false` restores pre-policy behavior exactly (every drop
  `leds_plus_lasers`); the mute and Solo pads keep working regardless.

## Scripted-Track Exemption

The policy applies to **autoloop (non-scripted) tracks only.** A scripted
track is a sovereign authored show: no suppression, no solos, no pre-dark, no
personality — lasers play exactly what was authored, and LEDs render only
their breakdown/buildup windows. A manual arm pressed during a scripted track
stays armed (subject to the track-change auto-clear) and can only fire on an
autoloop-mode true drop.

## Session & Counting Rules

- A track counts toward damper/spacing counters once it has been the audible
  active deck for ≥ 16 beats. Loaded-but-never-audible decks count nothing.
- Damper counters and the runway record live in memory for the session and
  reset on bridge restart. The learned store is the only persistent state.
- Decks 3/4 (mirrors) never generate presentation decisions; the policy
  follows `active_deck` authority only.

## Non-Inputs

Real audio loudness, spectral/energy models, star ratings, and randomness are
not inputs to this policy and must not become inputs without updating this
document. (Operator ruling 2026-07-04: ratings are polluted by energy-level
tagging; a dedicated playlist name is the sanctioned future bulk-curation
path if ever wanted.)

## Observability

Status must expose, per dealt drop, the presentation and a concise reason
string, e.g.: `solo_manual`, `solo_hotcue`, `solo_learned`, `solo_gearshift`,
`solo_record`, `both_finale`, `both_personality`, `leds_only_personality`,
`leds_only_damper`, `guard_fallback_both`. Plus: armed state and source,
learned-store size, tonight's runway record, damper tracks remaining, and any
unmatched hot-cue markers seen.

The bridge log must also leave an operator-visible trail for Solo pad handling:
DEBUG records mark each pad event when the bridge receives it, `perf.override`
records mark Solo feedback transitions across all five states
(`off`/`armed`/`pending`/`active`/`refused` — `pending` and `refused` added
2026-07-09, AWR-159 Task 3/5), and separate `perf.override` records mark veto
presses (including whether a learned solo was actually unlearned), cancel
presses (`[LASER] solo-cancelled by=pad`), refusals (`[LASER] solo-refused
reason=<gate>`), and stale-arm clears (`[LASER] solo-arm-cleared
reason=track_changed|deck_changed|stopped`). These records are observability
only; they must not change presentation, learned-store, or feedback behavior.

## Required Behavior Tests

1. Personality: rank/ratio correctness across 1-, 2-, and 4-drop tracks;
   outside the opening damper, the last true drop always at least
   `leds_plus_lasers`; identical plan across repeated plays.
2. Ladder precedence: a drop that is simultaneously tagged, learned, and
   record-breaking fires exactly one solo with the highest-tier reason.
3. Learned lifecycle: fire→learn→auto-solo next play→veto→un-learned;
   arm-without-fire teaches nothing; corrupt store = empty + one warning.
4. Gear-shift: fires at +10.0 in one mix; not at +9; not across two mixes of
   +5; not on the session's first master.
5. Record-breaker: strict-greater semantics; min-observation gate; groove
   resets runway contiguity; records tracked under damper without firing.
6. Damper: blocks tiers 5-6 and personality lasers for the first 3 counted
   tracks; manual/hot-cue/learned fire anyway; track-counting threshold obeyed.
7. Darkness guard: laser mute held → an AUTO-tier solo falls back to
   `leds_plus_lasers` and no pre-dark occurs; guard re-checked at impact. A
   MANUAL arm ignores the Director-enabled term and fires anyway when
   base_live/unmasked/role hold; when its own (narrower) guard still fails at
   impact it refuses visibly instead of falling back (AWR-159 Task 3) — arm
   cleared, LEDs/suppression untouched, one log line naming the gate.
8. Every fail-open trigger restores LEDs and releases suppression; a held
   manual LED mute survives all of them; a held laser static override survives
   an `leds_only` drop. Pressing the Solo pad while a window is open
   (`active`) is now one of these triggers (AWR-159 Task 1) — additive to the
   existing automatic releases, never replacing them. A hard **stop**
   (`_do_stop`) releases the window via `_drop_presentation_release_on_stop`;
   AWR-171 (D3-F1) adds the mirror release to **idle-no-audible**
   (`_enter_idle_no_audible`) so the same helper fires when the active-deck
   resolver lands on 0 mid-window — otherwise `_push_tick_inner` early-returns
   forever on `active_deck` not in (1,2) and a latched `drop_spotlight` owner
   would keep the room dark to the 192-beat cap. Fail-open beats fail-dark.
9. Scripted tracks: zero policy activity end-to-end; arm survives into the
   next autoloop track only via the allowed path.

## Implementation Notes

Planned home: the ladder, per-track plan, solo tiers, and window state machine
in `drop_presentation.py` (pure-logic-heavy, testable without hardware);
hot-cue names read from Rekordbox's `master.db` at track load (the
`Rekordbox6Database` pattern in `filepath_resolver.py` — NOT the ANLZ cue
cache, verified stale/empty library-wide 2026-07-04); base suppression in
`soundswitch_laser_player.py`; wiring in `state_manager.py`. Config block
`/drop_presentation` in `config/led_look_director.json`. The optional
`white_sand` handoff tier ships disabled (`ws_handoff_enabled: false`) with
its flesh-out recorded in the design spec Part D.
