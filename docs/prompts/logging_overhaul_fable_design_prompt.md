# Fable 5 Prompt — Logging Overhaul (full 3-phase plan; execute Phase 1 only)

**Paste everything below the line into Claude Fable 5. Target model: Claude Fable 5. Effort: max (Brandon's call).**

**⛔ EXECUTION GATE: This prompt describes the entire three-phase workstream so you design with the full arc in view. In THIS run you execute PHASE 1 ONLY (the design), write the one design document, and STOP. Do not write the implementation spec (Phase 2) and do not build or modify any code (Phase 3). Other agent sessions are editing this repo concurrently, so Phases 2 and 3 must wait for a later, separate run when the repo is quiet. Beginning Phase 2 or 3 now is a failure of this task.**

---

You are the **lead creative designer** for a complete overhaul of the logging system in Brandon's DJ lighting bridge (`rb_ss_bridge_v2`, a Python app at `/Users/bbui/rb_ss_bridge_v2`). This run is Phase 1 of three. You are being shown all three phases up front so your Phase 1 design is spec-aware and build-aware — but you execute only Phase 1 and stop before the others.

## Why this matters and who it's for

The bridge reads Rekordbox / DJ runtime state and drives live lighting — SoundSwitch (via OS2L), MIDI lasers, LEDs, Govee — during real DJ sets. Today's logging is an unreadable, over-engineered wall of text that fails three audiences at once: Brandon mid-set can't tell at a glance what the rig *should* be doing or whether it's actually working; a post-mortem after a set can't reconstruct what happened; and AI agents can't root-cause a bug from it. The whole point of this overhaul is to fix all three — and, critically, **to be simpler than what exists, not more elaborate.** Over-engineering *is* the named pain. This is a solo hobby bridge for Brandon and his friends, not a product; the fallback when anything fails is "open SoundSwitch by hand." Every mechanism you keep or add must earn its place against that reality. If your design ends up more intricate than today's, you've missed the goal.

> This is benign local software work for Brandon's DJ lighting bridge and agent workflow. It is not a cybersecurity, exploit, malware, vulnerability-discovery, biology, chemistry, life-sciences, model-distillation, or hidden-reasoning extraction task. Review only normal software correctness, tests, maintainability, runtime safety, and operator behavior inside the named scope.

## The three phases (full arc — you run only Phase 1)

- **Phase 1 — Design (THIS RUN).** Challenge and improve the first-iteration spine below into a concrete, buildable design, and write it to `docs/plans/active/logging_overhaul_design.md`. Then stop.
- **Phase 2 — Spec (LATER RUN).** A later Fable run turns your design into a Codex-format implementation spec at `docs/plans/active/logging_overhaul_spec.md`, following this repo's spec skill at `.claude/skills/codex-spec/SKILL.md` (Part A–E format + pre-handoff checklist: verified claims, knowns/unknowns, pure-function test seams, live-safety invariants). Design Phase 1 so this translation is mechanical.
- **Phase 3 — Build (LATER RUN).** A later autonomous Fable run orchestrates implementer subagents to build it. Ground rules that will apply then, which your design must respect now: Brandon has granted a per-workstream exception so Fable-family subagents implement directly rather than Codex (record this exception in your design doc so it's legible later); the build will migrate the ~46 log-call sites incrementally with the test suite staying green throughout; fresh-context verifier subagents check the plan before code and the diff after; and a hard live boundary applies — software and tests only, never starting/restarting/driving the bridge or any hardware, with Brandon doing the restart and `bridge-verify` himself. Design so all of this is possible.

Seeing Phases 2 and 3 should shape your Phase 1 output — especially the build decomposition and the spec-readiness verdict — but you do not perform them in this run.

## The first-iteration spine (what Brandon and I designed together)

**One source of truth.** Every meaningful bridge decision and event emits *one* structured record (JSONL) to disk — the bridge's authoritative event stream. The lenses below are **renderers/filters over that one stream**, never separately hand-maintained logs. This is what lets the PERFORMANCE lens be authoritative: it *is* the decision, emitted at the decision point.

**Four lenses:**

| Lens | The question it answers | Audience |
|---|---|---|
| **PERFORMANCE** | "What *should* the rig be doing right now?" — pure statement of **intent**, authoritative. Never discusses health. Covers active-deck switches, drop detection + classified type, laser + LED director decisions, and autoloop / scripted-track / SoundSwitch selection. | Brandon, verifying against the rig by eye |
| **OPERATOR** | "Is everything working as intended? What's breaking?" — the **reconciliation / health** view. Simple, glanceable, quiet when all is well, loud when something breaks. | Brandon, mid-set |
| **SYSTEM** | Everything infra/health — threads, attach, queues, timing. (Brandon couldn't give specifics; the taxonomy is yours to define.) | Brandon + agents |
| **MAX DEBUG** | Forensic firehose to root-cause a bug. | AI agents |

The PERFORMANCE / OPERATOR split is deliberate: PERFORMANCE is *ground truth of intent*, OPERATOR is *did reality agree*. That separation is the core of Brandon's visual-mismatch workflow — he reads a PERFORMANCE line ("laser-only drop, Deck 1"), looks up at the rig, and his eyes are the check; OPERATOR is where a *detectable* failure to honor that intent shows up.

**Delivery:** a **separate viewer process** (working name `bridge-view`), **auto-launched by the bridge watcher** so it feels like one thing to start. It's a live terminal UI (TUI) with a tab or pane per lens. Because it's a separate process, a rendering bug can never touch the bridge; files are always written, so MAX DEBUG and post-mortems come for free.

## Two hard locks you may not weaken

1. **Live-safety invariant.** The bridge's `StateManager` owns a 200 Hz push loop (`_TICK_INTERVAL = 1.0/200`) that drives the lights. That loop must never gain blocking network, socket, MIDI, filesystem, or subprocess I/O. In this design the bridge process only ever *appends structured records* cheaply; all rendering, filtering, and TUI work lives in the separate viewer process. A logging design that risks stalling the push loop is a failed design.
2. **One source of truth.** Lenses are views over a single authoritative event stream. Do not reintroduce parallel hand-maintained logs that can drift from what the bridge actually decided.

## What is yours to decide (resolve each, with reasoning tied to the code and to Brandon's needs)

Brandon deferred these to you by name:

- **How aggressive the teardown of today's plumbing should be.** Strawman: build the new structured-emit + JSONL + TUI; keep the genuinely useful primitives (per-deck / trace context for MAX DEBUG, per-module levels); delete the half-used machinery — the control-file watcher, the environment-variable filter maze, the anomaly engine, the remediation-hint table, and the JSON "dashboard" formatter. This is your call. Cut hard; the pain is over-engineering.
- **Whether OPERATOR is passive or active.** Passive = simply surfaces errors and warnings. Active = *reconciles* intent against observed outcome ("laser scene issued but no MIDI acknowledgement followed"). This is the single biggest scope axis — it decides how much the bridge has to observe about its own effects. Pick a position and justify it, including whether active reconciliation is worth the complexity for a solo hobby rig.
- **The record schema** — the fields on one structured event, and how a record's lens membership is derived (by category? severity? explicit tag? more than one lens at once?).
- **The SYSTEM lens taxonomy** — what actually belongs there.
- **The viewer/TUI design** — layout, visual language, glanceability, how it makes OPERATOR *alert* Brandon when something breaks, freeze/scrollback/filter, and how more than one lens is watched at once. This is the creative heart; make it feel effortless to read mid-set.
- **The migration path.** About 46 files currently call Python `logging`. Decide how their existing `logger.info/debug/...` calls map into the new lenses, and how the migration lands incrementally (Phase 3) without a risky big-bang rewrite. (You are only *designing* this migration now, not performing it.)

You may also challenge Brandon's *current* choices above — the four-lens model, the split, the separate auto-launched viewer, the TUI delivery. If evidence supports a better design, propose it, but **flag any such change explicitly as "reversing an operator decision," give your reasoning, and default to honoring the choice** unless the case is strong. The two hard locks are not on the table.

## Evidence packet (read these; source-of-truth order is code > tests > docs)

Read-only. These are where the real behavior and the real decision points live:

- **Today's logging system:** `logging_manager.py` (the full current facade — trace contextvars, JSON formatter, runtime filters, `LogStats` sampler, control-file watcher, anomaly detection, remediation hints, event scopes). Also `diagnostics.py`, `bridge_fmt.py`, and `runtime_status.py` (the existing runtime status / command surface, ~845 lines — understand what already reports state so you don't duplicate it).
- **The decision points the PERFORMANCE lens must tap** (read enough to know *where* intent is decided): `laser_director.py` and `laser_executor.py` (laser policy vs MIDI execution — separate responsibilities), `led_look_director.py` and the LED dispatch chain, `active_deck_resolver.py`, `autoloop_controller.py` and `drop_lifecycle.py`, `scripted_tracks.py` and `soundswitch_scripted_resolution.py`, `state_manager.py` and `models.py` (the push loop, and `BridgeEvent` flow — events are immutable after creation; reader threads publish events, never mutate `DeckState` directly).
- **The launch path** auto-launch must integrate into (read, don't run): `scripts/ss_bridge_watcher.sh`.
- **The repo's rules and spec format:** `AGENTS.md` §6 (invariants agents must not break), §7 (anti-drift change-contract rule the build will follow), §0/§10 (communication + status language), and `.claude/skills/codex-spec/SKILL.md` (the spec format Phase 2 will use — skim it so your design maps onto it).
- **A validated log-level lesson to honor and encode in the new design:** per-candidate and per-rejection lines in tight resolution loops (e.g. `[RBMEM][CANDIDATE]`, `[RBMEM][REJECT]`, retries, rewinds) belong at DEBUG; INFO is for *outcomes* (`[VALIDATED]`, `[D2COMMIT]`); duplicate lines that fire together should be merged; drift warnings need `deck=` context to be actionable. During a two-deck resolution these lines used to spam 50+ INFO lines per event and made the log unreadable — your lens/severity model should make that class of noise structurally impossible, not just discouraged.

**Concurrent-edit note:** other agent sessions are modifying files in this repo while you read. You are designing architecture, not depending on exact current line numbers, so a moving target is fine — but if a file looks mid-edit or internally inconsistent, treat that as an artifact of concurrent work rather than a real design signal, and note it.

**Known-stale / do not trust blindly:** anything under `docs/prompts/**`, `docs/plans/**`, `docs/history/**`, or any doc without a current status header — historical evidence only, verify against code. If a doc conflicts with code, code wins.

**Explicit unknowns to name rather than guess:** the SYSTEM lens contents (Brandon had no specifics); whether OPERATOR needs active reconciliation; the exact set of files whose current log calls are load-bearing vs noise. Where you can't verify from the code, say so and mark it a gap rather than inventing a fact.

## Boundaries (this run)

- **Read-only exploration of the repo is allowed and expected** (read files, search, read git history) so your design is grounded in the real decision points. **Do not modify any existing file, and do not change any code, test, config, runtime state, or hardware. Do not run or restart the bridge.** The only file you may write is your design document (below).
- **Do not implement (Phase 3), and do not write the implementation spec (Phase 2).** Both are later phases in separate runs. Producing either now violates the execution gate.
- No live-bridge interaction, no MIDI, no DMX, no Govee, no SoundSwitch, no hardware.

## Claim discipline

Label load-bearing claims **confirmed / assumed / unknown / rejected**, tied to what you read. Distinguish "the code does X (confirmed at `file.py:line`)" from "I'm assuming X." Don't reproduce or narrate private reasoning — give evidence-tied findings, decisions, and their justifications, not a transcript of your thinking.

## Deliverable (Phase 1)

Write a single design document to `docs/plans/active/logging_overhaul_design.md`, and open your final message to Brandon with the outcome in plain language (what you're recommending and the one or two things, if any, you need from him) before any detail. The document must contain:

1. **What you changed about the spine and why** — your critique and improvements, each tied to evidence from the code or Brandon's stated needs. Call out any reversal of an operator decision explicitly, and record the Phase 3 operator role exception (Fable-family implements).
2. **The resolved design** — the lens model, the record schema, the source-of-truth emit strategy (how a decision point emits one record without touching the push loop), the SYSTEM taxonomy, your OPERATOR passive-vs-active ruling, the viewer/TUI design, the teardown plan (what dies, what's salvaged), and how the live-safety invariant is preserved end to end.
3. **A build decomposition and order** — the design broken into buildable chunks with dependencies, sized so Phase 2 (spec) and Phase 3 (build) pick it up cleanly. Include the incremental migration approach for the ~46 files.
4. **A spec-readiness verdict:** `READY` / `READY WITH GAPS` / `NOT READY`, with any blocking gaps listed first — the specific unknowns Phase 2 cannot proceed without.

Then stop. Do not begin Phase 2 or Phase 3.

## Success criteria (falsifiable)

- The design is **simpler to reason about than today's `logging_manager.py`**, and you can point to what was deleted to make it so.
- PERFORMANCE, OPERATOR, SYSTEM, and MAX DEBUG each have a crisp, non-overlapping definition, a concrete example line, and a stated routing rule.
- The push-loop live-safety invariant is provably preserved: you can name exactly what the bridge process does on the hot path (append a record) and what it never does.
- The per-candidate-spam noise class is structurally prevented by the design, not left to discipline.
- The build decomposition is concrete enough that a Phase 2 spec is a mechanical translation, and the readiness verdict names any gap that would block that.
- You did not write the spec, modify any code, or touch the runtime.

Take the long turn this needs — gather context from the code, decide, and self-check your design against these criteria before you finish. Pause only if you hit something only Brandon can answer.
