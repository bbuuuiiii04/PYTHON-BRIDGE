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
- **Roles.** Claude = evidence / analysis / planning; **Codex implements bridge code.**
  Per-workstream exceptions are operator-granted and none are standing (the LED color-engine M2.5 exception closed 2026-06-18).
- **Verify before asserting.** Run tests / compile / inspect before presenting any plan or claim.
  Label every claim **confirmed / assumed / unknown**; surface unknowns, never guess. Memories and
  old plans may be stale — verify against current code.
- **Present findings, ask before changing.** No unsolicited changes beyond the stated scope.
- **Live safety first.** Reason through the live-mixing scenario before proposing any change. After
  any bridge restart, verify exactly one bridge process — must be `1`
  (SoundSwitch won't autorotate without the bridge running):

  ```bash
  pgrep -f "^[^[:space:]]*(python3|Python)[^[:space:]]*([[:space:]]+-u)?[[:space:]]+-m[[:space:]]+rb_ss_bridge_v2$" | wc -l
  ```

  Use exactly this anchored pattern (the same one `scripts/ss_bridge_watcher.sh:104` uses). A bare
  `pgrep -f rb_ss_bridge_v2` **over-counts badly** — it also matches the menubar, `led_pad`,
  `laser_pad`, `led_sim_web`, lane watchers, and any shell whose command line contains the repo
  name. Measured 2026-07-24: the bare form returned `8` while the bridge was **not running at all**.
- **Cost discipline.** Offload large read-only sweeps (logs / capture corpora / multi-file research)
  to a read-only subagent and verify its load-bearing claims before relying on them; keep
  safety-critical (live-mixing / runtime-invariant / laser-LED) reasoning on a high tier.
- **Graphify.** Use `graphify query`, `graphify explain`, or `graphify path` only for broad
  orientation before reading many files. Skip it for exact symbol/line/known-file lookup where `rg`
  is narrower. This is manual query access only, not a hook; code/tests still win. Never present
  Graphify output as confirmed architecture, ownership, call flow, blast radius, or live behavior.
  `INFERRED` / `AMBIGUOUS` edges and shortest paths require source/test confirmation.

## Prompt / spec authoring
One repo skill per target agent — read the matching skill before writing:
- Codex (or implementer) spec → `.claude/skills/codex-spec/SKILL.md`: the operator's Part A–E
  format and 9-point pre-handoff checklist (verified claims, knowns/unknowns, pending-state +
  mode-transition guards, third-party API completeness, pure-function test seam, live-safety
  invariants, adversarial self-review).
- Fable 5 prompt → `.claude/skills/fable-prompt-writer/SKILL.md` (hardest/ambiguous/long-horizon/
  safety-sensitive one-shots; safeguard hygiene lives there).
- Opus 4.8 prompt → `.claude/skills/opus-prompt-writer/SKILL.md` (default coding/agentic/knowledge/
  frontend/review work).
Fable/Opus prompts are for reasoning, planning, auditing, or review; Codex remains the
implementation path unless a current repo instruction explicitly says otherwise.
