# Color Engine — what comes after Phase 2b + Phase 3 (planning note, NOT a spec)

Grounded in current `main` code + the M2 specs. Planning only — each item needs its own spec before
implementation. No fantasy features.

## Gate first (before any of the below)
- **M1 live-validation on the rig** — engine has never been watched on hardware. Run a show with
  SoundSwitch up; `grep color-inject /tmp/bridge.log`, `grep color_engine_error`. Nothing below should be
  trusted live until this passes once.

## High-value, code-grounded next candidates
1. **BIG_DROP_SIGNATURE / M1 palette filtering (real open gap).** `led_color_engine.diy_eligible:438`
   treats `BIG_DROP_SIGNATURE` (+ `white`/`TODO`/compound `+`) as ALWAYS-eligible — it is not gated by
   actual big-drop context. Spec a proper gate so signature looks fire only in real big-drop sections.
2. **Runtime observability for active palette/fade.** Today the active palette/slot_colors/fade state is
   only visible via the `[RGB] color-inject` log line. Add a status field (the runner/state_manager already
   publish a lock-guarded snapshot) exposing current palette, focus window, and active fade — so the
   operator and dry-runs can see what the engine is doing without log-greps.
3. **Breakdown bank robustness (C4).** Breakdown bank is 3 DIY looks (red/cyan/green) with no realtime
   fallback; some palettes (e.g. `blue_cyan`) filter it down to 1. Phase 2b's engine breakdown cues
   (`breakdown_full_breathing`, `breakdown_star_twinkle`) are the durable fix once in rotation — track
   whether they fully remove the empty-bank risk and retire the C4 fallback workaround if so.
4. **Operator palette controls.** `LedColorEngine` already has `lock/unlock/set_palette/queue_palette/
   shift` stubs but no control surface. Spec wiring them to the menubar / a command so the operator can
   pin or nudge the palette journey live.
5. **Config-example hardening + the open sign-off.** Resolve the example-config redesign sign-off
   (automation_enabled true / ambient mapped) and make the example a clean, copy-safe reference.

## Lower priority / hygiene
- Richer palette policies (per-genre or per-set palette weighting) — only after live data shows the
  current journey model needs it; do NOT pre-build.
- Live rehearsal checklist doc (preflight for a show with the engine on).
- Docs/agent-workflow cleanup: the `docs/prompts/active/` dir now has many overlapping M2 docs; prune to
  the handoff + the two specs + these checklists once Phase 2b/3 land.

## Explicit non-goals for the roadmap
- Do NOT add new cue families speculatively — the 6 from the prototype are the agreed set.
- Do NOT change the slot model (6 slots, 0-4 palette + 5 white) — it is load-bearing across renderer +
  engine + tests.
