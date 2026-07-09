---
doc_status: current
truth_level: handoff-report
last_verified_commit: HEAD-2026-07-09-overnight
last_verified_date: 2026-07-09
validation_scope: >
  Executive kickoff brief for the USB workstream Fable manager (tmux claude6, spawned
  2026-07-09 by the superman executive on operator authorization). PAPER PHASE ONLY:
  design re-verification + USB-track-support design + M1 Codex spec. No code, no runtime,
  no implementation — the build gates on the executive. Operator directives quoted verbatim.
---

# USB workstream — Fable manager kickoff (2026-07-09)

You are the **Fable manager for the USB workstream**, reporting ONLY to the superman
executive (its watchers read your session; never message the operator directly). The
operator authorized this lane tonight with an explicit wait-on-gate structure: paper now,
build later behind the executive's gate.

## Operator directives (verbatim, tonight)
1. "Should we spawn a Fable manager to orchestrate packaging bridge into USB along with
   reading track files FROM USB" — authorized on executive judgment; this brief is that.
2. "i don't think we should hard code file paths, we should plan to fix this" — a DESIGN
   REQUIREMENT for D2 below, not a nice-to-have.
3. "If there are conflicts, then we can have FABLE MANAGER wait until it can continue
   based on YOUR gate" — conflicts ⇒ you STOP and flag, never push through.

## Org rules (standing, operator re-pinned tonight)
You are Fable. You may spawn **Opus tmux orchestrators** and **Sonnet subagents** for
read-only grind (claim sweeps, corpus greps) — **never Fable below you**, announce every
spawn. For this paper phase, prefer cheap read-only subagents over new tmux sessions.

## Deliverables (all docs-only)
**D1 — Re-verify the launcher design.** `docs/plans/active/usb_bridge_launcher_design.md`
was claim-verified at `8abccdf` (2026-07-04). Five days of heavy drift since, concentrated
in exactly its subject matter: AWR-151 launchd ProcessType deployed to all 4 plists + pad
plist Python pinning; menubar v2 checkbox + nested-status fix (7d58acf); watcher env flags
(incl. RBSS_POS_CHAIN_SKIP_OBJC=1); config schema growth (v2 engine block; f2/f4 blocks
landing tonight); logging overhaul. Re-verify every code claim + the env/plist/config
inventories at current HEAD; keep the locked design decisions; label every claim
confirmed/assumed/unknown; update the doc + its header.

**D2 — Design: track files FROM USB (new scope, new design section or sibling doc).**
Today the bridge assumes library-local absolute paths end-to-end: the v4 spectral cache
and the LED v2 identity store key on (filepath, beatgrid); `filepath_resolver.py` /
`anlz_reader.py` resolve library-side. A track played from a USB volume gets a different
path ⇒ silent cache/identity miss ⇒ the v2 brain (zones, F2 drop plans) degrades to
neutral. Per operator directive 2, design the fix: a path-independent stable track key or
normalization layer (evaluate content-based vs metadata-based candidates), the migration
path for the existing ~666-entry v4 cache, ANLZ location handling for USB-resident tracks,
and the full affected-module + change-contract list. Design-only, with falsifiable
acceptance criteria and flagged operator taste calls. Coordinate on paper with the F2 spec
(`docs/plans/active/lighting_engine_v2_f2_spec.md`) — its plan records key off the same
identity; do NOT propose edits to it, just name the interaction.

**D3 — M1 Codex implementation spec** at
`docs/plans/active/usb_bridge_launcher_m1_codex_spec.md` (the design doc already points
there). Read `.claude/skills/codex-spec/SKILL.md` FIRST and follow it (Part A–E + the
9-point pre-handoff checklist). M1 scope only; milestones 2-4 stay unspecced.

**D4 — Bookkeeping.** Registry row (re-check the current max AWR id fresh before claiming
the next — AWR-164 is taken and parallel lanes are writing tonight), doc_index rows, the
three hard checks green (`tools/check_docs_metadata.py`, `check_agent_contracts.py`,
`check_docs_drift.py`), work_status headers updated (paper active / build parked-on-gate).

## Hard boundaries
- **DOCS-ONLY.** Zero `*.py` edits, zero config edits, no bridge/pad/runtime contact, no
  builds, no PyInstaller runs, no branches/worktrees, never `git clean`.
- Implementation NEVER starts from this lane. The executive gates the build on: F2/F4
  landed + operator live-tuning, the phantom-load leak-source fix, and the Codex routing
  decision (quota returns Jul 11 18:28). If a deliverable seems to need code or runtime
  evidence: STOP, record the question in the deliverable, continue elsewhere.
- Shared docs (registry, doc_index) are under parallel-lane pressure tonight: fresh-read
  immediately before each edit, explicit-path commits only, HEAD-lock races ⇒ retry never
  rewrite; auto-sync may sweep your work into misattributed commits — check `git log`
  before treating a commit as failed.
- Out of scope entirely: the DIY-recreation workstream; every file the overnight program
  is editing (`state_manager.py`, `drop_presentation.py`, `govee_frame_renderer.py`,
  reader files, laser files — you have no reason to touch any of them).

## Sentinels
When all four deliverables are committed and checks pass, print exactly `USBPLAN-DONE`
on its own line with the three artifact paths listed above it. If blocked, print
`USBPLAN-BLOCKED` plus the reason. The executive's watcher reads your pane — no other
reporting channel.
