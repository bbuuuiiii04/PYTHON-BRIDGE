---
doc_status: current
truth_level: workflow-grounded
last_verified_commit: 87f3e5e
last_verified_date: 2026-06-23
validation_scope: workflow-only; software-validated only; hardware-unvalidated in repo evidence
---

# AI-only maintainer operator workflow

This file is for the maintainer/operator who uses AI agents and does not want to reason about software engineering internals. It does **not** replace `AGENTS.md`, `docs/agents/change_contracts.yml`, subsystem cards, tests, or validation docs. It is the human-facing prompt pack for getting useful work from agents with fewer prompts, fewer rate-limit hits, and no manual branch juggling.

## Core rule

One bundled request. Main-first. One evidence report.

Bundling related changes is allowed and expected. The agent's job is to sort the bundle into safe work units, implement what belongs together, and flag anything that should become a follow-up instead of silently expanding the change.

The maintainer should not have to remember branches. Default to working from the current default branch and making small, clearly described commits. Branches or PRs are allowed only when the agent/tooling manages the entire lifecycle and the final report clearly says what remains unmerged. Do not leave the maintainer with hidden branch state.

A bundle is acceptable when the items share the same goal, subsystem, or validation path. A bundle should be split when it crosses unrelated subsystems, mixes runtime behavior with unrelated cleanup, requires hardware evidence that is not available, or changes architecture without an explicit reason.

## The useful agent loop

1. **Plan the bundle** — ask the agent to classify the request, name the contracts, find the files, and flag risks before editing.
2. **Implement the approved bundle** — let the agent make the smallest coherent diff that satisfies the accepted items.
3. **Check the diff** — ask the agent or a fresh reviewer to attack assumptions, missing tests, unsafe hardware claims, and unrelated changes.
4. **Repair only findings** — fix blocking review findings without adding new feature scope.
5. **Record evidence** — finish only when the report says what changed, what was tested, what was not tested, what remains unknown, and whether anything is unmerged.

This does not require five separate chats. A single agent may plan, implement, and self-check low-risk bundled work. Risky runtime, config, hardware, or architecture changes still need fresh-context review before being treated as done.

## Standing better-approach clause

Use this in any planning or implementation prompt:

```text
You may suggest a better approach before implementation if it materially reduces risk, complexity, future maintenance, token waste, or hardware-safety risk. Limit this to one concise alternative. Do not implement the alternative unless I approve it. If it is outside the current scope, record it as a follow-up instead of expanding the PR.
```

This keeps the agent from becoming a silent code producer, while still preventing architecture side quests.

## Copy/paste prompt: bundled implementation

Use this when you want fewer prompts and already have a batch of related changes.

```text
You are working in bbuuuiiii04/PYTHON-BRIDGE.

Bundled request:
<PASTE THE FULL LIST OF FIXES / FEATURES / DOC UPDATES HERE>

Workflow preference:
- Do not make me manage branches.
- Prefer main/default-branch commits with clear evidence.
- If a branch or PR is unavoidable, you must say so before using it, explain why, and report exactly what remains unmerged.

Before editing:
1. Read AGENTS.md.
2. Read docs/agents/change_contracts.yml.
3. Sort the bundle into:
   - implement now
   - needs clarification
   - should be separate follow-up
   - should not be done
4. Name the contract key or keys for the implement-now items.
5. List the exact files you expect to inspect/change.
6. List required docs/tests/checks.
7. Apply the better-approach clause: suggest one better approach only if it materially reduces risk, complexity, future maintenance, token waste, or hardware-safety risk.

Then implement only the approved implement-now items.

Rules:
- Keep related bundled changes together when that reduces prompting and review overhead.
- Do not touch unrelated code.
- Do not reformat or reorganize unrelated files.
- Do not commit secrets, local IPs, device IDs, live configs, or backup files.
- Preserve SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED unless validation docs prove otherwise.
- If hardware proof is required, create a hardware-validation handoff; do not claim success.
- If the bundle becomes too broad, stop and recommend a split instead of pushing through.
- Do not leave work stranded on an unnamed branch.

Final report must include:
- bundle items completed
- bundle items not completed and why
- files changed
- behavior changed
- docs updated
- tests/checks run and exact results
- tests/checks not run and why
- follow-ups created
- remaining uncertainty
- current repo state: committed to main/default branch, open PR, unmerged branch, or no changes
```

