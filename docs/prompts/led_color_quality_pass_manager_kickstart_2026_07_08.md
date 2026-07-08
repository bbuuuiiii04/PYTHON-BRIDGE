# LED Color/Look Quality Pass — Fable Manager Kickstart (2026-07-08)

**Target:** Claude Fable 5 manager lane (tmux), effort `high`.
**From:** Executive seat. **Report to:** the executive seat (the chat that dispatched this), not Brandon directly.

## Mission

Find out, mechanism by mechanism, why Brandon's Govee cues read **too white** and why **hues
don't feel smooth** at runtime — then hand the executive a veto-ready tuning proposal:
per-knob, before/after, plain English. This is taste work feeding LIGHTING ENGINE v2; the
operator taste verdicts are recorded and are design inputs, not up for debate.

## Operator taste verdicts (do NOT re-litigate)

From the project memory `project_led_look_color_quality_pass.md` (shared store — read it first):

- "Too much white in every cue." Tension to preserve: *buildups* are supposed to be WHITE
  (RC-round call); the complaint is white leaking into EVERYTHING else.
- "Hues are not that smooth" — interpolation/quantization suspects.
- RT cue skeletons in `govee_frame_renderer.py` "look kind of bad during runtime" (both
  templates and colors).
- Keep BOTH cloud looks AND RT looks per role. Never pin a role to one transport.

## Evidence packet (verify against code — memories may be stale)

- `led_color_engine.py` — candidate white-injection mechanisms named in memory:
  `_blend_white(rgb, palette.white)` per-palette blending, slot5 forced (255,255,255),
  white_sand, white templates; hue suspects: `_p_to_rgb` piecewise lerp, cycle-seeded hue picks.
  Treat these as leads, not conclusions.
- `govee_frame_renderer.py` — RT cue skeletons.
- `led_look_director.py` + `config/led_look_director.json.example` — look/role wiring.
  The LIVE config is gitignored and was modified 2026-07-08 09:05 (uninvestigated); read-only
  inspection allowed, never edit it.
- Landed platform context you can rely on: AWR-146 frame-engine child, AWR-149 deterministic
  mixed-transport rotation, AWR-150 drop-impact guarantee (RT substitute on the beat + staged
  cloud takeover), AWR-151 ProcessType root-cause fix (machine now un-throttled).
- Candidate idea to assess (executive note, unreviewed): **"realtime twins for cloud drop
  looks"** — each cloud drop scene gets a matched RT twin so the AWR-150 on-beat substitute
  shares its aesthetic. Assess fit/cost; do not implement.

## Deliverable

1. A read-only audit: every path where white enters a cue color, each named with file:line and
   its contribution mechanism confirmed by reading the code (offline pure-render calculations
   are fine as proof; no hardware, no bridge).
2. A hue-smoothness diagnosis at the same evidence standard.
3. A veto-style proposal set for Brandon (routed through the executive): per knob — current
   value, proposed value, expected visible change in plain English. Include a
   keep/change/cut call on each RT skeleton, and a verdict on the realtime-twins idea.
4. A Template Lab iteration plan for skeletons only AFTER the executive relays Brandon's vetoes.

Proposals that cannot name their mechanism get cut — that is the rejection rule.

## Boundaries

- READ-ONLY on all code and config until the executive releases changes. No bridge process
  touches, no hardware, no live config edits.
- Brandon may start a verification mix at any time: no heavy compute (full suites, corpus
  sweeps) without an executive CLEAR; file reading and small pure-python calculations are fine.
- Delegate grinding (file sweeps, render-math tables) to cheaper-tier delegates or subagents —
  never spawn Fable-tier.
- New docs need doc-index/registry classification in the same commit (today's lesson);
  explicit-path commits only; re-read shared files (registry, contracts yml) fresh before
  editing; take the next free AWR id after re-checking the current max.
- Claim discipline: confirmed / assumed / unknown, tied to evidence. Status language per
  AGENTS.md §10.

## Done means

The executive has: the audit findings with file:line evidence, the per-knob proposal table,
skeleton verdicts, and the realtime-twins assessment — nothing implemented, nothing live
touched. Stop there and report.
