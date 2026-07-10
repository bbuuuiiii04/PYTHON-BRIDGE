# FINAL ROUND B — firework explosion redesign (operator visual spec, verbatim)

doc_status: current
truth_level: dispatch-brief (superman4 final round, ~21:1x)

## Operator spec (his words — this IS the acceptance)

Current defect: "it just looks like the leds turn all white and then relax and
then the sparkle look is too slow."
Wanted: "the firework background explosion should strobe with sparkling hues and
then when the firework explosion background quickly dims, the embers continue to
aggressively spark."

## Verified anchors (executive desk, HEAD)

- `govee_frame_renderer.py:668` `_drop_firework_explosion` — beat-tied surge
  (solid near-white bg 255,240,220) resolving to bg_hold over `surge_beats` 0.5,
  plus `_ember_field_frame` (:632) embers: density 0.35, size 1.0,
  life_s 0.35, sine envelopes, two spark colors. That IS his "white flash →
  relax → slow sparkle".
- AWR-161 `DropFireworkExplosionTests` pin the CURRENT behavior (post-surge ember
  contrast ≥60/255, surge resolves to bg_hold, not-a-strobe, time-based embers) —
  re-pin to the NEW spec where the spec changes them; the time-based-embers
  ruling (AWR-153) STANDS.

## Build shape

1. Explosion phase: background becomes a STROBING MULTI-HUE field (sparkling
   hues, not solid white) — wall-clock Hz strobe per the AWR-161 gate discipline
   (`_hz_strobe_on`), hues drawn from the injected palette tints (NOT baked white;
   the BAKED_WHITE ruling covered the old solid burst — this replaces it).
   REGISTER AS A STROBE (strobe class + C5 param allowlist: hz, duty + new keys).
2. Quick dim: background drops fast after the hit (shorten the resolve — expose
   `surge_beats` default ~0.25-0.3 and dim TO a much lower bg_hold).
3. Ember phase: AGGRESSIVE sparking — life_s default ~0.15, density up (~0.5),
   sharper-than-sine attack (fast-in/exponential-out), embers keep full intensity
   while the background dims (contrast target: ember vs dimmed bg ≥ the AWR-161
   bar, measure it the same way).

## Constraints

- Time-based embers stay time-based (AWR-153). Slot-5/white discipline per
  current code. No constant changes outside this effect. Params desk-tunable.
- Tests: rewrite `DropFireworkExplosionTests` to the new spec (strobe
  registration, quick-dim, aggressive-ember contrast, hz/duty allowlist); scoped
  file suite green; 3 hard doc checks green; led_govee.md one-paragraph update
  (contract docs_update); registry row (re-check max id).
- Commits by explicit paths. STAGED only — no restart, no process contact.
- Live config: look params update via a small apply-script (CFIX2 precedent),
  executed at the executive gate, atomic write + backup. Example config: update
  the look def + allowlist additively.

## Signals (executive is OUTSIDE tmux — files are the channel)

Done: write /tmp/rbss_lane_signals/ledfix3.FWRK.report.md (commits, test counts,
measured contrast, param defaults) + touch /tmp/rbss_lane_signals/ledfix3.FWRK.done
Blocked: .blocked + the evidence. Reviewer: ledtune. Run straight through.
SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED language.
