---
doc_status: current
truth_level: prompt/handoff — Opus 4.8 prompt text only
last_verified_commit: 34eb910
last_verified_date: 2026-07-05
validation_scope: Claude Opus 4.8 prompt text only; no bridge behavior, runtime action, or hardware validation. Seams cited were verified read-only against HEAD + working tree this session.
---

# Opus 4.8 Prompt — LIGHTING v1 foundation audit (stabilize the baseline before LIGHTING ENGINE v2)

**Paste-to-Opus kickstart:** *"Read `docs/prompts/lighting_v1_foundation_audit_opus_prompt.md` and execute it. Effort: xhigh. Set a large max-output budget (~64k)."*

---

**Target model: Claude Opus 4.8. Effort: `xhigh`. Set max output tokens to ~64k.** This run is authorized to author and run **Workflow** orchestrations (ultracode) and to spawn subagents.

This is benign local software work for Brandon's DJ lighting bridge. Review only normal software correctness, tests, maintainability, runtime safety, and operator-facing behavior inside the named scope. No safety ceremony is needed.

## Mission (one line)

**Audit every v1 lighting feature that LIGHTING ENGINE v2 will build on, find the real bugs, and hand back a ranked findings report plus a separate Codex-executable fix plan — so the v2 foundation is provably sound before Fable starts.** You reason, audit, and spec. You do **not** implement, and you do **not** hand anything to Codex or change any behavior until Brandon gives explicit approval at the one gate.

## Why it matters / who it's for

v2 is a **toggle over v1, not a replacement.** It reuses v1's machinery — the Govee renderer, drop-marker detection, the Stream Deck pads, the fade primitives, the active-deck resolver, LED dispatch, the color/palette engine. So a bug in shared code doesn't stay in v1; **v2 inherits it.** Three consequences make stabilizing the baseline first non-negotiable:

1. **The "v2-off ⇒ v1 byte-identical" guarantee only helps if v1 is the baseline Brandon actually wants.** Build on buggy v1 and the bug is baked into both modes — and the byte-identical golden tests would *lock the bug in as "correct."*
2. **Clean live diagnosis is the real payoff.** Brandon's eyes are the acceptance gate. When the room misbehaves in v2 he flips to v1: also wrong ⇒ v1 bug; fine ⇒ v2 bug. That single flip only works if v1 is trustworthy. A buggy v1 makes every v2 anomaly ambiguous — debugging two things at once, live, in front of a crowd.
3. **Fixing v1 is cheap Codex work** — it never touches Brandon's scarce Fable budget. Stabilizing the baseline costs almost nothing on the budget that matters.

Brandon (the operator, not a software engineer) is the audience for your gate message. He reads it cold, in chat, and refuses to open docs — so the gate must say everything he needs to decide, fully, in plain language. He decides what gets fixed.

## What "v2's path" means — the load-bearing classification

The Fable prompt `docs/prompts/lighting_engine_v2_fable_prompt.md` is the definition of scope. Its **"Verified seams"** and **"Gaps to consider"** sections enumerate exactly the code v2 F1–F4 builds on. Treat everything reachable from those seams in the live LED render path as **on v2's path**. Concretely, on-path modules include (verify each against code, do not treat this list as exhaustive or as gospel):

- Stream Deck: `streamdeck_midi.py`
- Color / palette / identity: `led_color_engine.py`, `led_palette_control.py`, `led_pad_controls.py`, `led_models.py`, `led_config.py`, `led_look_director.py`
- Drop presentation / dispatch: `led_dispatch_policy.py` (incl. `LED_MAX_DROP_IMPACTS`), `led_dispatch_coordinator.py`, `drop_lifecycle.py` and the drop-marker detection it consumes
- Govee render / fade primitives / slot contract: `govee_frame_renderer.py` (`universal_colorizer`, `_slots`, `resolve_fade`, `slot_colors_from|to`, `render_comet`), `govee_realtime_runner.py` (`_compose_frame`), `govee_realtime_transport.py`, `govee_runtime_sender.py`, `govee_scene_adapter.py`, `govee_owner_state.py`
- Beat / reset: `beat_sync_engine.py`
- Shared runtime seams v2 reads: `active_deck_resolver.py`, the first-load analysis + LED-relevant paths in `state_manager.py`

**Isolated from v2's path (defer, do NOT block on, do NOT write fix specs for):** laser subsystem (`laser_*.py`, `midi_output.py`, `personality_resolver.py` — Brandon has ruled lasers out of F1 scope and they do not coordinate with the LED blackout), SoundSwitch pack/output modules, Govee LAN discovery, session tooling, and any LED feature the v2 seams provably never reach. If a module straddles both (e.g. drop-marker detection feeds both LED and laser), classify by whether the *v2 LED path* depends on the buggy behavior — and say so.

