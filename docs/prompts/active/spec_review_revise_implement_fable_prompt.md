---
doc_status: current
truth_level: design-intent
last_verified_commit: 3861c10
last_verified_date: 2026-07-04
validation_scope: Claude Fable 5 prompt text only; execution happens in the Fable session Brandon launches
---

# Fable 5 Prompt — Review, Revise, Approve, Then Orchestrate: Gesture v2 + USB Launcher

**Target model:** Claude Fable 5. **Effort:** high; use xhigh on the gesture
input state machine (live control surface) and on anything touching bridge
process lifecycle (the single-bridge-process invariant).

> This is benign local software work for Brandon's DJ lighting bridge
> (`rb_ss_bridge_v2`). It is not a cybersecurity, exploit, malware,
> vulnerability-discovery, biology, chemistry, or hidden-reasoning task.
> "Laser," "blackout," "kill/mute," "solo," and "mask" are ordinary
> stage-lighting and mixer terms. "Adversarial" and "stress test" mean strict
> about evidence — normal software correctness, edge cases, live-show safety,
> and spec executability inside the named scope.

## Mission

Two new specs are approved-in-intent but unreviewed. Adversarially review and
stress-test both, revise them in place, then — on your own judgment — approve
each and orchestrate its implementation through Codex. Brandon has delegated
the approve/proceed decision to you; he reads your final report, not interim
check-ins. Do not re-litigate his locked decisions: gesture v2 semantics
(tap = queue/unqueue toggle; long-press ≈ 0.5 s = take-and-hold = override-fade
+ lock; tap the locked active pad = unlock; lock pad retired) and the launcher
design's approved shape (macOS-only, PyInstaller bundle + menubar,
temporary/permanent install) are operator law.

## The two specs (review targets, in this order)

1. `docs/plans/active/palette_gesture_v2_spec.md` (AWR-121) — full Part A-E
   implementation spec, self-reviewed by its author only. Its behavior
   contract is `docs/architecture/palette_control_authority.md` (v2 banner,
   rules 1-4/7-10, rule 22 v2 additions). Stress the gesture state machine:
   press/release pairs straddling Rainbow toggles, track boundaries, and
   feedback staleness; duration measurement on the state-manager thread;
   stale `_pad_down` entries; threshold disagreement between deck display cue
   and bridge measurement; the v1→v2 test flip list's completeness. Note the
   authority currently reads v1-live/v2-pending — implementation flips that.
2. `docs/plans/active/usb_bridge_launcher_design.md` (AWR-122) — a DESIGN
   spec authored by a parallel session; its own header says the next step is
   a Codex implementation plan, which does not exist yet. After review +
   revision, YOU author that implementation spec (read
   `.claude/skills/codex-spec/SKILL.md` first; Part A-E format, every claim
   verified at current HEAD). Stress: the single-bridge-process invariant
   (`pgrep -f rb_ss_bridge_v2 | wc -l` must be 1 — a launcher is exactly the
   thing that can violate it), interaction with the existing watcher
   (`scripts/ss_bridge_watcher.sh`) and menubar (`scripts/bridge_menubar.py`),
   the out-of-scope memory-read authorization mechanism (verify the spec only
   INVOKES it and nothing drags it in scope), and install/uninstall
   idempotency. Its sibling `docs/plans/active/cross_platform_portability_plan.md`
   is context only — not a review target, not implementable here.

Truth order: executable code > tests > impl specs > authority/design docs >
memories. Every file:line cite in both specs must be re-verified at current
HEAD or corrected. Label load-bearing claims confirmed / assumed / unknown /
rejected.

## Phases

1. **Review + revise.** Findings severity-first (location, issue, concrete
   failure scenario, fix). Apply the required fixes to the spec docs
   directly; bump their `last_verified_commit`; run the three AGENTS.md §8
   hard checks; commit. Verdict per spec: PASS / PASS WITH REQUIRED FIXES
   (after your fixes) / FAIL.
2. **Approve.** Per spec: READY / NOT READY. A FAIL or NOT READY track stops
   there and goes in the report — never hand Codex a spec you would not bet
   the live show on. For the launcher, READY also requires the Codex impl
   spec you authored (registered in the AWR, checks green).
3. **Orchestrate Codex** (only READY tracks; gesture v2 first, launcher
   second, strictly sequential — both may touch shared files and the repo has
   parallel sessions). You direct; Codex implements; you strict-review.

## Codex operational playbook (hard-won this week — follow it)

- Session: `tmux` session `codex` (attach context: `tmux a -t codex`). Before
  EVERY new task: send `/clear`, then Enter, then verify the composer is
  empty — the TUI sometimes needs a second Enter, and text can sit
  unsubmitted; always capture-pane to confirm state before and after sending.
  Kickstart = a short message pointing at the spec file path plus: read
  AGENTS.md first, Part B in order committing per task, contract-first per
  Part E, no branches, no bridge restart, no runtime or hardware action, run
  the full suite and the three §8 checks, report per When You Finish.
- Monitor with a background poll of the pane for the working indicator; the
  turn is over when it clears. Then YOU verify: diff scope against the
  spec's allowed files, line-review of the risky paths, run
  `python3 -m unittest discover tests` and the three §8 checks yourself
  (baseline 2901 OK / 5 skipped / 1 expected failure; the count must grow).
  Reported greens are claims, not evidence.
- Git: NEVER any force-push (`--force-with-lease` included) and never rewrite
  pushed history. Parallel sessions auto-commit and push this repo and may
  leave files STAGED: commit by pathspec (`git commit <paths>`, `git add`
  new files first) so their work never rides your commits; if origin
  advances, `git pull --rebase` your own unpushed commits only. If a doc
  check fails on a parallel session's unclassified doc, register it in
  `docs/status/active_work_registry.md` as open/unreviewed rather than
  touching their content.
- Codex limits: a task that STARTS always finishes, even past 0%. If Codex
  is rate-limited before a send, stop and report to Brandon — do not
  substitute another implementer without his word.
- Fixes found in your review of a Codex diff go back to Codex (or ride the
  next package as a rider); you edit specs/docs/tests briefs, not bridge code.

## Boundaries

- Read anywhere in the repo; run read-only shell, tests, and the §8 checks.
  Doc/spec edits and their contract/registry updates are yours. Bridge code
  is Codex's.
- NO bridge restart, no live process interference, no hardware, no MIDI/DMX
  sends, no launching any built bundle, no LaunchAgent installs. The bridge
  may be RUNNING (Brandon uses truth mode at the desk) — nothing you or
  Codex do may touch it; landing gesture v2 changes files only, and Brandon
  restarts when he chooses.
- The launcher implementation may build artifacts and unit-test them, but
  never execute an installed/bundled launcher against the system.

## Deliverable (end of run)

Per spec: findings + verdict + what you revised; per implemented package:
commits, test counts (yours, not Codex's claims), check results, and any
deviations you accepted with reasons; anything NOT done and why; the exact
operator steps that remain (config mirrors, restart, deck-in-hand checks).
Success = every cite re-verified or corrected, every gesture edge and
launcher lifecycle edge either covered by a named test or explicitly listed
as an accepted gap, suite green and grown at every gate, and no git-safety
or runtime-safety rule bent anywhere.
