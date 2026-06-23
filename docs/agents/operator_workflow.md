---
doc_status: current
truth_level: workflow-grounded
last_verified_commit: 87f3e5e
last_verified_date: 2026-06-23
validation_scope: workflow-only; software-validated only; hardware-unvalidated in repo evidence
---

# AI-only maintainer operator workflow

This file is for the maintainer/operator who uses AI agents and does not want to reason about software engineering internals. It does **not** replace `AGENTS.md`, `docs/agents/change_contracts.yml`, subsystem cards, tests, or validation docs. It is the human-facing operating loop that keeps agents from wandering.

## Core rule

One task. One branch. One contract. One evidence report.

If a request cannot fit that sentence, split it before implementation. Big vague prompts are how agents create impressive garbage.

## Session types

| Session | Goal | Agent role | Must produce |
| --- | --- | --- | --- |
| Intake | Convert a messy idea into a bounded task | planner | scope, contract key, files to inspect, stop conditions |
| Implementation | Make the smallest safe change | implementer | changed files, tests run, docs updated, uncertainty |
| Adversarial review | Try to break the change | reviewer | blocking issues, non-blocking issues, merge recommendation |
| Repair | Fix review findings only | implementer | focused diff, no scope creep |
| Operator validation | Prove local/hardware behavior | operator + reviewer | repeatable log entry, status wording, known limits |

Do not ask one agent to both implement and approve its own risky change. Self-review is useful, but it is not independent review.

## The default loop

1. **Intake first** — ask an agent to classify the task and name the contract before editing.
2. **Implement narrow** — ask for the smallest diff that satisfies the task.
3. **Run gates** — docs checks always for docs/routing changes; tests named by the contract when practical.
4. **Fresh-context review** — give a different agent the PR/diff plus the relevant contract and ask it to attack assumptions.
5. **Merge only after evidence** — merge when the PR says what changed, what was tested, what was not tested, and what remains unvalidated.

## Copy/paste prompt: intake

```text
You are working in bbuuuiiii04/PYTHON-BRIDGE.

Task idea:
<PASTE THE FEATURE / BUG / DOC REQUEST HERE>

Before editing anything:
1. Read AGENTS.md.
2. Pick the smallest matching task route and change_contracts.yml contract.
3. Report:
   - task classification: small / medium / large
   - contract key
   - exact files you need to inspect
   - exact docs/tests that must update
   - assumptions you refuse to make
   - stop conditions
4. Do not edit code yet.
5. Do not read archive/history/prompts unless you can explain why current code/docs are insufficient.
```

Use this when the idea is messy, emotional, or exciting. Especially then. Excitement is not a spec.

## Copy/paste prompt: implementation

```text
You are working in bbuuuiiii04/PYTHON-BRIDGE on branch <BRANCH>.

Implement only this approved scope:
<PASTE INTAKE SCOPE HERE>

Rules:
- Follow AGENTS.md and docs/agents/change_contracts.yml.
- Make the smallest safe diff.
- Do not change unrelated runtime behavior.
- Do not commit secrets, local IPs, device IDs, live configs, or backup files.
- Preserve SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED unless validation docs prove otherwise.
- If the task requires hardware proof, stop at a hardware-validation handoff; do not claim success.

Final report must include:
- files changed
- behavior changed
- docs updated
- tests/checks run and exact results
- tests/checks not run and why
- remaining uncertainty
```

## Copy/paste prompt: adversarial review

```text
You are the reviewer, not the implementer.

Review PR/diff:
<PASTE PR LINK OR DIFF SUMMARY>

Read only:
1. AGENTS.md
2. docs/agents/change_contracts.yml
3. the relevant task playbook
4. the relevant subsystem card
5. changed files and tests

Attack the change:
- What assumption did the implementer make that may be false?
- Did the diff violate StateManager ownership, hot-loop I/O, hardware safety, config secrecy, or docs/status wording?
- Did the required docs update according to change_contracts.yml?
- Are tests meaningful, or did they only prove parser/dry-run behavior?
- Is there any hardware claim without hardware evidence?

Return:
- BLOCKING issues
- NON-BLOCKING issues
- required repair prompt
- merge recommendation: approve / hold / reject
```

## Copy/paste prompt: repair

```text
Repair only these reviewer findings:
<PASTE FINDINGS>

Do not add new feature scope.
Do not clean up unrelated files.
Do not rewrite docs that are not required by the finding or change contract.
After repair, report the exact files changed and gates rerun.
```

## Copy/paste prompt: hardware/operator validation

```text
Create a hardware-validation handoff for this feature/path:
<FEATURE OR DEVICE PATH>

Do not claim hardware validation. Create a repeatable operator checklist that records:
- date
- OS version
- Rekordbox version
- SoundSwitch version if relevant
- Govee model/firmware/app assumptions if relevant
- laser fixture/interface/mapping if relevant
- config file used, sanitized of secrets/local IPs/device IDs
- exact command/run steps
- expected visible behavior
- observed visible behavior
- pass/fail/unknown
- safety notes and manual override/blackout behavior
- log/status files captured

Update validation/status docs only if actual evidence is supplied.
```

## ADHD/autism-friendly operating constraints

These are not medical advice. They are repo-control mechanics.

- Keep a single visible active task: one branch, one PR, one active prompt.
- Use checkboxes instead of memory.
- Time-box reading: if an agent asks to read the whole repo, redirect it to AGENTS → contract → playbook → subsystem card.
- Demand evidence paragraphs, not vibes. “Should work” means “unknown.”
- Prefer small merges over giant heroic PRs. Big PRs hide bugs and fry attention.
- Keep a parking lot for cool ideas. Do not let agents implement side quests inside the current PR.
- When overwhelmed, ask for a `merge / hold / abandon` recommendation with reasons.

## Hard stop conditions

Stop and get review when any of these appear:

- PR changes more than one subsystem without saying why.
- Runtime hot loop gains file, network, socket, MIDI, serial, subprocess, or blocking work.
- `StateManager` ownership gets fuzzy.
- Govee/laser/SoundSwitch behavior is described as validated without operator evidence.
- Agent edits tests to hide failures.
- Agent changes live config, secrets, local IPs, device IDs, or backup files.
- Agent reads old prompts/plans and treats them as current truth.
- PR grows beyond the original intake scope.

## Definition of done

A software PR is done when:

- the contract key is named;
- changed code/docs match that contract;
- required checks/tests are run or explicitly not run with a reason;
- status language stays conservative;
- independent review has no blocking findings;
- remaining uncertainty is written down.

A hardware claim is done only when `docs/validation/hardware_validation_log.md` contains repeatable operator evidence. Until then, the correct status is hardware-unvalidated, even if the code looks sick.
