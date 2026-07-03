---
doc_status: active-prompt
truth_level: code-grounded brief for spec authoring
last_verified_commit: e0eed61
last_verified_date: 2026-06-29
validation_scope: brief instructing Codex to AUTHOR (not implement) the native autoloop DMX runtime spec; SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED; spec authoring must not run the bridge, change runtime behavior, or open hardware
---

# Codex brief — AUTHOR the native Autoloop DMX runtime spec (grill me first)

You are authoring an **implementation spec**, not implementing. Output is a written spec
in the operator's Part A–E format at `docs/plans/active/<slug>_spec.md`. Do **not** write
runtime code in this task.

## Hard requirements (do these, in order)
1. **Invoke the `grill me` skill first.** Before writing any spec, use it to interrogate the
   operator on the Open Decisions below until each is answered. Do not guess these; do not
   write the spec around assumptions where a grill answer is available. One answered question
   is not approval to stop — work the whole list.
2. **Verify every load-bearing claim against current code** (`rg`/read the files named below).
   Memories and this brief may be stale; code wins. Label every spec claim
   `[confirmed]` / `[assumed]` / `[unknown]`.
3. **Spec only — no behavior change, no bridge run, no hardware.** Authoring this spec must
   not start the bridge, mutate config, open serial/MIDI/Art-Net/Enttec, or touch the
   SoundSwitch project.
4. Run the **codex-spec / rbss-codex-spec pre-handoff checklist** before calling the spec
   ready (verified claims, knowns/unknowns, pending-state guards, mode-transition cleanup,
   third-party API completeness, pure-function test seam, live-safety invariants, adversarial
   self-review).

## Goal
Spec a **generic** runtime that renders **any** SoundSwitch autoloop the operator has mapped
— breakdown, groove, buildup, drop, any category — natively in the bridge and outputs it on
the bridge's CH1-19 Enttec DMX path, so SoundSwitch can be retired to an authoring-only tool.
**Do not restrict to drops.** "Only drops have DMX content" is true of *today's* project, not
a design constraint; an empty/dark look must simply render dark, and the moment the operator
maps DMX content to a groove/breakdown/buildup look it must render with no code change.

## Settled facts — treat as given, verify, do not re-litigate
- Autoloops are **deterministic and not audio-reactive**: output is a pure function of
  (look, phase) over an 8-bar / 32-beat / 19,200-tick cycle (600 ticks/beat). [operator-confirmed]
- The renderer already exists and is **category-agnostic**: `render_autoloop_frame(loop,
  phase_tick)` (`soundswitch_laser_player.py:125`) → 19-channel CH1-19 tuple; wraps
  `phase_tick % cycle_ticks`; returns `ZERO_FRAME` for an unsupported/empty look. There is
  also `select_autoloop(identity, phase_tick)` (`:270`). [confirmed]
- `AUTOLOOP_CYCLE_TICKS = 19_200` (`soundswitch_pack_loader.py:26`); `load_pack()` (`:497`)
  yields `LoadedPack.autoloops: Mapping[str, LoadedAutoloop|LoadedDocument]`; `LoadedAutoloop`
  carries `supported_active` + `document` (cycle_ticks). [confirmed]
- Note→autoloop identity comes from the decoded project's `resolved_controls`
  (IAC-bus, `message_type=="note"`, `target_kind=="autoloop"` → `SSAutoLoopN.ssfile`), covering
  **all** roles (e.g. note 1 breakdown, 32 groove, 64 buildup, 96-111 drops)
  (`soundswitch_project_decoder.py`, `soundswitch_pack_models.py:283`). [confirmed]
- Native DMX output path is **Enttec serial** (`soundswitch_frame_sender.py` — 19-ch tuples →
  Enttec), the same path scripted/static/blackout already use. The pack runtime already owns
  scripted + static-override + blackout precedence and Enttec submit; the **Autoloop base is
  currently software-zero** (`StateManager` does not call `select_autoloop`). The gap is
  filling that base with the rendered active autoloop. [confirmed — re-verify exact files]
