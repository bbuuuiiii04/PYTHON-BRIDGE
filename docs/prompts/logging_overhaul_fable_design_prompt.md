# Fable 5 Prompt — Logging Overhaul, Phase 1 (Creative Design)

**Paste everything below the line into Claude Fable 5. Target model: Claude Fable 5. Effort: max (Brandon's call — this is the hardest, most ambiguous design work in the project right now).**

---

You are the **lead creative designer** for a complete overhaul of the logging system in Brandon's DJ lighting bridge (`rb_ss_bridge_v2`, a Python app at `/Users/bbui/rb_ss_bridge_v2`). Your job in this phase is to **challenge and improve** the first-iteration design spine below, then deliver a concrete, buildable design. This is Phase 1 of three: Phase 2 turns your design into a Codex implementation spec, Phase 3 orchestrates the build. **Do not implement anything and do not write the Codex spec** — your deliverable is the design that those later phases execute.

## Why this matters and who it's for

The bridge reads Rekordbox / DJ runtime state and drives live lighting — SoundSwitch (via OS2L), MIDI lasers, LEDs, Govee — during real DJ sets. Today's logging is an unreadable, over-engineered wall of text that fails three audiences at once: Brandon mid-set can't tell at a glance what the rig *should* be doing or whether it's actually working; a post-mortem after a set can't reconstruct what happened; and AI agents can't root-cause a bug from it. The whole point of this overhaul is to fix all three — and, critically, **to be simpler than what exists, not more elaborate.** Over-engineering *is* the named pain. This is a solo hobby bridge for Brandon and his friends, not a product; the fallback when anything fails is "open SoundSwitch by hand." Every mechanism you keep or add must earn its place against that reality. If your design ends up more intricate than today's, you've missed the goal.

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

1. **Live-safety invariant.** The bridge's `StateManager` owns a 200 Hz push loop (`_TICK_INTERVAL = 1.0/200`) that drives the lights. That loop must never gain blocking network, socket, MIDI, filesystem, or subprocess I/O. In this design, the bridge process only ever *appends structured records* cheaply; all rendering, filtering, and TUI work lives in the separate viewer process. A logging design that risks stalling the push loop is a failed design.
2. **One source of truth.** Lenses are views over a single authoritative event stream. Do not reintroduce parallel hand-maintained logs that can drift from what the bridge actually decided.

## What is yours to decide (resolve each, with reasoning tied to the code and to Brandon's needs)

Brandon explicitly wants you to own these — several he deferred to you by name:

- **How aggressive the teardown of today's plumbing should be.** My strawman: build the new structured-emit + JSONL + TUI; keep the genuinely useful primitives (per-deck / trace context for MAX DEBUG, per-module levels); delete the half-used machinery — the control-file watcher, the environment-variable filter maze, the anomaly engine, the remediation-hint table, and the JSON "dashboard" formatter. Brandon said this is your call. Cut hard; the pain is over-engineering.
- **Whether OPERATOR is passive or active.** Passive = it simply surfaces errors and warnings. Active = it *reconciles* intent against observed outcome ("laser scene was issued but no MIDI acknowledgement followed"). This is the single biggest scope axis in the whole design — it decides how much the bridge has to observe about its own effects. Pick a position and justify it, including whether active reconciliation is worth the added complexity for a solo hobby rig.
- **The record schema** — the fields on one structured event, and how a record's lens membership is derived (by category? severity? explicit tag? more than one lens at once?).
- **The SYSTEM lens taxonomy** — what actually belongs there.
- **The viewer/TUI design** — layout, visual language, glanceability, how it makes OPERATOR *alert* Brandon when something breaks, whether it supports freeze/scrollback/filter, and how more than one lens is watched at once. This is the creative heart; make it feel effortless to read mid-set.
- **The migration path.** About 46 files currently call Python `logging`. Decide how their existing `logger.info/debug/...` calls map into the new lenses, and how the migration lands without a risky big-bang rewrite of the whole bridge at once.

You may also challenge Brandon's *current* choices above — the four-lens model, the lens split, the separate auto-launched viewer, the TUI-vs-alternative delivery. If evidence says a better design exists, propose it, but **flag any such change explicitly as "reversing an operator decision," give your reasoning, and default to honoring the choice** unless the case is strong. The two hard locks are not on the table.

## Evidence packet (read these; source-of-truth order is code > tests > docs)

Read-only. These are where the real behavior and the real decision points live:

- **Today's logging system:** `logging_manager.py` (the full current facade — trace contextvars, JSON formatter, runtime filters, `LogStats` sampler, control-file watcher, anomaly detection, remediation hints, event scopes). Also `diagnostics.py`, `bridge_fmt.py`, and `runtime_status.py` (the existing runtime status / command surface, ~845 lines — understand what already reports state so you don't duplicate it).
- **The decision points the PERFORMANCE lens must tap** (read enough to know *where* intent is decided): `laser_director.py` and `laser_executor.py` (laser policy vs MIDI execution — separate responsibilities), `led_look_director.py` and the LED dispatch chain, `active_deck_resolver.py` (active-deck switches), `autoloop_controller.py` and `drop_lifecycle.py` (drop detection + type, autoloop arm/clear), `scripted_tracks.py` and `soundswitch_scripted_resolution.py` (scripted-track + SoundSwitch selection), `state_manager.py` and `models.py` (the push loop, and `BridgeEvent` flow — events are immutable after creation; reader threads publish events, never mutate `DeckState` directly).
- **The launch path** you must integrate auto-launch into: `scripts/ss_bridge_watcher.sh` (the canonical watcher; the bridge is launched only through it / the menubar, never raw `python3 -m rb_ss_bridge_v2`).
- **The repo's own rules:** `AGENTS.md` §6 (invariants agents must not break) and §0/§10 (communication + status language).
- **A validated log-level lesson to honor and encode in the new design:** per-candidate and per-rejection lines in tight resolution loops (e.g. `[RBMEM][CANDIDATE]`, `[RBMEM][REJECT]`, retries, rewinds) belong at DEBUG; INFO is for *outcomes* (`[VALIDATED]`, `[D2COMMIT]`); duplicate lines that fire together should be merged; drift warnings need `deck=` context to be actionable. During a two-deck resolution these lines used to spam 50+ INFO lines per event and made the log unreadable — your lens/severity model should make that class of noise structurally impossible, not just discouraged.

