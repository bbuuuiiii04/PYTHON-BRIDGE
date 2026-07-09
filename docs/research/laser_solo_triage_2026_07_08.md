---
doc_status: current
truth_level: measured
last_verified_commit: 96d0e07
last_verified_date: 2026-07-08
validation_scope: read-only triage of two operator-reported Laser Solo defects from the 2026-07-08 live session — mechanism confirmed against `drop_presentation.py` / `state_manager.py` at HEAD plus tonight's `~/Library/Logs/rb_ss_bridge/current.jsonl` (bridge-20260708-203103) and `/tmp/rb_ss_bridge_v2_status.json`; analysis only, no code changed, no runtime/hardware action. Fix shapes are direction, not specced implementation.
---

# Laser Solo triage — intermittent firing + no cancel (2026-07-08 live session)

**What this is.** A read-only investigation of two Laser Solo defects the
operator reported after the 2026-07-08 mix: (1) the solo *sometimes fires and
sometimes doesn't* — a dice roll from his seat; (2) there is *no way to cancel*
a solo once it has fired. Both are root-caused here against current code, with
log evidence, and both are named as pre-existing known limitations in
`docs/architecture/drop_presentation_authority.md`. This doc is the spec source
for the fix round. Nothing was modified during triage.

Claim labels: **confirmed** = verified in code + log this pass; **assumed** =
code-consistent and log-suggestive but not isolated to a single event;
**unknown** = not determinable from the evidence available.

---

## How a Laser Solo is meant to work

The "Laser Solo" pad (Stream Deck note 60 → MIDI ch3 → `Ev.LASER_SOLO_PAD`)
routes to `state_manager._drop_presentation_solo_pad_pressed`
(`state_manager.py:1598`, `state_manager.py:2786`). A press **arms the next true
drop** on the active deck to render *lasers-only*: the Govees black out so only
the lasers show ("the whole club saw it"). It is not a live effect you trigger —
it is an arm that pays off when the next drop lands. The presentation state
machine lives in `drop_presentation.py` (`WindowMachine`, planner, ladder,
session state); `state_manager.py` wires it to the 200 Hz tick.

Design intent, from `drop_presentation_authority.md:36`: a Laser Solo is
**"never a dice roll — every solo traces to an operator signal."** The
intermittency defect is a direct violation of that intent.

---

## Defect 1 — intermittent firing ("sometimes fires, sometimes doesn't")

### Log evidence (confirmed)

Tonight's log shows the same armed drop (deck 1, load_gen 12, beat 144.000)
armed four times with only one payoff:

| Wall ts | Event | Result |
| --- | --- | --- |
| 1783557830 | `solo_predark_hold` → `laser solo active` (`current.jsonl:2783`) | **FIRED** — Govees dark ~3.7 s |
| 1783557875 | `solo_predark_hold` → `clear` (`current.jsonl:2888`/`2890`) | miss — LEDs briefly dark, popped back, no solo |
| 1783557909 | `solo_predark_hold` → `clear` (`current.jsonl:3019`/`3024`) | miss |
| 1783558006 | `solo_predark_hold` → `clear` (`current.jsonl:3193`/`3199`) | miss |

One fire, three silent misses on the *same* armed drop. The `predark → clear`
transition is the fingerprint: the LED pre-dark countdown engaged (Govees briefly
dark) and then reset to idle without opening a solo window.

### Mechanism (confirmed)

A manual arm only produces a lasers-only spotlight when **four fragile
conditions all coincide on one 200 Hz tick**
(`state_manager.py:2622-2665`, `drop_presentation.py:680-699`):

1. **Impact edge that tick** — `impact_now` (the Laser Director's own
   `drop_crossing` decision) must be True at that exact tick.
2. **Exact plan-beat match** — `plan.decision_for(beat)` must find the live drop
   beat in the static plan by **exact float equality**
   (`drop_presentation.py:240`, `candidate_beat == beat`).
