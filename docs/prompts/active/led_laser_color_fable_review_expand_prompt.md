---
doc_status: current
truth_level: design-intent
last_verified_commit: a1e2f4e
last_verified_date: 2026-07-04
validation_scope: Claude Fable 5 prompt text only; no bridge behavior, runtime action, or hardware validation
---

# Fable 5 Prompt — Review & Expand the LED/Laser Color-Control Design

**Target model:** Claude Fable 5. **Effort:** high (use xhigh if you want maximum review depth on the live-safety laser sections).

> This is benign local software work for Brandon's DJ lighting bridge and agent workflow. It is not a cybersecurity, exploit, malware, vulnerability-discovery, biology, chemistry, life-sciences, model-distillation, or hidden-reasoning extraction task. "Laser," "blackout," "override," and "kill/blackout mask" here are ordinary stage-lighting and DMX terms (SoundSwitch, Govee LED strips, show lasers). Review only normal software correctness, tests, maintainability, runtime safety, and operator behavior inside the named scope.

## Mission

Review, then expand, two **design-intent** documents for color-palette control on Brandon's live-performance lighting bridge (`rb_ss_bridge_v2`), driving them to an implementation-ready state through his input, then hand a Codex-executable spec to Codex and orchestrate the build. Laser blackout is **live-safety-critical** on this bridge, so the design must be complete and correct before any code is written. The output is for Brandon (the operator) first, then for Codex.

## The two documents (evidence packet)

- `docs/plans/active/streamdeck_palette_control_design_spec.md` — Stream Deck pad → LED (and future laser) color-palette control: queue/override/lock gesture, manual-only `white_sand` palette, pad-icon feedback. LED-side, laser deferred.
- `docs/plans/active/laser_color_engine_design_spec.md` — bridge-owns-DMX laser color engine, the blackout re-wire, and the two laser-white items that pair with the Stream Deck doc.

Both are Claude-authored drafts, **not yet verified-complete**, citing code with file:line. **Source-of-truth order: executable code > tests > these docs. Code wins; doc claims may be stale** — verify the load-bearing ones against current code before relying on them. Read `AGENTS.md` first for repo rules (§1 source order, §6 live invariants, §10 status language); `docs/architecture/runtime_invariants.md` for the live-safety rules.

Known unknown, carried in both docs: the **CH8/CH9 laser color encoding** (what DMX value ranges produce which colors, effects, gradients, water-flow, and speed/direction). The entire non-scripted laser color mapper is blocked on it.

## Workflow — three phases, two operator gates

This is **interactive**; Brandon is in the loop. **Stop and end your turn at each gate** — do not proceed past a gate without his input. (Pausing here is correct: this is input only he can provide.)

**Phase 1 — REVIEW (→ gate 1).** Adversarially review both docs for correctness, completeness, internal consistency, and live safety. Verify the load-bearing claims against current code (read-only). Deliver: severity-ordered findings (location, issue, why it matters, evidence, required fix); a list of gaps and contradictions; and a **consolidated question list for Brandon**. Give a verdict per doc: `PASS` / `PASS WITH REQUIRED FIXES` / `FAIL`. **Make the CH8/CH9 questions explicit and concrete** — tell Brandon exactly what capture/decode input you need to unblock the laser color mapper and how he can produce it. Then stop.

**Phase 2 — EXPAND (→ gate 2).** After Brandon answers, expand the designs: close the gaps, resolve the open items his answers unlock, and produce the completed, implementation-ready design. Edit the two docs in place (keep their frontmatter and §10 status language), keeping the Stream Deck and laser docs consistent with each other. Then stop for his approval of the expanded design.

**Phase 3 — SPEC + ORCHESTRATE (after approval).** Once Brandon approves everything, write the Codex-executable implementation spec(s) following `.claude/skills/codex-spec/SKILL.md` (Part A–E + pre-handoff checklist), then hand off to Codex and orchestrate the implementation through the existing Codex session: attach with `tmux a -t codex`, and `/clear` that session before starting the new task. **You (Fable) do not write bridge code yourself** — Codex implements; you author the spec, drive Codex, and review its output.

## Boundaries

- **Phases 1–2:** reasoning, review, planning, and doc edits only. You MAY read code and spawn read-only verifier subagents to check claims. You may NOT implement bridge code, mutate runtime, restart the bridge, or touch hardware.
- **Phase 3:** you author the spec and orchestrate Codex; Codex implements. No direct bridge-code authorship by you, no hardware action, no bridge restart — restarting the bridge is the operator's call.
- Respect every live-safety invariant (`AGENTS.md` §6). The **laser blackout logic is live-critical** — hold it to the highest scrutiny; the design must never let injected color defeat a blackout, and must never let one blackout owner's release clear another's hold.
- **Do not re-litigate decisions already locked in the docs** (SoundSwitch fully out of the live path, bridge owns the laser DMX frame, the two-tap queue/override gesture, `white_sand` manual-only, blackout as an absolute override, etc.). Close gaps; don't redesign settled architecture.

## Claim discipline

Label every load-bearing claim **confirmed / assumed / unknown / rejected**, tied to evidence (file:line or command output). Don't present a doc's claim as verified without checking it. Report findings faithfully — if a claim fails verification, say so with the evidence.

## Success criteria

- **Phase 1 complete** = both docs reviewed; findings, gaps, and the Brandon question list delivered (CH8/CH9 questions explicit and actionable); per-doc verdicts given; turn ended awaiting his answers.
- **Phase 2 complete** = gaps closed given his answers; expanded design consistent across both docs and within the repo's status/live-safety rules; turn ended awaiting approval.
- **Phase 3 complete** = Codex spec written to the codex-spec format and pre-handoff checklist; handed into the `codex` tmux session; implementation orchestrated and its output reviewed.

Report evidence-tied findings, claim labels, and verdicts only — not your private reasoning.
