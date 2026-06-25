---
doc_status: active-review-prompt
truth_level: code-grounded
last_verified_commit: ea822b8
last_verified_date: 2026-06-25
validation_scope: strict code-grounded second-opinion review of the RW-7/T7d one-shot capture-agent prompt; READ-ONLY; reviewer must not capture, restart the bridge, open SoundSwitch, enable pack, touch hardware, or edit files
---

# Codex review — RW-7 / T7d capture-agent prompt (strict, code-grounded second opinion)

You are **Codex acting as a strict, independent, adversarial reviewer** working inside
`/Users/bbui/rb_ss_bridge_v2`. You are the **second opinion**. A prior Claude review and a
subagent review already passed this document — **do not defer to them.** Re-derive every
conclusion yourself from the actual code. If a prior verdict was wrong, say so with proof.

## What you are reviewing

The review target is the operator-facing one-shot capture prompt:

> `docs/prompts/active/soundswitch_rw7_capture_agent_prompt.md`

It instructs a future "observer/conductor" agent to drive the operator through the four remaining
T7d/RW-7 SoundSwitch autoloop-phase capture scenarios by driving the tool
`tools/t7d_capture_conductor.py`. Your job is to decide whether that prompt is **safe, internally
consistent, factually correct against the code, and strict enough to one-shot the capture session
without stalling, contaminating evidence, or falsely marking incomplete evidence as accepted.**

A contaminated or falsely-accepted capture is worse than no capture: it wastes a live operator
session and creates misleading evidence for reverse-engineering SoundSwitch's autoloop phase
behavior. Review accordingly.

## Authoritative sources you MUST read (code wins over the prompt's prose)

1. `tools/t7d_capture_conductor.py` — the tool the prompt drives. This is ground truth for every
   claim the prompt makes about conductor behavior, CLI flags, classification, and copied
   artifacts. **Read the actual code; do not trust the prompt's description of it.**
2. `docs/plans/active/soundswitch_t7d_capture_evidence_plan.md` — the governing plan (§A4 decisions,
   §B3 capture matrix/markers/windows, §B5 derivation+holdout, §B6 unblock criteria, Part C
   invariants).
3. `docs/plans/active/soundswitch_exporter_remaining_work.md` — current T7d/RW-7 status authority.

## HARD REVIEW BOUNDARIES — never cross

This is a **read-only review of a document.** You may read files, grep/search the repo, diff,
inspect git history, and run harmless read-only commands (`rg`, `sed -n`, `git --no-pager diff`,
`python3 tools/t7d_capture_conductor.py --help`). You may **NOT**:

- edit, "fix", or reformat any file (produce patch text in your report instead);
- run a capture, `run-scenario`, `prepare`, or any conductor subcommand that mutates state;
- start `tcpdump`, start/stop/restart the bridge, open or control SoundSwitch;
- enable `soundswitch_pack`, append runtime commands, or touch Enttec/MIDI/serial/DMX/fixtures;
- mutate the SoundSwitch project;
- produce a replacement capture procedure unless the prompt contradicts the plan/tool.

Assume the capture agent will follow the prompt **literally.** Catch ambiguity, missing gates,
unsafe wording, stale assumptions, contradictions, and anything that could stall the session,
contaminate evidence, or rubber-stamp incomplete evidence.

## Scrutinize the newest, least-reviewed change HARDEST

The most recent edit moved the **project hashing and AppLog collection from the operator to the
driving agent** (the "Run mechanics" section: the agent itself runs `shasum`/`cp` into the run
dir, with an absolute `RUN_DIR` literal re-declared per block). This part was changed *after* the
last independent review, so it has had the least scrutiny. Verify specifically:

- **Safety classification of agent-run evidence.** Is the agent running `shasum`/`find`/`cp`
  consistent with the prompt's own "observer only / cannot perform any physical action yourself"
  boundary and the §Part-C invariant that only an ignored capture dir is written? (Hashing/log-copy
  are read-only reads writing into the gitignored capture dir — confirm the prompt frames it that
  way and that nothing instructs the agent to perform a genuinely physical/unsafe action itself.)