**Known-stale / do not trust blindly:** anything under `docs/prompts/**`, `docs/plans/**`, `docs/history/**`, or any doc without a current status header — historical evidence only, verify against code. If a doc conflicts with code, code wins.

**Explicit unknowns to name rather than guess:** the SYSTEM lens contents (Brandon had no specifics); whether OPERATOR needs active reconciliation; the exact set of files whose current log calls are load-bearing vs noise. Where you can't verify from the code in the time you have, say so and mark it a gap rather than inventing a fact.

## Boundaries

- **Read-only exploration of the repo is allowed and expected** (read files, search, read git history) so your design is grounded in the real decision points. **Do not modify any code, tests, config, runtime state, or hardware, and do not run or restart the bridge.** The only file you may write is your design document (below).
- **Do not implement, and do not write the Codex spec.** Your design feeds a later Codex-spec step; producing the spec now is out of scope.
- This is design and planning. No live-bridge interaction, no MIDI, no DMX, no Govee, no SoundSwitch, no hardware.

## Claim discipline

Label load-bearing claims **confirmed / assumed / unknown / rejected**, tied to what you read. Distinguish "the code does X (confirmed at `file.py:line`)" from "I'm assuming X." Don't reproduce or narrate private reasoning — give evidence-tied findings, decisions, and their justifications, not a transcript of your thinking.

## Deliverable

Write a single design document to `docs/plans/active/logging_overhaul_design.md`, and open your final message to Brandon with the outcome in plain language (what you're recommending and the one or two things, if any, you need from him) before any detail. The document must contain:

1. **What you changed about the spine and why** — your critique and improvements, each tied to evidence from the code or Brandon's stated needs. Call out any reversal of an operator decision explicitly.
2. **The resolved design** — the lens model, the record schema, the source-of-truth emit strategy (how a decision point emits one record without touching the push loop), the SYSTEM taxonomy, your OPERATOR passive-vs-active ruling, the viewer/TUI design, the teardown plan (what dies, what's salvaged), and how the live-safety invariant is preserved end to end.
3. **A build decomposition and order** — the design broken into buildable chunks with dependencies, so Phase 2 (Codex spec) and Phase 3 (orchestration) can pick it up cleanly. Include the migration approach for the ~46 files.
4. **A spec-readiness verdict:** `READY` / `READY WITH GAPS` / `NOT READY`, with any blocking gaps listed first — the specific unknowns that Phase 2 cannot proceed without.

## Success criteria (falsifiable)

- The design is **simpler to reason about than today's `logging_manager.py`**, and you can point to what was deleted to make it so.
- PERFORMANCE, OPERATOR, SYSTEM, and MAX DEBUG each have a crisp, non-overlapping definition, a concrete example line, and a stated rule for what routes into them.
- The push-loop live-safety invariant is provably preserved: you can name exactly what the bridge process does on the hot path (append a record) and what it never does.
- The noise class from the log-level lesson (per-candidate spam in tight loops) is structurally prevented by the design, not left to discipline.
- The build decomposition is concrete enough that a Codex spec is a mechanical translation, and the readiness verdict names any gap that would block that.

Take the long turn this needs — gather context from the code, decide, and self-check your design against these criteria before you finish. Pause only if you hit something only Brandon can answer.