**Do not over-fix.** A bug isolated from v2 is a note in the deferred bucket, not a fix spec, and never a reason to hold the crown jewel hostage.

## Deliverables

Two artifacts, plus the gate message in chat:

1. **A findings report** at `docs/plans/active/lighting_v1_foundation_audit.md` (repo frontmatter; status `current`). It contains, for **every** finding: a plain-language symptom (what goes wrong in the room), exact `file:line` at HEAD/working-tree, the **authoritative intent it violates** (which doc + section says the other behavior is correct — see Grounding below), classification (**on-v2-path / isolated**), severity, confidence, the adversarial verdict (CONFIRMED / PLAUSIBLE / REJECTED), and whether a golden/byte-identical test currently encodes the buggy behavior.

2. **A Codex fix plan** — one Part A–E spec per `.claude/skills/codex-spec/SKILL.md` covering the **on-v2-path CONFIRMED** fixes, authored as a **standalone v1-baseline-stabilization pass, explicitly NOT folded into the v2 build.** File: `docs/plans/active/lighting_v1_foundation_fix_spec.md`. Each fix must state which tests need re-baselining (a v1 behavior change is a baseline change, and any byte-identical golden that encoded the bug must be updated with a note, not silently) and flag re-baselining as a Brandon decision.

3. **The gate message, in chat, in plain language** (Grounding + gate below). This is where Brandon decides. The docs are Codex-facing records; chat carries the decision.

**Do not implement. Do not edit bridge code. Do not hand anything to Codex.** Your output is the audit + the spec Codex will later execute — after, and only after, Brandon approves.

## Grounding — the regression guard (do this or the audit is unsafe)

"Working as intended" is undefined without a definition of intent. So:

- **A finding is a CONFIRMED bug only if an authoritative doc says the behavior should be otherwise.** Cite it: `docs/architecture/lighting_engine_v2_authority.md` (the intended-experience authority), `docs/architecture/LIGHTING_ENGINE_V2_DESIGN.md` (locked v2 design), `docs/architecture/runtime_invariants.md`, `AGENTS.md §6` invariants, `docs/agents/change_contracts.yml`, the relevant subsystem card under `docs/subsystems/`, or an existing test that asserts the correct behavior.
- **If no authoritative doc defines the intent, the behavior is AMBIGUOUS, not a bug.** Flag it as an operator decision ("is this a bug or intended? — needs your eyes"), do not write a fix for it, and do not assume. This is what stops you from "fixing" deliberate behavior and *causing* the regression you were sent to prevent.
- **Code wins over docs when they conflict** (`AGENTS.md §1`). If a doc claims X and code does Y, that is itself a finding (drift), classified by whether v2 depends on it.
- **Hunt the byte-identical trap explicitly:** find golden/snapshot/byte-identical tests in `tests/` that assert current LED output. For each on-path bug, check whether such a test has frozen the buggy behavior as "correct." If so, the fix spec must call out that test by name.

## Evidence packet — source-of-truth order: code > tests > this packet > docs

- **Scope definition:** `docs/prompts/lighting_engine_v2_fable_prompt.md` — "Verified seams" + "Gaps" = the v2-path surface.
- **Intended behavior (authoritative):** `docs/architecture/lighting_engine_v2_authority.md`, `docs/architecture/LIGHTING_ENGINE_V2_DESIGN.md`, `docs/architecture/runtime_invariants.md`, `docs/agents/change_contracts.yml`, `docs/subsystems/led_govee.md` (and `runtime_commands.md`, `laser.md` for boundary calls).
- **Working-tree state (uncommitted at session start — audit the actual current code, and flag anything here you cannot explain):** `led_dispatch_policy.py`, `led_palette_control.py`, `state_manager.py`, `tests/test_led_palette_control.py` are modified vs HEAD `34eb910`. These sit squarely on v2's path — read the working tree, not just HEAD, and note whether the uncommitted diff introduces, fixes, or masks any finding.
- **Test surface:** `python3 -m unittest discover tests` (read-only, to establish the current green/red baseline and to see which behaviors are pinned). Some tests need optional deps and none prove hardware.
- **Known-stale / unknowns:** any pre-2026-07-05 spec/plan; live config values (gitignored); Govee/Stream Deck device latency and hardware behavior (unvalidated — never claim a hardware-level bug as confirmed). Verify before relying.

## Orchestration (Workflow + ultracode) — how to run this

Run this as a **Workflow** you author, using the canonical find → adversarially-verify → classify → synthesize pipeline. Guidance, not a cage — scale the fan-out to the surface:

