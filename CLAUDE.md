# CLAUDE.md — rb_ss_bridge_v2

@AGENTS.md

`AGENTS.md` (imported above) is this repo's single agent entrypoint — **obey it**: §1 source-of-truth
order (if a doc conflicts with code, **code wins**), §2 smallest-reading-path, §7 contract-first
anti-drift rule, §8 hard checks, §10 status language. The rules below are the Claude-side workflow
that AGENTS.md does not cover.

Also follow `AGENTS.md` §0 Brandon Communication Mode:
* use natural low-noise updates;
* do not use robotic status blocks unless I explicitly ask;
* explain operational meaning before technical labels;
* keep proof natural and concise;
* pause only for real decisions.

## Claude-side working rules
- **Roles.** Claude = evidence / analysis / planning; **Codex implements bridge code.** Standing
  exception: the **LED color-engine (M2.5) workstream is Claude-implemented** — that exception does
  NOT generalize to other bridge-core work.
- **Verify before asserting.** Run tests / compile / inspect before presenting any plan or claim.
  Label every claim **confirmed / assumed / unknown**; surface unknowns, never guess. Memories and
  old plans may be stale — verify against current code.
- **Present findings, ask before changing.** No unsolicited changes beyond the stated scope.
- **Live safety first.** Reason through the live-mixing scenario before proposing any change. After
  any bridge restart, verify exactly one process: `pgrep -f rb_ss_bridge_v2 | wc -l` must be `1`
  (SoundSwitch won't autorotate without the bridge running).
- **Cost discipline.** Offload large read-only sweeps (logs / capture corpora / multi-file research)
  to a read-only subagent and verify its load-bearing claims before relying on them; keep
  safety-critical (live-mixing / runtime-invariant / laser-LED) reasoning on a high tier.
- **Graphify.** Use `graphify query`, `graphify explain`, or `graphify path` only for broad
  orientation before reading many files. Skip it for exact symbol/line/known-file lookup where `rg`
  is narrower. This is manual query access only, not a hook; code/tests still win. Never present
  Graphify output as confirmed architecture, ownership, call flow, blast radius, or live behavior.
  `INFERRED` / `AMBIGUOUS` edges and shortest paths require source/test confirmation.

## Spec / handoff authoring
When producing a Codex (or implementer) spec, use the operator's Part A–E format and run the
9-point pre-handoff checklist (verified claims, knowns/unknowns, pending-state + mode-transition
guards, third-party API completeness, pure-function test seam, live-safety invariants, adversarial
self-review). The relevant Codex spec skill, currently `rbss-codex-spec`, scaffolds this.
