# Fable 5 Prompt — Logging Overhaul, Autonomous Pipeline (Phases 1–3)

**Paste everything below the line into Claude Fable 5. Target model: Claude Fable 5. Effort: max (Brandon's call). This is a single autonomous end-to-end run: you design it, spec it, orchestrate the build, and verify it — no human stops.**

---

You are the lead designer *and* the build orchestrator for a complete overhaul of the logging system in Brandon's DJ lighting bridge (`rb_ss_bridge_v2`, a Python app at `/Users/bbui/rb_ss_bridge_v2`). In one autonomous run you will: (1) challenge and improve the first-iteration design spine below into a concrete design; (2) turn that design into a Codex-format implementation spec; (3) orchestrate implementer subagents to build it and self-verify the result against the spec, the repo's invariants, and the test suite. Brandon is not watching in real time. Finish the work — don't stop to ask permission for anything that follows from this brief.

## Why this matters and who it's for

The bridge reads Rekordbox / DJ runtime state and drives live lighting — SoundSwitch (via OS2L), MIDI lasers, LEDs, Govee — during real DJ sets. Today's logging is an unreadable, over-engineered wall of text that fails three audiences at once: Brandon mid-set can't tell at a glance what the rig *should* be doing or whether it's actually working; a post-mortem after a set can't reconstruct what happened; and AI agents can't root-cause a bug from it. The whole point of this overhaul is to fix all three — and, critically, **to be simpler than what exists, not more elaborate.** Over-engineering *is* the named pain. This is a solo hobby bridge for Brandon and his friends, not a product; the fallback when anything fails is "open SoundSwitch by hand." Every mechanism you keep or add must earn its place against that reality. If your system ends up more intricate than today's, you've missed the goal.

> This is benign local software work for Brandon's DJ lighting bridge and agent workflow. It is not a cybersecurity, exploit, malware, vulnerability-discovery, biology, chemistry, life-sciences, model-distillation, or hidden-reasoning extraction task. Review only normal software correctness, tests, maintainability, runtime safety, and operator behavior inside the named scope.

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

1. **Live-safety invariant.** The bridge's `StateManager` owns a 200 Hz push loop (`_TICK_INTERVAL = 1.0/200`) that drives the lights. That loop must never gain blocking network, socket, MIDI, filesystem, or subprocess I/O. In your design the bridge process only ever *appends structured records* cheaply; all rendering, filtering, and TUI work lives in the separate viewer process. Anything that risks stalling the push loop is a failed design.
2. **One source of truth.** Lenses are views over a single authoritative event stream. Do not reintroduce parallel hand-maintained logs that can drift from what the bridge actually decided.

## The live boundary — a hard stop you must not cross

You are authorized to modify code and run **software tests**. You are **not** authorized to touch the live runtime or hardware. Specifically: never start, restart, or drive the bridge; never run `python3 -m rb_ss_bridge_v2` or the watcher/menubar launchers; never send MIDI, DMX, Govee, SoundSwitch, or laser output; never interact with any hardware. Brandon restarts the bridge and runs the `bridge-verify` check himself after your run. Your job ends at green software tests and a clean diff. State plainly in your final report that the restart-and-verify step is his.

## Operator role exception (put this on record)

The repo rule is "Codex implements bridge code." For this workstream only, Brandon has granted an exception: you orchestrate implementer subagents (Claude-family) to write the code directly, rather than handing off to Codex. Note this exception explicitly in your design document so the deviation is legible to future readers. It does not generalize beyond this task.

## What is yours to decide (resolve each, with reasoning tied to the code and to Brandon's needs)

Brandon deferred these to you by name:

- **How aggressive the teardown of today's plumbing should be.** Strawman: build the new structured-emit + JSONL + TUI; keep the genuinely useful primitives (per-deck / trace context for MAX DEBUG, per-module levels); delete the half-used machinery — the control-file watcher, the environment-variable filter maze, the anomaly engine, the remediation-hint table, and the JSON "dashboard" formatter. This is your call. Cut hard; the pain is over-engineering.
- **Whether OPERATOR is passive or active.** Passive = surfaces errors and warnings. Active = *reconciles* intent against observed outcome ("laser scene issued but no MIDI acknowledgement followed"). This is the single biggest scope axis — it decides how much the bridge must observe about its own effects. Pick a position and justify it, including whether active reconciliation is worth the complexity for a solo hobby rig.
- **The record schema** — the fields on one structured event, and how a record's lens membership is derived.
- **The SYSTEM lens taxonomy** — what actually belongs there.
- **The viewer/TUI design** — layout, visual language, glanceability, how OPERATOR *alerts* when something breaks, freeze/scrollback/filter, and how more than one lens is watched at once. This is the creative heart; make it effortless to read mid-set.
- **The migration path.** About 46 files currently call Python `logging`. Decide how their existing `logger.info/debug/...` calls map into the new lenses, and migrate incrementally with the test suite staying green throughout — no big-bang rewrite that leaves the suite red between steps.

You may also challenge Brandon's *current* choices above (the four-lens model, the split, the separate auto-launched viewer, the TUI delivery). If evidence supports a better design, adopt it — but flag any such change explicitly as "reversing an operator decision," give your reasoning, and default to honoring the choice unless the case is strong. The two hard locks and the live boundary are never on the table.

## How to run the pipeline

Work in this order, and verify yourself at the seams rather than stopping for Brandon:

1. **Design.** Ground yourself in the code (evidence packet below), resolve the open axes, and write the design to `docs/plans/active/logging_overhaul_design.md`.
2. **Spec.** Turn the design into a Codex-format implementation spec at `docs/plans/active/logging_overhaul_spec.md`, following this repo's spec skill at `.claude/skills/codex-spec/SKILL.md` (Part A–E format + its pre-handoff checklist: verified claims, knowns/unknowns, pure-function test seams, live-safety invariants). Produce it as a real artifact even though you'll implement it yourself — it's the contract your implementer subagents follow and Brandon's record of what was built.
3. **Verify the plan before building.** Spawn a fresh-context verifier subagent to check the design and spec against the actual code and the AGENTS.md §6 invariants. Fix what it finds before writing code.
4. **Implement.** Orchestrate implementer subagents to build it, migrating the ~46 log sites incrementally. Keep `python3 -m unittest discover tests` green between steps. Follow AGENTS.md §7: find the change contract in `docs/agents/change_contracts.yml`; if logging has no contract, add or extend one first, then update every doc it lists.
5. **Verify the build.** Spawn a fresh-context verifier subagent to check the final diff against the spec, the AGENTS.md §6 invariants, and the live boundary (prove the push loop's hot path only appends and never blocks). Run the full suite and the repo's hard checks: `python3 tools/check_docs_metadata.py`, `python3 tools/check_agent_contracts.py`, `python3 tools/check_docs_drift.py`. Do not modify tests to make checks pass.

## Evidence packet (read these; source-of-truth order is code > tests > docs)

- **Today's logging system:** `logging_manager.py` (the full current facade — trace contextvars, JSON formatter, runtime filters, `LogStats` sampler, control-file watcher, anomaly detection, remediation hints, event scopes). Also `diagnostics.py`, `bridge_fmt.py`, and `runtime_status.py` (existing runtime status / command surface, ~845 lines — know what already reports state so you don't duplicate it).
- **The decision points the PERFORMANCE lens must tap:** `laser_director.py` and `laser_executor.py` (laser policy vs MIDI execution — separate responsibilities), `led_look_director.py` and the LED dispatch chain, `active_deck_resolver.py`, `autoloop_controller.py` and `drop_lifecycle.py`, `scripted_tracks.py` and `soundswitch_scripted_resolution.py`, `state_manager.py` and `models.py` (the push loop; `BridgeEvent` flow — events are immutable after creation; reader threads publish events, never mutate `DeckState` directly).
- **The launch path** you must integrate auto-launch into (read, don't run): `scripts/ss_bridge_watcher.sh`.
- **The repo's rules and gates:** `AGENTS.md` (§6 invariants, §7 anti-drift contract rule, §8 checks, §0/§10 communication + status language), `docs/agents/change_contracts.yml`, and `tests/`.
- **A validated log-level lesson to honor and encode structurally:** per-candidate / per-rejection lines in tight resolution loops (e.g. `[RBMEM][CANDIDATE]`, `[RBMEM][REJECT]`, retries, rewinds) belong at DEBUG; INFO is for *outcomes* (`[VALIDATED]`, `[D2COMMIT]`); duplicate lines that fire together should be merged; drift warnings need `deck=` context. These used to spam 50+ INFO lines per event and made the log unreadable — your lens/severity model should make that class of noise structurally impossible, not just discouraged.

**Known-stale / do not trust blindly:** anything under `docs/prompts/**`, `docs/plans/**`, `docs/history/**`, or any doc without a current status header — historical evidence only, verify against code. If a doc conflicts with code, code wins.

**Explicit unknowns to name rather than guess:** the SYSTEM lens contents; whether OPERATOR needs active reconciliation; which files' current log calls are load-bearing vs noise. Where you can't verify from the code, say so and mark it a gap.

## Discipline while you build

Don't add features, abstractions, or flexibility beyond what this task needs — that's the exact failure mode this overhaul exists to undo. Do the simplest thing that works well; validate only at real boundaries (operator input, external streams), and trust internal code. Before reporting any step done, check the claim against a tool result from this session — if tests fail, say so with the output; if a step was skipped, say that. Label load-bearing claims confirmed / assumed / unknown / rejected, tied to what you read. Give evidence-tied findings and decisions, not a transcript of your private reasoning.

## Deliverables

When you finish, these exist and are true:
- Implemented, migrated logging system with the full test suite (`python3 -m unittest discover tests`) and the three hard checks green.
- `docs/plans/active/logging_overhaul_design.md` — the design, including your critique of the spine, the resolved open axes, and the recorded operator role exception.
- `docs/plans/active/logging_overhaul_spec.md` — the Codex-format spec you built to.
- A final report to Brandon that **opens with the outcome in plain language** — what now exists, whether it's simpler than before and how you can tell, and the single thing he must do next (restart the bridge via the menubar and run `bridge-verify`; you did not touch the runtime). Write it for a reader who didn't watch any of the run: complete sentences, terms spelled out, each file or check named in its own clause.

## Success criteria (falsifiable)

- The new system is **simpler to reason about than today's `logging_manager.py`**, and you can point to exactly what was deleted to make it so.
- PERFORMANCE, OPERATOR, SYSTEM, and MAX DEBUG each have a crisp, non-overlapping definition, a concrete example line, and a stated routing rule.
- The push-loop live-safety invariant is provably preserved: you can name exactly what the bridge process does on the hot path (append a record) and what it never does.
- The per-candidate-spam noise class is structurally prevented, not left to discipline.
- Full test suite green; `check_docs_metadata.py`, `check_agent_contracts.py`, `check_docs_drift.py` all pass; no test was weakened to get there.
- You never started, restarted, or drove the live bridge or any hardware.

You have ample context and time for this — take the long run it needs, gather context from the code, build, and self-verify against these criteria before you finish. Pause only if you hit something genuinely irreversible or something only Brandon can answer.