## Copy/paste prompt: quick fix bundle

Use this for small batches of obvious fixes.

```text
Fix this small bundle with the minimum safe diff:
<PASTE ITEMS>

Follow AGENTS.md. Do not make me manage branches. Prefer main/default-branch commits with a clear final report. Do not touch unrelated code. If any item is not obvious, skip it and report why instead of guessing. Suggest one better approach only if it clearly reduces risk, complexity, future maintenance, token waste, or hardware-safety risk. Report changed files, checks run, skipped items, uncertainty, and whether anything is unmerged.
```

## Copy/paste prompt: adversarial review

Use this before treating a bundled change as done, especially if it touched runtime behavior, config, hardware paths, or architecture.

```text
You are the reviewer, not the implementer.

Review change:
<PASTE PR LINK, COMMIT, OR DIFF SUMMARY>

Read only:
1. AGENTS.md
2. docs/agents/change_contracts.yml
3. relevant task playbooks/subsystem cards
4. changed files and tests

Attack the change:
- Are the bundled items actually related enough to land together?
- Did the diff touch unrelated code or perform opportunistic cleanup?
- Did the implementer miss a simpler or safer approach?
- Did the diff violate StateManager ownership, hot-loop I/O, hardware safety, config secrecy, or docs/status wording?
- Did required docs update according to change_contracts.yml?
- Are tests meaningful, or did they only prove parser/dry-run behavior?
- Is there any hardware claim without hardware evidence?
- Is anything left on a branch or PR that the maintainer might forget?

Return:
- recommendation: done / hold / split / revert
- blocking issues
- non-blocking issues
- bundled items that should be split out
- missing tests/checks
- unsafe or overclaimed validation language
- branch/merge state risk
- required repair prompt
```

## Copy/paste prompt: repair

```text
Repair only these reviewer findings:
<PASTE FINDINGS>

Do not add new feature scope.
Do not clean up unrelated files.
Do not rewrite docs that are not required by the finding or change contract.
Do not strand work on a forgotten branch.
After repair, report exact files changed, gates rerun, and current repo state.
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

- Prefer main/default-branch commits over manual branch management.
- If a branch or PR exists, the final report must say exactly what remains unmerged.
- Bundles are allowed; invisible scope creep is not.
- Use checkboxes instead of memory.
- Demand evidence paragraphs, not vibes. "Should work" means "unknown."
- Let agents suggest one better path, but do not let them implement unapproved side quests.
- Keep a parking lot for useful follow-ups.
- When overwhelmed, ask for a `done / hold / split / revert` recommendation with reasons.

## Hard stop conditions

Stop and get review when any of these appear:

- Change touches unrelated subsystems without saying why they belong in the same bundle.
- Runtime hot loop gains file, network, socket, MIDI, serial, subprocess, or blocking work.
- `StateManager` ownership gets fuzzy.
- Govee/laser/SoundSwitch behavior is described as validated without operator evidence.
- Agent edits tests to hide failures.
- Agent changes live config, secrets, local IPs, device IDs, or backup files.
- Agent reads old prompts/plans and treats them as current truth.
- Agent implements the better-approach alternative without approval.
- Agent leaves unmerged branch/PR state without making it explicit.

## Definition of done

A bundled software change is done when:

- the implemented bundle items are listed;
- the skipped/deferred bundle items are listed with reasons;
- the contract key or keys are named;
- changed code/docs match those contracts;
- required checks/tests are run or explicitly not run with a reason;
- status language stays conservative;
- review/self-check has no blocking findings;
- remaining uncertainty is written down;
- current repo state is explicit: committed to main/default branch, open PR, unmerged branch, or no changes.

A hardware claim is done only when `docs/validation/hardware_validation_log.md` contains repeatable operator evidence. Until then, the correct status is hardware-unvalidated, even if the code looks sick.