- **Run-dir path identity.** The agent pre-creates and hashes into
  `RUN_DIR="/Users/bbui/rb_ss_bridge_v2/tools/ssfmt/captures/t7d/t7d_<scenario>_<run-stamp>"`. The
  conductor computes its run dir from `DEFAULT_CAPTURE_ROOT`/`REPO_ROOT` (script location, NOT cwd)
  and `run_id = f"t7d_{scenario}_{run_stamp}"`. Confirm the agent's absolute literal resolves to the
  **exact same directory** the conductor uses, that pre-creating it is harmless
  (`mkdir(..., exist_ok=True)`), and that there is no off-by-one in the `<scenario>`/`<run-stamp>`
  placeholder coupling across steps 2–5.
- **Shell-state assumptions.** The prompt claims env vars do not persist between command calls and
  re-declares `RUN_DIR` per block. Confirm that assumption is stated correctly and that no step
  silently depends on a variable, cwd, or terminal that won't survive (e.g., `validate-scenario`
  uses the full absolute literal, not a possibly-empty `$RUN_DIR`).
- **Hash bracket timing.** before-hash is taken before `run-scenario`; after-hash immediately after
  the window stops. Confirm this actually brackets the capture so any project mutation during the
  run is caught by `validate-scenario`.

## Code-grounded claims the prompt makes — confirm EACH against `t7d_capture_conductor.py`

For every item below, open the code, confirm or refute, and cite `file:line`. Flag any claim that
is inverted, stale, or unprovable.

1. `cmd_run_scenario` hard-codes `"project_hash_matched": True` (it does **not** hash the project),
   so a `run-scenario` ACCEPTED verdict does not itself prove project immutability.
2. `cmd_validate_scenario` → `_project_hashes_match(run_dir)` returns **False (fail-closed)** when
   `project.before.sha256`/`project.after.sha256` are absent, else compares their contents — so the
   prompt's operator/agent hash steps are load-bearing for a trustworthy verdict.
3. The conductor copies **only** `bridge.log` (`_copy(BRIDGE_LOG, ...)`) and **never** copies
   AppLogs — so the prompt's AppLog copy step is required, and AppLogs are time-sensitive/rotating.
   Cross-check the plan (§A4, §B4 step 5, §B5.3) that AppLogs are needed to join identity offline.
4. `classify_gate` rules: **FAIL** = pack enabled / not exactly one core bridge / project bytes
   changed; **INCOMPLETE** = timeout / recorder drops / missing markers / too few Universe-0 frames
   / insufficient playing-phase rows or beat-span; **ACCEPTED** = all green. Confirm the prompt's
   "Fail-closed discipline" section matches these exactly and does not soften them.
5. argparse (`main()`): `--run-stamp` is `required=True`; `--start-timeout-s` default 180;
   `--window-timeout-s` default 420; `summarize-corpus` takes **no positional** and `--capture-root`
   is a **global** flag (must precede the subcommand); `validate-scenario` takes a positional
   `run_dir`; the classifier function is named `classify_gate`. Confirm the prompt's invocations are
   all runnable verbatim and would not error.
6. `core_bridge_process_count` / `is_core_bridge_line` exclude the menubar, the `| tee` wrapper, the
   laser pad, and the conductor itself (`_CORE_EXCLUDE_TOKENS`, `_CORE_SHELL_HINTS`) — i.e. a bare
   `pgrep -f rb_ss_bridge_v2 | wc -l` over-counts in this repo. Confirm the prompt defers the
   bridge-count gate to `prepare`/`core_bridge_process_count` and demotes the bare `pgrep` to a hint
   **everywhere it appears** (including the per-scenario preflight checklist).
