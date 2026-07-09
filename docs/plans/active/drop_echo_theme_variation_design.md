---
doc_status: current
truth_level: design-note
last_verified_commit: d93f047
last_verified_date: 2026-07-09
validation_scope: >
  Design note (NOT an implementation spec) for AWR-178: theme-and-variation
  drop echoes — the one surviving 2026-07-09 creative proposal (#4, operator
  ruling "forget everything but 4"). Mechanism sketched over the F2 plan
  surface as it exists at d93f047; config shape and open taste calls named.
  Build is QUEUED behind the 2026-07-09 F2/F4 live-tuning outcomes; nothing
  here is implemented or authorized to implement.
---

# Design note - Drop-echo theme-and-variation (AWR-178)

## What it is, in plain words

Music develops: the same chorus comes back bigger. Today the room plays the
identical cue every time that chorus returns — the robotic tell. This feature
makes the room develop with the track: the first big drop states the THEME
(its family look at base presentation); each time a comparable drop returns,
the room plays a recognizable VARIATION — the same shape family, escalated —
peaking at the final chorus. Recognition plus development, instead of
repetition.

**Operator design input (2026-07-09, load-bearing — raw ordinal is WRONG):**
house / tech-house / bass-house / techno tracks often open with a low-energy
"drop-phrase" groove entry ~32–64 beats in, while other tracks open with a
buildup into a HUGE first drop. So:

- the variation ordinal counts **within comparable drops** (same family +
  tier band), never across everything;
- the THEME is stated by the **first drop in the track's own PEAK tier
  band** — early groove-entry drops never consume the theme slot (F2's runway
  damping + measured tier already classify them out);
- huge-first-drop tracks state the theme at full presentation immediately;
  escalation for their repeats lives in the **aggression axes** — density,
  motion, strobe structure, white share — **never brightness** (full-scale
  law untouched).

## Why it is cheap (the F2 plan surface, verified at d93f047)

Everything the mechanism needs already exists per track at load time, pure
and push-loop-free:

- `build_track_plan` (`lighting_moments_v2.py:830-865`) types EVERY raw drop
  once on the ANLZ worker: `DropPlanEntry` (`:739-746`) carries `drop_beat`,
  `decision.family`, `decision.tier` (damped), `white_share`, and the F4
  texture vector. Entries are ordered by beat (`sorted` at `:845`).
- Dispatch-side, the current drop's entry is already looked up per drop
  anchor (`_led_f4_active_drop_entry`, `led_dispatch_policy.py:1159-1171`)
  and two params-only injection seams already exist and are containment-
  proven (engine colors `:1501`, F4 seasoning `:1508`; white share joins as
  AWR-177). **No new analysis, no new hardware, no new dispatch machinery.**

## Mechanism sketch (plan-time labels + dispatch-time seasoning)

1. **Plan time** (inside `build_track_plan`, pure): group the track's entries
   by comparability key = `(family, tier-band)`. Find the track's peak tier
   band; the first entry in that band is labeled `theme`. Within each group,
   label subsequent entries `echo_ordinal = 1, 2, …` (the theme is 0).
   Entries outside the peak band (early groove-entry drops, NEUTRAL/small
   drops per taste call below) carry no echo labels and render exactly as
   today. Two new optional fields on `DropPlanEntry` (defaulted, additive —
   the F4-fields precedent at `:744-746`): e.g. `echo_ordinal: int = 0`,
   `echo_theme: bool = False`.
2. **Dispatch time** (params-only injection, the F4/AWR-177 seam): when the
   drop cue for an echo entry fires, escalate aggression-axis params by
   ordinal — the existing F4 seasoning vocabulary (`sparkle_density` et al.),
   the rate rung within the alias guard (`drop_rate_rung`'s 30 fps rule,
   `lighting_moments_v2.py:502-512`, must keep winning), and the white
   mapping. **Brightness/scale is never an escalation axis.**
3. **Recognition** requires the same shape family to return — how strongly to
   pin it is a named taste call (below), because today the look is chosen at
   dispatch time by `drop_look_routing` + rotation, not by the plan.
4. **White interaction — one owner:** AWR-177 owns the white blend. The echo
   escalates white by nudging that consumer's INPUT (e.g. per-ordinal +Δ on
   the effective `white_share` before its lo/hi mapping), never by adding a
   second white blender. One mechanism, one knob surface.

## Config shape (sketch)

The F2 sub-block idiom (`impact_burndown` / `drop_white` precedent —
absent-OFF, example-OFF, fail-closed parsing, byte-identical when off):

```json
"drop_echo": {
  "enabled": false,
  "max_steps": 3,
  "per_step": { "sparkle_density_mult": 1.25, "white_share_delta": 0.1 },
  "final_jump": true
}
```

Exact knob names are the future spec's job; the containment requirements are
not negotiable: absent block ⇒ off ⇒ byte-identical dispatch; scripted decks
stand down; masks and darkness untouched; escalation is params-only.

## Open taste calls — named veto list (operator rules on each; none assumed)

1. **Tier-band width for "comparable":** exact tier match, or T2+T3 pooled as
   one "big" band? (Affects how often echoes trigger at all.)
2. **NEUTRAL / `small` drops:** excluded entirely (proposed default — they
   already render minimal), or eligible as their own group?
3. **Escalation curve:** linear per repeat vs. hold-then-jump at the final
   chorus (`final_jump`)? And does escalation cap at `max_steps` or keep
   climbing?
4. **Recognition strength:** pin the theme's accepted look NAME so every echo
   replays the same look with escalated params (strongest recognition;
   needs a small dispatch-side latch per load_gen), or only pin the family
   bank and let rotation vary the shape (weakest, zero new state)?
5. **Reset semantics:** does the ordinal reset if the track's family
   classification differs between drops (mixed-family tracks), or does each
   group independently escalate (proposed: independent per group — that is
   what "comparable" means)?
6. **Laser participation:** LED-only first round (proposed — lasers just had
   their own tier round, AWR-170), or should laser tier chases eventually see
   the ordinal too?
7. **Interaction with F4 seasoning:** echo multipliers compose ON TOP of the
   texture-selected variant params (proposed), or replace them?

## Sequencing (operator ruling, verbatim anchor)

"A small round AFTER F2/F4 land + operator live-tuning; spec through the
normal chain." F2/F4 live-tuning is happening TODAY (2026-07-09, ledtune
session) — so this build is **queued behind those outcomes**: the live-tuned
F4 seasoning values and the AWR-177 white mapping are inputs to the echo's
escalation axes, and the taste-call answers above may shift with what he
hears. Next step when re-raised: answers to the veto list → a full Part A–E
Codex spec via `.claude/skills/codex-spec/SKILL.md` (this note is its Part A
seed). Status: **planned** — nothing implemented.

Dead siblings (do not revive without the operator's word): charge-discharge
laser handoff (#1), spatial stems unmixing (#2), room-geometry calibration
(#3, briefly confirmed then withdrawn), set-arc dramaturgy (#5).
