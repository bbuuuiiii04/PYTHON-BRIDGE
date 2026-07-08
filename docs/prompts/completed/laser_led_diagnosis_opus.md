# Diagnosis prompt — laser color / drop-firing / laser-solo LED blackout

**Target:** Claude Opus 4.8 · **effort: xhigh** · set a large max-output-token budget (~64k).

---

## Mission

Diagnose three live-lighting bugs in `/Users/bbui/rb_ss_bridge_v2` and produce a
root-cause report precise enough for Codex to write fixes from. You are the analyst,
not the implementer. **Do not change any code.** Your output feeds a Codex fix spec.

Why it matters: this bridge drives lasers + LEDs during live DJ sets. All three bugs
are visible on the dance floor right now. The operator has already lived through
symptom-patch cycles, so he needs the *actual* mechanism behind each, tied to code and
to the repo's authoritative design docs — not a plausible-sounding guess.

## The three symptoms (operator's words, verbatim)

1. **Laser color not following the LED palette.** The laser color engine still isn't
   tracking the LED color palette. Lasers show a color that doesn't match what the LEDs
   are doing.
2. **Lasers not obeying the drop presentation policy.** Lasers do **not** fire at the
   true drop crossing, then fire in the *middle* of the drop section — e.g. no fire at
   the true drop, then a fire ~32 beats later. It looks like the drop cycling / MIDI
   refire is running free and is **not** gated by the drop-presentation state.
3. **Laser solo still flashes an LED drop.** When laser solo is activated, the LEDs
   still play a drop look for a moment, then quickly correct themselves and black out.
   The LEDs should already be dark going into the hit.

## Deliverable — one report, all three issues

Produce a single markdown report. **Diagnose all three issues independently and to the
same depth — do not stop after the first, and do not let one diagnosis's findings stand
in for another's.** For **each** issue, in this exact structure:

- **Symptom** — one line restating what the operator sees.
- **Root cause** — the specific mechanism, named at `file.py:line` with a short quote of
  the offending code. Distinguish *the* root cause from contributing factors.
- **Authoritative rule it violates** — quote the governing line from the authoritative
  doc (path + line) that says what the behavior *should* be. If code and doc conflict,
  say so explicitly and note that code is the source of truth for *current* behavior
  while the doc states *intended* behavior.
- **Why the current code produces the symptom** — a plain-English walk of the actual
  execution path (tick ordering, event flow, gating conditions) that ends in the wrong
  output. Name every branch/condition that matters.
- **Fix direction for Codex** — the smallest change that addresses the root cause (which
  function, what invariant to enforce), plus any sibling callers that share the bug.
  Direction only — do not write the patch.
- **Confidence** — `confirmed` / `assumed` / `unknown`, tied to the evidence you cite.

End with a **Cross-cutting** section: do any two of these share a root cause (e.g. a
single tick-ordering problem), and is there any fix that would help one but regress
another? Call that out.

## Evidence packet

**Source-of-truth order (AGENTS.md §1) — obey it:** executable `*.py` > tests > config
examples > `runtime_status.py` > file tree > docs. **If a doc conflicts with code, code
wins for describing current behavior.** Docs state intended behavior; use them to define
the *should*, use code to define the *is*, and name the gap.

**Authoritative docs (confirmed on disk, current status headers):**
- `docs/architecture/drop_presentation_authority.md` — IMPLEMENTED / SOFTWARE-TESTED;
  governs Issues 2 and 3 (drop firing/timing + `lasers_only` / Laser Solo choreography).
- `docs/subsystems/laser.md` — `doc_status: current`; Package 4 states the laser-color
  rule for Issue 1.
- `docs/architecture/laser_color_authority.md` — design-intent authority for Issue 1
  (referenced from `drop_presentation_authority.md`). Confirm it exists and read it.
- `docs/architecture/laser_blackout_authority.md` — owner semantics relevant to Issue 3.
- `docs/architecture/laser_director_design.md` — CURRENT AUTHORITATIVE; scopes itself to
  scene *selection*, and states drop rotation rules.
- `docs/subsystems/led_govee.md` — `doc_status: current`; LED dispatch/blackout side.
- Note: the lighting-engine-v2 docs (`docs/architecture/lighting_engine_v2_authority.md`,
  `docs/architecture/LIGHTING_ENGINE_V2_DESIGN.md`) are PLANNED / not-yet-implemented —
  do **not** treat them as governing current runtime behavior for these three bugs.

**Starting leads (from a prior read-only recon — treat as leads to VERIFY against code,
not as facts; code wins):**

Issue 1 — laser color follows LED palette:
- `laser_color_engine.py` — `LaserColorEngine.update()` (~:78), `snapshot()` (~:111),
  `_target()` (~:113), `FIXED_COLOR_ORDER` (~:13). Pure mapper: LED rgb → nearest of 6
  fixed colors → `LaserColorSnapshot(ch8, ch9, seq)`.
- `state_manager.py` — the coupling: `_update_laser_color_from_led()` (~:3097),
  `_sync_laser_color_if_needed()` (~:3120), `_bootstrap_laser_color_if_needed()` (~:3158);
  re-sampled on accepted LED automation triggers (~:4260-4266). It's a **sampled
  snapshot**, not a live subscription — verify when/whether the sample is actually taken
  and whether a code path leaves CH8 stale or unsampled.
- `soundswitch_laser_player.py` — `_merge_color_snapshot()` (~:124) overwrites frame
  index [7]=CH8 (~:139) and CH9; `set_color_snapshot()` (~:350) applied at ~:428/:463.
  Verify the merge actually reaches the wire on every healthy frame.
- The color logic is NOT in `laser_director.py` / `laser_executor.py` /
  `personality_resolver.py` / `midi_output.py`. Confirm before pointing there.