3. **Arm key still matches** — the arm is keyed to `(active_deck, load_gen)`;
   `armed = self._drop_presentation_armed_key == track_key`
   (`state_manager.py:2622`).
4. **Lasers "visible"** — `laser_visible` requires `base_live` **and**
   role ∈ {drop, post_drop} **and** not masked **and**
   `laser_director.is_enabled()` (`state_manager.py:2657-2665`).

The pre-dark phase (`drop_presentation.py:689-696`) **resets to idle** the moment
the beat passes `target_impact_beat` without an `impact_now` tick, **or** the
moment `laser_visible` drops. That reset is exactly the `predark → clear` seen in
the log. Four things must line up on one tick; if any slips, the arm does not
fire — and it fails **silently** (no operator-facing signal).

### The silent gates, individually

- **Laser Director enable coupling (confirmed for current state).** `laser_visible`
  requires `laser_director.is_enabled()`. Live, right now,
  `laser_director.enabled = false` in `/tmp/rb_ss_bridge_v2_status.json`, and the
  session's `last_command` was `set_laser_director` — the director was toggled
  *during* the session. `drop_presentation_authority.md:11` names this as known
  limitation #1: *"the policy is inert if the Laser Director is ever
  unconfigured."* Same arm gesture, opposite result before vs. after that toggle
  = intermittent from the operator's seat. Note the actual lasers are driven by
  the SoundSwitch pack path independently of the Director's enable flag, so
  lasers can be physically firing while `laser_visible` reads False — the guard
  then downgrades the solo even though a spotlight was possible.

- **`base_live` fragility (confirmed as a gate).** `laser_visible` also requires
  `self._drop_presentation_base_live`, which is forced False whenever
  SoundSwitch is connected (zero-frame path, `state_manager.py:3888`), on any
  pack render error (`state_manager.py:3927`), or on a missing autoloop file
  (`state_manager.py:3839`). Any of those silently downgrades a solo. Which one
  bit each specific miss tonight is **unknown** (see open item).

- **Stale arm key / active-deck flip (assumed).** The arm is keyed to
  `(active_deck, load_gen)`. Log line `current.jsonl:2871` shows
  `armed_manual:true` alongside `pending_reason:both_finale`, which means at that
  resolve tick `armed` evaluated **False** (key mismatch) even though an arm was
  latched — otherwise `resolve_presentation` would have returned `solo_manual`,
  which is checked first (`drop_presentation.py:361-363`). A re-cue/reload bumps
  `load_gen`, or the active deck resolves differently between arm and drop, and
  the arm quietly stops matching — while the pad still displays "armed". Not
  isolated to a single press this pass, hence **assumed**.

- **Exact-float plan match + single-tick edge (confirmed structural race).**
  Even with the Director enabled and the key matching, `impact_now`
  (a single-tick `drop_crossing` edge) must coincide with the tick where
  `decision_for(active_drop_beat)` returns a match under exact float equality.
  When the live beat sails past `target_impact_beat` without that coincidence,
  pre-dark resets (`drop_presentation.py:689-696`) → no fire. When `decision` is
  `None` at impact while armed, the code falls to
  `LEDS_PLUS_LASERS / "plan_unavailable"` (`state_manager.py:2643-2646`) — i.e.
  the explicit manual override is dropped to leds+lasers instead of honored.

**Net:** the manual arm — an *explicit* operator override — is gated behind four
coincidences and fails silently when any misses. That is the dice roll.

---

## Defect 2 — no way to cancel a solo once fired (confirmed)

### Before impact (pending/armed) — a cancel DOES exist

A pad press while a solo is pending cancels it: it disarms a manual arm, or
vetoes a pending auto-tier (`state_manager.py:2801-2839`). This path works and
is the designed "single veto gesture" (`drop_presentation_authority.md:82`).

### After it fires (window open, Govees dark) — NO cancel exists

Once the window is open, pressing the pad does nothing useful:

- The arm key was already cleared at impact (`state_manager.py:2690`), so the
  "disarm" branch (`state_manager.py:2801`) doesn't match.
