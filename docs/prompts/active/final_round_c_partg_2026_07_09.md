# FINAL ROUND C — Part G palette-cycling comet (build + re-bank)

doc_status: current
truth_level: dispatch-brief (superman4 final round, ~21:1x)

## Context

Operator overruled the bench: rainbow-class looks get FIXED tonight, not pulled.
The executive pulled `rt_rainbow_drop`/`rt_rainbow_post_drop` from all routing/
banks earlier (~20:35, backup exists) because they are BAKED-rainbow and fired
palette-blind. This round builds the proper replacement and re-banks it.

## Design authority (already operator-shaped): Part G in
`docs/plans/active/rt_phase_ember_visibility_spec_2026_07_09.md:210-220`

- Palette-cycling comet primitive: a slot-based comet chase that CYCLES the
  track's palette slots per cycle/segment — deterministic, seeded, any palette
  length. On rainbow-classified tracks the PALETTE is rainbow, so the same
  effect goes rainbow there; on everything else it cycles that track's colors.
  A palette, not a renderer branch.
- New looks: `rt_drop_palette_comet` (drop role) + `rt_post_drop_palette_comet`
  (post_drop, pair). Register (not-a-strobe unless design demands), C5 allowlist,
  drop_pairs entry mirroring the old rainbow pair.
- Migration: the bespoke `rt_rainbow_*` looks stay DEFINED but unrouted (their
  kill is a later cleanup once the operator accepts the replacement live —
  ponytail: do not delete tonight).

## Scope fence (CONFIG COLLISION)

ledtune is concurrently re-writing `f2.drop_look_routing` (Round A). DO NOT edit
the live config yourself. Deliver a python APPLY-SCRIPT (CFIX2 precedent:
atomic write, timestamped backup, self-verifying, idempotent) that: adds the two
look defs + drop_pairs to the LIVE config, and appends `rt_drop_palette_comet`
into the COMET-family t2/t3 routing pools + `banks.default.drop`, and the
post_drop look into `banks.default.post_drop`. The EXECUTIVE runs it AFTER
Round A lands. Example config: add the look defs + allowlist additively in-round
(safe, no tripwire).

## Tests + checks

- Renderer tests: deterministic seeded cycling (same seed+local_t ⇒ same frame),
  palette-length sweep (3/5/6-slot palettes), slot-discipline (writes only its
  documented slots; slot 5 per current white rules), registration + allowlist
  guard, pair wiring.
- Scoped file suites green; 3 hard doc checks green; led_govee.md paragraph;
  registry row (re-check max id). Commits by explicit paths. STAGED only.

## Signals (executive is OUTSIDE tmux — files are the channel)

Done: /tmp/rbss_lane_signals/ledfix2.PARTG.report.md (+ .done touch);
Blocked: .blocked + evidence. Reviewer: ledtune. Run straight through.
SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED language.