7. `cmd_run_scenario`'s second active-wait requires playing-phase beat-span ≥ `min_window_beats`
   **and** new window markers; a bridge with no schema-2 `autoloop_phase` rows times out to
   INCOMPLETE only after the operator has already performed the action. Confirm the prompt's "B1
   schema-2 wiring" pre-check is accurate and that the conductor implements **no** smoke test of its
   own (so the prompt's manual pre-check is the only guard).
8. Per-scenario required markers and windows in `SCENARIOS` match the plan §B3 (e.g. `correction`
   requires `arm-grace-late`, `arm-correction-pending`, `arm-correction-clear`; `buildup` requires
   `[LX] fired role=buildup` and `buildup_to_drop_window`). Confirm the prompt spells the
   `correction` markers correctly and does not introduce dropped scenarios (`phrase-anchor` must
   stay out — confirm it is gated off in code and absent from the prompt).
9. `HARDWARE_STATUS = "SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED"` — confirm the prompt
   uses this exact string everywhere and never claims the capture authorizes T7d implementation or
   hardware output.
10. `summarize-corpus` enforces `needed = 2` accepted reps; the conductor manifest/summary store
    only scenario/markers/verdict (no identity/BPM). Confirm the prompt requires two ACCEPTED reps
    per scenario AND assigns the agent to track identity/BPM/holdout out-of-band, since the
    conductor cannot.

## Internal-consistency sweep (a prior pass already found one contradiction here)

Read the whole prompt end-to-end and hunt for contradictions between sections — who performs each
action (operator vs agent vs conductor), which artifacts are produced, which check is authoritative.
A real contradiction (e.g., one section calling a step an "operator step" while another says the
agent does it) is at least MAJOR. Confirm the Authority section, the preflight checklist, the
Run-mechanics steps, and the Report-back section all agree.

## Evidence-sufficiency for the later autoloop reverse-engineering

Assess whether a corpus produced by following this prompt would later let the §B5 derivation answer:
ticks-per-beat/scale, origin/reset behavior, integer quantization rule, drop-hold advance/freeze/
restart, master-switch ownership/phase, buildup origin, correction origin. If the prompt would
produce captures that are integrity-ACCEPTED but RE-insufficient (e.g., missing AppLog identity
join, no passive Universe-0 oracle, OS2L treated as proof, identity inferred from frame similarity
or display name), say exactly what is missing.

## Required output format

**Verdict** — exactly one:
- ACCEPT — safe and correct to send as-is
- ACCEPT WITH REQUIRED PATCHES — safe only after the listed prompt edits
- REJECT — not safe/correct/complete enough to send

**Summary** — 2–5 sentences, no fluff.

**Findings** — for every issue:
```
ID:
Severity: BLOCKER / MAJOR / MINOR / NIT
Location: <prompt section / line, and the code file:line that proves it>
Problem:
Evidence: <exact code/plan citation>
Why it matters:
Required fix: <and suggested replacement text if applicable>
```

**Coverage checklist** — PASS / FAIL / PARTIAL for each, with the proving `file:line`:
- Conductor-fact accuracy (all 10 claims above)
- Agent-run hashing/AppLog: safe + path-correct + shell-state-correct
- Internal consistency (no contradictions)
- Safety boundaries (observer-only, pack-disabled, no restart, no hardware)
- Fail-closed FAIL/INCOMPLETE/ACCEPTED matches `classify_gate`
- Active-wait operator flow (one physical action at a time, no "how to proceed")
- Remaining-scenario coverage + 2 accepted reps + identity/BPM/holdout tracking
- No phrase-anchor scope creep
- No implementation/hardware authorization claim
- Evidence sufficiency for §B5 RE
- Every CLI invocation runs verbatim against the real argparse

**Final answer** — the exact minimum set of edits to make before sending, or "no edits required"
explicitly. Do not implement them; produce patch text only.

If any claimed fix in the prompt is itself factually wrong against the code (e.g., the conductor
actually DOES hash the project, or `summarize-corpus` DOES take a positional), that is a BLOCKER —
state it plainly with the `file:line` proof.