- **Find (coverage):** one finder subagent per on-v2-path subsystem grouping, each handed its exact modules + the matching subsystem card + the authoritative intent doc. Instruct finders for **coverage, not precision** — surface everything with confidence + severity; a later stage filters. (Paste `review-coverage` below into finder prompts.)
- **Verify (adversarial, perspective-diverse):** every candidate bug gets independent skeptic verification before it earns CONFIRMED. Use distinct lenses: (a) **does it reproduce** — trace the actual code path at the cited lines; (b) **does an authoritative doc actually mandate the other behavior** — the intent check; (c) **is there a golden test encoding current behavior** — the regression check. Default to PLAUSIBLE/REJECTED when uncertain; a false "confirmed bug" that changes a live baseline is worse than a miss you flag for Brandon's eyes.
- **Classify & synthesize:** dedup, split on-path vs isolated, rank by severity, and you (Opus) write the report + the Codex fix spec from the survivors yourself.
- **Completeness critic:** a final subagent that asks "what v2-path seam, intended behavior, or golden test did we not check?" — its gaps become one more finder round.
- **Subagents:** spawn on **non-Fable models** (Opus/Sonnet/Haiku — Brandon's Fable quota is scarce and this run must not touch it). Pick model and effort per stage: finders and verifiers benefit from `high`; cheap mechanical grep-and-trace can run lower. **Never spawn a Fable subagent.**

## Scope, boundaries, allowed tools

- **You may:** read any repo file; run `python3 -m unittest discover tests` and the repo doc/contract checks read-only; `rg`/`grep`/graph orientation; author and run Workflows and non-Fable subagents; write the two named docs under `docs/plans/active/`.
- **You may not:** edit any bridge code (`*.py` runtime modules); modify tests (do not change tests to make anything pass); touch the running bridge, hardware, or live config; hand anything to Codex; create branches/worktrees; force-push or rewrite history. Work on `main`.
- **Keep it minimal:** report the bugs that matter to v2, not a style sweep. No refactor proposals beyond what a fix needs. Isolated bugs get a one-line deferred note, not a spec.

## Claim discipline

Label every claim **confirmed / assumed / unknown / rejected**, tied to a `file:line` you (or a subagent whose result you re-checked) verified at HEAD/working-tree. This packet and any memory may be stale — code wins. Report progress only against real tool results; if the suite fails, say so with the output. State a finding CONFIRMED only after adversarial verification survived.

## Success criteria (falsifiable) / the one gate

- Every on-v2-path lighting subsystem in the scope list was audited by a finder **and** a completeness pass; coverage gaps are named, not silent.
- Every CONFIRMED bug cites the authoritative doc it violates; every AMBIGUOUS one is flagged as a Brandon decision, not fixed.
- On-path vs isolated classification is explicit for every finding, with the dependency reason for straddlers.
- The Codex fix spec covers only on-path CONFIRMED fixes, is a standalone v1-baseline pass (not folded into v2), satisfies the codex-spec 9-point checklist, and lists every test needing re-baselining.
- The byte-identical trap was checked: golden tests encoding buggy behavior are named.

**THE GATE — hard stop, explicit approval required.** After the audit and the draft fix spec are done, **STOP.** Do not hand anything to Codex, do not edit code, do not begin implementation. Present in chat, plain language, lead with the outcome:

> what you audited → the on-path CONFIRMED bugs (each: what the room does wrong, the fix in one line, confidence, which authoritative doc backs "correct," and any golden test that must be re-baselined) → the AMBIGUOUS items needing his eyes → the deferred isolated bugs (brief) → the explicit ask: *approve the v1-baseline fix pass for Codex, per-item veto.*

Only after Brandon's explicit approval does the fix pass proceed (and it proceeds as a **separate Codex pass**, kept out of the v2 build so the v1↔v2 byte-identical toggle stays clean). If you hit a genuine scope change or a decision only he can make, surface it at this same gate.

**Do not reveal, transcribe, or explain private chain-of-thought** — give evidence-tied findings, claim labels, and verdicts only.

---

### Paste-in blocks (from `docs/prompts/snippets/opus48_snippets.md`)

**Into every finder subagent prompt (`review-coverage`):**

> Report every issue you find, including ones you are uncertain about or consider low-severity. Do not filter for importance or confidence at this stage - a separate verification step will do that. Your goal here is coverage: it is better to surface a finding that later gets filtered out than to silently drop a real bug. For each finding, include your confidence level and an estimated severity so a downstream filter can rank them.

**Into the orchestration, so scope is applied to all subsystems, not just the first (`apply-broadly`):**

> Apply this audit to every subsystem on v2's path, not just the first one.

**Subagent spawning (`subagent-control`):**

> Do not spawn a subagent for work you can complete directly in a single response. Spawn multiple subagents in the same turn when fanning out across items or reading multiple files.