- Lasers are MIDI (LaserDirector), a **separate** path, **out of scope**.
- **Refire / re-anchor / arm-correction are NOT needed natively.** They existed only to keep
  SoundSwitch's free-running 32-beat loop clock re-synced to the musical phrase over a laggy
  MIDI leash. The bridge computes phase directly, so there is no second clock to correct.
  Do not port that machinery.
- Anchor rule (generic): each look's phase=0 is its **trigger instant** — `phrase_boundary`
  (groove), `breakdown_active` (breakdown), `buildup_to_drop_window` (buildup), `drop_crossing`
  (drop). One uniform rule across roles. [assumed — confirm empirically and/or by grill]
- Evidence we have: two offline scout captures + an offline equivalence oracle
  (`tools/ssfmt/re/autoloop_oracle/`) showing the renderer reproduces SoundSwitch's real
  per-frame DMX byte-exact for several looks that had content. Decode fidelity is **proven for
  looks that had DMX content to compare, unconfirmed for the rest** — the runtime supports all
  looks regardless; per-look fidelity is confirmed when content is mapped and A/B'd on the rig.

## Open Decisions — GRILL THE OPERATOR on these before writing the spec
1. **Anchor semantics:** confirm each look anchors phase=0 to its own trigger instant (above),
   vs the absolute 32-beat phrase grid, vs something else. This is the make-or-break behavior.
2. **Loop behavior per look:** when a look is active, does it loop continuously (wrap) until the
   next trigger, play once and hold the last frame, or go dark after one 8-bar cycle?
3. **End-of-role / between-looks:** when a role ends (e.g. drop → groove), what renders in the
   gap — the dark base, the next role's look, or a hold?
4. **SoundSwitch coexistence / fallback:** must SoundSwitch be disabled (and how) when native
   autoloop DMX is enabled, to avoid two sources driving the same fixtures/Enttec port? What is
   the exact one-click fallback to SoundSwitch?
5. **Precedence:** how the native autoloop base slots into existing precedence
   (blackout > emergency > held static override > scripted > autoloop). Confirm it fills the
   slot where software-zero is today and never overrides blackout/static.
6. **Validation bar + method:** operator wants byte-exact (100%) equivalence. How is that
   gated before trusting it live — rig A/B by eye, a one-off per-phase capture check, or both?
   What is "good enough to enable"?
7. **Rollout:** flag name + default (off), dry-run/observe-first stage, which deck/active-deck
   authority drives it, and the per-look trigger-beat source at runtime (which beat/phase
   authority var).
8. **Scope of first cut:** all roles at once, or wire the generic path and let the operator map
   content per role incrementally (the generic design allows either — confirm intent).

## Constraints / live safety (Part C of the spec must state these)
- `StateManager` stays the only `DeckState` writer and sole per-tick frame-submit owner; the
  **200 Hz push loop gains no blocking I/O** (no serial/MIDI/socket/file/subprocess in-tick;
  rendering must be pure/precomputed).
- Native direct DMX and physical MIDI-laser output remain mutually exclusive per existing
  invariants; do not regress laser/LED/Govee/OS2L/Rekordbox behavior.
- Automatic base resolves **software-zero** on unowned mode, stop/unload, stale/invalid
  authority, failed render, disable, and shutdown. Blackout/emergency win; held static is not
  overridden except by blackout/emergency.
- Off by default; enabling requires explicit operator config. No hardware claim — status stays
  `SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED`; SoundSwitch is the fallback.

## Output
- `docs/plans/active/<slug>_spec.md` in Part A–E format (Context & root cause / Tasks /
  Invariants / Tests — incl. a pure-function render+anchor test seam / Acceptance).
- The spec must be **generic across all autoloop categories**, encode the grilled answers, label
  every claim confirmed/assumed/unknown, and pass the pre-handoff checklist.

## Report back
- The grill transcript outcome (each Open Decision → operator's answer).
- The spec path, and a 5-line plain-language summary of the runtime it specs.
- Any claim that stayed `[unknown]` and what would resolve it.
