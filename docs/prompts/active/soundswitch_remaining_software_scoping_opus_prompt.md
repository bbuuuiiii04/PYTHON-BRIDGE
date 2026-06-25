---
doc_status: active-prompt
truth_level: scoping-instructions
last_verified_commit: 3b7469a
last_verified_date: 2026-06-24
validation_scope: read-only Opus scoping pass over remaining SOFTWARE SoundSwitch exporter / bridge-native DMX work; scoping only; SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Opus scoping pass — remaining SOFTWARE SoundSwitch exporter work

You are a senior planning analyst for `rb_ss_bridge_v2`. Your job is to **scope**,
not implement: produce a code-verified, dependency-aware, prioritized breakdown of
the remaining **software** work for the SoundSwitch exporter and bridge-native
CH1–CH19 DMX project. You write a scope document; you change no behavior.

## Hard boundary

Read-only analysis. Do **not**:

- edit, implement, refactor, or commit code or tests;
- read or edit ignored live configuration;
- start, stop, restart, signal, or count live bridge processes;
- append runtime commands or invoke menubar actions;
- open MIDI, serial, Enttec, or DMX interfaces, or connect fixtures;
- execute any `OPERATOR ACTION` from the hardware procedure;
- propose or design native Autoloop DMX behavior, T7d phase mappings, or
  roadmap/registry reconciliation (these are scoped only as blocked items).

You **may** run the read-only software gates (tests, docs checks, `git diff --check`,
the pack-generation proof against its default canonical project) to verify claims.
Running tests is allowed; implementing is not.

## Source-of-truth order (AGENTS.md §1)

Code → tests → config examples → `runtime_status.py` → file tree → docs → history.
**If a doc conflicts with code, code wins.** Treat the roadmap below as a claim set
to verify, not as truth. Label every finding **confirmed / assumed / unknown** and
never guess.

## What "remaining SOFTWARE work" means here

In scope: anything that is software and can move without a fixture, e.g. the
independent-review follow-through, software pieces of T7d (the oracle/reconciliation
logic, not the operator capture collection), the *spec authoring* for native Autoloop
DMX, final software closeout (proof rerun + gates + adversarial review), and any
code/doc drift or cleanup you can prove.

Explicitly **out of "doable-now"** but still listed as blocked items with their exact
gate named:

- the operator hardware run (`docs/validation/soundswitch_hardware_validation_procedure.md`);
- operator-conducted T7d **capture collection** (needs the rig + operator);
- native Autoloop DMX **implementation** (blocked until `PASS_T7D_PHASE_CONTRACT`).

Your value is separating *software, doable now* from *software, blocked on X*, and
killing any phantom work the roadmap implies that the code shows is already done.

## Read these (smallest path first)

1. `docs/plans/active/soundswitch_exporter_remaining_work.md` — the roadmap/claim set.
2. `docs/plans/active/soundswitch_README.md` — project index.
3. `docs/status/active_work_registry.md` (AWR-107) — active authority.
4. `docs/research/soundswitch/soundswitch_importer_exporter_player_codex_spec.md` — product/format contract.
5. `docs/plans/active/soundswitch_t7d_capture_evidence_plan.md` and `soundswitch_t7d_capture_gate_handoff.md` — the T7d gate.
6. Completed specs under `docs/plans/completed/soundswitch/` — **history only**.

Verify against code + tests at HEAD:

- exporter tool(s) under `tools/` (e.g. `export_soundswitch_pack`, `prove_soundswitch_pack_generation.py`, `inventory_project_artifacts`);
- `soundswitch_pack_runtime.py`, `state_manager.py` (pack driver + `_publish_pack_status`), `runtime_status.py`, `scripts/bridge_menubar.py`;
- the SoundSwitch laser player / frame sender / enttec modules;
- the matching tests: `tests/test_state_manager_pack_driver.py`, `test_soundswitch_pack_commands.py`, `test_runtime_status.py`, `test_bridge_menubar.py`, `test_soundswitch_frame_sender.py`, `test_enttec_dmx_pro.py`, `test_soundswitch_pack_startup.py`.

## Produce, per remaining software item

For each item, a short block with:

1. **Name + plain-language meaning** (what it gives the operator).
2. **Current state**, code-verified, labeled `confirmed` / `assumed` / `unknown`
   with `file:line` evidence. Call out anything the roadmap lists as remaining that
   is actually already done, or actually not software.
3. **Doable now or blocked** — if blocked, the exact gate (which operator capture,
   hardware run, or prior item) and what unblocks it.
4. **Dependencies / ordering** against the other items.
5. **Smallest bounded next deliverable** — one tiny, clear first step.
6. **Effort (S/M/L)** and **risk**, flagging any live-safety exposure.
7. **Invariants it must not break** (cite the numbered invariants in the roadmap).
8. **Owner type** — Codex implementation spec, Claude analysis, or operator action.

Then:

- a **prioritized sequence**: do-first software, then blocked-software with gates,
  then optional/cleanup;
- a **phantom-work list**: roadmap items that code shows are already satisfied;
- a one-paragraph **recommended first move**.

## Constraints

- Status language (AGENTS.md §10): never `stable`, `production-ready`, `show-ready`,
  `plug-and-play`, `broadly compatible`, `generally supported`, or `hardware-validated`.
- Never imply hardware validation; software/wire evidence only. `software_zero_frame`
  and `frame_count` prove no serial send, Enttec acceptance, or physical darkness.
- No scope creep beyond this named project.
- Private-data hygiene: no local paths, ports, aliases, device names, fixture serials,
  project UUIDs, raw frames/hashes/errors, config contents, or raw status files in output.
- Communication mode (AGENTS.md §0): plain-language meaning before technical labels;
  no robotic status blocks; surface real decisions only.

## Output

1. Write the scope to `docs/plans/active/soundswitch_remaining_software_scope.md`
   with a proper status header (`doc_status`, `truth_level`, `last_verified_commit`,
   `last_verified_date`, `validation_scope`). Do not modify any other file except,
   if needed, one classification line in `docs/architecture/doc_index.md` for the new
   doc, then run the hard checks.
2. Print a short chat summary: the top 3 doable-now software items, the blockers with
   their gates, and the recommended first move.
3. Run and report the read-only gates you used to verify claims:

```bash
python3 -m unittest discover tests
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
python3 tools/check_docs_staleness.py --report
git diff --check
```

These do not authorize any live, process, runtime-command, config, or hardware action.
Absence of work is not proof of completion — only code and passing tests are.