- `last_pending` is no longer a pending non-manual tier, so the "veto" branch
  (`state_manager.py:2807`) doesn't match.
- The press falls through to `state_manager.py:2841`, which **arms the *next*
  drop** — leaving the currently-dark window untouched.

The `WindowMachine` actually has a built-in cancel: `manual_interaction=True`
triggers a universal fail-open reset regardless of phase
(`drop_presentation.py:672-678`). But **nothing in `state_manager.py` ever sets
it True** — a repo-wide grep finds it only in the test file
(`tests/test_drop_presentation.py`), never in a runtime caller. The pad press
does not feed it. `drop_presentation_authority.md:11` names this as known
limitation #2: *"the 'manual interaction' fail-open trigger is implemented and
tested at the window-machine level but has no wired state_manager-level detector
yet."*

So an active solo releases **only** on the enumerated automatic conditions
(`drop_presentation.py:701-718`): the drop/post-drop role ending, the 192-beat
cap, lasers losing visibility, or a track/deck change or stop. The operator
waits it out. **Confirmed: there is no manual cancel for an active solo.**

---

## Proposed fix shapes (direction, not specced)

Both changes route through the two functions every solo press already flows
through — `_drop_presentation_solo_pad_pressed` and `_drop_presentation_tick` —
so this is a contained change, not a rewrite.

### Fix 2 first — wire the cancel (nearly free)

The cancel hook already exists and is already tested; it just isn't plugged in.
In `_drop_presentation_solo_pad_pressed`, when the feedback state is `"active"`
(window currently lasers-only), set a one-tick flag; have
`_drop_presentation_tick` pass it as `manual_interaction=True` into
`WindowInputs`. That reuses the existing fail-open reset — restores LEDs,
releases base suppression, returns the machine to idle — with no new state
machine. Net effect: one pad becomes a clean four-state — arm / disarm /
veto-pending / **cancel-active**.

### Fix 1 — make the outcome honest (deterministic-or-visibly-refused)

The manual arm is an *explicit* override, so stop letting it die on the
Director/plan-match coincidence, and never fail it silently:

- **Honor the arm without an exact plan-beat match.** When `armed` and
  `impact_now` but `decision is None`, resolve as `solo_manual` instead of
  falling to `plan_unavailable` / leds+lasers (`state_manager.py:2643-2646`).
  Removes the exact-float-beat dependency for the one case the operator
  explicitly asked for.
- **Don't gate a manual arm's visibility on the Laser Director enable flag.** If
  lasers genuinely cannot be presented (Director truly off / no MIDI path),
  **refuse visibly** — flash the pad red + one operator-facing log line
  ("solo refused: lasers unavailable") — instead of the current silent downgrade
  to leds+lasers. That delivers "deterministic **or** visibly refused" rather
  than a dice roll.

### Logging improvement (make future misses self-explaining)

The `predark → clear` reset (`drop_presentation.py:689-696`) currently logs the
transition but not *why* it reset. Add the reset reason to that line
(`passed_without_drop` vs. `not laser_visible`, and if the latter, which gate:
Director-disabled / `base_live`-false / masked). This turns every future miss
into a self-explaining log entry and closes the open unknown below without
needing another triage pass.

---

## Open item (unknown)

Which specific gate caused each of tonight's three misses — `base_live` false vs.
Director-disabled vs. stale arm key — is **not determinable** from the current
log, which records the `predark → clear` transition but not the reset reason.
The logging improvement above resolves this going forward.

---

## Cross-references

- Behavior contract / known limitations: `docs/architecture/drop_presentation_authority.md`
  (limitations #1 and #2 correspond directly to Defects 1 and 2).
- Implementation: `drop_presentation.py` (planner / ladder / session / window
  machine), wiring in `state_manager.py`, base suppression in
  `soundswitch_laser_player.py`.
- Evidence: `~/Library/Logs/rb_ss_bridge/bridge-20260708-203103.jsonl`
  (symlinked `current.jsonl` at triage time), `/tmp/rb_ss_bridge_v2_status.json`.