Issue 2 — drop firing / refire gating:
- `drop_lifecycle.py` — `impact_allowed()` (~:59), `resolve()` (~:80); `armed_this_tick`
  true only on `impact_allowed` (needs `smart_drop_crossing` + tension predecessor). This
  is the true-drop-crossing gate.
- `laser_director.py` — `reason="drop_crossing"` immediate fire on `armed_this_tick`
  (~:485); sustained `reason="drop_cycle"` (~:497); `post_drop_cycle` (~:504); legacy
  ungated path (~:520).
- `laser_executor.py` — refire cadence: `cycling = decision.reason in ("drop_cycle",
  "post_drop_cycle")` (~:191); `refire_allowed = ctx.autoloop_tick_just_fired and …`
  (~:194). Lead: the refire cycling appears gated by the **autoloop tick edge**, not by
  the drop-presentation state — verify whether that lets it fire mid-section without a
  real drop crossing, and whether the `drop_crossing` immediate fire is actually reaching
  the wire at the crossing.
- `state_manager.py` — `_drop_presentation_tick(…, impact_now=…)` (~:4517) reuses the
  Laser Director's own `drop_crossing` decision as "impact now". Verify the two agree.
- Governing rules: `drop_presentation_authority.md:44` ("this policy invents no new drop
  detection"), `:46` (drop window = impact → end of drop role, cap `drop_window_cap_beats`
  default 32 — "never an LED- or laser-private timer"); `laser_director_design.md:96`
  ("drop: rotate on each drop crossing"), `:101` (phrase MIDI must not fire immediately
  when post-drop expires; waits for a real boundary edge).

Issue 3 — laser solo → LED blackout race:
- `drop_presentation.py` — `LASERS_ONLY = "lasers_only"` (~:39); `resolve_presentation()`
  returns `LASERS_ONLY` with `solo_*` reasons (~:326, :361-370).
- `state_manager.py` — `_drop_presentation_apply_actions()` (~:2663): on
  `actions.led_dark_hold` emits `Ev.LED_BLACKOUT reason="drop_spotlight"` (~:2670-2673),
  release emits `Ev.LED_CLEAR_BLACKOUT` (~:2676). **Tick ordering lead:**
  `_dispatch_led_automation()` (~:4253) runs BEFORE `_drop_presentation_tick()` (~:4517)
  in the same push tick — so on the impact tick the LED drop look may be dispatched
  before the solo blackout lands, giving "drop flashes then blacks out". Verify this
  ordering and whether pre-dark (`led_predark_beats`, default 4) is supposed to engage
  the blackout *before* impact but doesn't for auto-solo tiers (learned/gearshift/record).
- `led_dispatch_policy.py` — `_led_blackout_owners` (~:76, added ~:448);
  `led_look_director.py` — `set_emergency_blackout()` (~:81) → renders `config.blackout`
  (~:99).
- Governing rules: `drop_presentation_authority.md:32` ("Govees black out; lasers alone.
  Preceded by a full-dark beat."), `:47` (pre-dark: "total darkness into the hit"),
  `:127` (choreography), `:135` (fail-open: "policy can never latch a fixture dark").

**Explicit unknowns you must resolve, not assume:**
- Whether each "starting lead" line number/symbol still matches current code (they came
  from recon, not from your own read — re-open and confirm).
- Whether the operator's runtime config actually enables the paths involved
  (`config/laser_color_map.json`, laser director enabled/dry_run, `led_predark_beats`).
  Check the `config/*.example.json` and any live config the source-of-truth order allows.
- For Issue 2: whether the bug is a *missing* fire at the crossing, an *extra* fire
  mid-section, or both — and whether they're the same root cause or two.

**Optional live correlation:** if a symptom's mechanism is ambiguous from code alone, the
event log at `~/Library/Logs/rb_ss_bridge/current.jsonl` is JSONL with epoch `ts`, persists
across restarts. You may `rg`/read it read-only to confirm ordering (e.g. LED drop dispatch
vs. blackout on a solo tick). State plainly when a claim rests on log evidence vs. code.

## Scope and rules

- **Read-only diagnosis. Change no files. Write no code. Do not touch the running bridge**
  (`pgrep`/restart/kill all forbidden). Do not `git clean`.
- Codex implements bridge code — your "fix direction" is direction, not a patch.
- You MAY read any repo file, run `rg`/tests read-only, and read the log above. Prefer `rg`
  for known symbols; only fan out to subagents to read across many files in parallel.
- Do not expand scope beyond these three issues. If you find a fourth adjacent bug, note
  it in one line under Cross-cutting and stop there.

## Claim discipline

Label every load-bearing claim **confirmed** (you read the exact code/doc/log line and
quote it), **assumed** (inferred, not directly verified — say why), or **unknown** (state
what you'd need). Do not present a recon lead as confirmed until you've re-read it yourself.
No hidden chain-of-thought — give evidence-tied reasoning and quoted lines only.

## Success criteria (falsifiable)

- All three issues diagnosed to the same depth, each with a root cause at `file:line` + a
  quoted authoritative rule it violates.
- Every root-cause claim is `confirmed` against a code line you quote, or explicitly
  downgraded to `assumed`/`unknown` with the reason.
- The tick-ordering / gating mechanism for Issues 2 and 3 is traced as an actual execution
  path, not asserted.
- Cross-cutting section states whether any fixes interact.
- Zero files modified; report is the only output.

**Stop condition:** if the code contradicts a "starting lead" or an authoritative doc,
report the contradiction and proceed on what the code says — do not spend effort
reconciling the doc. If a mechanism is genuinely undeterminable from code + logs, mark it
`unknown` and move on rather than guessing.
