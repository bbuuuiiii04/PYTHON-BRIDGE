---
doc_status: current
truth_level: workflow-grounded
last_verified_commit: 87f3e5e
last_verified_date: 2026-06-23
validation_scope: workflow-only; software-validated only; hardware-unvalidated in repo evidence
---

# AI-only maintainer operator workflow

This file is for the maintainer/operator who uses AI agents and does not want to reason about software engineering internals. It does **not** replace `AGENTS.md`, `docs/agents/change_contracts.yml`, subsystem cards, tests, or validation docs. It is the human-facing prompt pack for getting useful work from agents with fewer prompts and fewer rate-limit hits.

## Core rule

One bundled request. One branch. One evidence report.

Bundling related changes is allowed and expected. The agent's job is to sort the bundle into safe work units, implement what belongs together, and flag anything that should become a follow-up instead of silently expanding the PR.

A bundle is acceptable when the items share the same goal, subsystem, or validation path. A bundle should be split when it crosses unrelated subsystems, mixes runtime behavior with unrelated cleanup, requires hardware evidence that is not available, or changes architecture without an explicit reason.

## The useful agent loop

1. **Plan the bundle** — ask the agent to classify the request, name the contracts, find the files, and flag risks before editing.
2. **Implement the approved bundle** — let the agent make the smallest coherent diff that satisfies the accepted items.
3. **Review the PR/diff** — ask a fresh reviewer to attack assumptions, missing tests, unsafe hardware claims, and unrelated changes.
4. **Repair only findings** — fix blocking review findings without adding new feature scope.
5. **Record evidence** — merge only when the PR says what changed, what was tested, what was not tested, and what remains unknown.

This does not require five separate chats. A single agent may plan and implement low-risk bundled work, but risky PRs still need fresh-context review before merge.

## Standing better-approach clause

Use this in any planning or implementation prompt:

```text
You may suggest a better approach before implementation if it materially reduces risk, complexity, future maintenance, token waste, or hardware-safety risk. Limit this to one concise alternative. Do not implement the alternative unless I approve it. If it is outside the current scope, record it as a follow-up instead of expanding the PR.
```

This keeps the agent from becoming a silent code producer, while still preventing architecture side quests.

## Copy/paste prompt: bundled implementation

Use this when you want fewer prompts and already have a batch of related changes.

```text
You are working in bbuuuiiii04/PYTHON-BRIDGE on branch <BRANCH OR NEW BRANCH>.

Bundled request:
<PASTE THE FULL LIST OF FIXES / FEATURES / DOC UPDATES HERE>

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
```

## Copy/paste prompt: quick fix bundle

Use this for small batches of obvious fixes.

```text
Fix this small bundle with the minimum safe diff:
<PASTE ITEMS>

Follow AGENTS.md. Do not touch unrelated code. If any item is not obvious, skip it and report why instead of guessing. Suggest one better approach only if it clearly reduces risk, complexity, future maintenance, token waste, or hardware-safety risk. Report changed files, checks run, skipped items, and uncertainty.
```

## Copy/paste prompt: adversarial review

Use this before merging a PR, especially a bundled one.

```text
You are the reviewer, not the implementer.

Review PR/diff:
<PASTE PR LINK OR DIFF SUMMARY>

Read only:
1. AGENTS.md
2. docs/agents/change_contracts.yml
3. relevant task playbooks/subsystem cards
4. changed files and tests

Attack the change:
- Are the bundled items actually related enough to merge together?
- Did the diff touch unrelated code or perform opportunistic cleanup?
- Did the implementer miss a simpler or safer approach?
- Did the diff violate StateManager ownership, hot-loop I/O, hardware safety, config secrecy, or docs/status wording?
- Did required docs update according to change_contracts.yml?
- Are tests meaningful, or did they only prove parser/dry-run behavior?
- Is there any hardware claim without hardware evidence?

Return:
- merge recommendation: approve / hold / reject
- blocking issues
- non-blocking issues
- bundled items that should be split out
- missing tests/checks
- unsafe or overclaimed validation language
- required repair prompt
```

## Copy/paste prompt: repair

```text
Repair only these reviewer findings:
<PASTE FINDINGS>

Do not add new feature scope.
Do not clean up unrelated files.
Do not rewrite docs that are not required by the finding or change contract.
After repair, report exact files changed and gates rerun.
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

- Prefer one visible branch and PR per bundle.
- Bundles are allowed; invisible scope creep is not.
- Use checkboxes instead of memory.
- Demand evidence paragraphs, not vibes. "Should work" means "unknown."
- Let agents suggest one better path, but do not let them implement unapproved side quests.
- Keep a parking lot for useful follow-ups.
- When overwhelmed, ask for a `merge / hold / split / abandon` recommendation with reasons.

## Hard stop conditions

Stop and get review when any of these appear:

- PR changes unrelated subsystems without saying why they belong in the same bundle.
- Runtime hot loop gains file, network, socket, MIDI, serial, subprocess, or blocking work.
- `StateManager` ownership gets fuzzy.
- Govee/laser/SoundSwitch behavior is described as validated without operator evidence.
- Agent edits tests to hide failures.
- Agent changes live config, secrets, local IPs, device IDs, or backup files.
- Agent reads old prompts/plans and treats them as current truth.
- Agent implements the better-approach alternative without approval.

## Definition of done

A bundled software PR is done when:

- the implemented bundle items are listed;
- the skipped/deferred bundle items are listed with reasons;
- the contract key or keys are named;
- changed code/docs match those contracts;
- required checks/tests are run or explicitly not run with a reason;
- status language stays conservative;
- review has no blocking findings;
- remaining uncertainty is written down.

A hardware claim is done only when `docs/validation/hardware_validation_log.md` contains repeatable operator evidence. Until then, the correct status is hardware-unvalidated, even if the code looks sick.
